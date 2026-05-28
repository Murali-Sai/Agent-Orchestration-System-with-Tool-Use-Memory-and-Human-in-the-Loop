"""FastAPI backend — task submission, status polling, HITL resolution."""
from __future__ import annotations
import threading
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from graph.workflow import build_graph, create_initial_state
from graph.state import AgentState
from hitl.queue import get_queue
from db import crud as db
from db.client import is_enabled as supabase_enabled
from config.settings import get_settings
from config.logging_config import configure_logging

settings = get_settings()
configure_logging(settings.log_level)

app = FastAPI(title="Multi-Agent Orchestration System", version="1.0.0")

app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)

# In-memory cache — source of truth when Supabase is absent,
# write-through cache when Supabase is present.
_tasks: dict[str, AgentState] = {}
_graph = None


def get_graph():
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph


# ── Request / Response models ── #

class TaskRequest(BaseModel):
    request: str
    user_id: str = "default"


class ResolveRequest(BaseModel):
    item_id: str
    approved: bool
    response: str = ""
    modified_output: str = ""


# ── Task runner ── #

def _run_task(task_id: str, state: AgentState) -> None:
    try:
        graph = get_graph()
        result = graph.invoke(state)
        _tasks[task_id] = result
        db.upsert_task(result)
    except Exception as e:
        state["status"] = "failed"
        state["errors"].append(str(e))
        _tasks[task_id] = state
        db.upsert_task(state)


def _get_task(task_id: str) -> Optional[AgentState]:
    """Return task from memory cache, falling back to Supabase."""
    if task_id in _tasks:
        return _tasks[task_id]
    loaded = db.get_task(task_id)
    if loaded:
        _tasks[task_id] = loaded
    return loaded


# ── Routes ── #

@app.get("/health")
def health():
    return {
        "status": "ok",
        "tasks_active": len(_tasks),
        "supabase": supabase_enabled(),
    }


@app.post("/tasks")
def submit_task(req: TaskRequest, background_tasks: BackgroundTasks):
    state = create_initial_state(req.request, req.user_id)
    task_id = state["task_id"]
    _tasks[task_id] = state
    db.upsert_task(state)
    background_tasks.add_task(_run_task, task_id, state)
    return {"task_id": task_id, "status": "started"}


@app.get("/tasks/{task_id}")
def get_task_route(task_id: str):
    state = _get_task(task_id)
    if not state:
        raise HTTPException(404, "Task not found")
    return {
        "task_id":        task_id,
        "status":         state["status"],
        "plan":           state["execution_plan"],
        "plan_confidence": state["plan_confidence"],
        "completed":      len(state["completed_subtasks"]),
        "total":          len(state["execution_plan"]),
        "reviewer_score": state["reviewer_score"],
        "reviewer_feedback": state.get("reviewer_feedback"),
        "final_output":   state["final_output"],
        "awaiting_human": state["awaiting_human"],
        "escalations":    state["escalations"],
        "memories_used":  state.get("memories_used", []),
        "total_tokens":   state["total_tokens"],
        "total_tool_calls": state["total_tool_calls"],
        "errors":         state["errors"],
    }


@app.get("/tasks/{task_id}/trace")
def get_trace(task_id: str):
    state = _get_task(task_id)
    if not state:
        raise HTTPException(404, "Task not found")
    return {"trace": state["trace"]}


@app.get("/tasks")
def list_tasks_route(user_id: Optional[str] = None):
    # Prefer Supabase list (persistent) over in-memory (session-only)
    if supabase_enabled():
        rows = db.list_tasks(user_id=user_id)
        return [
            {
                "task_id": r["id"],
                "status": r["status"],
                "request": r["original_request"][:100],
                "created_at": r.get("created_at"),
            }
            for r in rows
        ]
    return [
        {"task_id": tid, "status": s["status"], "request": s["original_request"][:100]}
        for tid, s in _tasks.items()
        if not user_id or s["user_id"] == user_id
    ]


# ── HITL routes ── #

@app.get("/hitl/queue")
def hitl_pending():
    if supabase_enabled():
        return {"items": db.list_hitl_events(status="pending")}
    queue = get_queue(settings.redis_url)
    return {"items": queue.list_pending()}


@app.post("/hitl/resolve")
def hitl_resolve(req: ResolveRequest):
    resolved = False

    # Try Supabase first
    if supabase_enabled():
        resolved = db.resolve_hitl_event(req.item_id, req.approved, req.response, req.modified_output)

    # Fall back to Redis queue
    if not resolved:
        queue = get_queue(settings.redis_url)
        resolved = queue.resolve(req.item_id, req.approved, req.response, req.modified_output)

    if not resolved:
        raise HTTPException(404, "Approval item not found")

    if req.approved:
        _resume_paused_task(req.response, req.modified_output)

    return {"resolved": True}


def _resume_paused_task(human_feedback: str, modified_output: str) -> None:
    """Find the first paused task and resume it — checks memory then Supabase."""
    # 1. Check in-memory cache first (fast path)
    for task_id, state in list(_tasks.items()):
        if state.get("awaiting_human"):
            _apply_resume(task_id, state, human_feedback, modified_output)
            return

    # 2. Fall back to Supabase — handles restart-after-escalation case
    if supabase_enabled():
        rows = db.list_tasks()
        for row in rows:
            if row.get("awaiting_human"):
                state = db.get_task(row["id"])
                if state:
                    _tasks[row["id"]] = state
                    _apply_resume(row["id"], state, human_feedback, modified_output)
                    return


def _apply_resume(task_id: str, state: dict, human_feedback: str, modified_output: str) -> None:
    state["awaiting_human"] = False
    state["human_feedback"] = human_feedback
    if modified_output:
        state["final_output"] = modified_output
    for e in state["escalations"]:
        if not e.get("resolved"):
            e["resolved"] = True
            e["human_response"] = human_feedback
    db.upsert_task(state)
    t = threading.Thread(target=_run_task, args=(task_id, state), daemon=True)
    t.start()


@app.get("/hitl/resolved")
def hitl_resolved():
    if supabase_enabled():
        return {"items": db.list_hitl_events(status="approved") + db.list_hitl_events(status="rejected")}
    queue = get_queue(settings.redis_url)
    return {"items": queue.get_resolved()}


# ── Observability routes ── #

@app.get("/memory/stats")
def memory_stats():
    from memory.longterm import LongTermMemory
    ltm = LongTermMemory(settings.chroma_persist_dir)
    return {
        "long_term_memories": ltm.count(),
        "supabase_enabled": supabase_enabled(),
    }


@app.get("/tools/logs")
def tool_logs(task_id: Optional[str] = None):
    if supabase_enabled():
        return {"logs": db.get_tool_calls(task_id=task_id, limit=50)}
    from tools.registry import get_registry
    return {"logs": get_registry().get_logs(50)}

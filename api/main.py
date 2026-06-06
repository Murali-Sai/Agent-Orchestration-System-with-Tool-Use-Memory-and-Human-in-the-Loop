"""FastAPI backend — task submission, status polling, HITL resolution, analytics."""
from __future__ import annotations
import threading
import time
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

app = FastAPI(
    title="Agent Orchestration System with Tool Use, Memory, and Human-in-the-Loop",
    version="2.0.0",
    description="Production-grade multi-agent platform: supervisor decomposes tasks, specialists execute with real tools, persistent memory improves over time, and humans stay in the loop for critical decisions.",
)

_cors_origins = (
    ["*"] if settings.cors_origins.strip() == "*"
    else [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory cache — source of truth when Supabase absent, write-through when present.
_tasks: dict[str, AgentState] = {}
_graph = None

# Detect whether Celery/Redis is available for async dispatch
_celery_available: bool | None = None


def _is_celery_available() -> bool:
    global _celery_available
    if _celery_available is not None:
        return _celery_available
    # Only treat Celery as available when explicitly enabled — a reachable Redis
    # broker is NOT enough; without a running worker, jobs would never execute.
    if not settings.use_celery:
        _celery_available = False
        return _celery_available
    try:
        from workers.celery_app import celery_app
        celery_app.backend.client  # ping backend
        _celery_available = True
    except Exception:
        _celery_available = False
    return _celery_available


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

def _run_task_thread(task_id: str, state: AgentState) -> None:
    """Fallback: run graph in a daemon thread (used when Celery is unavailable)."""
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


def _dispatch_task(task_id: str, state: AgentState) -> str:
    """Dispatch to Celery if explicitly enabled AND a worker is reachable,
    otherwise run in a daemon thread. The thread fallback is the default so that
    hosts with Redis but no worker (e.g. Render free tier) still execute tasks."""
    if _is_celery_available():
        try:
            from workers.tasks import run_agent_task
            run_agent_task.delay(task_id, dict(state))
            return "celery"
        except Exception:
            pass
    t = threading.Thread(target=_run_task_thread, args=(task_id, state), daemon=True)
    t.start()
    return "thread"


def _get_task(task_id: str) -> Optional[AgentState]:
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
        "celery": _is_celery_available(),
    }


@app.post("/tasks")
def submit_task(req: TaskRequest, background_tasks: BackgroundTasks):
    state = create_initial_state(req.request, req.user_id)
    task_id = state["task_id"]
    _tasks[task_id] = state
    db.upsert_task(state)
    runner = _dispatch_task(task_id, state)
    return {"task_id": task_id, "status": "started", "runner": runner}


@app.get("/tasks/{task_id}")
def get_task_route(task_id: str):
    state = _get_task(task_id)
    if not state:
        raise HTTPException(404, "Task not found")
    return {
        "task_id":           task_id,
        "status":            state["status"],
        "plan":              state["execution_plan"],
        "plan_confidence":   state["plan_confidence"],
        "completed":         len(state["completed_subtasks"]),
        "total":             len(state["execution_plan"]),
        "reviewer_score":    state["reviewer_score"],
        "reviewer_feedback": state.get("reviewer_feedback"),
        "final_output":      state["final_output"],
        "awaiting_human":    state["awaiting_human"],
        "escalations":       state["escalations"],
        "memories_used":     state.get("memories_used", []),
        "total_tokens":      state["total_tokens"],
        "total_tool_calls":  state["total_tool_calls"],
        "model_usage":       state.get("model_usage", {}),
        "cost_usd":          state.get("cost_usd", 0.0),
        "wall_time_s":       state.get("wall_time_s", 0.0),
        "errors":            state["errors"],
    }


@app.get("/tasks/{task_id}/trace")
def get_trace(task_id: str):
    state = _get_task(task_id)
    if not state:
        raise HTTPException(404, "Task not found")
    return {"trace": state["trace"]}


@app.get("/tasks")
def list_tasks_route(user_id: Optional[str] = None):
    if supabase_enabled():
        rows = db.list_tasks(user_id=user_id)
        return [
            {
                "task_id":    r["id"],
                "status":     r["status"],
                "request":    r["original_request"][:100],
                "created_at": r.get("created_at"),
                "cost_usd":   r.get("cost_usd", 0.0),
            }
            for r in rows
        ]
    return [
        {
            "task_id":  tid,
            "status":   s["status"],
            "request":  s["original_request"][:100],
            "cost_usd": s.get("cost_usd", 0.0),
        }
        for tid, s in _tasks.items()
        if not user_id or s["user_id"] == user_id
    ]


# ── Analytics ── #

@app.get("/stats/aggregate")
def aggregate_stats():
    """Cross-task analytics: cost, model usage, escalation rate, tool patterns."""
    all_tasks = list(_tasks.values())

    if not all_tasks:
        return {
            "total_tasks": 0, "completed_tasks": 0, "failed_tasks": 0,
            "escalated_tasks": 0, "escalation_rate": 0.0,
            "total_tokens": 0, "total_cost_usd": 0.0,
            "model_usage": {}, "avg_cost_usd": 0.0,
            "avg_tokens": 0, "avg_reviewer_score": 0.0,
            "avg_wall_time_s": 0.0, "tool_usage": {},
        }

    completed  = [t for t in all_tasks if t["status"] == "done"]
    failed     = [t for t in all_tasks if t["status"] == "failed"]
    escalated  = [t for t in all_tasks if t.get("escalations")]

    total_tokens = sum(t["total_tokens"] for t in all_tasks)
    total_cost   = sum(t.get("cost_usd", 0.0) for t in all_tasks)

    # Aggregate model usage
    model_totals: dict[str, int] = {}
    for t in all_tasks:
        for model, tokens in t.get("model_usage", {}).items():
            model_totals[model] = model_totals.get(model, 0) + tokens

    # Tool usage patterns
    tool_counts: dict[str, int] = {}
    for t in all_tasks:
        for st in t.get("completed_subtasks", []):
            for tc in st.get("tool_calls", []):
                tool = tc.get("tool", "unknown")
                tool_counts[tool] = tool_counts.get(tool, 0) + 1

    avg_score = (
        sum(t["reviewer_score"] for t in completed) / len(completed)
        if completed else 0.0
    )
    avg_wall = (
        sum(t.get("wall_time_s", 0) for t in completed) / len(completed)
        if completed else 0.0
    )

    return {
        "total_tasks":       len(all_tasks),
        "completed_tasks":   len(completed),
        "failed_tasks":      len(failed),
        "escalated_tasks":   len(escalated),
        "escalation_rate":   round(len(escalated) / max(len(all_tasks), 1), 3),
        "total_tokens":      total_tokens,
        "total_cost_usd":    round(total_cost, 4),
        "avg_cost_usd":      round(total_cost / max(len(all_tasks), 1), 4),
        "avg_tokens":        total_tokens // max(len(all_tasks), 1),
        "avg_reviewer_score": round(avg_score, 3),
        "avg_wall_time_s":   round(avg_wall, 2),
        "model_usage":       model_totals,
        "tool_usage":        tool_counts,
    }


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
    if supabase_enabled():
        resolved = db.resolve_hitl_event(req.item_id, req.approved, req.response, req.modified_output)
    if not resolved:
        queue = get_queue(settings.redis_url)
        resolved = queue.resolve(req.item_id, req.approved, req.response, req.modified_output)
    if not resolved:
        raise HTTPException(404, "Approval item not found")
    if req.approved:
        _resume_paused_task(req.response, req.modified_output)
    return {"resolved": True}


def _resume_paused_task(human_feedback: str, modified_output: str) -> None:
    for task_id, state in list(_tasks.items()):
        if state.get("awaiting_human"):
            _apply_resume(task_id, state, human_feedback, modified_output)
            return
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
    _dispatch_task(task_id, state)


class ChatMessage(BaseModel):
    role: str = "human"   # "human" or "agent"
    message: str


@app.post("/hitl/chat/{item_id}")
def hitl_chat(item_id: str, msg: ChatMessage):
    """Add a clarification message to an open HITL item (human ↔ agent chat)."""
    queue = get_queue(settings.redis_url)
    ok = queue.add_message(item_id, msg.role, msg.message)
    if not ok:
        raise HTTPException(404, "HITL item not found")
    return {"ok": True}


@app.get("/hitl/chat/{item_id}")
def hitl_get_chat(item_id: str):
    """Retrieve the message thread for a HITL item."""
    queue = get_queue(settings.redis_url)
    messages = queue.get_messages(item_id)
    return {"messages": messages}


@app.get("/hitl/resolved")
def hitl_resolved():
    if supabase_enabled():
        return {"items": db.list_hitl_events(status="approved") + db.list_hitl_events(status="rejected")}
    queue = get_queue(settings.redis_url)
    return {"items": queue.get_resolved()}


# ── Memory routes ── #

@app.get("/memory/stats")
def memory_stats():
    from memory.longterm import LongTermMemory
    ltm = LongTermMemory(settings.chroma_persist_dir)
    return {
        "long_term_memories": ltm.count(),
        "supabase_enabled": supabase_enabled(),
    }


@app.get("/memory/list")
def memory_list(limit: int = 20):
    """Return recent long-term memories with content and metadata."""
    from memory.longterm import LongTermMemory
    ltm = LongTermMemory(settings.chroma_persist_dir)
    memories = ltm.list_all(limit=limit)
    return {"memories": memories}


@app.delete("/memory/{memory_id}")
def memory_delete(memory_id: str):
    """Delete a specific memory by ID (GDPR / user data request)."""
    from memory.longterm import LongTermMemory
    ltm = LongTermMemory(settings.chroma_persist_dir)
    ltm.delete(memory_id)
    return {"deleted": memory_id}


@app.post("/memory/consolidate")
def memory_consolidate():
    """Merge near-duplicate memories to keep the store clean."""
    from memory.longterm import LongTermMemory
    ltm = LongTermMemory(settings.chroma_persist_dir)
    removed = ltm.consolidate()
    return {"merged_removed": removed, "remaining": ltm.count()}


@app.post("/memory/prune")
def memory_prune(max_age_days: float = 90.0):
    """Delete memories older than max_age_days."""
    from memory.longterm import LongTermMemory
    ltm = LongTermMemory(settings.chroma_persist_dir)
    removed = ltm.prune_old(max_age_days)
    return {"pruned": removed, "remaining": ltm.count()}


# ── Observability routes ── #

@app.get("/tasks/{task_id}/checkpoints")
def get_checkpoints(task_id: str):
    """Return ordered execution checkpoints for replay / step-through debugging."""
    state = _get_task(task_id)
    if not state:
        raise HTTPException(404, "Task not found")

    checkpoints = []

    # Checkpoint 0: initial state (plan)
    plan_event = next((e for e in state["trace"] if e["action"] == "plan_created"), None)
    if plan_event:
        checkpoints.append({
            "step": 0,
            "label": "Plan Created",
            "agent": "supervisor",
            "ts": plan_event["ts"],
            "detail": plan_event.get("detail", {}),
            "snapshot": {
                "execution_plan": state["execution_plan"],
                "plan_confidence": state["plan_confidence"],
                "memories_used": state.get("memories_used", []),
            },
        })

    # One checkpoint per completed subtask
    for i, subtask in enumerate(state.get("completed_subtasks", []), 1):
        done_event = next(
            (e for e in state["trace"]
             if e["action"] == "subtask_done"
             and isinstance(e.get("detail"), dict)
             and e["detail"].get("subtask_id") == subtask["id"]),
            None,
        )
        checkpoints.append({
            "step": i,
            "label": f"{subtask['specialist'].title()} — {subtask['description'][:60]}",
            "agent": subtask["specialist"],
            "ts": done_event["ts"] if done_event else None,
            "detail": {
                "tool_calls": len(subtask.get("tool_calls", [])),
                "tokens": done_event["detail"].get("tokens") if done_event else None,
            },
            "snapshot": {
                "id": subtask["id"],
                "specialist": subtask["specialist"],
                "result_preview": (subtask.get("result") or "")[:400],
                "tool_calls": subtask.get("tool_calls", []),
            },
        })

    # Review checkpoint
    review_event = next((e for e in state["trace"] if e["action"] == "review_complete"), None)
    if review_event:
        checkpoints.append({
            "step": len(checkpoints),
            "label": "Reviewer Evaluation",
            "agent": "reviewer",
            "ts": review_event["ts"],
            "detail": review_event.get("detail", {}),
            "snapshot": {
                "reviewer_score": state["reviewer_score"],
                "reviewer_feedback": state.get("reviewer_feedback"),
            },
        })

    # Final checkpoint
    final_event = next((e for e in state["trace"] if e["action"] == "task_complete"), None)
    if final_event:
        checkpoints.append({
            "step": len(checkpoints),
            "label": "Task Complete",
            "agent": "system",
            "ts": final_event["ts"],
            "detail": final_event.get("detail", {}),
            "snapshot": {
                "final_output_preview": (state.get("final_output") or "")[:600],
                "cost_usd": state.get("cost_usd", 0),
                "wall_time_s": state.get("wall_time_s", 0),
            },
        })

    return {"task_id": task_id, "checkpoints": checkpoints}


@app.post("/tasks/{task_id}/replay")
def replay_from_checkpoint(task_id: str, background_tasks: BackgroundTasks, modified_request: str = ""):
    """Re-run a completed task (optionally with a modified request) for debugging."""
    original = _get_task(task_id)
    if not original:
        raise HTTPException(404, "Task not found")
    request_text = modified_request.strip() or original["original_request"]
    new_state = create_initial_state(request_text, original.get("user_id", "default"))
    new_state["trace"].append({
        "id": "replay",
        "ts": time.time(),
        "agent": "system",
        "action": "replay_of",
        "detail": {"original_task_id": task_id, "modified": bool(modified_request)},
    })
    _tasks[new_state["task_id"]] = new_state
    db.upsert_task(new_state)
    _dispatch_task(new_state["task_id"], new_state)
    return {
        "original_task_id": task_id,
        "replay_task_id": new_state["task_id"],
        "modified": bool(modified_request),
    }


@app.get("/tools/logs")
def tool_logs(task_id: Optional[str] = None):
    if supabase_enabled():
        return {"logs": db.get_tool_calls(task_id=task_id, limit=50)}
    from tools.registry import get_registry
    return {"logs": get_registry().get_logs(50)}

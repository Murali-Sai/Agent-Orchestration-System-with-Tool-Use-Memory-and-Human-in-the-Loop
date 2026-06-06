"""CRUD helpers for tasks, tool_calls, and hitl_events tables."""
from __future__ import annotations
import json
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Optional
import structlog

from db.client import get_supabase, is_enabled

log = structlog.get_logger()


# ── Serialization helpers ──────────────────────────────────────────────── #

def _serialize(state: dict) -> dict:
    """Convert AgentState to a flat dict safe for Supabase upsert."""
    return {
        "id":                  state["task_id"],
        "user_id":             state["user_id"],
        "original_request":    state["original_request"],
        "status":              state["status"],
        "plan_confidence":     state.get("plan_confidence", 0),
        "reviewer_score":      state.get("reviewer_score", 0),
        "reviewer_feedback":   state.get("reviewer_feedback"),
        "final_output":        state.get("final_output"),
        "awaiting_human":      state.get("awaiting_human", False),
        "human_feedback":      state.get("human_feedback"),
        "total_tokens":        state.get("total_tokens", 0),
        "total_tool_calls":    state.get("total_tool_calls", 0),
        "errors":              json.dumps(state.get("errors", [])),
        "execution_plan":      json.dumps(state.get("execution_plan", [])),
        "completed_subtasks":  json.dumps(state.get("completed_subtasks", [])),
        "escalations":         json.dumps(state.get("escalations", [])),
        "memories_used":       json.dumps(state.get("memories_used", [])),
        "trace":               json.dumps(state.get("trace", [])),
    }


def _deserialize(row: dict) -> dict:
    """Reconstruct AgentState from a Supabase row."""
    def loads(v):
        if isinstance(v, str):
            return json.loads(v)
        return v or []

    return {
        "task_id":             row["id"],
        "user_id":             row["user_id"],
        "original_request":    row["original_request"],
        "status":              row["status"],
        "plan_confidence":     row.get("plan_confidence", 0),
        "reviewer_score":      row.get("reviewer_score", 0),
        "reviewer_feedback":   row.get("reviewer_feedback"),
        "final_output":        row.get("final_output"),
        "awaiting_human":      row.get("awaiting_human", False),
        "human_feedback":      row.get("human_feedback"),
        "total_tokens":        row.get("total_tokens", 0),
        "total_tool_calls":    row.get("total_tool_calls", 0),
        "errors":              loads(row.get("errors", "[]")),
        "execution_plan":      loads(row.get("execution_plan", "[]")),
        "completed_subtasks":  loads(row.get("completed_subtasks", "[]")),
        "escalations":         loads(row.get("escalations", "[]")),
        "memories_used":       loads(row.get("memories_used", "[]")),
        "trace":               loads(row.get("trace", "[]")),
        "current_subtask":     None,
        "retry_count":         0,
    }


# ── Task CRUD ─────────────────────────────────────────────────────────── #

def upsert_task(state: dict) -> bool:
    """Create or update a task row. Returns True on success."""
    if not is_enabled():
        return False
    try:
        sb = get_supabase()
        sb.table("tasks").upsert(_serialize(state)).execute()
        return True
    except Exception as e:
        log.warning("supabase_upsert_failed", error=str(e))
        return False


def get_task(task_id: str) -> Optional[dict]:
    """Load full AgentState from Supabase. Returns None if not found."""
    if not is_enabled():
        return None
    try:
        sb = get_supabase()
        resp = sb.table("tasks").select("*").eq("id", task_id).single().execute()
        return _deserialize(resp.data) if resp.data else None
    except Exception as e:
        log.warning("supabase_get_task_failed", error=str(e))
        return None


def list_tasks(user_id: Optional[str] = None, limit: int = 50) -> list[dict]:
    """List task summaries, optionally filtered by user."""
    if not is_enabled():
        return []
    try:
        sb = get_supabase()
        q = sb.table("tasks").select(
            "id,user_id,original_request,status,plan_confidence,"
            "reviewer_score,total_tokens,awaiting_human,created_at,updated_at"
        ).order("created_at", desc=True).limit(limit)
        if user_id:
            q = q.eq("user_id", user_id)
        return q.execute().data or []
    except Exception as e:
        log.warning("supabase_list_tasks_failed", error=str(e))
        return []


# ── Tool call audit log ───────────────────────────────────────────────── #

def log_tool_call(task_id: str, tool: str, agent: str, inputs: dict,
                  output: Any, success: bool, error: Optional[str], latency: float) -> None:
    if not is_enabled():
        return
    try:
        sb = get_supabase()
        sb.table("tool_calls").insert({
            "task_id":   task_id,
            "tool_name": tool,
            "agent":     agent,
            "inputs":    json.dumps(inputs),
            "output":    json.dumps(output),
            "success":   success,
            "error":     error,
            "latency_s": latency,
        }).execute()
    except Exception as e:
        log.warning("supabase_tool_log_failed", error=str(e))


def get_tool_calls(task_id: Optional[str] = None, limit: int = 100) -> list[dict]:
    if not is_enabled():
        return []
    try:
        sb = get_supabase()
        q = sb.table("tool_calls").select("*").order("created_at", desc=True).limit(limit)
        if task_id:
            q = q.eq("task_id", task_id)
        return q.execute().data or []
    except Exception as e:
        log.warning("supabase_get_tool_calls_failed", error=str(e))
        return []


# ── HITL events ──────────────────────────────────────────────────────── #

def create_hitl_event(task_id: str, task_request: str, escalation: dict) -> str:
    event_id = str(uuid.uuid4())[:12]
    if not is_enabled():
        return event_id
    try:
        sb = get_supabase()
        sb.table("hitl_events").insert({
            "id":           event_id,
            "task_id":      task_id,
            "task_request": task_request[:500],
            "trigger":      escalation.get("trigger", ""),
            "level":        escalation.get("level", ""),
            "context":      json.dumps(escalation.get("context", {})),
            "status":       "pending",
        }).execute()
    except Exception as e:
        log.warning("supabase_hitl_create_failed", error=str(e))
    return event_id


def resolve_hitl_event(event_id: str, approved: bool,
                       response: str = "", modified_output: str = "") -> bool:
    if not is_enabled():
        return False
    try:
        sb = get_supabase()
        sb.table("hitl_events").update({
            "status":          "approved" if approved else "rejected",
            "human_response":  response,
            "modified_output": modified_output,
            "resolved_at":     datetime.now(timezone.utc).isoformat(),
        }).eq("id", event_id).execute()
        return True
    except Exception as e:
        log.warning("supabase_hitl_resolve_failed", error=str(e))
        return False


def list_hitl_events(status: Optional[str] = None, limit: int = 50) -> list[dict]:
    if not is_enabled():
        return []
    try:
        sb = get_supabase()
        q = sb.table("hitl_events").select("*").order("created_at", desc=True).limit(limit)
        if status:
            q = q.eq("status", status)
        return q.execute().data or []
    except Exception as e:
        log.warning("supabase_list_hitl_failed", error=str(e))
        return []

"""LangGraph state machine for the full multi-agent orchestration workflow."""
from __future__ import annotations
import time
import uuid
from typing import Literal

from langgraph.graph import StateGraph, END

from graph.state import AgentState
from agents.supervisor import plan_task, synthesize_results
from agents.specialists import run_specialist
from agents.reviewer import review_output
from agents.base import trace_event
from hitl.escalation import (
    check_plan_confidence,
    check_repeated_failure,
    check_sensitive_operation,
    check_review_quality,
)
from hitl.queue import get_queue
from memory.longterm import LongTermMemory
from memory.working import WorkingMemory
from config.settings import get_settings

settings = get_settings()


def _get_ltm() -> LongTermMemory:
    return LongTermMemory(persist_dir=settings.chroma_persist_dir)


# ──────────────────────────── Node functions ────────────────────────────── #

def node_plan(state: AgentState) -> AgentState:
    # Skip re-planning when resuming after a human approval
    if state.get("execution_plan") and state["status"] != "planning":
        trace_event(state, "supervisor", "plan_skipped_resume", {})
        return state

    ltm = _get_ltm()
    state = plan_task(state, ltm)

    escalation = check_plan_confidence(state)
    if escalation:
        from db import crud as db
        queue = get_queue(settings.redis_url)
        item_id = queue.push(state["task_id"], state["original_request"], escalation)
        db.create_hitl_event(state["task_id"], state["original_request"], escalation)

    return state


def node_execute(state: AgentState) -> AgentState:
    """Execute pending subtasks in dependency order."""
    from agents.specialists import run_specialist

    plan = state["execution_plan"]
    completed_ids = {st["id"] for st in state["completed_subtasks"]}
    queue = get_queue(settings.redis_url)

    # Working memory: mirror current plan so external readers can see live progress
    wm = WorkingMemory(state["task_id"], settings.redis_url)
    wm.set("plan", [{"id": s["id"], "status": s["status"], "specialist": s["specialist"]} for s in plan])

    for subtask in plan:
        if subtask["status"] == "done":
            continue
        # Check dependencies satisfied
        if any(dep not in completed_ids for dep in subtask["depends_on"]):
            continue

        # Sensitive operation check
        escalation = check_sensitive_operation(state, subtask["description"])
        if escalation:
            from db import crud as db_crud
            queue.push(state["task_id"], state["original_request"], escalation)
            db_crud.create_hitl_event(state["task_id"], state["original_request"], escalation)
            return state  # pause, wait for human

        subtask["status"] = "in_progress"
        state["current_subtask"] = subtask

        try:
            result = run_specialist(state, subtask)
            result["status"] = "done"
            state["completed_subtasks"].append(result)
            completed_ids.add(result["id"])
            wm.append("completed_results", {"id": result["id"], "specialist": result["specialist"], "result_preview": (result.get("result") or "")[:200]})
            # Update plan entry
            for i, st in enumerate(state["execution_plan"]):
                if st["id"] == result["id"]:
                    state["execution_plan"][i] = result
                    break
        except Exception as e:
            subtask["retries"] += 1
            state["errors"].append(str(e))
            escalation = check_repeated_failure(state, subtask["id"], subtask["retries"])
            if escalation:
                queue.push(state["task_id"], state["original_request"], escalation)
                return state

    return state


def node_synthesize(state: AgentState) -> AgentState:
    ltm = _get_ltm()
    return synthesize_results(state, ltm)


def node_review(state: AgentState) -> AgentState:
    state = review_output(state)
    escalation = check_review_quality(state)
    if escalation:
        from db import crud as db_crud
        queue = get_queue(settings.redis_url)
        queue.push(state["task_id"], state["original_request"], escalation)
        db_crud.create_hitl_event(state["task_id"], state["original_request"], escalation)
    return state


def node_finalize(state: AgentState) -> AgentState:
    state["status"] = "done"
    trace_event(state, "system", "task_complete", {
        "total_tokens": state["total_tokens"],
        "total_tool_calls": state["total_tool_calls"],
        "reviewer_score": state["reviewer_score"],
        "escalations": len(state["escalations"]),
    })
    return state


# ──────────────────────────── Routing functions ─────────────────────────── #

def route_after_plan(state: AgentState) -> Literal["execute", "await_human"]:
    if state["awaiting_human"]:
        return "await_human"
    return "execute"


def route_after_execute(state: AgentState) -> Literal["execute", "synthesize", "await_human"]:
    if state["awaiting_human"]:
        return "await_human"
    # Check if all subtasks are done
    pending = [st for st in state["execution_plan"] if st["status"] != "done"]
    if pending:
        return "execute"
    return "synthesize"


def route_after_review(state: AgentState) -> Literal["finalize", "synthesize", "await_human"]:
    if state["awaiting_human"]:
        return "await_human"
    # If score is good enough, finalize
    if state["reviewer_score"] >= settings.quality_threshold:
        return "finalize"
    # Allow one re-synthesis attempt
    if len([e for e in state["escalations"] if e["trigger"] == "low_review_score"]) <= 1:
        return "synthesize"
    return "finalize"


def node_await_human(state: AgentState) -> AgentState:
    """Pause point — in async mode this returns immediately; caller polls for resolution."""
    trace_event(state, "system", "awaiting_human", {"escalations": len(state["escalations"])})
    return state


# ──────────────────────────── Graph assembly ────────────────────────────── #

def build_graph() -> StateGraph:
    g = StateGraph(AgentState)

    g.add_node("plan", node_plan)
    g.add_node("execute", node_execute)
    g.add_node("synthesize", node_synthesize)
    g.add_node("review", node_review)
    g.add_node("finalize", node_finalize)
    g.add_node("await_human", node_await_human)

    g.set_entry_point("plan")

    g.add_conditional_edges("plan", route_after_plan, {"execute": "execute", "await_human": "await_human"})
    g.add_conditional_edges("execute", route_after_execute, {
        "execute": "execute",
        "synthesize": "synthesize",
        "await_human": "await_human",
    })
    g.add_edge("synthesize", "review")
    g.add_conditional_edges("review", route_after_review, {
        "finalize": "finalize",
        "synthesize": "synthesize",
        "await_human": "await_human",
    })
    g.add_edge("finalize", END)
    g.add_edge("await_human", END)  # human must resume externally

    return g.compile()


def create_initial_state(request: str, user_id: str = "default") -> AgentState:
    return AgentState(
        task_id=str(uuid.uuid4())[:12],
        original_request=request,
        user_id=user_id,
        execution_plan=[],
        plan_confidence=0.0,
        memories_used=[],
        completed_subtasks=[],
        current_subtask=None,
        retry_count=0,
        escalations=[],
        awaiting_human=False,
        human_feedback=None,
        reviewer_score=0.0,
        reviewer_feedback=None,
        final_output=None,
        status="planning",
        trace=[],
        total_tokens=0,
        total_tool_calls=0,
        errors=[],
    )

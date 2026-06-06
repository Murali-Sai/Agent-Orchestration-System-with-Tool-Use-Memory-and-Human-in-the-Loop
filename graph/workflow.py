"""LangGraph state machine for the full multi-agent orchestration workflow."""
from __future__ import annotations
import time
import uuid
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Literal

from langgraph.graph import StateGraph, END

from graph.state import AgentState, SubTask
from agents.supervisor import plan_task, synthesize_results
from agents.specialists import run_specialist
from agents.reviewer import review_output
from agents.base import trace_event, token_cost_usd
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
        queue.push(state["task_id"], state["original_request"], escalation)
        db.create_hitl_event(state["task_id"], state["original_request"], escalation)

    return state


def _run_subtask_isolated(state: AgentState, subtask: SubTask) -> tuple[SubTask, int, int, dict, list]:
    """Run one specialist in an isolated context to avoid cross-thread state mutation.

    Returns: (result_subtask, token_delta, tool_call_delta, model_usage_delta, trace_events)
    """
    # Shallow copy with isolated tracking fields so concurrent threads don't race
    local_state: dict = {
        **state,
        "total_tokens": 0,
        "total_tool_calls": 0,
        "model_usage": {},
        "trace": [],
    }
    result = run_specialist(local_state, subtask)
    return (
        result,
        local_state["total_tokens"],
        local_state["total_tool_calls"],
        local_state["model_usage"],
        local_state["trace"],
    )


def node_execute(state: AgentState) -> AgentState:
    """Execute pending subtasks in parallel per dependency frontier."""
    plan = state["execution_plan"]
    completed_ids = {st["id"] for st in state["completed_subtasks"]}
    queue = get_queue(settings.redis_url)

    # Working memory: mirror current plan for external observers
    wm = WorkingMemory(state["task_id"], settings.redis_url)
    wm.set("plan", [
        {"id": s["id"], "status": s["status"], "specialist": s["specialist"]}
        for s in plan
    ])

    # Find the current "frontier" — all subtasks whose dependencies are satisfied
    ready: list[SubTask] = []
    for subtask in plan:
        if subtask["status"] == "done":
            continue
        if any(dep not in completed_ids for dep in subtask["depends_on"]):
            continue

        # Sensitive operation check before adding to parallel batch
        escalation = check_sensitive_operation(state, subtask["description"])
        if escalation:
            from db import crud as db_crud
            queue.push(state["task_id"], state["original_request"], escalation)
            db_crud.create_hitl_event(state["task_id"], state["original_request"], escalation)
            return state  # pause execution, wait for human

        subtask["status"] = "in_progress"
        ready.append(subtask)

    if not ready:
        return state

    # ── Run frontier subtasks in parallel ──────────────────────────────── #
    n_workers = min(len(ready), 4)
    successes: list[tuple] = []
    failures: list[tuple] = []
    lock = threading.Lock()

    def _worker(st: SubTask):
        try:
            result = _run_subtask_isolated(state, st)
            with lock:
                successes.append(result)
        except Exception as exc:
            with lock:
                failures.append((st, exc))

    if n_workers == 1:
        # No overhead for single subtask
        _worker(ready[0])
    else:
        with ThreadPoolExecutor(max_workers=n_workers) as pool:
            futures = {pool.submit(_worker, st): st for st in ready}
            for f in as_completed(futures):
                f.result()  # re-raise any unhandled exception from _worker

    # ── Merge results back into shared state ────────────────────────────── #
    for result_st, tok, tc, model_usage, trace_evts in successes:
        result_st["status"] = "done"
        state["completed_subtasks"].append(result_st)
        completed_ids.add(result_st["id"])
        state["total_tokens"] += tok
        state["total_tool_calls"] += tc
        state["trace"].extend(trace_evts)
        for model, mtok in model_usage.items():
            state["model_usage"][model] = state["model_usage"].get(model, 0) + mtok

        # Update plan entry
        for i, st in enumerate(state["execution_plan"]):
            if st["id"] == result_st["id"]:
                state["execution_plan"][i] = result_st
                break

        wm.append("completed_results", {
            "id": result_st["id"],
            "specialist": result_st["specialist"],
            "result_preview": (result_st.get("result") or "")[:200],
        })

    # ── Handle failures ─────────────────────────────────────────────────── #
    for subtask, exc in failures:
        subtask["retries"] += 1
        state["errors"].append(str(exc))
        escalation = check_repeated_failure(state, subtask["id"], subtask["retries"])
        if escalation:
            queue.push(state["task_id"], state["original_request"], escalation)
            from db import crud as db_crud
            db_crud.create_hitl_event(state["task_id"], state["original_request"], escalation)

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

    # ── Cost calculation ─────────────────────────────────────────────────── #
    total_cost = sum(
        token_cost_usd(model, tokens)
        for model, tokens in state.get("model_usage", {}).items()
    )
    state["cost_usd"] = round(total_cost, 6)

    # ── Wall-clock time ──────────────────────────────────────────────────── #
    started = state.get("started_at", time.time())
    state["wall_time_s"] = round(time.time() - started, 2)

    trace_event(state, "system", "task_complete", {
        "total_tokens": state["total_tokens"],
        "total_tool_calls": state["total_tool_calls"],
        "cost_usd": state["cost_usd"],
        "wall_time_s": state["wall_time_s"],
        "reviewer_score": state["reviewer_score"],
        "escalations": len(state["escalations"]),
        "models_used": list(state.get("model_usage", {}).keys()),
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
    pending = [st for st in state["execution_plan"] if st["status"] != "done"]
    if pending:
        return "execute"
    return "synthesize"


def route_after_review(state: AgentState) -> Literal["finalize", "synthesize", "await_human"]:
    if state["awaiting_human"]:
        return "await_human"
    if state["reviewer_score"] >= settings.quality_threshold:
        return "finalize"
    if len([e for e in state["escalations"] if e["trigger"] == "low_review_score"]) <= 1:
        return "synthesize"
    return "finalize"


def node_await_human(state: AgentState) -> AgentState:
    """Pause point — returns immediately; caller polls for resolution."""
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
    g.add_edge("await_human", END)

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
        model_usage={},
        cost_usd=0.0,
        wall_time_s=0.0,
        started_at=time.time(),
        errors=[],
    )

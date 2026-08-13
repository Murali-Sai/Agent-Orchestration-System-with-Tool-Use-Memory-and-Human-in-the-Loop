from __future__ import annotations
import time
from typing import Literal
from graph.state import AgentState, EscalationEvent
from config.settings import get_settings

settings = get_settings()

EscalationLevel = Literal["notify", "approve_action", "approve_plan", "take_over"]

_SENSITIVE_KEYWORDS = [
    "delete", "remove", "drop", "payment", "transaction", "credit card",
    "password", "secret", "private key", "send email", "publish", "deploy to production",
]


def check_plan_confidence(state: AgentState) -> EscalationEvent | None:
    if state["plan_confidence"] < settings.confidence_threshold:
        return _make_event(
            state,
            trigger="low_plan_confidence",
            level="approve_plan",
            context={
                "confidence": state["plan_confidence"],
                "threshold": settings.confidence_threshold,
                "plan_summary": [st["description"] for st in state["execution_plan"]],
            },
        )
    return None


def check_repeated_failure(state: AgentState, subtask_id: str, retries: int) -> EscalationEvent | None:
    if retries >= settings.max_retries:
        return _make_event(
            state,
            trigger="repeated_failure",
            level="approve_action",
            context={"subtask_id": subtask_id, "retries": retries},
        )
    return None


def check_sensitive_operation(state: AgentState, subtask_description: str) -> EscalationEvent | None:
    lower = subtask_description.lower()
    for kw in _SENSITIVE_KEYWORDS:
        if kw in lower:
            return _make_event(
                state,
                trigger=f"sensitive_operation:{kw}",
                level="approve_action",
                context={"subtask": subtask_description, "matched_keyword": kw},
            )
    return None


def check_review_quality(state: AgentState) -> EscalationEvent | None:
    """Handle a below-threshold review score.

    The first low score is recorded but does NOT pause the graph — the workflow
    gets one automatic rework pass at the specialists first. Pausing here would
    set `awaiting_human`, which `route_after_review` checks before it looks at
    the score, sending the task straight to END and making rework unreachable.

    A second low score means rework didn't help, so a human is pulled in.
    Returns the event only when it actually wants human attention; returning
    None keeps the item out of the approval queue on the auto-retry pass.
    """
    if state["reviewer_score"] >= settings.quality_threshold:
        return None

    prior_attempts = len([e for e in state["escalations"] if e["trigger"] == "low_review_score"])
    needs_human = prior_attempts >= 1

    event = _make_event(
        state,
        trigger="low_review_score",
        level="approve_action",
        context={
            "score": state["reviewer_score"],
            "threshold": settings.quality_threshold,
            "feedback": state["reviewer_feedback"],
            "attempt": prior_attempts + 1,
            "auto_rework": not needs_human,
        },
        pause=needs_human,
    )
    return event if needs_human else None


def _make_event(
    state: AgentState,
    trigger: str,
    level: EscalationLevel,
    context: dict,
    pause: bool = True,
) -> EscalationEvent:
    """Record an escalation. `pause=False` logs it without halting the graph."""
    event: EscalationEvent = {
        "trigger": trigger,
        "level": level,
        "context": context,
        "human_response": None,
        "resolved": False,
        "timestamp": time.time(),
    }
    state["escalations"].append(event)
    if pause:
        state["awaiting_human"] = True
        state["status"] = "escalated"
    return event

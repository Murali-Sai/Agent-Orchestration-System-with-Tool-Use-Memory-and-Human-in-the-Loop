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
    if state["reviewer_score"] < settings.quality_threshold:
        return _make_event(
            state,
            trigger="low_review_score",
            level="approve_action",
            context={
                "score": state["reviewer_score"],
                "threshold": settings.quality_threshold,
                "feedback": state["reviewer_feedback"],
            },
        )
    return None


def _make_event(state: AgentState, trigger: str, level: EscalationLevel, context: dict) -> EscalationEvent:
    event: EscalationEvent = {
        "trigger": trigger,
        "level": level,
        "context": context,
        "human_response": None,
        "resolved": False,
        "timestamp": time.time(),
    }
    state["escalations"].append(event)
    state["awaiting_human"] = True
    state["status"] = "escalated"
    return event

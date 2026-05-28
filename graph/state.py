from __future__ import annotations
from typing import Any, Optional, Literal
from typing_extensions import TypedDict


class SubTask(TypedDict):
    id: str
    description: str
    specialist: str          # research | analysis | writing | code
    depends_on: list[str]    # list of subtask IDs
    required_inputs: list[str]
    expected_output: str
    complexity: Literal["low", "medium", "high"]
    status: Literal["pending", "in_progress", "done", "failed", "escalated"]
    result: Optional[str]
    retries: int
    tool_calls: list[dict]


class EscalationEvent(TypedDict):
    trigger: str
    level: Literal["notify", "approve_action", "approve_plan", "take_over"]
    context: dict
    human_response: Optional[str]
    resolved: bool
    timestamp: float


class AgentState(TypedDict):
    # Task identity
    task_id: str
    original_request: str
    user_id: str

    # Planning
    execution_plan: list[SubTask]
    plan_confidence: float          # 0–1; below threshold → escalate
    memories_used: list[dict]       # memories injected at planning time

    # Execution tracking
    completed_subtasks: list[SubTask]
    current_subtask: Optional[SubTask]
    retry_count: int

    # Human-in-the-loop
    escalations: list[EscalationEvent]
    awaiting_human: bool
    human_feedback: Optional[str]

    # Review
    reviewer_score: float           # 0–1
    reviewer_feedback: Optional[str]

    # Final output
    final_output: Optional[str]
    status: Literal["planning", "executing", "reviewing", "escalated", "done", "failed"]

    # Observability
    trace: list[dict]               # append-only event log
    total_tokens: int
    total_tool_calls: int
    errors: list[str]

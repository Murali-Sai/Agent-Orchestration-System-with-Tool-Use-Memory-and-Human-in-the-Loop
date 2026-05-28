from __future__ import annotations
import json
import re
from graph.state import AgentState
from agents.base import llm_call, trace_event

_SYSTEM = """You are the Reviewer Agent. You evaluate the quality of the synthesized output against the original request.

Score each dimension 0.0–1.0:
- completeness: Does it fully address what was asked?
- accuracy: Are facts/calculations correct and well-supported?
- clarity: Is it well-written, structured, and easy to understand?
- actionability: Is the output useful and actionable?

Return ONLY valid JSON:
{
  "overall_score": 0.0-1.0,
  "completeness": 0.0-1.0,
  "accuracy": 0.0-1.0,
  "clarity": 0.0-1.0,
  "actionability": 0.0-1.0,
  "feedback": "specific improvement guidance if score < 0.7",
  "approved": true|false
}"""


def review_output(state: AgentState) -> AgentState:
    """Score the synthesized output and decide whether it passes or needs rework."""
    prompt = (
        f"ORIGINAL REQUEST:\n{state['original_request']}\n\n"
        f"SYNTHESIZED OUTPUT:\n{state['final_output']}"
    )

    content, tokens = llm_call(_SYSTEM, [{"role": "user", "content": prompt}], temperature=0.1)
    state["total_tokens"] += tokens

    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        match = re.search(r'\{.*\}', content, re.DOTALL)
        parsed = json.loads(match.group()) if match else {"overall_score": 0.5, "approved": True, "feedback": ""}

    state["reviewer_score"] = float(parsed.get("overall_score", 0.5))
    state["reviewer_feedback"] = parsed.get("feedback", "")

    trace_event(state, "reviewer", "review_complete", {
        "score": state["reviewer_score"],
        "approved": parsed.get("approved", True),
        "dimensions": {k: parsed.get(k) for k in ("completeness", "accuracy", "clarity", "actionability")},
    })

    return state

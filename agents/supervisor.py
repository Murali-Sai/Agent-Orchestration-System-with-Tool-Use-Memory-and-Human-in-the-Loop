from __future__ import annotations
import json
import uuid
import time
from graph.state import AgentState, SubTask
from agents.base import llm_call, trace_event
from memory.longterm import LongTermMemory
from config.settings import get_settings

settings = get_settings()

_SYSTEM = """You are the Supervisor Agent in a multi-agent orchestration system.

Your job:
1. Decompose complex user requests into ordered subtasks
2. Assign each subtask to the right specialist: research, analysis, writing, or code
3. Identify task dependencies
4. Set your confidence level in the plan

Available specialists:
- research: web search, information gathering, fact-finding
- analysis: data processing, calculations, code execution, structured reasoning
- writing: drafting reports, summaries, formatted documents
- code: writing and executing Python scripts, automation

Return ONLY valid JSON in this exact schema:
{
  "confidence": 0.0-1.0,
  "reasoning": "brief explanation of the plan",
  "subtasks": [
    {
      "id": "st_1",
      "description": "what to do",
      "specialist": "research|analysis|writing|code",
      "depends_on": [],
      "required_inputs": [],
      "expected_output": "what this produces",
      "complexity": "low|medium|high"
    }
  ]
}"""

_SYNTHESIS_SYSTEM = """You are the Supervisor Agent. You have received completed outputs from all specialist agents.
Synthesize them into a single, coherent, high-quality response to the original user request.
Be thorough. Format nicely using markdown. Do not add filler text."""


def plan_task(state: AgentState, ltm: LongTermMemory) -> AgentState:
    """Decompose the task into a subtask plan, informed by long-term memory."""
    request = state["original_request"]

    # Query long-term memory for relevant past experience
    memories = ltm.query(request, n_results=4)
    state["memories_used"] = memories

    memory_ctx = ""
    if memories:
        memory_ctx = "\n\nRELEVANT PAST EXPERIENCE:\n" + "\n".join(
            f"- {m['content']} (relevance: {m['relevance']})" for m in memories
        )

    prompt = f"User request: {request}{memory_ctx}\n\nCreate an execution plan."

    content, tokens = llm_call(_SYSTEM, [{"role": "user", "content": prompt}])
    state["total_tokens"] += tokens

    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        # Try to extract JSON from the response
        import re
        match = re.search(r'\{.*\}', content, re.DOTALL)
        parsed = json.loads(match.group()) if match else {"confidence": 0.3, "subtasks": [], "reasoning": "parse error"}

    state["plan_confidence"] = float(parsed.get("confidence", 0.5))

    subtasks: list[SubTask] = []
    for st in parsed.get("subtasks", []):
        subtasks.append({
            "id": st.get("id", str(uuid.uuid4())[:8]),
            "description": st["description"],
            "specialist": st["specialist"],
            "depends_on": st.get("depends_on", []),
            "required_inputs": st.get("required_inputs", []),
            "expected_output": st.get("expected_output", ""),
            "complexity": st.get("complexity", "medium"),
            "status": "pending",
            "result": None,
            "retries": 0,
            "tool_calls": [],
        })

    state["execution_plan"] = subtasks
    state["status"] = "executing"

    trace_event(state, "supervisor", "plan_created", {
        "confidence": state["plan_confidence"],
        "n_subtasks": len(subtasks),
        "reasoning": parsed.get("reasoning", ""),
    })
    return state


def synthesize_results(state: AgentState, ltm: LongTermMemory) -> AgentState:
    """Combine all specialist outputs into the final response, then save to memory."""
    completed = state["completed_subtasks"]
    results_ctx = "\n\n".join(
        f"### {st['specialist'].upper()} — {st['description']}\n{st['result']}"
        for st in completed if st.get("result")
    )

    content, tokens = llm_call(
        _SYNTHESIS_SYSTEM,
        [{"role": "user", "content": f"ORIGINAL REQUEST:\n{state['original_request']}\n\nSPECIALIST OUTPUTS:\n{results_ctx}"}],
        max_tokens=6000,
    )
    state["total_tokens"] += tokens
    state["final_output"] = content
    state["status"] = "reviewing"

    # Persist to long-term memory
    tools_used = list({tc["tool"] for st in completed for tc in st.get("tool_calls", [])})
    ltm.save(
        f"Task: {state['original_request'][:200]} | Specialists: {[s['specialist'] for s in completed]} | Tools: {tools_used} | Confidence: {state['plan_confidence']}",
        metadata={"task_id": state["task_id"], "user_id": state["user_id"]},
    )

    trace_event(state, "supervisor", "synthesis_done", {"output_len": len(content)})
    return state

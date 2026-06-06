from __future__ import annotations
import json
from graph.state import AgentState, SubTask
from agents.base import llm_call, trace_event, route_model
from tools.registry import get_registry

_SPECIALIST_SYSTEMS = {
    "research": """You are the Research Specialist. Your job is to gather information using web_search.
Always call web_search with targeted queries. Synthesize results into structured findings.
Return your findings as clear, well-organized markdown. Cite sources where possible.
When ready to use a tool, output JSON like: {"tool": "web_search", "args": {"query": "...", "max_results": 5}}
After tool results, analyze and produce your final answer.""",

    "analysis": """You are the Analysis Specialist. You reason about data, run calculations, and execute code.
Use execute_python for any numerical or algorithmic work.
When ready to use a tool, output JSON like: {"tool": "execute_python", "args": {"code": "..."}}
Return structured analysis with clear reasoning, numbers, and conclusions.""",

    "writing": """You are the Writing Specialist. You produce high-quality written content.
You can use read_file to load context and write_file to save deliverables.
Write in clear, professional prose. Format with markdown. Be thorough and well-structured.""",

    "code": """You are the Code Specialist. You write and execute Python code.
Use execute_python to run code and verify it works.
When ready to use a tool, output JSON like: {"tool": "execute_python", "args": {"code": "..."}}
Always test your code. Return working, clean, commented code with execution results.""",
}

_MAX_TOOL_ROUNDS = 4


def run_specialist(state: AgentState, subtask: SubTask) -> SubTask:
    """Run a single subtask through the appropriate specialist with tool use."""
    specialist = subtask["specialist"]
    registry = get_registry()
    system_prompt = _SPECIALIST_SYSTEMS.get(specialist, _SPECIALIST_SYSTEMS["research"])

    # Build context from completed dependencies
    dep_context = _build_dependency_context(subtask, state["completed_subtasks"])

    messages = [{
        "role": "user",
        "content": f"TASK: {subtask['description']}\nEXPECTED OUTPUT: {subtask['expected_output']}\n{dep_context}",
    }]

    model = route_model(specialist, subtask.get("complexity"))
    tool_calls: list[dict] = []
    total_tokens = 0
    final_result = ""

    for round_num in range(_MAX_TOOL_ROUNDS):
        content, tokens = llm_call(system_prompt, messages, model=model, max_tokens=4096)
        total_tokens += tokens

        # Check if agent wants to call a tool
        tool_request = _parse_tool_request(content)
        if tool_request and round_num < _MAX_TOOL_ROUNDS - 1:
            tool_name = tool_request["tool"]
            tool_args = tool_request.get("args", {})
            result = registry.call(tool_name, specialist, **tool_args)
            tool_calls.append({"tool": tool_name, "args": tool_args, "result": result})

            messages.append({"role": "assistant", "content": content})
            messages.append({"role": "user", "content": f"TOOL RESULT ({tool_name}):\n{json.dumps(result, indent=2)}\n\nContinue with your analysis."})
        else:
            # No more tool calls — this is the final answer
            final_result = content
            break

    subtask["result"] = final_result
    subtask["status"] = "done"
    subtask["tool_calls"] = tool_calls
    state["total_tokens"] += total_tokens
    state["total_tool_calls"] += len(tool_calls)
    state["model_usage"][model] = state["model_usage"].get(model, 0) + total_tokens

    trace_event(state, specialist, "subtask_done", {
        "subtask_id": subtask["id"],
        "tool_calls": len(tool_calls),
        "tokens": total_tokens,
    })
    return subtask


def _parse_tool_request(content: str) -> dict | None:
    """Extract a JSON tool call from agent output, handling nested objects."""
    # Find every '{' and try to parse a valid JSON object from it
    for i, ch in enumerate(content):
        if ch != '{':
            continue
        # Walk forward matching braces to find the closing '}'
        depth = 0
        for j, c in enumerate(content[i:], i):
            if c == '{':
                depth += 1
            elif c == '}':
                depth -= 1
                if depth == 0:
                    candidate = content[i:j + 1]
                    try:
                        obj = json.loads(candidate)
                        if isinstance(obj, dict) and "tool" in obj:
                            return obj
                    except json.JSONDecodeError:
                        pass
                    break
    return None


def _build_dependency_context(subtask: SubTask, completed: list[SubTask]) -> str:
    if not subtask["depends_on"]:
        return ""
    relevant = [s for s in completed if s["id"] in subtask["depends_on"] and s.get("result")]
    if not relevant:
        return ""
    ctx = "\n\nCONTEXT FROM PREVIOUS STEPS:\n"
    for s in relevant:
        ctx += f"\n[{s['id']}] {s['description']}:\n{s['result'][:800]}\n"
    return ctx

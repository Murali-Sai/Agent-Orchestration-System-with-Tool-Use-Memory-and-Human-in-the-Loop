from __future__ import annotations
import time
import structlog
from dataclasses import dataclass, field
from typing import Any, Callable, Optional
from collections import defaultdict

log = structlog.get_logger()


@dataclass
class ToolSpec:
    name: str
    description: str
    fn: Callable
    allowed_agents: list[str]  # empty = all agents
    rate_limit: int = 60       # calls per minute; 0 = unlimited
    _call_times: list[float] = field(default_factory=list, repr=False)

    def rate_limited(self) -> bool:
        if self.rate_limit == 0:
            return False
        now = time.time()
        self._call_times = [t for t in self._call_times if now - t < 60]
        return len(self._call_times) >= self.rate_limit

    def record_call(self):
        self._call_times.append(time.time())


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, ToolSpec] = {}
        self._logs: list[dict] = []

    def register(
        self,
        name: str,
        description: str,
        fn: Callable,
        allowed_agents: list[str] | None = None,
        rate_limit: int = 0,
    ) -> None:
        self._tools[name] = ToolSpec(
            name=name,
            description=description,
            fn=fn,
            allowed_agents=allowed_agents or [],
            rate_limit=rate_limit,
        )

    def call(self, name: str, agent: str, **kwargs) -> dict[str, Any]:
        if name not in self._tools:
            return {"error": f"Tool '{name}' not found"}

        spec = self._tools[name]

        if spec.allowed_agents and agent not in spec.allowed_agents:
            return {"error": f"Agent '{agent}' is not permitted to use tool '{name}'"}

        if spec.rate_limited():
            return {"error": f"Tool '{name}' rate limit exceeded"}

        start = time.time()
        try:
            result = spec.fn(**kwargs)
            success = True
            error = None
        except Exception as e:
            result = None
            success = False
            error = str(e)

        latency = round(time.time() - start, 3)
        spec.record_call()

        entry = {
            "tool": name,
            "agent": agent,
            "inputs": kwargs,
            "output": result,
            "success": success,
            "error": error,
            "latency_s": latency,
            "timestamp": time.time(),
        }
        self._logs.append(entry)
        log.info("tool_call", **{k: v for k, v in entry.items() if k != "output"})

        # Persist to Supabase if available (task_id passed via agent name convention "agent:task_id")
        task_id = kwargs.pop("_task_id", None)
        if task_id:
            try:
                from db.crud import log_tool_call
                log_tool_call(task_id, name, agent, kwargs, result, success, error, latency)
            except Exception:
                pass

        return {"result": result, "error": error, "latency_s": latency}

    def list_tools(self, agent: str | None = None) -> list[dict]:
        tools = []
        for spec in self._tools.values():
            if agent and spec.allowed_agents and agent not in spec.allowed_agents:
                continue
            tools.append({"name": spec.name, "description": spec.description})
        return tools

    def get_logs(self, limit: int = 100) -> list[dict]:
        return self._logs[-limit:]


# Singleton
_registry: Optional[ToolRegistry] = None


def get_registry() -> ToolRegistry:
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
        _register_defaults(_registry)
    return _registry


def _register_defaults(registry: ToolRegistry) -> None:
    from tools.web_search import web_search
    from tools.code_executor import execute_python
    from tools.file_tools import read_file, write_file
    from tools.db_query import db_query, db_list_tables
    from tools.http_call import http_call

    registry.register(
        "web_search",
        "Search the web and return relevant results for a query.",
        web_search,
        allowed_agents=["research", "supervisor"],
        rate_limit=30,
    )
    registry.register(
        "execute_python",
        "Execute a Python code snippet in a sandboxed environment and return stdout/result.",
        execute_python,
        allowed_agents=["code", "analysis"],
        rate_limit=20,
    )
    registry.register(
        "read_file",
        "Read the contents of a file by path.",
        read_file,
        allowed_agents=[],  # all
        rate_limit=0,
    )
    registry.register(
        "write_file",
        "Write content to a file at the given path.",
        write_file,
        allowed_agents=["writing", "code"],
        rate_limit=0,
    )
    registry.register(
        "db_query",
        "Execute a read-only SELECT query against the agent SQLite database and return rows as JSON.",
        db_query,
        allowed_agents=["analysis", "research", "code"],
        rate_limit=60,
    )
    registry.register(
        "db_list_tables",
        "List all tables available in the agent database.",
        db_list_tables,
        allowed_agents=[],  # all agents
        rate_limit=0,
    )
    registry.register(
        "http_call",
        "Make an HTTP GET or POST request to an external API and return the response body.",
        http_call,
        allowed_agents=["research", "code", "analysis"],
        rate_limit=20,
    )

"""Tests for the tool registry and individual tools."""
import pytest
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tools.registry import ToolRegistry
from tools.code_executor import execute_python
from tools.file_tools import read_file, write_file


# ── Tool Registry ────────────────────────────────────────────────────── #

class TestToolRegistry:
    def setup_method(self):
        self.registry = ToolRegistry()
        self.registry.register(
            "add", "Add two numbers", lambda a, b: a + b,
            allowed_agents=["math"], rate_limit=0
        )

    def test_registered_tool_callable(self):
        result = self.registry.call("add", "math", a=2, b=3)
        assert result["result"] == 5
        assert result["error"] is None

    def test_unknown_tool_returns_error(self):
        result = self.registry.call("nonexistent", "math")
        assert "error" in result
        assert result["error"] is not None

    def test_agent_permission_enforced(self):
        result = self.registry.call("add", "unauthorized_agent", a=1, b=2)
        assert "not permitted" in result["error"]

    def test_call_logged(self):
        self.registry.call("add", "math", a=1, b=1)
        logs = self.registry.get_logs()
        assert len(logs) >= 1
        assert logs[-1]["tool"] == "add"
        assert logs[-1]["success"] is True

    def test_tool_failure_logged(self):
        self.registry.register("fail", "Always fails", lambda: 1 / 0, rate_limit=0)
        result = self.registry.call("fail", "any")
        assert result["error"] is not None
        logs = self.registry.get_logs()
        assert logs[-1]["success"] is False

    def test_list_tools_filters_by_agent(self):
        tools = self.registry.list_tools(agent="math")
        assert any(t["name"] == "add" for t in tools)
        tools_other = self.registry.list_tools(agent="other")
        assert not any(t["name"] == "add" for t in tools_other)

    def test_rate_limit_blocks_excess_calls(self):
        self.registry.register("limited", "Rate limited", lambda: "ok",
                                allowed_agents=[], rate_limit=2)
        self.registry.call("limited", "any")
        self.registry.call("limited", "any")
        result = self.registry.call("limited", "any")
        assert "rate limit" in result["error"]


# ── Code Executor ─────────────────────────────────────────────────────── #

class TestCodeExecutor:
    def test_basic_execution(self):
        result = execute_python("print('hello')")
        assert result["stdout"].strip() == "hello"
        assert result["error"] is None

    def test_result_variable_captured(self):
        result = execute_python("result = 2 + 2")
        assert result["result"] == 4

    def test_syntax_error_caught(self):
        result = execute_python("def bad(")
        assert result["error"] is not None

    def test_runtime_error_caught(self):
        result = execute_python("x = 1 / 0")
        assert result["error"] is not None

    def test_blocked_module_import(self):
        result = execute_python("import os; result = os.getcwd()")
        assert result["error"] is not None

    def test_stdout_captured(self):
        result = execute_python("for i in range(3): print(i)")
        assert "0" in result["stdout"]
        assert "2" in result["stdout"]

    def test_multiline_code(self):
        code = """
numbers = [1, 2, 3, 4, 5]
result = sum(numbers)
"""
        result = execute_python(code)
        assert result["result"] == 15


# ── File Tools ─────────────────────────────────────────────────────────── #

class TestFileTools:
    def test_write_and_read(self):
        write_result = write_file("test_output.txt", "hello world")
        assert write_result.get("written") is True
        read_result = read_file("test_output.txt")
        assert read_result["content"] == "hello world"

    def test_path_traversal_blocked(self):
        result = read_file("../../etc/passwd")
        assert "error" in result

    def test_nonexistent_file_returns_error(self):
        result = read_file("does_not_exist_xyz.txt")
        assert "error" in result

"""Tests for the MCP bridge.

The unit tests here run without spawning anything. The one integration test
actually starts the in-repo stdio server, so it costs a couple of seconds — it
earns that by proving the bridge works end to end rather than just in mocks.
"""
import sys
import os
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tools.registry import ToolRegistry, _register_mcp_tools
from tools.mcp_client import make_tool_fn, server_available, _server_params

mcp_installed = pytest.importorskip("mcp", reason="mcp SDK not installed") is not None


# ── Client helpers ───────────────────────────────────────────────────────── #

class TestMCPClient:
    def test_known_server_uses_current_interpreter(self):
        """Spawning via sys.executable is what keeps this Node-free and portable."""
        params = _server_params("workspace")
        assert params.command == sys.executable
        assert params.args == ["-m", "tools.mcp_server"]

    def test_unknown_server_rejected(self):
        with pytest.raises(ValueError):
            _server_params("not_a_real_server")

    def test_server_available_false_for_unknown(self):
        assert server_available("not_a_real_server") is False

    def test_workspace_server_is_available(self):
        assert server_available("workspace") is True

    def test_tool_fns_bind_their_own_names(self):
        """Guards the late-binding closure bug: building callables in a loop
        must not leave every tool pointing at the last iteration's name."""
        fns = [make_tool_fn("workspace", name) for name in ("alpha", "beta", "gamma")]
        assert [f.__name__ for f in fns] == [
            "mcp_workspace_alpha",
            "mcp_workspace_beta",
            "mcp_workspace_gamma",
        ]

        called = []
        with patch("tools.mcp_client.call_mcp_tool", lambda s, t, **kw: called.append(t)):
            for f in fns:
                f()
        assert called == ["alpha", "beta", "gamma"]


# ── Registry integration ─────────────────────────────────────────────────── #

class _FakeSettings:
    def __init__(self, enable_mcp=True, mcp_servers="workspace"):
        self.enable_mcp = enable_mcp
        self.mcp_servers = mcp_servers


class TestMCPRegistration:
    def test_disabled_registers_nothing(self):
        registry = ToolRegistry()
        with patch("config.settings.get_settings", lambda: _FakeSettings(enable_mcp=False)):
            _register_mcp_tools(registry)
        assert registry.list_tools() == []

    def test_empty_server_list_registers_nothing(self):
        registry = ToolRegistry()
        with patch("config.settings.get_settings", lambda: _FakeSettings(mcp_servers="  ")):
            _register_mcp_tools(registry)
        assert registry.list_tools() == []

    def test_unknown_server_is_skipped_not_fatal(self):
        registry = ToolRegistry()
        with patch("config.settings.get_settings", lambda: _FakeSettings(mcp_servers="nope")):
            _register_mcp_tools(registry)   # must not raise
        assert registry.list_tools() == []

    def test_discovery_failure_degrades_gracefully(self):
        """A server that won't start must leave the custom tools working."""
        registry = ToolRegistry()
        registry.register("custom", "still here", lambda: "ok")

        def _boom(_server):
            raise RuntimeError("server refused to start")

        with patch("config.settings.get_settings", lambda: _FakeSettings()), \
             patch("tools.mcp_client.discover_mcp_tools", _boom):
            _register_mcp_tools(registry)

        assert [t["name"] for t in registry.list_tools()] == ["custom"]

    def test_discovered_tools_are_namespaced_and_permissioned(self):
        registry = ToolRegistry()
        fake_tools = [{"name": "thing", "description": "does a thing", "schema": None}]

        with patch("config.settings.get_settings", lambda: _FakeSettings()), \
             patch("tools.mcp_client.discover_mcp_tools", lambda _s: fake_tools):
            _register_mcp_tools(registry)

        listed = registry.list_tools()
        assert [t["name"] for t in listed] == ["mcp_workspace_thing"]
        assert listed[0]["description"].startswith("[MCP:workspace]")
        # Same permission model as custom tools — supervisor isn't on the list
        assert registry.list_tools(agent="supervisor") == []
        assert registry.list_tools(agent="research")


# ── End-to-end against the real stdio server ─────────────────────────────── #

class TestMCPEndToEnd:
    def test_real_server_discovery_and_call(self):
        registry = ToolRegistry()
        with patch("config.settings.get_settings", lambda: _FakeSettings()):
            _register_mcp_tools(registry)

        names = [t["name"] for t in registry.list_tools()]
        assert "mcp_workspace_text_stats" in names

        result = registry.call(
            "mcp_workspace_text_stats", "research", text="one two\nthree"
        )
        assert result["error"] is None
        assert "words: 3" in result["result"]
        assert "lines: 2" in result["result"]

    def test_workspace_boundary_is_enforced_through_mcp(self):
        """An MCP tool must not become a way around the file sandbox."""
        registry = ToolRegistry()
        with patch("config.settings.get_settings", lambda: _FakeSettings()):
            _register_mcp_tools(registry)

        result = registry.call(
            "mcp_workspace_file_info", "research", path="../../../etc/passwd"
        )
        assert "escapes workspace boundary" in (result["result"] or "")

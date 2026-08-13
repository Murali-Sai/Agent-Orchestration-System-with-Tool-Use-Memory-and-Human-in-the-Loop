"""Bridges MCP servers into the custom ToolRegistry.

The point of the bridge is that specialists can't tell the difference: an MCP
tool is registered, permissioned, rate-limited, traced and logged exactly like
a hand-written one, so "Custom + MCP" describes one uniform tool surface rather
than two parallel systems.

Connection model — one stdio subprocess per call:

Each call spawns the server, runs the tool, and tears the process down. That is
slower than holding a session open (roughly half a second of process startup),
but it is stateless, thread-safe, and cannot leak a subprocess or wedge the API
behind a half-dead connection — and `node_execute` runs specialists on several
threads at once. A persistent session would need a dedicated event-loop thread
with its own lifecycle management; worth doing if MCP tools ever land on a hot
path, unnecessary while they don't.
"""
from __future__ import annotations

import asyncio
import shutil
import sys
from typing import Any

import structlog

log = structlog.get_logger()

_DEFAULT_TIMEOUT_S = 30.0


def _server_params(server: str):
    """Build stdio parameters for a known server. Imported lazily so the rest of
    the tool framework still works when the `mcp` package isn't installed."""
    from mcp import StdioServerParameters

    if server == "workspace":
        # Our own in-repo server (tools/mcp_server.py). Uses the running
        # interpreter so it works identically in Docker, on Render, and locally.
        return StdioServerParameters(
            command=sys.executable,
            args=["-m", "tools.mcp_server"],
        )

    if server == "git":
        # Optional third-party example: pip install mcp-server-git
        return StdioServerParameters(
            command=sys.executable,
            args=["-m", "mcp_server_git", "--repository", "."],
        )

    raise ValueError(f"Unknown MCP server '{server}'")


def server_available(server: str) -> bool:
    """Cheap pre-flight so discovery failures aren't reported as errors for
    servers that were never installed in the first place."""
    try:
        params = _server_params(server)
    except Exception:
        return False
    return shutil.which(params.command) is not None or params.command == sys.executable


async def _with_session(server: str, fn):
    from mcp import ClientSession
    from mcp.client.stdio import stdio_client

    async with stdio_client(_server_params(server)) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            return await fn(session)


def _run(coro, timeout: float = _DEFAULT_TIMEOUT_S):
    """Run an async MCP interaction from sync code, bounded by a timeout.

    asyncio.run creates and disposes its own loop, so this is safe to call from
    any of the specialist worker threads.
    """
    async def _bounded():
        return await asyncio.wait_for(coro, timeout=timeout)

    return asyncio.run(_bounded())


def discover_mcp_tools(server: str) -> list[dict]:
    """Return [{name, description, schema}] for everything the server exposes."""
    async def _list(session):
        tools = await session.list_tools()
        return [
            {
                "name": t.name,
                "description": (t.description or "").strip(),
                "schema": getattr(t, "inputSchema", None),
            }
            for t in tools.tools
        ]

    return _run(_with_session(server, _list))


def call_mcp_tool(server: str, tool_name: str, **arguments: Any) -> Any:
    """Invoke a tool on an MCP server and return its content as plain text."""
    async def _call(session):
        result = await session.call_tool(tool_name, arguments=arguments)
        parts = [getattr(block, "text", None) for block in result.content]
        text = "\n".join(p for p in parts if p)
        if getattr(result, "isError", False):
            raise RuntimeError(text or f"MCP tool '{tool_name}' failed")
        return text

    return _run(_with_session(server, _call))


def make_tool_fn(server: str, tool_name: str):
    """Build the sync callable ToolRegistry will store.

    A factory rather than an inline lambda: closing over the loop variable
    directly would give every registered tool the last iteration's name.
    """
    def _fn(**kwargs):
        return call_mcp_tool(server, tool_name, **kwargs)

    _fn.__name__ = f"mcp_{server}_{tool_name}"
    return _fn

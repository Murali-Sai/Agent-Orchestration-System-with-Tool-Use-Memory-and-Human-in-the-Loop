"""An MCP server exposing workspace inspection tools over stdio.

Shipping the server in-repo rather than depending on an external one keeps the
MCP integration honest and reproducible:

- no Node.js / `npx` in the container (the reference filesystem server needs it)
- no network fetch or API key at startup, so it works on a cold free-tier boot
- it demonstrates both halves of MCP — authoring a server *and* bridging a
  client into an existing tool framework

Run standalone with:  python -m tools.mcp_server
Agents never invoke it directly; `tools/mcp_client.py` spawns it and registers
whatever it advertises into the normal ToolRegistry.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

from mcp.server.fastmcp import FastMCP

# WARNING level keeps the child process from writing a per-request INFO line
# into the parent's stderr on every tool call.
mcp = FastMCP("workspace", log_level="WARNING")

# Same workspace root and boundary rule as tools/file_tools.py — an MCP tool is
# not a way around the sandbox.
_WORKSPACE = Path(os.getenv("FILE_WORKSPACE", "./workspace")).resolve()
_WORKSPACE.mkdir(parents=True, exist_ok=True)


def _safe_path(path: str) -> Path:
    resolved = (_WORKSPACE / path).resolve()
    if not str(resolved).startswith(str(_WORKSPACE)):
        raise PermissionError(f"Path '{path}' escapes workspace boundary")
    return resolved


@mcp.tool()
def list_workspace(subdir: str = "") -> str:
    """List files in the agent workspace, with sizes in bytes."""
    try:
        root = _safe_path(subdir) if subdir else _WORKSPACE
    except PermissionError as e:
        return f"error: {e}"

    if not root.exists():
        return f"error: '{subdir or '.'}' does not exist"
    if not root.is_dir():
        return f"error: '{subdir}' is not a directory"

    entries = sorted(root.iterdir(), key=lambda p: p.name)
    if not entries:
        return "(empty)"

    lines = []
    for entry in entries:
        rel = entry.relative_to(_WORKSPACE)
        if entry.is_dir():
            lines.append(f"{rel}/")
        else:
            lines.append(f"{rel}  ({entry.stat().st_size} bytes)")
    return "\n".join(lines)


@mcp.tool()
def file_info(path: str) -> str:
    """Report size and last-modified time for a file in the workspace."""
    try:
        p = _safe_path(path)
    except PermissionError as e:
        return f"error: {e}"

    if not p.exists():
        return f"error: '{path}' does not exist"

    stat = p.stat()
    modified = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()
    kind = "directory" if p.is_dir() else "file"
    return f"path: {p.relative_to(_WORKSPACE)}\ntype: {kind}\nsize_bytes: {stat.st_size}\nmodified_utc: {modified}"


@mcp.tool()
def text_stats(text: str) -> str:
    """Count lines, words and characters in a block of text."""
    lines = text.splitlines()
    return (
        f"lines: {len(lines)}\n"
        f"words: {len(text.split())}\n"
        f"characters: {len(text)}\n"
        f"non_empty_lines: {sum(1 for line in lines if line.strip())}"
    )


if __name__ == "__main__":
    mcp.run()

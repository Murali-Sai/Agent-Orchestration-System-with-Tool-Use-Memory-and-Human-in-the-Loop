from __future__ import annotations
import os
from pathlib import Path

# Limit file access to a safe workspace directory
_WORKSPACE = Path(os.getenv("FILE_WORKSPACE", "./workspace")).resolve()
_WORKSPACE.mkdir(parents=True, exist_ok=True)


def _safe_path(path: str) -> Path:
    resolved = (_WORKSPACE / path).resolve()
    if not str(resolved).startswith(str(_WORKSPACE)):
        raise PermissionError(f"Path '{path}' escapes workspace boundary")
    return resolved


def read_file(path: str) -> dict:
    try:
        p = _safe_path(path)
        return {"content": p.read_text(encoding="utf-8"), "path": str(p)}
    except Exception as e:
        return {"error": str(e)}


def write_file(path: str, content: str) -> dict:
    try:
        p = _safe_path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return {"written": True, "path": str(p), "bytes": len(content.encode())}
    except Exception as e:
        return {"error": str(e)}

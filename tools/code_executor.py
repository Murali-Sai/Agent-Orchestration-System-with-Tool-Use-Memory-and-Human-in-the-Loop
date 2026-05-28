from __future__ import annotations
import sys
import io
import traceback
import builtins
from typing import Any

_BLOCKED = {
    "os", "subprocess", "shutil", "pathlib",
    "socket", "http", "urllib", "ftplib", "smtplib",
    "importlib",
}

_original_import = builtins.__import__


def _sandboxed_import(name, *args, **kwargs):
    if name.split(".")[0] in _BLOCKED:
        raise ImportError(f"Module '{name.split('.')[0]}' is blocked in the sandbox")
    return _original_import(name, *args, **kwargs)


def execute_python(code: str, timeout: int = 10) -> dict[str, Any]:
    """Execute Python code in a restricted sandbox. Returns stdout and result."""
    stdout_capture = io.StringIO()
    stderr_capture = io.StringIO()

    old_stdout, old_stderr = sys.stdout, sys.stderr
    sys.stdout = stdout_capture
    sys.stderr = stderr_capture

    # Inject sandboxed __import__ so frozen modules are also blocked
    safe_builtins = vars(builtins).copy()
    safe_builtins["__import__"] = _sandboxed_import

    namespace: dict = {"__builtins__": safe_builtins}
    error = None
    result = None

    try:
        exec(compile(code, "<sandbox>", "exec"), namespace)
        result = namespace.get("result", None)
    except Exception:
        error = traceback.format_exc()
    finally:
        sys.stdout = old_stdout
        sys.stderr = old_stderr

    return {
        "stdout": stdout_capture.getvalue(),
        "stderr": stderr_capture.getvalue(),
        "result": result,
        "error": error,
    }

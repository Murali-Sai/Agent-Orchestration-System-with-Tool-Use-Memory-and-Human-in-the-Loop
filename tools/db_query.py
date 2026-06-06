"""Database query tool — executes read-only SQL against a local SQLite database.

Agents use this to query structured data stored during task execution.
Write operations are blocked at the SQL level (SELECT-only enforcement).
"""
from __future__ import annotations
import os
import re
import sqlite3
import json
from pathlib import Path

_DB_PATH = os.getenv("AGENT_DB_PATH", "./workspace/agent_data.db")
_MAX_ROWS = 200
_BLOCKED_KEYWORDS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|TRUNCATE|REPLACE|GRANT|REVOKE)\b",
    re.IGNORECASE,
)


def _ensure_db() -> sqlite3.Connection:
    Path(_DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    # Seed example table so agents always have something to query
    conn.execute("""
        CREATE TABLE IF NOT EXISTS task_results (
            id          TEXT PRIMARY KEY,
            user_id     TEXT,
            request     TEXT,
            status      TEXT,
            score       REAL,
            tokens      INTEGER,
            cost_usd    REAL,
            created_at  TEXT
        )
    """)
    conn.commit()
    return conn


def db_query(sql: str, params: list | None = None) -> dict:
    """Execute a read-only SQL query and return results as JSON.

    Args:
        sql:    A SELECT statement to execute.
        params: Optional list of positional parameters (e.g. ["value1"]).

    Returns:
        {"rows": [...], "columns": [...], "count": N}  on success
        {"error": "..."}                               on failure
    """
    sql = sql.strip()

    # Block any non-SELECT statements
    if _BLOCKED_KEYWORDS.search(sql):
        return {"error": "Only SELECT statements are permitted."}

    if not sql.upper().startswith("SELECT"):
        return {"error": "Only SELECT statements are permitted."}

    try:
        conn = _ensure_db()
        cursor = conn.execute(sql, params or [])
        columns = [d[0] for d in cursor.description] if cursor.description else []
        rows = [dict(r) for r in cursor.fetchmany(_MAX_ROWS)]
        conn.close()
        return {"rows": rows, "columns": columns, "count": len(rows)}
    except sqlite3.Error as e:
        return {"error": f"SQL error: {e}"}
    except Exception as e:
        return {"error": str(e)}


def db_list_tables() -> dict:
    """List all tables available in the agent database."""
    try:
        conn = _ensure_db()
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        conn.close()
        return {"tables": [r[0] for r in rows]}
    except Exception as e:
        return {"error": str(e)}

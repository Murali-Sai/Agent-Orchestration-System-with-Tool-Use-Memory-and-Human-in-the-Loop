#!/usr/bin/env python3
"""
AgentOS Demo — end-to-end showcase of the multi-agent orchestration system.

Submits a complex research + analysis + writing task, streams live progress,
and prints a formatted summary of every decision the system made.

Usage:
    python demo.py
    python demo.py --url http://localhost:8000
    python demo.py --task "Compare LangGraph and AutoGen architectures"
    python demo.py --no-wait       # just submit and exit (non-blocking)
"""
from __future__ import annotations
import argparse
import json
import sys
import time

import requests

# ── Config ─────────────────────────────────────────────────────────────── #

DEFAULT_API = "http://localhost:8000"
POLL_INTERVAL = 4       # seconds between status checks
MAX_WAIT = 300          # seconds before giving up
DEMO_USER = "demo_showcase"

DEMO_TASK = """\
Research the top 3 AI agent frameworks of 2025 — LangGraph, AutoGen, and CrewAI.
For each framework:
  1. Summarise its architecture and core abstractions
  2. Identify its key strengths and typical use cases
  3. Note any production limitations

Then write a concise technical brief (≤600 words) with a clear recommendation
for a team building a production-grade, multi-agent, human-in-the-loop system.
Include a comparison table.\
"""

# ── Helpers ─────────────────────────────────────────────────────────────── #

RESET   = "\033[0m"
BOLD    = "\033[1m"
GREEN   = "\033[92m"
YELLOW  = "\033[93m"
BLUE    = "\033[94m"
MAGENTA = "\033[95m"
CYAN    = "\033[96m"
RED     = "\033[91m"
DIM     = "\033[2m"


def c(color: str, text: str) -> str:
    return f"{color}{text}{RESET}"


def _api(base: str, path: str, method: str = "GET", **kwargs) -> dict | None:
    try:
        resp = getattr(requests, method.lower())(f"{base}{path}", timeout=10, **kwargs)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(c(RED, f"  ✗ API error: {e}"))
        return None


def _bar(fraction: float, width: int = 30) -> str:
    filled = int(fraction * width)
    return "█" * filled + "░" * (width - filled)


def _status_color(status: str) -> str:
    return {
        "done": GREEN, "failed": RED, "escalated": YELLOW,
        "executing": CYAN, "reviewing": MAGENTA, "planning": BLUE,
    }.get(status, DIM)


# ── Main ─────────────────────────────────────────────────────────────────── #

def run(api_url: str, task: str, no_wait: bool = False) -> None:
    print()
    print(c(BOLD, "╔══════════════════════════════════════════════════════════╗"))
    print(c(BOLD, "║         ⚡  AgentOS — Multi-Agent Orchestration Demo      ║"))
    print(c(BOLD, "╚══════════════════════════════════════════════════════════╝"))
    print()

    # 1. Health check
    health = _api(api_url, "/health")
    if not health:
        print(c(RED, "✗ Cannot reach API at " + api_url))
        print(c(DIM, "  Start the API with: python -m uvicorn api.main:app --port 8000"))
        sys.exit(1)

    print(c(GREEN, f"✓ API online") + c(DIM, f"  — Supabase: {'✓' if health.get('supabase') else '✗'}"
          f"  Celery: {'✓' if health.get('celery') else '✗'}"))
    print()

    # 2. Submit task
    print(c(BOLD, "📝 Task:"))
    for line in task.strip().splitlines():
        print(c(DIM, f"   {line}"))
    print()

    resp = _api(api_url, "/tasks", method="post", json={"request": task, "user_id": DEMO_USER})
    if not resp:
        print(c(RED, "✗ Failed to submit task"))
        sys.exit(1)

    task_id = resp["task_id"]
    runner  = resp.get("runner", "thread")
    print(c(GREEN, f"✓ Task submitted") + c(DIM, f"  id={task_id}  runner={runner}"))
    print(c(DIM, f"  UI: http://localhost:8501"))
    print()

    if no_wait:
        print(c(YELLOW, "  --no-wait flag set. Poll manually:"))
        print(c(DIM, f"  curl {api_url}/tasks/{task_id}"))
        return

    # 3. Poll for completion
    print(c(BOLD, "⏳ Waiting for execution…"))
    start = time.time()
    last_completed = -1

    while time.time() - start < MAX_WAIT:
        state = _api(api_url, f"/tasks/{task_id}")
        if not state:
            time.sleep(POLL_INTERVAL)
            continue

        status    = state.get("status", "unknown")
        completed = state.get("completed", 0)
        total     = state.get("total", 0)
        tokens    = state.get("total_tokens", 0)
        cost      = state.get("cost_usd", 0.0)

        # Print subtask progress as they complete
        if completed != last_completed and total > 0:
            frac = completed / total
            bar  = _bar(frac)
            plan = state.get("plan", [])
            print(f"  [{bar}] {completed}/{total}  "
                  + c(DIM, f"{tokens:,} tok  ${cost:.4f}"))
            for st_item in plan:
                if st_item.get("status") == "done":
                    sp = st_item.get("specialist", "?")
                    desc = st_item.get("description", "")[:55]
                    print(c(GREEN, f"    ✓ {sp:10s}") + c(DIM, f" — {desc}"))
            last_completed = completed

        if state.get("awaiting_human"):
            print()
            print(c(YELLOW, "⚠  Task paused — human review required."))
            escs = state.get("escalations", [])
            for e in escs:
                if not e.get("resolved"):
                    print(c(YELLOW, f"   Trigger: {e.get('trigger')}  Level: {e.get('level')}"))
            print(c(DIM, f"  Review at: http://localhost:8501 → HITL Queue"))
            break

        if status in ("done", "failed"):
            break

        time.sleep(POLL_INTERVAL)

    # 4. Final summary
    state = _api(api_url, f"/tasks/{task_id}") or {}
    status = state.get("status", "unknown")
    color  = _status_color(status)
    print()
    print(c(BOLD, f"{'═' * 60}"))
    print(c(BOLD + color, f"  Status: {status.upper()}"))
    print(c(BOLD, f"{'═' * 60}"))
    print()

    # Metrics
    plan = state.get("plan", [])
    print(c(BOLD, "📊 Metrics:"))
    print(f"  Subtasks completed : {len([s for s in plan if s.get('status')=='done'])}/{len(plan)}")
    print(f"  Total tokens       : {state.get('total_tokens',0):,}")
    print(f"  Estimated cost     : ${state.get('cost_usd',0.0):.4f}")
    print(f"  Wall-clock time    : {state.get('wall_time_s',0):.1f}s")
    print(f"  Reviewer score     : {state.get('reviewer_score',0):.2f}/1.00")
    model_usage = state.get("model_usage", {})
    if model_usage:
        print(f"  Models used        : {', '.join(model_usage.keys())}")
    if state.get("escalations"):
        print(c(YELLOW, f"  Escalations        : {len(state['escalations'])}"))
    print()

    # Execution plan
    if plan:
        print(c(BOLD, "🗺  Execution plan:"))
        for st_item in plan:
            sp     = st_item.get("specialist", "?")
            desc   = st_item.get("description", "")[:70]
            st_status = st_item.get("status", "?")
            sc     = _status_color(st_status)
            tc     = len(st_item.get("tool_calls", []))
            print(c(sc, f"  {'✓' if st_status=='done' else '○'} [{sp:10s}]")
                  + f" {desc}"
                  + c(DIM, f"  ({tc} tool calls)"))
        print()

    # Reviewer feedback
    if state.get("reviewer_feedback"):
        print(c(BOLD, "🔎 Reviewer feedback:"))
        print(c(DIM, f"  {state['reviewer_feedback'][:300]}"))
        print()

    # Final output preview
    if state.get("final_output"):
        print(c(BOLD, "📄 Output preview (first 1000 chars):"))
        print(c(DIM, "─" * 60))
        print(state["final_output"][:1000])
        if len(state["final_output"]) > 1000:
            print(c(DIM, f"… [{len(state['final_output'])-1000} more chars — view full output in the UI]"))
        print(c(DIM, "─" * 60))
        print()

    print(c(BOLD, "🔭 Full trace:"))
    print(c(DIM, f"  http://localhost:8501  →  Trace Explorer  →  {task_id}"))
    print()

    if status == "failed":
        print(c(RED, "✗ Task failed. Errors:"))
        for err in state.get("errors", []):
            print(c(RED, f"  - {err}"))
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AgentOS end-to-end demo")
    parser.add_argument("--url",     default=DEFAULT_API, help="API base URL")
    parser.add_argument("--task",    default=DEMO_TASK,   help="Task description to submit")
    parser.add_argument("--no-wait", action="store_true", help="Submit task and exit without polling")
    args = parser.parse_args()

    run(args.url, args.task, args.no_wait)

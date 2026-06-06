"""End-to-end integration tests for the FastAPI HTTP layer.

These tests exercise the full request/response cycle without making real LLM
calls — the OpenAI and Anthropic clients are patched to return deterministic
fixture responses.

Run with:  pytest tests/test_api_e2e.py -v
"""
from __future__ import annotations
import json
import time
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


# ── LLM fixture responses ────────────────────────────────────────────────── #

_PLAN_JSON = json.dumps({
    "confidence": 0.85,
    "reasoning": "Simple research + writing task",
    "subtasks": [
        {
            "id": "st_1",
            "description": "Research AI agent frameworks",
            "specialist": "research",
            "depends_on": [],
            "required_inputs": [],
            "expected_output": "Summary of findings",
            "complexity": "medium",
        },
        {
            "id": "st_2",
            "description": "Write technical brief",
            "specialist": "writing",
            "depends_on": ["st_1"],
            "required_inputs": ["st_1"],
            "expected_output": "500-word brief",
            "complexity": "low",
        },
    ],
})

_SPECIALIST_RESPONSE = "Here are the research findings on AI agent frameworks."

_REVIEW_JSON = json.dumps({
    "overall_score": 0.88,
    "completeness": 0.90,
    "accuracy": 0.85,
    "clarity": 0.90,
    "actionability": 0.88,
    "feedback": "",
    "approved": True,
})

_SYNTHESIS_RESPONSE = "# Technical Brief\n\nBased on research findings, LangGraph is recommended."


def _mock_openai_response(content: str, tokens: int = 150):
    resp = MagicMock()
    resp.choices[0].message.content = content
    resp.usage.prompt_tokens = tokens
    resp.usage.completion_tokens = tokens
    return resp


def _make_mock_client(responses: list[str]):
    """Build an OpenAI client mock that cycles through the given response list."""
    client = MagicMock()
    client.chat.completions.create.side_effect = [
        _mock_openai_response(r) for r in responses
    ]
    return client


# ── Fixtures ─────────────────────────────────────────────────────────────── #

@pytest.fixture()
def client():
    """TestClient with a mocked OpenAI backend."""
    llm_responses = [
        _PLAN_JSON,             # supervisor: plan
        _SPECIALIST_RESPONSE,   # research specialist (round 1 — no tool call)
        _SPECIALIST_RESPONSE,   # writing specialist
        _SYNTHESIS_RESPONSE,    # supervisor: synthesis
        _REVIEW_JSON,           # reviewer
    ]
    mock_openai = _make_mock_client(llm_responses)

    with patch("agents.base.get_client", return_value=mock_openai), \
         patch("agents.base._get_anthropic", return_value=None):
        from api.main import app
        with TestClient(app, raise_server_exceptions=True) as c:
            yield c


# ── Health check ─────────────────────────────────────────────────────────── #

class TestHealth:
    def test_health_returns_200(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "ok"
        assert "tasks_active" in body
        assert "supabase" in body


# ── Task submission ───────────────────────────────────────────────────────── #

class TestTaskSubmission:
    def test_submit_task_returns_task_id(self, client):
        r = client.post("/tasks", json={"request": "Test task", "user_id": "test"})
        assert r.status_code == 200
        body = r.json()
        assert "task_id" in body
        assert body["status"] == "started"

    def test_submit_empty_request(self, client):
        """Empty requests should still be accepted (validation is the agent's job)."""
        r = client.post("/tasks", json={"request": "", "user_id": "test"})
        assert r.status_code == 200

    def test_task_appears_in_list(self, client):
        r = client.post("/tasks", json={"request": "List me test", "user_id": "u1"})
        task_id = r.json()["task_id"]

        tasks = client.get("/tasks").json()
        ids = [t.get("task_id") or t.get("id") for t in tasks]
        assert task_id in ids


# ── Task polling ─────────────────────────────────────────────────────────── #

class TestTaskPolling:
    def test_get_task_404_unknown(self, client):
        r = client.get("/tasks/nonexistent_id")
        assert r.status_code == 404

    def test_get_task_returns_structure(self, client):
        r = client.post("/tasks", json={"request": "Poll test", "user_id": "u2"})
        task_id = r.json()["task_id"]

        r2 = client.get(f"/tasks/{task_id}")
        assert r2.status_code == 200
        body = r2.json()
        assert body["task_id"] == task_id
        assert "status" in body
        assert "plan" in body
        assert "total_tokens" in body

    def test_task_completes(self, client):
        """Submit a task and wait up to 30s for it to reach done/failed/escalated."""
        r = client.post("/tasks", json={
            "request": "Compare LangGraph and AutoGen and write a brief.",
            "user_id": "e2e",
        })
        assert r.status_code == 200
        task_id = r.json()["task_id"]

        deadline = time.time() + 30
        while time.time() < deadline:
            state = client.get(f"/tasks/{task_id}").json()
            if state["status"] in ("done", "failed", "escalated"):
                break
            time.sleep(0.5)

        assert state["status"] in ("done", "failed", "escalated"), \
            f"Task still '{state['status']}' after 30s"

        if state["status"] == "done":
            assert state["reviewer_score"] > 0
            assert state["total_tokens"] > 0


# ── Trace ─────────────────────────────────────────────────────────────────── #

class TestTrace:
    def test_trace_endpoint(self, client):
        r = client.post("/tasks", json={"request": "Trace test", "user_id": "u3"})
        task_id = r.json()["task_id"]
        time.sleep(0.2)

        r2 = client.get(f"/tasks/{task_id}/trace")
        assert r2.status_code == 200
        assert "trace" in r2.json()

    def test_checkpoints_endpoint(self, client):
        r = client.post("/tasks", json={"request": "Checkpoint test", "user_id": "u4"})
        task_id = r.json()["task_id"]
        # Wait for task to make some progress
        time.sleep(1)

        r2 = client.get(f"/tasks/{task_id}/checkpoints")
        assert r2.status_code == 200
        body = r2.json()
        assert "checkpoints" in body
        assert body["task_id"] == task_id


# ── HITL endpoints ────────────────────────────────────────────────────────── #

class TestHITL:
    def test_hitl_queue_returns_list(self, client):
        r = client.get("/hitl/queue")
        assert r.status_code == 200
        assert "items" in r.json()

    def test_hitl_resolve_404_unknown(self, client):
        r = client.post("/hitl/resolve", json={
            "item_id": "does_not_exist",
            "approved": True,
        })
        assert r.status_code == 404

    def test_hitl_chat_404_unknown(self, client):
        r = client.post("/hitl/chat/nonexistent", json={"role": "human", "message": "hello"})
        # Queue reports item not found → 404
        assert r.status_code == 404

    def test_hitl_get_chat_empty(self, client):
        r = client.get("/hitl/chat/some_item")
        assert r.status_code == 200
        assert r.json()["messages"] == []


# ── Memory endpoints ──────────────────────────────────────────────────────── #

class TestMemory:
    def test_memory_stats(self, client):
        r = client.get("/memory/stats")
        assert r.status_code == 200
        assert "long_term_memories" in r.json()

    def test_memory_list(self, client):
        r = client.get("/memory/list")
        assert r.status_code == 200
        assert "memories" in r.json()

    def test_memory_consolidate(self, client):
        r = client.post("/memory/consolidate")
        assert r.status_code == 200
        assert "remaining" in r.json()

    def test_memory_prune(self, client):
        r = client.post("/memory/prune?max_age_days=365")
        assert r.status_code == 200
        assert "pruned" in r.json()


# ── Tools ─────────────────────────────────────────────────────────────────── #

class TestTools:
    def test_tool_logs(self, client):
        r = client.get("/tools/logs")
        assert r.status_code == 200
        assert "logs" in r.json()


# ── Analytics ─────────────────────────────────────────────────────────────── #

class TestAnalytics:
    def test_aggregate_stats(self, client):
        r = client.get("/stats/aggregate")
        assert r.status_code == 200
        body = r.json()
        assert "total_tasks" in body
        assert "total_cost_usd" in body
        assert "model_usage" in body
        assert "tool_usage" in body
        assert "escalation_rate" in body


# ── Replay ────────────────────────────────────────────────────────────────── #

class TestReplay:
    def test_replay_creates_new_task(self, client):
        r = client.post("/tasks", json={"request": "Replay source task", "user_id": "u5"})
        task_id = r.json()["task_id"]
        time.sleep(0.5)

        r2 = client.post(f"/tasks/{task_id}/replay", json={"modified_request": ""})
        assert r2.status_code == 200
        body = r2.json()
        assert "replay_task_id" in body
        assert body["original_task_id"] == task_id
        assert body["replay_task_id"] != task_id

    def test_replay_404_unknown(self, client):
        r = client.post("/tasks/nonexistent/replay", json={"modified_request": ""})
        assert r.status_code == 404

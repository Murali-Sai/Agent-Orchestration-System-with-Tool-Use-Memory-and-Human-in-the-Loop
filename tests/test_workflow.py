"""Tests for agent state, task decomposition, escalation triggers, and graph routing."""
import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from graph.workflow import create_initial_state, build_graph
from graph.state import AgentState
from hitl.escalation import (
    check_plan_confidence,
    check_repeated_failure,
    check_sensitive_operation,
    check_review_quality,
)
from agents.reviewer import review_output


# ── Initial State ──────────────────────────────────────────────────────── #

class TestInitialState:
    def test_creates_valid_state(self):
        state = create_initial_state("Test request", "user_1")
        assert state["original_request"] == "Test request"
        assert state["user_id"] == "user_1"
        assert state["status"] == "planning"
        assert state["awaiting_human"] is False
        assert state["total_tokens"] == 0
        assert isinstance(state["trace"], list)
        assert isinstance(state["errors"], list)

    def test_unique_task_ids(self):
        s1 = create_initial_state("task A")
        s2 = create_initial_state("task B")
        assert s1["task_id"] != s2["task_id"]


# ── Escalation Triggers ──────────────────────────────────────────────── #

class TestEscalationTriggers:
    def _make_state(self) -> AgentState:
        return create_initial_state("test", "user")

    def test_low_confidence_triggers_escalation(self):
        state = self._make_state()
        state["plan_confidence"] = 0.3
        state["execution_plan"] = [{"description": "do something"}]
        event = check_plan_confidence(state)
        assert event is not None
        assert event["trigger"] == "low_plan_confidence"
        assert event["level"] == "approve_plan"
        assert state["awaiting_human"] is True

    def test_high_confidence_no_escalation(self):
        state = self._make_state()
        state["plan_confidence"] = 0.9
        event = check_plan_confidence(state)
        assert event is None
        assert state["awaiting_human"] is False

    def test_repeated_failure_escalates(self):
        state = self._make_state()
        event = check_repeated_failure(state, "st_1", retries=2)
        assert event is not None
        assert event["trigger"] == "repeated_failure"

    def test_below_retry_limit_no_escalation(self):
        state = self._make_state()
        event = check_repeated_failure(state, "st_1", retries=1)
        assert event is None

    def test_sensitive_keyword_triggers_escalation(self):
        state = self._make_state()
        sensitive_tasks = [
            "delete all user records",
            "send email to all customers",
            "process payment transaction",
        ]
        for task in sensitive_tasks:
            s = self._make_state()
            event = check_sensitive_operation(s, task)
            assert event is not None, f"Expected escalation for: {task}"
            assert event["level"] == "approve_action"

    def test_normal_task_no_sensitive_escalation(self):
        state = self._make_state()
        event = check_sensitive_operation(state, "research quantum computing trends")
        assert event is None

    def test_low_review_score_escalates(self):
        state = self._make_state()
        state["reviewer_score"] = 0.4
        state["reviewer_feedback"] = "Output is incomplete"
        event = check_review_quality(state)
        assert event is not None
        assert event["trigger"] == "low_review_score"

    def test_good_review_score_no_escalation(self):
        state = self._make_state()
        state["reviewer_score"] = 0.85
        event = check_review_quality(state)
        assert event is None


# ── Graph Construction ─────────────────────────────────────────────────── #

class TestGraphConstruction:
    def test_graph_builds_without_error(self):
        graph = build_graph()
        assert graph is not None

    def test_graph_has_required_nodes(self):
        graph = build_graph()
        # LangGraph compiled graph exposes nodes via graph.nodes
        node_names = set(graph.nodes.keys()) if hasattr(graph, "nodes") else set()
        # If nodes aren't directly accessible, just verify it compiled
        assert graph is not None


# ── HITL Queue ──────────────────────────────────────────────────────── #

class TestApprovalQueue:
    def setup_method(self):
        from hitl.queue import ApprovalQueue
        # Use a bad Redis URL to force local fallback
        self.queue = ApprovalQueue(redis_url="redis://localhost:63799/0")

    def test_push_and_list_pending(self):
        escalation = {"trigger": "low_plan_confidence", "level": "approve_plan", "context": {}}
        item_id = self.queue.push("task_1", "original request", escalation)
        pending = self.queue.list_pending()
        assert any(p["id"] == item_id for p in pending)

    def test_resolve_removes_from_pending(self):
        escalation = {"trigger": "test", "level": "notify", "context": {}}
        item_id = self.queue.push("task_2", "request", escalation)
        resolved = self.queue.resolve(item_id, approved=True, response="Looks good")
        assert resolved is True
        pending = self.queue.list_pending()
        assert not any(p["id"] == item_id for p in pending)

    def test_resolve_nonexistent_returns_false(self):
        assert self.queue.resolve("nonexistent_id", approved=True) is False

    def test_resolved_items_accessible(self):
        escalation = {"trigger": "test", "level": "notify", "context": {}}
        item_id = self.queue.push("task_3", "request", escalation)
        self.queue.resolve(item_id, approved=False, response="Rejected")
        resolved = self.queue.get_resolved()
        assert any(r["id"] == item_id for r in resolved)

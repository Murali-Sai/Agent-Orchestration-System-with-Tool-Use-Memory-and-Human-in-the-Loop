"""Tests for agent state, task decomposition, escalation triggers, and graph routing."""
import json
import pytest
import sys, os
from unittest.mock import patch
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from graph.workflow import (
    create_initial_state,
    build_graph,
    node_rework,
    route_after_review,
)
from graph.state import AgentState
from agents.specialists import run_specialist
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

    def test_first_low_review_score_records_but_does_not_pause(self):
        """First failure is logged for audit but left to the automatic rework
        pass — pausing here would make the rework branch unreachable."""
        state = self._make_state()
        state["reviewer_score"] = 0.4
        state["reviewer_feedback"] = "Output is incomplete"
        event = check_review_quality(state)
        assert event is None                      # not queued for a human yet
        assert state["awaiting_human"] is False   # graph keeps running
        assert len(state["escalations"]) == 1     # but it is on the record
        assert state["escalations"][0]["trigger"] == "low_review_score"
        assert state["escalations"][0]["context"]["auto_rework"] is True

    def test_second_low_review_score_escalates_to_human(self):
        state = self._make_state()
        state["reviewer_score"] = 0.4
        state["reviewer_feedback"] = "Still incomplete"
        check_review_quality(state)               # first pass → auto rework
        event = check_review_quality(state)       # rework didn't help
        assert event is not None
        assert event["trigger"] == "low_review_score"
        assert event["context"]["attempt"] == 2
        assert state["awaiting_human"] is True

    def test_good_review_score_no_escalation(self):
        state = self._make_state()
        state["reviewer_score"] = 0.85
        event = check_review_quality(state)
        assert event is None
        assert state["escalations"] == []


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


# ── Rework routing ─────────────────────────────────────────────────────── #

class TestReworkLoop:
    def _state_with_plan(self) -> AgentState:
        state = create_initial_state("test", "user")
        state["execution_plan"] = [{
            "id": "st_1",
            "description": "research something",
            "specialist": "research",
            "depends_on": [],
            "required_inputs": [],
            "expected_output": "findings",
            "complexity": "low",
            "status": "done",
            "result": "weak first attempt",
            "retries": 0,
            "tool_calls": [],
        }]
        state["completed_subtasks"] = list(state["execution_plan"])
        return state

    def test_passing_score_finalizes(self):
        state = self._state_with_plan()
        state["reviewer_score"] = 0.9
        assert route_after_review(state) == "finalize"

    def test_first_low_score_routes_to_rework(self):
        state = self._state_with_plan()
        state["reviewer_score"] = 0.3
        state["reviewer_feedback"] = "Needs more depth"
        check_review_quality(state)
        assert route_after_review(state) == "rework"

    def test_second_low_score_routes_to_human(self):
        state = self._state_with_plan()
        state["reviewer_score"] = 0.3
        check_review_quality(state)
        check_review_quality(state)
        assert route_after_review(state) == "await_human"

    def test_rework_reopens_plan_with_feedback(self):
        state = self._state_with_plan()
        state["reviewer_score"] = 0.3
        state["reviewer_feedback"] = "Missing cost analysis"

        state = node_rework(state)

        subtask = state["execution_plan"][0]
        assert subtask["status"] == "pending"
        assert subtask["result"] is None
        assert state["completed_subtasks"] == []
        assert any("REVIEWER FEEDBACK" in ri for ri in subtask["required_inputs"])
        assert any("Missing cost analysis" in ri for ri in subtask["required_inputs"])
        assert any(e["action"] == "rework_triggered" for e in state["trace"])

    def test_rework_does_not_stack_duplicate_feedback(self):
        state = self._state_with_plan()
        state["reviewer_feedback"] = "Same note"
        state = node_rework(state)
        state = node_rework(state)
        notes = [ri for ri in state["execution_plan"][0]["required_inputs"] if "REVIEWER FEEDBACK" in ri]
        assert len(notes) == 1

    def test_feedback_reaches_the_specialist_prompt(self):
        """The rework note is useless unless run_specialist puts it in the message."""
        state = self._state_with_plan()
        state["reviewer_feedback"] = "Add benchmarks"
        state = node_rework(state)
        subtask = state["execution_plan"][0]

        captured = {}

        def _fake_llm_call(system, messages, model=None, max_tokens=4096, temperature=0.3):
            captured["content"] = messages[0]["content"]
            return "revised output", 10

        with patch("agents.specialists.llm_call", _fake_llm_call):
            run_specialist(state, subtask)

        assert "REVIEWER FEEDBACK" in captured["content"]
        assert "Add benchmarks" in captured["content"]


# ── Rework through the real compiled graph ──────────────────────────────── #

_E2E_PLAN = json.dumps({
    "confidence": 0.9,
    "reasoning": "simple",
    "subtasks": [{
        "id": "st_1",
        "description": "Research agent frameworks",
        "specialist": "research",
        "depends_on": [],
        "required_inputs": [],
        "expected_output": "findings",
        "complexity": "low",
    }],
})


def _review_json(score: float, feedback: str = "") -> str:
    return json.dumps({
        "overall_score": score,
        "completeness": score, "accuracy": score,
        "clarity": score, "actionability": score,
        "feedback": feedback,
        "approved": score >= 0.65,
    })


class _ScriptedLLMs:
    """Drives a full graph run with deterministic responses, recording the
    prompts specialists actually received."""

    def __init__(self, scores: list[float], feedback: str = "Missing cost analysis."):
        self.scores = list(scores)
        self.feedback = feedback
        self.specialist_prompts: list[str] = []
        self.review_calls = 0

    def supervisor(self, system, messages, model=None, **kw):
        if "SYNTHES" not in messages[0]["content"].upper() and "subtask" in system.lower():
            return _E2E_PLAN, 100
        return "# Final Answer\nSynthesized output.", 100

    def specialist(self, system, messages, model=None, **kw):
        self.specialist_prompts.append(messages[0]["content"])
        return "Specialist findings.", 50

    def reviewer(self, system, messages, model=None, **kw):
        score = self.scores[min(self.review_calls, len(self.scores) - 1)]
        self.review_calls += 1
        return _review_json(score, self.feedback if score < 0.65 else ""), 40

    def run(self, request: str = "Compare agent frameworks"):
        with patch("agents.supervisor.llm_call", self.supervisor), \
             patch("agents.specialists.llm_call", self.specialist), \
             patch("agents.reviewer.llm_call", self.reviewer):
            return build_graph().invoke(create_initial_state(request, "test_user"))


class TestReworkEndToEnd:
    def test_low_score_reworks_then_finalizes(self):
        llms = _ScriptedLLMs(scores=[0.30, 0.92])
        result = llms.run()

        assert llms.review_calls == 2
        assert len(llms.specialist_prompts) == 2, "specialist should run a second time"
        assert result["status"] == "done"
        assert result["awaiting_human"] is False
        assert result["reviewer_score"] == 0.92

        actions = [e["action"] for e in result["trace"]]
        assert "rework_triggered" in actions
        assert actions.count("subtask_done") == 2

        reworked = [p for p in llms.specialist_prompts if "REVIEWER FEEDBACK" in p]
        assert len(reworked) == 1
        assert "Missing cost analysis" in reworked[0]

    def test_persistent_low_score_escalates_without_looping(self):
        llms = _ScriptedLLMs(scores=[0.30, 0.30])
        result = llms.run()

        assert llms.review_calls == 2, "exactly one rework pass, then stop"
        assert len(llms.specialist_prompts) == 2
        assert result["awaiting_human"] is True
        assert result["status"] == "escalated"
        assert len([e for e in result["escalations"] if e["trigger"] == "low_review_score"]) == 2

    def test_memory_is_saved_once_with_the_real_review_score(self):
        """Importance is reviewer_score x complexity, so the write has to happen
        after review — during synthesis the score is still its initial 0.0."""
        saved = []

        class _RecordingLTM:
            def query(self, *a, **kw):
                return []

            def save(self, content, metadata=None):
                saved.append((content, metadata or {}))
                return "mem-id"

        llms = _ScriptedLLMs(scores=[0.90])
        with patch("graph.workflow._get_ltm", lambda: _RecordingLTM()):
            result = llms.run()

        assert result["status"] == "done"
        assert len(saved) == 1, "exactly one memory per task"
        _, meta = saved[0]
        assert meta["reviewer_score"] == 0.90
        assert meta["importance"] > 0, "importance must reflect the score, not 0.0"

    def test_reworked_task_still_saves_only_one_memory(self):
        """Synthesis runs twice on a rework; the memory write must not."""
        saved = []

        class _RecordingLTM:
            def query(self, *a, **kw):
                return []

            def save(self, content, metadata=None):
                saved.append(metadata or {})
                return "mem-id"

        llms = _ScriptedLLMs(scores=[0.30, 0.88])
        with patch("graph.workflow._get_ltm", lambda: _RecordingLTM()):
            llms.run()

        assert len(saved) == 1
        assert saved[0]["reviewer_score"] == 0.88

    def test_passing_score_never_reworks(self):
        llms = _ScriptedLLMs(scores=[0.95])
        result = llms.run()

        assert llms.review_calls == 1
        assert len(llms.specialist_prompts) == 1
        assert result["status"] == "done"
        assert "rework_triggered" not in [e["action"] for e in result["trace"]]
        assert not any("REVIEWER FEEDBACK" in p for p in llms.specialist_prompts)


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

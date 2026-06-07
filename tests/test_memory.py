"""Tests for working memory and long-term memory."""
import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from memory.working import WorkingMemory
from memory.longterm import LongTermMemory

# LTM tests require Supabase + OpenAI — skip gracefully in plain unit-test envs.
_ltm_available = bool(os.getenv("SUPABASE_URL") and os.getenv("OPENAI_API_KEY"))
_ltm_skip = pytest.mark.skipif(not _ltm_available, reason="Supabase + OpenAI not configured")


# ── Working Memory ────────────────────────────────────────────────────── #

class TestWorkingMemory:
    def setup_method(self):
        # Use a fresh task ID each test — forces local fallback (no Redis needed)
        import uuid
        self.wm = WorkingMemory(f"test_{uuid.uuid4().hex[:8]}", redis_url="redis://localhost:63799/0")

    def test_set_and_get(self):
        self.wm.set("plan", {"subtasks": [1, 2, 3]})
        val = self.wm.get("plan")
        assert val == {"subtasks": [1, 2, 3]}

    def test_get_missing_returns_default(self):
        assert self.wm.get("nonexistent", default="fallback") == "fallback"

    def test_append_builds_list(self):
        self.wm.append("results", "first")
        self.wm.append("results", "second")
        val = self.wm.get("results")
        assert val == ["first", "second"]

    def test_clear_removes_all(self):
        self.wm.set("a", 1)
        self.wm.set("b", 2)
        self.wm.clear()
        assert self.wm.get("a") is None
        assert self.wm.get("b") is None

    def test_get_all_returns_dict(self):
        self.wm.set("x", 10)
        self.wm.set("y", 20)
        all_data = self.wm.get_all()
        assert "x" in all_data
        assert "y" in all_data


# ── Long-Term Memory (Supabase pgvector) ─────────────────────────────── #

class TestLongTermMemory:
    """
    LTM is backed by Supabase pgvector.  Tests run only when SUPABASE_URL and
    OPENAI_API_KEY are present in the environment (i.e. integration test runs).
    In plain unit-test mode they are skipped — the no-op degradation path is
    validated by test_disabled_ltm_noop below.
    """

    def setup_method(self):
        self.ltm = LongTermMemory()

    @_ltm_skip
    def test_save_and_query(self):
        self.ltm.save("Python is great for machine learning", {"type": "fact"})
        results = self.ltm.query("machine learning programming language")
        assert len(results) >= 1
        assert any("Python" in r["content"] for r in results)

    @_ltm_skip
    def test_query_returns_relevance_score(self):
        self.ltm.save("LangGraph is used for agent orchestration")
        results = self.ltm.query("agent workflow")
        assert all("relevance" in r for r in results)
        assert all(0.0 <= r["relevance"] <= 1.0 for r in results)

    @_ltm_skip
    def test_count_increases_on_save(self):
        initial = self.ltm.count()
        self.ltm.save("New fact about AI")
        assert self.ltm.count() == initial + 1

    @_ltm_skip
    def test_delete_removes_memory(self):
        mem_id = self.ltm.save("Memory to be deleted")
        count_before = self.ltm.count()
        self.ltm.delete(mem_id)
        assert self.ltm.count() == count_before - 1

    def test_disabled_ltm_noop(self):
        """When Supabase is absent, all methods must return safe empty values."""
        ltm = LongTermMemory()
        if ltm._enabled:
            pytest.skip("Supabase available — noop test not applicable")
        assert ltm.save("anything") == ""
        assert ltm.query("anything") == []
        assert ltm.list_all() == []
        assert ltm.count() == 0
        assert ltm.prune_old() == 0
        assert ltm.consolidate() == 0
        ltm.delete("fake-id")  # must not raise

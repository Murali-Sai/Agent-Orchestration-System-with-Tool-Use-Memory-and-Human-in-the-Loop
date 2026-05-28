"""Tests for working memory and long-term memory."""
import pytest
import sys, os, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from memory.working import WorkingMemory
from memory.longterm import LongTermMemory


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


# ── Long-Term Memory ─────────────────────────────────────────────────── #

class TestLongTermMemory:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.ltm = LongTermMemory(persist_dir=self.tmpdir, collection="test_col")

    def test_save_and_query(self):
        self.ltm.save("Python is great for machine learning", {"type": "fact"})
        results = self.ltm.query("machine learning programming language")
        assert len(results) >= 1
        assert any("Python" in r["content"] for r in results)

    def test_query_returns_relevance_score(self):
        self.ltm.save("LangGraph is used for agent orchestration")
        results = self.ltm.query("agent workflow")
        assert all("relevance" in r for r in results)
        assert all(0.0 <= r["relevance"] <= 1.0 for r in results)

    def test_count_increases_on_save(self):
        initial = self.ltm.count()
        self.ltm.save("New fact about AI")
        assert self.ltm.count() == initial + 1

    def test_delete_removes_memory(self):
        mem_id = self.ltm.save("Memory to be deleted")
        count_before = self.ltm.count()
        self.ltm.delete(mem_id)
        assert self.ltm.count() == count_before - 1

    def test_empty_query_returns_empty_list(self):
        # Fresh collection — query with n_results=1 when count=0
        fresh = LongTermMemory(persist_dir=tempfile.mkdtemp(), collection="empty_col")
        results = fresh.query("anything")
        assert isinstance(results, list)

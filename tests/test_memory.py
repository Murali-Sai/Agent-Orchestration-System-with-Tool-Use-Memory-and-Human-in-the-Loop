"""Tests for working memory and long-term memory."""
import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from memory.working import WorkingMemory
from memory.longterm import (
    LongTermMemory,
    _frequency_boost,
    _parse_embedding,
    _MAX_FREQUENCY_BOOST,
)

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

    @_ltm_skip
    def test_query_tracks_access_count(self):
        """Retrieval should make a memory measurably more important over time."""
        self.ltm.save("Kubernetes handles container orchestration", {"type": "fact"})

        first = self.ltm.query("container orchestration")
        assert first, "expected the saved memory to be retrievable"
        baseline = next(r for r in first if "Kubernetes" in r["content"])

        for _ in range(4):
            self.ltm.query("container orchestration")

        latest = self.ltm.query("container orchestration")
        after = next(r for r in latest if "Kubernetes" in r["content"])

        assert after["access_count"] > baseline["access_count"]
        assert after["importance"] >= baseline["importance"]

    @_ltm_skip
    def test_consolidate_merges_near_duplicates(self):
        self.ltm.save("User prefers concise technical answers")
        self.ltm.save("User likes short, technical responses")
        removed = self.ltm.consolidate(similarity_threshold=0.80)
        assert removed >= 1

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


# ── Scoring helpers (pure functions — no Supabase required) ──────────────── #

class TestFrequencyBoost:
    def test_no_accesses_no_boost(self):
        assert _frequency_boost(0) == 0.0
        assert _frequency_boost(-1) == 0.0

    def test_boost_grows_with_access_count(self):
        assert _frequency_boost(1) < _frequency_boost(5) < _frequency_boost(20)

    def test_boost_is_capped(self):
        assert _frequency_boost(10_000) == _MAX_FREQUENCY_BOOST

    def test_growth_is_sublinear(self):
        """A memory read 50 times shouldn't outrank everything forever."""
        first_five = _frequency_boost(5) - _frequency_boost(0)
        next_five = _frequency_boost(10) - _frequency_boost(5)
        assert next_five < first_five


class _FakeTable:
    """Minimal stand-in for supabase.table(...) covering the chained calls
    consolidate() makes: select/execute, update/eq/execute, delete/in_/execute."""

    def __init__(self, rows: list[dict], deleted: list[str], updated: dict):
        self._rows = rows
        self._deleted = deleted
        self._updated = updated
        self._pending_update: dict | None = None
        self._mode: str | None = None

    def select(self, *_a, **_k):
        self._mode = "select"
        return self

    def update(self, values):
        self._mode = "update"
        self._pending_update = values
        return self

    def delete(self):
        self._mode = "delete"
        return self

    def eq(self, _col, value):
        if self._mode == "update":
            self._updated[value] = self._pending_update
        return self

    def in_(self, _col, values):
        self._deleted.extend(values)
        return self

    def execute(self):
        if self._mode == "select":
            return type("Resp", (), {"data": self._rows})()
        return type("Resp", (), {"data": []})()


class _FakeSupabase:
    def __init__(self, rows: list[dict]):
        self.rows = rows
        self.deleted: list[str] = []
        self.updated: dict[str, dict] = {}

    def table(self, _name):
        return _FakeTable(self.rows, self.deleted, self.updated)


def _ltm_with_rows(rows: list[dict]) -> LongTermMemory:
    ltm = LongTermMemory.__new__(LongTermMemory)   # bypass Supabase connection
    ltm._enabled = True
    ltm._sb = _FakeSupabase(rows)
    return ltm


class TestConsolidate:
    def test_merges_duplicates_and_keeps_highest_importance(self):
        rows = [
            {"id": "a", "content": "x", "embedding": [1.0, 0.0], "ts": 100.0, "importance": 0.4},
            {"id": "b", "content": "x again", "embedding": [1.0, 0.0], "ts": 200.0, "importance": 0.9},
            {"id": "c", "content": "unrelated", "embedding": [0.0, 1.0], "ts": 300.0, "importance": 0.5},
        ]
        ltm = _ltm_with_rows(rows)
        removed = ltm.consolidate(similarity_threshold=0.95)

        assert removed == 1
        assert ltm._sb.deleted == ["a"]           # lower importance loses
        assert "b" in ltm._sb.updated             # survivor gets corroboration bump
        assert ltm._sb.updated["b"]["importance"] == pytest.approx(0.95)

    def test_distinct_memories_are_left_alone(self):
        rows = [
            {"id": "a", "content": "x", "embedding": [1.0, 0.0], "ts": 1.0, "importance": 0.5},
            {"id": "b", "content": "y", "embedding": [0.0, 1.0], "ts": 2.0, "importance": 0.5},
        ]
        ltm = _ltm_with_rows(rows)
        assert ltm.consolidate(similarity_threshold=0.95) == 0
        assert ltm._sb.deleted == []

    def test_handles_postgrest_string_embeddings(self):
        """The live DB returns vectors as strings — consolidate must not choke."""
        rows = [
            {"id": "a", "content": "x", "embedding": "[1.0, 0.0]", "ts": 1.0, "importance": 0.5},
            {"id": "b", "content": "x", "embedding": "[1.0, 0.0]", "ts": 2.0, "importance": 0.5},
        ]
        ltm = _ltm_with_rows(rows)
        assert ltm.consolidate(similarity_threshold=0.95) == 1

    def test_skips_rows_with_unparseable_embeddings(self):
        rows = [
            {"id": "a", "content": "x", "embedding": None, "ts": 1.0, "importance": 0.5},
            {"id": "b", "content": "y", "embedding": "garbage", "ts": 2.0, "importance": 0.5},
        ]
        ltm = _ltm_with_rows(rows)
        assert ltm.consolidate() == 0

    def test_zero_vector_does_not_divide_by_zero(self):
        rows = [
            {"id": "a", "content": "x", "embedding": [0.0, 0.0], "ts": 1.0, "importance": 0.5},
            {"id": "b", "content": "y", "embedding": [0.0, 0.0], "ts": 2.0, "importance": 0.5},
        ]
        ltm = _ltm_with_rows(rows)
        ltm.consolidate()   # must not raise


class TestParseEmbedding:
    def test_parses_postgrest_string_form(self):
        """pgvector comes back from PostgREST as a string, not a list."""
        assert _parse_embedding("[0.1, 0.2, 0.3]") == [0.1, 0.2, 0.3]

    def test_passes_through_list_form(self):
        assert _parse_embedding([0.1, 0.2]) == [0.1, 0.2]

    def test_coerces_ints_to_floats(self):
        assert _parse_embedding([1, 2]) == [1.0, 2.0]

    def test_returns_none_on_garbage(self):
        assert _parse_embedding(None) is None
        assert _parse_embedding("not json") is None
        assert _parse_embedding(["a", "b"]) is None

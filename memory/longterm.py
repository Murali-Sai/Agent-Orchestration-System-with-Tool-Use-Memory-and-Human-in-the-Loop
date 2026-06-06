"""Long-term semantic memory backed by ChromaDB.

Improvements over baseline:
- importance field stored per memory (reviewer_score × complexity_weight)
- Decay scoring: older memories rank lower (exponential decay, half-life ~30 days)
- Composite retrieval: relevance × importance_weight × recency_weight
- consolidate(): merge near-duplicate memories
- prune_old(): remove memories older than N days
"""
from __future__ import annotations
import math
import time
import uuid
from typing import Any, Optional
import structlog

log = structlog.get_logger()

_DECAY_HALF_LIFE_DAYS = 30.0   # importance halves every 30 days


def _recency_weight(timestamp: float) -> float:
    """Exponential decay weight: 1.0 at creation, 0.5 after 30 days, etc."""
    age_days = (time.time() - timestamp) / 86400.0
    return math.exp(-math.log(2) * age_days / _DECAY_HALF_LIFE_DAYS)


class LongTermMemory:
    def __init__(self, persist_dir: str = "./chroma_db", collection: str = "agent_memory"):
        # Degrade gracefully: if ChromaDB can't initialise (e.g. memory-constrained
        # host, missing native deps), run in a disabled no-op mode rather than
        # crashing the core task flow. All read methods return empty, writes no-op.
        self._client = None
        self._col = None
        try:
            import chromadb
            self._client = chromadb.PersistentClient(path=persist_dir)
            self._col = self._client.get_or_create_collection(
                name=collection,
                metadata={"hnsw:space": "cosine"},
            )
        except Exception as e:  # pragma: no cover - environment dependent
            log.warning("longterm_memory_unavailable", error=str(e))

    # ── Write ──────────────────────────────────────────────────────────── #

    def save(self, content: str, metadata: dict[str, Any] | None = None) -> str:
        """Embed and store a memory string. Returns the memory ID.

        Pass ``importance`` in metadata (0–1) to influence future retrieval ranking.
        Defaults to 0.5 if not provided.
        """
        if self._col is None:
            return ""
        mem_id = str(uuid.uuid4())
        now = time.time()
        meta = {
            "timestamp": now,
            "importance": 0.5,   # default; callers should override
            **(metadata or {}),
        }
        safe_meta = {k: str(v)[:512] for k, v in meta.items()}
        self._col.add(documents=[content], metadatas=[safe_meta], ids=[mem_id])
        log.info("memory_saved", id=mem_id, importance=meta["importance"], preview=content[:80])
        return mem_id

    # ── Read ───────────────────────────────────────────────────────────── #

    def query(self, query: str, n_results: int = 5, where: dict | None = None) -> list[dict]:
        """Retrieve semantically similar memories, re-ranked by composite score.

        Composite score = cosine_relevance × importance_weight × recency_weight
        """
        if self._col is None:
            return []
        count = self._col.count()
        if count == 0:
            return []

        # Fetch more candidates so re-ranking has something to work with
        fetch_n = min(max(n_results * 3, 10), count)
        kwargs: dict[str, Any] = {"query_texts": [query], "n_results": fetch_n}
        if where:
            kwargs["where"] = where

        try:
            results = self._col.query(**kwargs)
        except Exception as e:
            log.warning("memory_query_failed", error=str(e))
            return []

        docs = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]
        ids = results.get("ids", [[]])[0]

        scored = []
        for doc, meta, dist, mid in zip(docs, metas, distances, ids):
            cosine_relevance = max(0.0, 1 - dist)
            importance = float(meta.get("importance", 0.5))
            ts = float(meta.get("timestamp", time.time()))
            recency = _recency_weight(ts)
            composite = round(cosine_relevance * (0.5 + 0.5 * importance) * (0.7 + 0.3 * recency), 4)
            scored.append({
                "id": mid,
                "content": doc,
                "metadata": meta,
                "relevance": round(cosine_relevance, 3),
                "importance": round(importance, 3),
                "recency_weight": round(recency, 3),
                "composite_score": composite,
            })

        scored.sort(key=lambda x: x["composite_score"], reverse=True)
        return scored[:n_results]

    def list_all(self, limit: int = 50) -> list[dict]:
        """Return up to `limit` memories sorted by timestamp descending."""
        if self._col is None:
            return []
        count = self._col.count()
        if count == 0:
            return []
        results = self._col.get(limit=min(limit, count))
        memories = []
        for doc, meta, mid in zip(
            results.get("documents", []),
            results.get("metadatas", []),
            results.get("ids", []),
        ):
            memories.append({"id": mid, "content": doc, "metadata": meta})
        memories.sort(key=lambda x: float(x["metadata"].get("timestamp", 0)), reverse=True)
        return memories

    # ── Maintenance ────────────────────────────────────────────────────── #

    def delete(self, memory_id: str) -> None:
        if self._col is None:
            return
        self._col.delete(ids=[memory_id])
        log.info("memory_deleted", id=memory_id)

    def prune_old(self, max_age_days: float = 90.0) -> int:
        """Delete memories older than `max_age_days`. Returns count deleted."""
        if self._col is None:
            return 0
        cutoff = time.time() - max_age_days * 86400
        results = self._col.get()
        ids_to_delete = [
            mid for mid, meta in zip(results.get("ids", []), results.get("metadatas", []))
            if float(meta.get("timestamp", 0)) < cutoff
        ]
        if ids_to_delete:
            self._col.delete(ids=ids_to_delete)
            log.info("memory_pruned", count=len(ids_to_delete))
        return len(ids_to_delete)

    def consolidate(self, similarity_threshold: float = 0.95) -> int:
        """Merge near-duplicate memories (cosine distance < 1 - threshold).

        For each cluster of near-duplicates, the highest-importance memory
        is kept and the rest are deleted. Returns the number of memories removed.
        """
        if self._col is None:
            return 0
        count = self._col.count()
        if count < 2:
            return 0

        results = self._col.get()
        ids = results.get("ids", [])
        docs = results.get("documents", [])
        metas = results.get("metadatas", [])

        removed = 0
        deleted_set: set[str] = set()

        for i, (doc_i, id_i) in enumerate(zip(docs, ids)):
            if id_i in deleted_set:
                continue
            # Query for near-duplicates of this document
            try:
                dupes = self._col.query(
                    query_texts=[doc_i],
                    n_results=min(5, count),
                )
            except Exception:
                continue

            dup_ids = dupes.get("ids", [[]])[0]
            dup_dists = dupes.get("distances", [[]])[0]
            dup_metas = dupes.get("metadatas", [[]])[0]

            for dup_id, dist, dup_meta in zip(dup_ids, dup_dists, dup_metas):
                if dup_id == id_i or dup_id in deleted_set:
                    continue
                if dist < (1 - similarity_threshold):
                    # Near-duplicate — keep the one with higher importance
                    imp_i = float(metas[i].get("importance", 0.5))
                    imp_d = float(dup_meta.get("importance", 0.5))
                    to_remove = dup_id if imp_i >= imp_d else id_i
                    deleted_set.add(to_remove)
                    self._col.delete(ids=[to_remove])
                    removed += 1

        if removed:
            log.info("memory_consolidated", removed=removed)
        return removed

    def count(self) -> int:
        if self._col is None:
            return 0
        return self._col.count()

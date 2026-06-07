"""Long-term semantic memory backed by Supabase pgvector.

Replaces ChromaDB with durable cloud-native vector storage.
Same public interface as the previous ChromaDB implementation so
workflow.py / supervisor.py / api/main.py require zero changes.

Architecture:
- OpenAI text-embedding-3-small generates 1536-dim embeddings (~$0.02/M tokens)
- Vectors stored in Supabase `memory_embeddings` table (pgvector extension)
- Cosine similarity search via `match_memories` Postgres RPC function
- Composite retrieval: cosine_relevance × importance_weight × recency_weight
- Exponential decay scoring (importance halves every 30 days)
- Graceful no-op degradation when Supabase or OpenAI are unavailable
"""
from __future__ import annotations
import math
import time
import uuid
from typing import Any
import structlog

log = structlog.get_logger()

_DECAY_HALF_LIFE_DAYS = 30.0
_EMBED_MODEL = "text-embedding-3-small"
_EMBED_DIM = 1536


def _recency_weight(timestamp: float) -> float:
    """Exponential decay: 1.0 at creation, 0.5 after 30 days."""
    age_days = (time.time() - timestamp) / 86400.0
    return math.exp(-math.log(2) * age_days / _DECAY_HALF_LIFE_DAYS)


def _get_embedding(text: str) -> list[float] | None:
    """Generate a 1536-dim embedding via OpenAI. Returns None on failure."""
    try:
        from openai import OpenAI
        from config.settings import get_settings
        client = OpenAI(api_key=get_settings().openai_api_key)
        response = client.embeddings.create(model=_EMBED_MODEL, input=text[:8000])
        return response.data[0].embedding
    except Exception as e:
        log.warning("embedding_failed", error=str(e))
        return None


class LongTermMemory:
    """Supabase pgvector-backed long-term semantic memory.

    Falls back to a silent no-op when Supabase is not configured, so the
    rest of the system continues without error — same behaviour as before.
    """

    def __init__(self, persist_dir: str = "./chroma_db", collection: str = "agent_memory"):
        # persist_dir / collection kept for API compatibility — unused by pgvector.
        self._enabled = False
        self._sb = None
        try:
            from db.client import is_enabled, get_supabase
            if is_enabled():
                self._sb = get_supabase()
                self._enabled = True
                log.info("longterm_memory_ready", backend="supabase_pgvector")
            else:
                log.warning("longterm_memory_unavailable", reason="Supabase not configured")
        except Exception as e:
            log.warning("longterm_memory_unavailable", error=str(e))

    # ── Write ──────────────────────────────────────────────────────────── #

    def save(self, content: str, metadata: dict[str, Any] | None = None) -> str:
        """Embed and store a memory string. Returns the memory ID (or "" on failure)."""
        if not self._enabled:
            return ""

        mem_id = str(uuid.uuid4())
        now = time.time()
        importance = float((metadata or {}).get("importance", 0.5))

        embedding = _get_embedding(content)
        if embedding is None:
            return ""

        try:
            self._sb.table("memory_embeddings").insert({
                "id":         mem_id,
                "content":    content[:2000],
                "embedding":  embedding,
                "metadata":   metadata or {},
                "timestamp":  now,
                "importance": importance,
            }).execute()
            log.info("memory_saved", id=mem_id, importance=importance, preview=content[:80])
            return mem_id
        except Exception as e:
            log.warning("memory_save_failed", error=str(e))
            return ""

    # ── Read ───────────────────────────────────────────────────────────── #

    def query(self, query: str, n_results: int = 5, where: dict | None = None) -> list[dict]:
        """Retrieve semantically similar memories, re-ranked by composite score.

        Composite score = cosine_relevance × importance_weight × recency_weight
        The `where` parameter is accepted for API compatibility but ignored
        (filtering can be added via Postgres function args if needed).
        """
        if not self._enabled:
            return []

        embedding = _get_embedding(query)
        if embedding is None:
            return []

        try:
            resp = self._sb.rpc("match_memories", {
                "query_embedding": embedding,
                "match_count":     min(n_results * 3, 30),
            }).execute()
            rows = resp.data or []
        except Exception as e:
            log.warning("memory_query_failed", error=str(e))
            return []

        scored = []
        for row in rows:
            cosine_relevance = float(row.get("similarity", 0))
            importance = float(row.get("importance", 0.5))
            ts = float(row.get("timestamp", time.time()))
            recency = _recency_weight(ts)
            composite = round(
                cosine_relevance * (0.5 + 0.5 * importance) * (0.7 + 0.3 * recency), 4
            )
            scored.append({
                "id":              row["id"],
                "content":         row["content"],
                "metadata":        row.get("metadata", {}),
                "relevance":       round(cosine_relevance, 3),
                "importance":      round(importance, 3),
                "recency_weight":  round(recency, 3),
                "composite_score": composite,
            })

        scored.sort(key=lambda x: x["composite_score"], reverse=True)
        return scored[:n_results]

    def list_all(self, limit: int = 50) -> list[dict]:
        """Return up to `limit` memories sorted by timestamp descending."""
        if not self._enabled:
            return []
        try:
            resp = self._sb.table("memory_embeddings").select(
                "id, content, metadata, timestamp, importance"
            ).order("timestamp", desc=True).limit(limit).execute()
            return [
                {"id": r["id"], "content": r["content"], "metadata": r.get("metadata", {})}
                for r in (resp.data or [])
            ]
        except Exception as e:
            log.warning("memory_list_failed", error=str(e))
            return []

    # ── Maintenance ────────────────────────────────────────────────────── #

    def delete(self, memory_id: str) -> None:
        if not self._enabled:
            return
        try:
            self._sb.table("memory_embeddings").delete().eq("id", memory_id).execute()
            log.info("memory_deleted", id=memory_id)
        except Exception as e:
            log.warning("memory_delete_failed", error=str(e))

    def prune_old(self, max_age_days: float = 90.0) -> int:
        """Delete memories older than `max_age_days`. Returns count deleted."""
        if not self._enabled:
            return 0
        cutoff = time.time() - max_age_days * 86400
        try:
            resp = self._sb.table("memory_embeddings").select("id").lt(
                "timestamp", cutoff
            ).execute()
            ids = [r["id"] for r in (resp.data or [])]
            if ids:
                self._sb.table("memory_embeddings").delete().in_("id", ids).execute()
                log.info("memory_pruned", count=len(ids))
            return len(ids)
        except Exception as e:
            log.warning("memory_prune_failed", error=str(e))
            return 0

    def consolidate(self, similarity_threshold: float = 0.95) -> int:
        """Near-duplicate removal — handled at query time via similarity threshold.

        Returns 0 (no-op). Deduplication can be added as a scheduled Postgres
        function if needed in future.
        """
        return 0

    def count(self) -> int:
        if not self._enabled:
            return 0
        try:
            resp = self._sb.table("memory_embeddings").select(
                "id", count="exact"
            ).execute()
            return resp.count or 0
        except Exception as e:
            log.warning("memory_count_failed", error=str(e))
            return 0

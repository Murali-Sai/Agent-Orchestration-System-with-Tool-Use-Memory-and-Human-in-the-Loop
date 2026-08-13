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
import json
import math
import time
import uuid
from typing import Any
import structlog

log = structlog.get_logger()

_DECAY_HALF_LIFE_DAYS = 30.0
_EMBED_MODEL = "text-embedding-3-small"
_EMBED_DIM = 1536


_MAX_FREQUENCY_BOOST = 0.3


def _recency_weight(timestamp: float) -> float:
    """Exponential decay: 1.0 at creation, 0.5 after 30 days."""
    age_days = (time.time() - timestamp) / 86400.0
    return math.exp(-math.log(2) * age_days / _DECAY_HALF_LIFE_DAYS)


def _frequency_boost(access_count: int) -> float:
    """Importance bonus for often-retrieved memories.

    Log-scaled and capped so the 50th access doesn't count for much more than
    the 5th — otherwise a single popular memory would crowd out everything else.
    """
    if access_count <= 0:
        return 0.0
    return min(_MAX_FREQUENCY_BOOST, math.log1p(access_count) * 0.08)


def _as_float(raw: Any, default: float) -> float:
    """Coerce a stored numeric to float, falling back only when it is missing.

    Deliberately not `float(raw or default)`: 0.0 is falsy, and a stored
    importance of 0.0 is a real value, not an absent one.
    """
    if raw is None:
        return default
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


def _parse_embedding(raw: Any) -> list[float] | None:
    """Normalise an embedding column into a Python list of floats.

    PostgREST serialises pgvector as a JSON *string* (`"[0.1,0.2,...]"`) rather
    than an array, so rows fetched via the table API need decoding before any
    numeric work.
    """
    if raw is None:
        return None
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (ValueError, TypeError):
            return None
    try:
        return [float(x) for x in raw]
    except (TypeError, ValueError):
        return None


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

    def __init__(self):
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
                "ts":         now,
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

        Composite score = cosine_relevance × importance_weight × recency_weight,
        where importance is the stored score plus a boost for how often the
        memory has actually been retrieved. Frequently-surfaced memories are
        empirically more useful than their write-time score suggests.

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
            base_importance = float(row.get("importance", 0.5))
            access_count = int(row.get("access_count") or 0)
            ts = float(row.get("ts", time.time()))
            recency = _recency_weight(ts)

            effective_importance = min(1.0, base_importance + _frequency_boost(access_count))

            composite = round(
                cosine_relevance * (0.5 + 0.5 * effective_importance) * (0.7 + 0.3 * recency), 4
            )
            scored.append({
                "id":              row["id"],
                "content":         row["content"],
                "metadata":        row.get("metadata", {}),
                "relevance":       round(cosine_relevance, 3),
                "importance":      round(effective_importance, 3),
                "base_importance": round(base_importance, 3),
                "access_count":    access_count,
                "recency_weight":  round(recency, 3),
                "composite_score": composite,
            })

        scored.sort(key=lambda x: x["composite_score"], reverse=True)
        top = scored[:n_results]

        # Only count memories that were actually handed to an agent, not every
        # candidate the vector search considered. Failures here must not break
        # retrieval, so they're swallowed per-row.
        for m in top:
            try:
                self._sb.rpc("increment_access", {"mem_id": m["id"]}).execute()
            except Exception as e:
                log.debug("memory_access_increment_failed", id=m["id"], error=str(e))

        return top

    def list_all(self, limit: int = 50) -> list[dict]:
        """Return up to `limit` memories sorted by timestamp descending."""
        if not self._enabled:
            return []
        try:
            resp = self._sb.table("memory_embeddings").select(
                "id, content, metadata, ts, importance, access_count"
            ).order("ts", desc=True).limit(limit).execute()
            return [
                {
                    "id":           r["id"],
                    "content":      r["content"],
                    "metadata":     r.get("metadata", {}),
                    # `x or default` would rewrite a legitimately-stored 0.0 as
                    # the default, hiding low-importance memories behind a
                    # plausible-looking 0.5. Only None should fall back.
                    "importance":   round(_as_float(r.get("importance"), 0.5), 3),
                    "access_count": int(r.get("access_count") or 0),
                }
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
                "ts", cutoff
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
        """Merge near-duplicate memories. Returns the number deleted.

        For each cluster of memories with cosine similarity >= the threshold,
        the highest-importance member survives (tie-break: most recent) and the
        rest are deleted. The survivor gets a small importance bump for having
        been independently corroborated.

        This is O(n²) in Python — fine for the hundreds of memories a demo
        accumulates. At real scale you'd push it into Postgres as a self-join
        over an ivfflat/HNSW index instead of pulling every vector into memory.
        """
        if not self._enabled:
            return 0

        try:
            resp = self._sb.table("memory_embeddings").select(
                "id, content, embedding, metadata, ts, importance"
            ).execute()
            rows = resp.data or []
        except Exception as e:
            log.warning("consolidate_fetch_failed", error=str(e))
            return 0

        # Rows whose embedding won't parse can't be compared — drop them from
        # consideration rather than crashing the whole pass.
        parsed: list[tuple[dict, list[float]]] = []
        for r in rows:
            vec = _parse_embedding(r.get("embedding"))
            if vec is not None:
                parsed.append((r, vec))

        if len(parsed) < 2:
            return 0

        try:
            import numpy as np
        except ImportError:
            log.warning("consolidate_unavailable", reason="numpy not installed")
            return 0

        entries = [r for r, _ in parsed]
        vecs = np.array([v for _, v in parsed], dtype=float)
        norms = np.linalg.norm(vecs, axis=1, keepdims=True)
        norms[norms == 0] = 1.0          # guard against a zero vector
        unit = vecs / norms
        sim = unit @ unit.T

        merged: set[str] = set()
        removed = 0

        for i, entry in enumerate(entries):
            if entry["id"] in merged:
                continue
            dupes = [
                j for j in range(i + 1, len(entries))
                if entries[j]["id"] not in merged and sim[i, j] >= similarity_threshold
            ]
            if not dupes:
                continue

            group = [i] + dupes
            keeper_idx = max(
                group,
                key=lambda k: (
                    _as_float(entries[k].get("importance"), 0.0),
                    _as_float(entries[k].get("ts"), 0.0),
                ),
            )
            keeper = entries[keeper_idx]
            loser_ids = [entries[k]["id"] for k in group if k != keeper_idx]

            new_importance = min(
                1.0, _as_float(keeper.get("importance"), 0.5) + 0.05 * len(loser_ids)
            )
            try:
                self._sb.table("memory_embeddings").update(
                    {"importance": new_importance}
                ).eq("id", keeper["id"]).execute()
                self._sb.table("memory_embeddings").delete().in_("id", loser_ids).execute()
            except Exception as e:
                log.warning("consolidate_merge_failed", keeper=keeper["id"], error=str(e))
                continue

            merged.update(loser_ids)
            removed += len(loser_ids)

        log.info("memories_consolidated", removed=removed, scanned=len(entries))
        return removed

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

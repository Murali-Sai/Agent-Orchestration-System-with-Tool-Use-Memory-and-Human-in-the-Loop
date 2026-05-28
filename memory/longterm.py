"""Long-term semantic memory backed by ChromaDB."""
from __future__ import annotations
import time
import uuid
from typing import Any, Optional
import structlog

log = structlog.get_logger()


class LongTermMemory:
    def __init__(self, persist_dir: str = "./chroma_db", collection: str = "agent_memory"):
        import chromadb
        self._client = chromadb.PersistentClient(path=persist_dir)
        self._col = self._client.get_or_create_collection(
            name=collection,
            metadata={"hnsw:space": "cosine"},
        )

    def save(self, content: str, metadata: dict[str, Any] | None = None) -> str:
        """Embed and store a memory string. Returns the memory ID."""
        mem_id = str(uuid.uuid4())
        meta = {"timestamp": time.time(), **(metadata or {})}
        # Truncate metadata values to strings (ChromaDB requirement)
        safe_meta = {k: str(v)[:512] for k, v in meta.items()}
        self._col.add(documents=[content], metadatas=[safe_meta], ids=[mem_id])
        log.info("memory_saved", id=mem_id, preview=content[:80])
        return mem_id

    def query(self, query: str, n_results: int = 5, where: dict | None = None) -> list[dict]:
        """Retrieve the most semantically similar memories."""
        kwargs: dict[str, Any] = {"query_texts": [query], "n_results": min(n_results, self._col.count() or 1)}
        if where:
            kwargs["where"] = where
        try:
            results = self._col.query(**kwargs)
        except Exception as e:
            log.warning("memory_query_failed", error=str(e))
            return []

        memories = []
        docs = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]
        for doc, meta, dist in zip(docs, metas, distances):
            memories.append({"content": doc, "metadata": meta, "relevance": round(1 - dist, 3)})
        return memories

    def delete(self, memory_id: str) -> None:
        self._col.delete(ids=[memory_id])

    def count(self) -> int:
        return self._col.count()

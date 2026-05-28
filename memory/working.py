"""Short-term working memory scoped to a single task execution."""
from __future__ import annotations
import json
import time
from typing import Any, Optional

try:
    import redis
    _REDIS_AVAILABLE = True
except ImportError:
    _REDIS_AVAILABLE = False


class WorkingMemory:
    """
    Redis-backed working memory with in-process dict fallback.
    All data is scoped to a task_id and expires automatically.
    """

    def __init__(self, task_id: str, redis_url: str = "redis://localhost:6379/0", ttl: int = 3600):
        self.task_id = task_id
        self.ttl = ttl
        self._prefix = f"task:{task_id}:"
        self._client: Optional[Any] = None
        self._local: dict = {}

        if _REDIS_AVAILABLE:
            try:
                self._client = redis.from_url(redis_url, decode_responses=True, socket_connect_timeout=2)
                self._client.ping()
            except Exception:
                self._client = None

    def _key(self, field: str) -> str:
        return f"{self._prefix}{field}"

    def set(self, field: str, value: Any) -> None:
        serialized = json.dumps(value)
        if self._client:
            self._client.setex(self._key(field), self.ttl, serialized)
        else:
            self._local[field] = serialized

    def get(self, field: str, default: Any = None) -> Any:
        if self._client:
            raw = self._client.get(self._key(field))
        else:
            raw = self._local.get(field)
        if raw is None:
            return default
        return json.loads(raw)

    def append(self, field: str, item: Any) -> None:
        existing = self.get(field, [])
        existing.append(item)
        self.set(field, existing)

    def get_all(self) -> dict:
        if self._client:
            keys = self._client.keys(f"{self._prefix}*")
            return {
                k.replace(self._prefix, ""): json.loads(self._client.get(k) or "null")
                for k in keys
            }
        return {k: json.loads(v) for k, v in self._local.items()}

    def clear(self) -> None:
        if self._client:
            for key in self._client.keys(f"{self._prefix}*"):
                self._client.delete(key)
        else:
            self._local.clear()

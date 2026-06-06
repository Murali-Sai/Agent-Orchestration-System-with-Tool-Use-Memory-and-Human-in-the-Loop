"""Approval queue for human-in-the-loop review items."""
from __future__ import annotations
import json
import time
import uuid
from typing import Any, Optional

try:
    import redis as redis_lib
    _REDIS_OK = True
except ImportError:
    _REDIS_OK = False

_QUEUE_KEY = "hitl:queue"
_RESOLVED_KEY = "hitl:resolved"
_CHAT_PREFIX = "hitl:chat:"

# In-memory fallback for chat messages when Redis is unavailable
_local_chats: dict[str, list[dict]] = {}


class ApprovalQueue:
    def __init__(self, redis_url: str = "redis://localhost:6379/0"):
        self._client = None
        self._local_queue: list[dict] = []
        self._local_resolved: list[dict] = []

        if _REDIS_OK:
            try:
                c = redis_lib.from_url(redis_url, decode_responses=True, socket_connect_timeout=2)
                c.ping()
                self._client = c
            except Exception:
                pass

    def push(self, task_id: str, task_request: str, escalation: dict) -> str:
        item_id = str(uuid.uuid4())[:12]
        item = {
            "id": item_id,
            "task_id": task_id,
            "task_request": task_request,
            "escalation": escalation,
            "created_at": time.time(),
            "status": "pending",
        }
        serialized = json.dumps(item)
        if self._client:
            self._client.lpush(_QUEUE_KEY, serialized)
        else:
            self._local_queue.append(item)
        return item_id

    def list_pending(self) -> list[dict]:
        if self._client:
            raw = self._client.lrange(_QUEUE_KEY, 0, -1)
            return [json.loads(r) for r in raw]
        return list(self._local_queue)

    def resolve(self, item_id: str, approved: bool, response: str = "", modified_output: str = "") -> bool:
        if self._client:
            items = self._client.lrange(_QUEUE_KEY, 0, -1)
            for raw in items:
                item = json.loads(raw)
                if item["id"] == item_id:
                    item["status"] = "approved" if approved else "rejected"
                    item["human_response"] = response
                    item["modified_output"] = modified_output
                    item["resolved_at"] = time.time()
                    # Remove from pending, add to resolved
                    self._client.lrem(_QUEUE_KEY, 1, raw)
                    self._client.lpush(_RESOLVED_KEY, json.dumps(item))
                    return True
            return False
        else:
            for item in self._local_queue:
                if item["id"] == item_id:
                    item["status"] = "approved" if approved else "rejected"
                    item["human_response"] = response
                    item["modified_output"] = modified_output
                    item["resolved_at"] = time.time()
                    self._local_queue.remove(item)
                    self._local_resolved.append(item)
                    return True
            return False

    def add_message(self, item_id: str, role: str, message: str) -> bool:
        """Append a chat message to a HITL item. Returns False if item not found."""
        msg = {"role": role, "message": message, "ts": time.time()}
        chat_key = f"{_CHAT_PREFIX}{item_id}"

        if self._client:
            # Verify item exists
            raw_items = self._client.lrange(_QUEUE_KEY, 0, -1)
            if not any(json.loads(r)["id"] == item_id for r in raw_items):
                return False
            self._client.rpush(chat_key, json.dumps(msg))
            self._client.expire(chat_key, 86400 * 7)  # 7-day TTL
            return True
        else:
            # In-memory fallback — accept any item_id
            if item_id not in _local_chats:
                _local_chats[item_id] = []
            _local_chats[item_id].append(msg)
            return True

    def get_messages(self, item_id: str) -> list[dict]:
        """Retrieve the full chat thread for a HITL item."""
        chat_key = f"{_CHAT_PREFIX}{item_id}"
        if self._client:
            raw = self._client.lrange(chat_key, 0, -1)
            return [json.loads(r) for r in raw]
        return _local_chats.get(item_id, [])

    def get_resolved(self, limit: int = 50) -> list[dict]:
        if self._client:
            raw = self._client.lrange(_RESOLVED_KEY, 0, limit - 1)
            return [json.loads(r) for r in raw]
        return self._local_resolved[-limit:]


_queue: Optional[ApprovalQueue] = None


def get_queue(redis_url: str = "redis://localhost:6379/0") -> ApprovalQueue:
    global _queue
    if _queue is None:
        _queue = ApprovalQueue(redis_url)
    return _queue

from __future__ import annotations
import time
import uuid
from typing import Any, Optional
from openai import OpenAI
from config.settings import get_settings

settings = get_settings()
_client: Optional[OpenAI] = None


def get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=settings.openai_api_key)
    return _client


def llm_call(
    system: str,
    messages: list[dict],
    model: str | None = None,
    max_tokens: int = 4096,
    temperature: float = 0.3,
) -> tuple[str, int]:
    """Call OpenAI and return (content, total_tokens)."""
    model = model or settings.primary_model
    client = get_client()
    full_messages = [{"role": "system", "content": system}] + messages
    resp = client.chat.completions.create(
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        messages=full_messages,
    )
    content = resp.choices[0].message.content
    tokens = resp.usage.prompt_tokens + resp.usage.completion_tokens
    return content, tokens


def trace_event(state: dict, agent: str, action: str, detail: Any = None) -> None:
    state["trace"].append({
        "id": str(uuid.uuid4())[:8],
        "ts": time.time(),
        "agent": agent,
        "action": action,
        "detail": detail,
    })

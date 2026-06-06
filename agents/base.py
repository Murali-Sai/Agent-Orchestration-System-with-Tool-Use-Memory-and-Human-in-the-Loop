"""LLM routing: OpenAI + Anthropic with model selection and cost tracking."""
from __future__ import annotations
import time
import uuid
from typing import Any, Optional
from openai import OpenAI
from config.settings import get_settings

settings = get_settings()

# ── Cost constants (USD per 1 000 tokens, blended input+output estimate) ──
MODEL_COST_PER_1K: dict[str, float] = {
    "gpt-4o":                    0.0100,   # ~$10/1M avg
    "gpt-4o-mini":               0.000375, # ~$0.375/1M avg
    "claude-3-haiku-20240307":   0.000750, # ~$0.75/1M avg
    "claude-3-5-haiku-20241022": 0.001000, # ~$1/1M avg
}

_openai_client: Optional[OpenAI] = None


def get_client() -> OpenAI:
    global _openai_client
    if _openai_client is None:
        _openai_client = OpenAI(api_key=settings.openai_api_key)
    return _openai_client


def _get_anthropic():
    """Lazy-import Anthropic client (only when Anthropic key is present)."""
    if not settings.anthropic_api_key:
        return None
    try:
        from anthropic import Anthropic
        return Anthropic(api_key=settings.anthropic_api_key)
    except ImportError:
        return None


def route_model(specialist: str | None = None, complexity: str | None = None) -> str:
    """Pick the best model based on specialist role and task complexity.

    Routing logic:
    - writing specialist  → Claude Haiku  (demonstrate Anthropic integration)
    - reviewer            → GPT-4o-mini   (fast, structured JSON scoring)
    - low complexity      → GPT-4o-mini   (cost-efficient)
    - everything else     → GPT-4o        (planning, analysis, code, synthesis)
    """
    if specialist == "writing" and settings.anthropic_api_key:
        return "claude-3-haiku-20240307"
    if specialist == "reviewer":
        return settings.fast_model
    if complexity == "low":
        return settings.fast_model
    return settings.primary_model


def token_cost_usd(model: str, tokens: int) -> float:
    """Estimate cost in USD for the given model and token count."""
    rate = MODEL_COST_PER_1K.get(model, MODEL_COST_PER_1K.get("gpt-4o", 0.010))
    return round(tokens * rate / 1000, 6)


def llm_call(
    system: str,
    messages: list[dict],
    model: str | None = None,
    max_tokens: int = 4096,
    temperature: float = 0.3,
) -> tuple[str, int]:
    """Route to OpenAI or Anthropic based on model name. Returns (content, tokens)."""
    model = model or settings.primary_model

    if model.startswith("claude-"):
        client = _get_anthropic()
        if client is None:
            # Anthropic unavailable — fall back gracefully
            model = settings.fast_model
        else:
            resp = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system,
                messages=messages,
            )
            content = resp.content[0].text
            tokens = resp.usage.input_tokens + resp.usage.output_tokens
            return content, tokens

    # ── OpenAI path ──
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

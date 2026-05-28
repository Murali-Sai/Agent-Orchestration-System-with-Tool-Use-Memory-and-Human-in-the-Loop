from __future__ import annotations
import os
from typing import Any


def web_search(query: str, max_results: int = 5) -> list[dict[str, Any]]:
    """Search the web. Uses Tavily if key present, else DuckDuckGo."""
    tavily_key = os.getenv("TAVILY_API_KEY", "")
    if tavily_key:
        return _tavily_search(query, max_results, tavily_key)
    return _ddg_search(query, max_results)


def _tavily_search(query: str, max_results: int, api_key: str) -> list[dict]:
    from tavily import TavilyClient
    client = TavilyClient(api_key=api_key)
    resp = client.search(query=query, max_results=max_results)
    return [
        {"title": r.get("title", ""), "url": r.get("url", ""), "content": r.get("content", "")}
        for r in resp.get("results", [])
    ]


def _ddg_search(query: str, max_results: int) -> list[dict]:
    from duckduckgo_search import DDGS
    with DDGS() as ddgs:
        results = list(ddgs.text(query, max_results=max_results))
    return [
        {"title": r.get("title", ""), "url": r.get("href", ""), "content": r.get("body", "")}
        for r in results
    ]

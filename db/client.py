"""Supabase client — singleton with graceful fallback when credentials are absent."""
from __future__ import annotations
from typing import Optional
import structlog

log = structlog.get_logger()

_client = None
_enabled: Optional[bool] = None


def get_supabase():
    """Return the Supabase client, or None if not configured."""
    global _client, _enabled
    if _enabled is not None:
        return _client

    from config.settings import get_settings
    s = get_settings()

    if not s.supabase_url or not s.supabase_anon_key:
        log.warning("supabase_disabled", reason="SUPABASE_URL or SUPABASE_ANON_KEY not set — using local fallbacks")
        _enabled = False
        return None

    try:
        from supabase import create_client
        _client = create_client(s.supabase_url, s.supabase_anon_key)
        _enabled = True
        log.info("supabase_connected", url=s.supabase_url)
    except Exception as e:
        log.error("supabase_init_failed", error=str(e))
        _enabled = False

    return _client


def is_enabled() -> bool:
    get_supabase()
    return bool(_enabled)

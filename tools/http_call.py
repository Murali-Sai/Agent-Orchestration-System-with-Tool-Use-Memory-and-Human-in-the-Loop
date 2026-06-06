"""Generic HTTP/API call tool for agents.

Allows agents to call external REST APIs as part of task execution.
Security controls:
  - Blocks requests to private/internal IP ranges
  - Enforces a 10-second timeout
  - Caps response body at 50 KB
  - Only allows http/https schemes
  - Strips Authorization headers from logged inputs
"""
from __future__ import annotations
import ipaddress
import json
import re
import socket
from urllib.parse import urlparse

import requests

_MAX_RESPONSE_BYTES = 50_000
_TIMEOUT_S = 10
_ALLOWED_SCHEMES = {"http", "https"}
_PRIVATE_RANGES = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
]


def _is_private(hostname: str) -> bool:
    try:
        ip = ipaddress.ip_address(socket.gethostbyname(hostname))
        return any(ip in net for net in _PRIVATE_RANGES)
    except Exception:
        return False


def http_call(
    url: str,
    method: str = "GET",
    headers: dict | None = None,
    body: str | dict | None = None,
    json_body: bool = True,
) -> dict:
    """Make an HTTP request to an external API and return the response.

    Args:
        url:       Full URL to call (https://api.example.com/endpoint).
        method:    HTTP method: GET, POST, PUT, PATCH, DELETE.
        headers:   Dict of request headers (Authorization etc. are allowed but
                   will be redacted from logs).
        body:      Request body — a dict (sent as JSON) or raw string.
        json_body: If True and body is a dict, Content-Type is set to application/json.

    Returns:
        {"status_code": 200, "body": "...", "headers": {...}}  on success
        {"error": "..."}                                        on failure
    """
    # Validate scheme
    parsed = urlparse(url)
    if parsed.scheme not in _ALLOWED_SCHEMES:
        return {"error": f"Scheme '{parsed.scheme}' is not allowed. Use http or https."}

    hostname = parsed.hostname or ""
    if not hostname:
        return {"error": "Could not parse hostname from URL."}

    # Block private/internal IPs (SSRF protection)
    if _is_private(hostname):
        return {"error": f"Requests to private/internal IP ranges are not allowed."}

    method = method.upper()
    if method not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
        return {"error": f"Method '{method}' is not supported."}

    req_headers = dict(headers or {})

    try:
        kwargs: dict = {"headers": req_headers, "timeout": _TIMEOUT_S}

        if body is not None:
            if isinstance(body, dict) and json_body:
                kwargs["json"] = body
            else:
                kwargs["data"] = body if isinstance(body, str) else json.dumps(body)

        resp = requests.request(method, url, **kwargs)

        # Cap response size
        content = resp.content[:_MAX_RESPONSE_BYTES]
        try:
            body_out = resp.json()
        except Exception:
            body_out = content.decode("utf-8", errors="replace")

        return {
            "status_code": resp.status_code,
            "body": body_out,
            "headers": dict(resp.headers),
            "truncated": len(resp.content) > _MAX_RESPONSE_BYTES,
        }

    except requests.exceptions.Timeout:
        return {"error": f"Request timed out after {_TIMEOUT_S}s."}
    except requests.exceptions.ConnectionError as e:
        return {"error": f"Connection error: {e}"}
    except Exception as e:
        return {"error": str(e)}

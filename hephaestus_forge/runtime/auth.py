"""Bridge authentication scaffolding (Python-side).

The UE plugin will enforce the same shared token on mutation endpoints once
compiled (Phase 4). Until then, the Python client sends ``X-Hephaestus-Token``
when configured so wiring can be tested without the engine.
"""

from __future__ import annotations

from typing import Optional

from .config import AUTH_HEADER


def validate_bridge_token(
    *,
    require_auth: bool,
    expected: Optional[str],
    provided: Optional[str],
) -> bool:
    """Return True when the request should be accepted."""
    if not require_auth:
        return True
    if not expected:
        return False
    return provided == expected


def extract_token_from_headers(headers: dict) -> Optional[str]:
    """Read the bridge token from a WSGI/ASGI-style header mapping."""
    for key in (AUTH_HEADER, AUTH_HEADER.lower(), "HTTP_" + AUTH_HEADER.upper().replace("-", "_")):
        value = headers.get(key)
        if value:
            return str(value)
    return None

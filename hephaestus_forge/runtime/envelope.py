"""Validate command envelopes against the packaged JSON schema."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Tuple

_SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schemas" / "command_envelope.json"


def load_command_envelope_schema() -> Dict[str, Any]:
    data: Dict[str, Any] = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    return data


def validate_command_envelope(envelope: Dict[str, Any]) -> Tuple[bool, str]:
    """Lightweight structural validation (no jsonschema dependency required)."""
    if not isinstance(envelope, dict):
        return False, "envelope must be an object"
    command = envelope.get("command")
    if not command or not isinstance(command, str):
        return False, "missing string 'command'"
    params = envelope.get("params")
    if not isinstance(params, dict):
        return False, "missing object 'params'"
    if set(envelope.keys()) - {"command", "params"}:
        return False, "unexpected envelope fields"
    return True, ""

"""Command argument validation before hitting the UE bridge."""

from __future__ import annotations

import re

from .errors import ToolError

ALLOWED_SPAWN_PREFIXES = ("/Script/", "/Game/", "/Engine/")
MAX_STRING_LEN = 4096


def validate_spawn_class_path(class_path: object) -> str:
    if not class_path or not isinstance(class_path, str):
        raise ToolError("world.spawn_actor requires a string 'class_path'")
    if len(class_path) > MAX_STRING_LEN:
        raise ToolError("class_path too long", code="VALIDATION_TOO_LONG")
    if not any(class_path.startswith(prefix) for prefix in ALLOWED_SPAWN_PREFIXES):
        raise ToolError(
            f"class_path must start with one of {ALLOWED_SPAWN_PREFIXES}",
            code="VALIDATION_SPAWN_CLASS_DENIED",
        )
    if re.search(r"[;\0]", class_path):
        raise ToolError("class_path contains illegal characters", code="VALIDATION_INVALID_CHARS")
    return class_path


def validate_required_string(value: object, field: str, tool_name: str) -> str:
    if not value or not isinstance(value, str):
        raise ToolError(f"{tool_name} requires a string '{field}'", code="VALIDATION_MISSING_FIELD")
    if len(value) > MAX_STRING_LEN:
        raise ToolError(f"{field} too long", code="VALIDATION_TOO_LONG")
    return value

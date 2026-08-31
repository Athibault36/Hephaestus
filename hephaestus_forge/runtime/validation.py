"""Command argument validation before hitting the UE bridge."""

from __future__ import annotations

import re
from typing import List

from .errors import ToolError

ALLOWED_SPAWN_PREFIXES = ("/Script/", "/Game/", "/Engine/")
ALLOWED_UNREAL_PATH_PREFIXES = ("/Game/", "/Engine/", "/Script/")
MAX_STRING_LEN = 4096


def validate_required_string(value: object, field: str, tool_name: str) -> str:
    if not value or not isinstance(value, str):
        raise ToolError(f"{tool_name} requires a string '{field}'", code="VALIDATION_MISSING_FIELD")
    if len(value) > MAX_STRING_LEN:
        raise ToolError(f"{field} too long", code="VALIDATION_TOO_LONG")
    return value


def validate_spawn_class_path(class_path: object) -> str:
    value = validate_required_string(class_path, "class_path", "world.spawn_actor")
    if not any(value.startswith(prefix) for prefix in ALLOWED_SPAWN_PREFIXES):
        raise ToolError(
            f"class_path must start with one of {ALLOWED_SPAWN_PREFIXES}",
            code="VALIDATION_SPAWN_CLASS_DENIED",
        )
    if re.search(r"[;\0]", value):
        raise ToolError("class_path contains illegal characters", code="VALIDATION_INVALID_CHARS")
    return value


def validate_actor_path(value: object, *, tool_name: str = "world.destroy_actor") -> str:
    path = validate_required_string(value, "actor_path", tool_name)
    _reject_unsafe_path(path, "actor_path")
    return path


def validate_unreal_asset_path(value: object, field: str, tool_name: str) -> str:
    path = validate_required_string(value, field, tool_name)
    if not any(path.startswith(prefix) for prefix in ALLOWED_UNREAL_PATH_PREFIXES):
        raise ToolError(
            f"{field} must start with one of {ALLOWED_UNREAL_PATH_PREFIXES}",
            code="VALIDATION_PATH_DENIED",
        )
    _reject_unsafe_path(path, field)
    return path


def validate_actor_path_list(values: object, *, tool_name: str = "world.batch_edit") -> List[str]:
    if not isinstance(values, list) or not values:
        raise ToolError(f"{tool_name} requires a non-empty 'actors' list", code="VALIDATION_MISSING_FIELD")
    return [validate_actor_path(item, tool_name=tool_name) for item in values]


def _reject_unsafe_path(path: str, field: str) -> None:
    if ".." in path or "\\" in path or "\0" in path or ";" in path:
        raise ToolError(f"{field} contains illegal path segments", code="VALIDATION_INVALID_PATH")

# Copyright (c) 2024 HephaestusForge. All Rights Reserved.
"""
Pure-Python validation of Hephaestus Remote API command JSON shapes.

Mirrors the UE CommandHandler contract so clients/tests catch params/args
and transform mistakes without launching Unreal.
"""

from __future__ import annotations

from typing import Any, Optional


def resolve_params(command_obj: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Prefer params; fall back to args. Missing → None (not {})."""
    if not isinstance(command_obj, dict):
        return None
    params = command_obj.get("params")
    if isinstance(params, dict):
        return params
    args = command_obj.get("args")
    if isinstance(args, dict):
        return args
    return None


def _as_xyz(value: Any) -> Optional[tuple[float, float, float]]:
    if isinstance(value, dict) and all(k in value for k in ("x", "y", "z")):
        return float(value["x"]), float(value["y"]), float(value["z"])
    if isinstance(value, (list, tuple)) and len(value) >= 3:
        return float(value[0]), float(value[1]), float(value[2])
    return None


def parse_location(params: dict[str, Any]) -> Optional[tuple[float, float, float]]:
    """Read location from nested transform and/or flat location field."""
    if not isinstance(params, dict):
        return None
    loc = None
    transform = params.get("transform")
    if isinstance(transform, dict) and "location" in transform:
        loc = _as_xyz(transform["location"])
    flat = _as_xyz(params.get("location")) if "location" in params else None
    return flat if flat is not None else loc


def parse_scale(params: dict[str, Any]) -> tuple[float, float, float]:
    if not isinstance(params, dict):
        return (1.0, 1.0, 1.0)
    transform = params.get("transform")
    scale = None
    if isinstance(transform, dict) and "scale" in transform:
        scale = _as_xyz(transform["scale"])
    if scale is None and "scale" in params:
        scale = _as_xyz(params["scale"])
    return scale if scale is not None else (1.0, 1.0, 1.0)


def validate_world_spawn_mesh(command_obj: dict[str, Any]) -> list[str]:
    """Return list of problems (empty = ok)."""
    errors: list[str] = []
    if command_obj.get("command") != "world.spawn_mesh":
        errors.append("command must be world.spawn_mesh")
    params = resolve_params(command_obj)
    if params is None:
        errors.append("missing params/args object")
        return errors
    mesh = params.get("mesh_path") or params.get("mesh")
    if not mesh:
        # Empty mesh is allowed (engine default cube) — not an error
        pass
    return errors


def validate_world_get_actor(command_obj: dict[str, Any]) -> list[str]:
    """Return list of problems (empty = ok). Requires a non-empty actor_path."""
    errors: list[str] = []
    if command_obj.get("command") != "world.get_actor":
        errors.append("command must be world.get_actor")
    params = resolve_params(command_obj)
    if params is None:
        errors.append("missing params/args object")
        return errors
    actor_path = params.get("actor_path") or params.get("actor")
    if not isinstance(actor_path, str) or not actor_path.strip():
        errors.append("actor_path must be a non-empty string")
    return errors


def assert_uses_params_key(command_obj: dict[str, Any]) -> None:
    """Client builders should emit params (args is only a server-side alias)."""
    assert "params" in command_obj, "payload must include params for Remote API clients"

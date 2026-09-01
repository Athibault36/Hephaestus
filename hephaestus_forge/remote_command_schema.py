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


def validate_world_get_actor(command_obj: dict[str, Any]) -> list[str]:
    """Return list of problems (empty = ok)."""
    errors: list[str] = []
    if command_obj.get("command") != "world.get_actor":
        errors.append("command must be world.get_actor")
    params = resolve_params(command_obj)
    if params is None:
        errors.append("missing params/args object")
        return errors
    path = params.get("actor_path") or params.get("actor")
    if not path:
        errors.append("missing actor_path")
    return errors


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


def assert_uses_params_key(command_obj: dict[str, Any]) -> None:
    """Client builders should emit params (args is only a server-side alias)."""
    assert "params" in command_obj, "payload must include params for Remote API clients"


def validate_world_apply_move_input(command_obj: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if command_obj.get("command") != "world.apply_move_input":
        errors.append("command must be world.apply_move_input")
    params = resolve_params(command_obj)
    if params is None:
        errors.append("missing params/args object")
    return errors


def validate_animation_play_montage(command_obj: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if command_obj.get("command") != "animation.play_montage":
        errors.append("command must be animation.play_montage")
    params = resolve_params(command_obj)
    if params is None:
        errors.append("missing params/args object")
        return errors
    if not params.get("actor_path"):
        errors.append("missing actor_path")
    if not params.get("montage_path"):
        errors.append("missing montage_path")
    return errors


def validate_animation_play_locomotion(command_obj: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if command_obj.get("command") != "animation.play_locomotion":
        errors.append("command must be animation.play_locomotion")
    params = resolve_params(command_obj)
    if params is None:
        errors.append("missing params/args object")
        return errors
    if not params.get("actor_path"):
        errors.append("missing actor_path")
    return errors


def validate_sequence_play(command_obj: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if command_obj.get("command") != "sequence.play":
        errors.append("command must be sequence.play")
    params = resolve_params(command_obj)
    if params is None:
        errors.append("missing params/args object")
        return errors
    if not (params.get("sequence_path") or params.get("path")):
        errors.append("missing sequence_path")
    return errors


def validate_sequence_create_shot(command_obj: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if command_obj.get("command") != "sequence.create_shot":
        errors.append("command must be sequence.create_shot")
    params = resolve_params(command_obj)
    if params is None:
        errors.append("missing params/args object")
        return errors
    if parse_location(params) is None and not any(k in params for k in ("x", "y", "z")):
        errors.append("missing target location")
    return errors


def validate_asset_search(command_obj: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if command_obj.get("command") != "asset.search":
        errors.append("command must be asset.search")
    params = resolve_params(command_obj)
    if params is None:
        errors.append("missing params/args object")
        return errors
    query = params.get("query")
    if not query or not str(query).strip():
        errors.append("missing query")
    return errors


def validate_asset_create_material(command_obj: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if command_obj.get("command") != "asset.create_material":
        errors.append("command must be asset.create_material")
    params = resolve_params(command_obj)
    if params is None:
        errors.append("missing params/args object")
    return errors


def validate_asset_export(command_obj: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if command_obj.get("command") != "asset.export":
        errors.append("command must be asset.export")
    params = resolve_params(command_obj)
    if params is None:
        errors.append("missing params/args object")
        return errors
    if not params.get("asset_path"):
        errors.append("missing asset_path")
    return errors


def validate_asset_import(command_obj: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if command_obj.get("command") != "asset.import":
        errors.append("command must be asset.import")
    params = resolve_params(command_obj)
    if params is None:
        errors.append("missing params/args object")
        return errors
    if not params.get("file_path"):
        errors.append("missing file_path")
    if not params.get("destination_path"):
        errors.append("missing destination_path")
    return errors


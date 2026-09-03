# Copyright (c) 2024 HephaestusForge. All Rights Reserved.
"""
JSON command builders and Unreal-side execution helpers for HephaestusBridge.
"""

from __future__ import annotations

import json
from typing import Any, Mapping, Optional, Sequence, Tuple, Union

Vec3 = Union[Sequence[float], Mapping[str, float], None]


def _vec3(value: Vec3, default: Tuple[float, float, float]) -> dict[str, float]:
    if value is None:
        x, y, z = default
        return {"x": float(x), "y": float(y), "z": float(z)}
    if isinstance(value, Mapping):
        return {
            "x": float(value.get("x", default[0])),
            "y": float(value.get("y", default[1])),
            "z": float(value.get("z", default[2])),
        }
    seq = list(value)
    return {
        "x": float(seq[0] if len(seq) > 0 else default[0]),
        "y": float(seq[1] if len(seq) > 1 else default[1]),
        "z": float(seq[2] if len(seq) > 2 else default[2]),
    }


def _rotator(value: Vec3, default: Tuple[float, float, float] = (0.0, 0.0, 0.0)) -> dict[str, float]:
    if value is None:
        pitch, yaw, roll = default
        return {"pitch": float(pitch), "yaw": float(yaw), "roll": float(roll)}
    if isinstance(value, Mapping):
        return {
            "pitch": float(value.get("pitch", value.get("x", default[0]))),
            "yaw": float(value.get("yaw", value.get("y", default[1]))),
            "roll": float(value.get("roll", value.get("z", default[2]))),
        }
    seq = list(value)
    return {
        "pitch": float(seq[0] if len(seq) > 0 else default[0]),
        "yaw": float(seq[1] if len(seq) > 1 else default[1]),
        "roll": float(seq[2] if len(seq) > 2 else default[2]),
    }


def _transform(location: Vec3 = None, rotation: Vec3 = None, scale: Vec3 = None) -> dict[str, Any]:
    return {
        "location": _vec3(location, (0.0, 0.0, 0.0)),
        "rotation": _rotator(rotation),
        "scale": _vec3(scale, (1.0, 1.0, 1.0)),
    }


def build_spawn_actor_command(
    class_path: str = "/Script/Engine.PointLight",
    location: Vec3 = None,
    rotation: Vec3 = None,
    scale: Vec3 = None,
) -> dict[str, Any]:
    """Build a world.spawn_actor command dict for UHephaestusCommandHandler."""
    return {
        "command": "world.spawn_actor",
        "params": {
            "class_path": class_path,
            "transform": _transform(location, rotation, scale),
        },
    }


def build_spawn_mesh_command(
    mesh_path: str = "/Engine/BasicShapes/Cube.Cube",
    location: Vec3 = None,
    rotation: Vec3 = None,
    scale: Vec3 = None,
) -> dict[str, Any]:
    return {
        "command": "world.spawn_mesh",
        "params": {
            "mesh_path": mesh_path,
            "transform": _transform(location, rotation, scale),
        },
    }


def build_destroy_actor_command(actor_path: str) -> dict[str, Any]:
    return {
        "command": "world.destroy_actor",
        "params": {"actor_path": actor_path},
    }


def build_list_actors_command(class_path: str = "") -> dict[str, Any]:
    params: dict[str, Any] = {}
    if class_path:
        params["class_path"] = class_path
    return {"command": "world.list_actors", "params": params}


def build_capture_frame_command() -> dict[str, Any]:
    return {"command": "vision.capture_frame", "params": {}}


def build_apply_move_input_command(
    forward: float = 1.0,
    right: float = 0.0,
    duration: float = 2.0,
) -> dict[str, Any]:
    return {
        "command": "world.apply_move_input",
        "params": {"forward": float(forward), "right": float(right), "duration": float(duration)},
    }


def build_get_pawn_state_command() -> dict[str, Any]:
    return {"command": "world.get_pawn_state", "params": {}}


def build_play_montage_command(
    actor_path: str,
    montage_path: str,
    *,
    loop: bool = False,
) -> dict[str, Any]:
    return {
        "command": "animation.play_montage",
        "params": {
            "actor_path": actor_path,
            "montage_path": montage_path,
            "loop": bool(loop),
        },
    }


def build_asset_search_command(query: str, *, asset_class: str = "", limit: int = 12) -> dict[str, Any]:
    params: dict[str, Any] = {"query": query, "limit": int(limit)}
    if asset_class:
        params["class"] = asset_class
    return {"command": "asset.search", "params": params}


def build_spawn_skeletal_command(
    mesh_path: str = "",
    location: Vec3 = None,
    rotation: Vec3 = None,
    scale: Vec3 = None,
) -> dict[str, Any]:
    return {
        "command": "animation.spawn_skeletal_mesh",
        "params": {
            "mesh_path": mesh_path,
            "transform": _transform(location, rotation, scale),
        },
    }


def build_spawn_character_command(
    mesh_path: str = "",
    location: Vec3 = None,
    rotation: Vec3 = None,
    scale: Vec3 = None,
) -> dict[str, Any]:
    return {
        "command": "animation.spawn_character",
        "params": {
            "mesh_path": mesh_path,
            "transform": _transform(location, rotation, scale),
        },
    }


def build_play_locomotion_command(
    actor_path: str,
    mode: str = "idle",
    *,
    loop: bool = True,
) -> dict[str, Any]:
    return {
        "command": "animation.play_locomotion",
        "params": {"actor_path": actor_path, "mode": mode, "loop": bool(loop)},
    }


def build_play_sequence_command(
    actor_path: str,
    anim_path: str,
    *,
    loop: bool = False,
) -> dict[str, Any]:
    return {
        "command": "animation.play_sequence",
        "params": {
            "actor_path": actor_path,
            "anim_path": anim_path,
            "loop": bool(loop),
        },
    }


def build_get_actor_command(actor_path: str) -> dict[str, Any]:
    return {"command": "world.get_actor", "params": {"actor_path": actor_path}}


def build_get_view_command() -> dict[str, Any]:
    return {"command": "world.get_view", "params": {}}


def build_set_view_command(
    location: Vec3 = None,
    rotation: Vec3 = None,
    *,
    mode: str = "free",
    look_at_actor: str = "",
    distance: float = 0.0,
    yaw_offset: float = 90.0,
    height: float = 120.0,
) -> dict[str, Any]:
    """Position PIE camera. Default mode=free uses Hephaestus CameraActor (does not move pawn)."""
    params: dict[str, Any] = {
        "mode": mode or "free",
        "transform": {
            "location": _vec3(location, (0.0, 0.0, 200.0)),
            "rotation": _rotator(rotation),
        },
    }
    if look_at_actor:
        params["look_at_actor"] = look_at_actor
    if distance and distance > 1.0:
        params["distance"] = float(distance)
        params["yaw_offset"] = float(yaw_offset)
        params["height"] = float(height)
    elif look_at_actor:
        params["distance"] = 450.0
        params["yaw_offset"] = float(yaw_offset)
        params["height"] = float(height)
    return {"command": "world.set_view", "params": params}


def build_stop_animation_command(actor_path: str) -> dict[str, Any]:
    return {"command": "animation.stop", "params": {"actor_path": actor_path}}


def build_sequence_play_command(sequence_path: str, *, loop: bool = False) -> dict[str, Any]:
    return {
        "command": "sequence.play",
        "params": {"sequence_path": sequence_path, "loop": bool(loop)},
    }


def build_sequence_create_shot_command(
    location: Vec3 = None,
    rotation: Vec3 = None,
    *,
    duration: float = 4.0,
    actor_path: str = "",
    actor_target: Vec3 = None,
    look_at_actor: str = "",
    mode: str = "free",
    distance: float = 0.0,
    yaw_offset: float = 90.0,
    height: float = 120.0,
) -> dict[str, Any]:
    params: dict[str, Any] = {
        "location": _vec3(location, (0.0, 0.0, 200.0)),
        "rotation": _rotator(rotation),
        "duration": float(duration),
        "mode": mode or "free",
    }
    if look_at_actor:
        params["look_at_actor"] = look_at_actor
    if distance and distance > 1.0:
        params["distance"] = float(distance)
        params["yaw_offset"] = float(yaw_offset)
        params["height"] = float(height)
    if actor_path:
        params["actor_path"] = actor_path
        params["target_location"] = _vec3(actor_target, params["location"])
    return {"command": "sequence.create_shot", "params": params}


def build_sequence_stop_command() -> dict[str, Any]:
    return {"command": "sequence.stop", "params": {}}


def build_create_material_command(
    name: str = "HephaestusMaterial",
    *,
    base_material_path: str = "",
    parameters: Optional[Mapping[str, str]] = None,
) -> dict[str, Any]:
    params: dict[str, Any] = {"name": name}
    if base_material_path:
        params["base_material_path"] = base_material_path
    if parameters:
        params["parameters"] = dict(parameters)
    return {"command": "asset.create_material", "params": params}


def build_import_fbx_command(
    source_path: str,
    *,
    destination_path: str = "/Game/Hephaestus/Imported",
    destination_name: Optional[str] = None,
    destination_rename: bool = False,
    destination_force_reimport: bool = False,
    destination_package_error: bool = False,
    auto_verify: bool = True,
    import_materials: bool = True,
    import_textures: bool = True,
    uniform_scale: float = 1.0,
) -> dict[str, Any]:
    """Build an FBX import command (asset.import_fbx / import_fbx alias)."""
    params: dict[str, Any] = {
        "source_path": source_path,
        "file_path": source_path,
        "destination_path": destination_path,
        "destination_rename": destination_rename,
        "destination_force_reimport": destination_force_reimport,
        "destination_package_error": destination_package_error,
        "auto_verify": auto_verify,
        "import_materials": import_materials,
        "import_textures": import_textures,
        "uniform_scale": uniform_scale,
    }
    if destination_name is not None:
        params["destination_name"] = destination_name
    return {"command": "asset.import_fbx", "params": params}


def build_import_fbx_command_v2(
    source_path: str,
    *,
    destination_path: str = "/Game/Hephaestus/Imported",
    destination_name: Optional[str] = None,
    destination_subobject_index: int = 0,
    destination_subobject_name: Optional[str] = None,
    destination_rename: bool = False,
    destination_force_reimport: bool = False,
    destination_package_error: bool = False,
    auto_verify: bool = True,
    verify_mesh_count: bool = True,
    verify_anim_count: int = 0,
    verify_texture_count: int = 0,
) -> dict[str, Any]:
    """FBX import with optional verify block (client-side expectations)."""
    command = build_import_fbx_command(
        source_path,
        destination_path=destination_path,
        destination_name=destination_name,
        destination_rename=destination_rename,
        destination_force_reimport=destination_force_reimport,
        destination_package_error=destination_package_error,
        auto_verify=auto_verify,
    )
    params = command["params"]
    if destination_subobject_index >= 0:
        params["destination_subobject_index"] = destination_subobject_index
    if destination_subobject_name is not None:
        params["destination_subobject_name"] = destination_subobject_name
    params["verify"] = {
        "mesh_count": verify_mesh_count,
        "anim_count": verify_anim_count,
        "texture_count": verify_texture_count,
    }
    return command


def spawn_actor_json(**kwargs: Any) -> str:
    """JSON string ready for ExecuteCommand."""
    return json.dumps(build_spawn_actor_command(**kwargs))


def spawn_mesh_json(**kwargs: Any) -> str:
    return json.dumps(build_spawn_mesh_command(**kwargs))


def destroy_actor_json(actor_path: str) -> str:
    return json.dumps(build_destroy_actor_command(actor_path))


def list_actors_json(class_path: str = "") -> str:
    return json.dumps(build_list_actors_command(class_path))


def capture_frame_json() -> str:
    return json.dumps(build_capture_frame_command())


def _get_pie_world():
    import unreal

    # Prefer UnrealEditorSubsystem game/PIE world (safe during PIE)
    try:
        ues = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
        if ues:
            world = ues.get_game_world()
            if world is not None:
                return world
            world = ues.get_editor_world()
            if world is not None:
                return world
    except Exception:
        pass

    try:
        return unreal.EditorLevelLibrary.get_game_world()
    except Exception:
        return None


def execute_command(command: Mapping[str, Any] | str) -> dict[str, Any]:
    """
    Execute a Hephaestus command via UHephaestusCommandHandler.ExecuteCommandForWorld.

    Requires PIE. Uses the static BlueprintCallable bridge (Python cannot call
    GameInstance.get_subsystem).
    """
    import unreal

    payload = command if isinstance(command, str) else json.dumps(command)
    world = _get_pie_world()
    if world is None:
        raise RuntimeError("No PIE/game world — press Play first, then retry.")

    result = unreal.HephaestusCommandHandler.execute_command_for_world(world, payload)
    return {
        "success": bool(result.success),
        "error": str(result.error_message),
        "result_json": str(result.result_json),
        "actor_paths": [str(p) for p in result.actor_references],
        "command_id": str(result.command_id),
        "time_ms": float(result.execution_time_ms),
    }


def smoke_spawn_point_light(
    location: Tuple[float, float, float] = (0.0, 0.0, 200.0),
) -> dict[str, Any]:
    """PIE smoke test: spawn a PointLight via CommandHandler."""
    return execute_command(
        build_spawn_actor_command(
            class_path="/Script/Engine.PointLight",
            location=location,
        )
    )

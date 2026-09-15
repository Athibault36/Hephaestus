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


def validate_animation_retarget(command_obj: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if command_obj.get("command") != "animation.retarget":
        errors.append("command must be animation.retarget")
    params = resolve_params(command_obj)
    if params is None:
        errors.append("missing params/args object")
        return errors
    if not params.get("source_mesh"):
        errors.append("missing source_mesh")
    if not params.get("target_mesh"):
        errors.append("missing target_mesh")
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
    cmd = command_obj.get("command")
    if cmd not in ("asset.import", "asset.import_fbx", "import_fbx"):
        errors.append("command must be asset.import, asset.import_fbx, or import_fbx")
    params = resolve_params(command_obj)
    if params is None:
        errors.append("missing params/args object")
        return errors
    if not (params.get("file_path") or params.get("source_path")):
        errors.append("missing file_path or source_path")
    if not params.get("destination_path"):
        errors.append("missing destination_path")
    return errors


def validate_import_fbx_command(command_obj: dict[str, Any]) -> list[str]:
    """Validate import_fbx / asset.import_fbx (alias of asset.import)."""
    return validate_asset_import(command_obj)


def validate_asset_reimport(command_obj: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if command_obj.get("command") != "asset.reimport":
        errors.append("command must be asset.reimport")
    params = resolve_params(command_obj)
    if params is None:
        errors.append("missing params/args object")
        return errors
    if not params.get("asset_path"):
        errors.append("missing asset_path")
    return errors


def validate_asset_create_instance(command_obj: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if command_obj.get("command") != "asset.create_instance":
        errors.append("command must be asset.create_instance")
    params = resolve_params(command_obj)
    if params is None:
        errors.append("missing params/args object")
    return errors


def validate_audio_create_metasound(command_obj: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if command_obj.get("command") != "audio.create_metasound":
        errors.append("command must be audio.create_metasound")
    params = resolve_params(command_obj)
    if params is None:
        errors.append("missing params/args object")
    return errors


def validate_audio_synthesize(command_obj: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if command_obj.get("command") != "audio.synthesize":
        errors.append("command must be audio.synthesize")
    params = resolve_params(command_obj)
    if params is None:
        errors.append("missing params/args object")
        return errors
    if not (params.get("sound_path") or params.get("path")):
        errors.append("missing sound_path")
    return errors


def validate_blueprint_add_function(command_obj: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if command_obj.get("command") != "blueprint.add_function":
        errors.append("command must be blueprint.add_function")
    params = resolve_params(command_obj)
    if params is None:
        errors.append("missing params/args object")
        return errors
    if not params.get("blueprint_path"):
        errors.append("missing blueprint_path")
    if not params.get("function_name"):
        errors.append("missing function_name")
    return errors


def validate_blueprint_diff(command_obj: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if command_obj.get("command") != "blueprint.diff":
        errors.append("command must be blueprint.diff")
    params = resolve_params(command_obj)
    if params is None:
        errors.append("missing params/args object")
        return errors
    if not (params.get("blueprint_path_a") or params.get("path_a")):
        errors.append("missing blueprint_path_a")
    if not (params.get("blueprint_path_b") or params.get("path_b")):
        errors.append("missing blueprint_path_b")
    return errors


def validate_blueprint_set_property(command_obj: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if command_obj.get("command") != "blueprint.set_property":
        errors.append("command must be blueprint.set_property")
    params = resolve_params(command_obj)
    if params is None:
        errors.append("missing params/args object")
        return errors
    if not params.get("blueprint_path"):
        errors.append("missing blueprint_path")
    if not params.get("property_name"):
        errors.append("missing property_name")
    return errors


def validate_rendering_add_pass(command_obj: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if command_obj.get("command") != "rendering.add_pass":
        errors.append("command must be rendering.add_pass")
    params = resolve_params(command_obj)
    if params is None:
        errors.append("missing params/args object")
        return errors
    if not params.get("pass_name"):
        errors.append("missing pass_name")
    return errors


def validate_pcg_mutate_graph(command_obj: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if command_obj.get("command") != "pcg.mutate_graph":
        errors.append("command must be pcg.mutate_graph")
    params = resolve_params(command_obj)
    if params is None:
        errors.append("missing params/args object")
        return errors
    if not (params.get("graph_path") or params.get("path")):
        errors.append("missing graph_path")
    return errors


def validate_pcg_set_metadata(command_obj: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if command_obj.get("command") != "pcg.set_metadata":
        errors.append("command must be pcg.set_metadata")
    params = resolve_params(command_obj)
    if params is None:
        errors.append("missing params/args object")
        return errors
    if not params.get("component_path"):
        errors.append("missing component_path")
    return errors


# --- Movie Render Queue (MRQ) submit ------------------------------------------

def validate_sequence_render(command_obj: dict[str, Any]) -> list[str]:
    """sequence.render — submit a Level Sequence to the Movie Render Queue."""
    errors: list[str] = []
    if command_obj.get("command") != "sequence.render":
        errors.append("command must be sequence.render")
    params = resolve_params(command_obj)
    if params is None:
        errors.append("missing params/args object")
        return errors
    if not (params.get("sequence_path") or params.get("path")):
        errors.append("missing sequence_path")
    if not (params.get("output_dir") or params.get("output_directory") or params.get("output")):
        errors.append("missing output_dir")
    return errors


# --- Landscape (Gaea → UE height apply / weightmap paint layers) --------------

def validate_landscape_import(command_obj: dict[str, Any]) -> list[str]:
    """landscape.import — apply a Gaea/heightmap raster to a real UE Landscape."""
    errors: list[str] = []
    if command_obj.get("command") != "landscape.import":
        errors.append("command must be landscape.import")
    params = resolve_params(command_obj)
    if params is None:
        errors.append("missing params/args object")
        return errors
    if not (params.get("heightmap_path") or params.get("heightmap")):
        errors.append("missing heightmap_path")
    return errors


def validate_landscape_import_weightmap(command_obj: dict[str, Any]) -> list[str]:
    """landscape.import_weightmap — import a mask as a landscape paint layer."""
    errors: list[str] = []
    if command_obj.get("command") != "landscape.import_weightmap":
        errors.append("command must be landscape.import_weightmap")
    params = resolve_params(command_obj)
    if params is None:
        errors.append("missing params/args object")
        return errors
    if not (params.get("weightmap_path") or params.get("mask_path")):
        errors.append("missing weightmap_path")
    if not (params.get("layer_name") or params.get("layer")):
        errors.append("missing layer_name")
    if not (params.get("landscape_path") or params.get("landscape") or params.get("actor_path")):
        errors.append("missing landscape_path")
    return errors


# --- PCG (create graph + terrain / vegetation binding) ------------------------

def validate_pcg_create_graph(command_obj: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if command_obj.get("command") != "pcg.create_graph":
        errors.append("command must be pcg.create_graph")
    params = resolve_params(command_obj)
    if params is None:
        errors.append("missing params/args object")
        return errors
    if not (params.get("name") or params.get("graph_path") or params.get("path")):
        errors.append("missing name or graph_path")
    return errors


def validate_pcg_bind_terrain(command_obj: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if command_obj.get("command") != "pcg.bind_terrain":
        errors.append("command must be pcg.bind_terrain")
    params = resolve_params(command_obj)
    if params is None:
        errors.append("missing params/args object")
        return errors
    if not (params.get("graph_path") or params.get("component_path") or params.get("path")):
        errors.append("missing graph_path or component_path")
    if not (params.get("landscape_path") or params.get("landscape") or params.get("actor_path")):
        errors.append("missing landscape_path")
    return errors


def validate_pcg_bind_vegetation(command_obj: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if command_obj.get("command") != "pcg.bind_vegetation":
        errors.append("command must be pcg.bind_vegetation")
    params = resolve_params(command_obj)
    if params is None:
        errors.append("missing params/args object")
        return errors
    if not (params.get("graph_path") or params.get("component_path") or params.get("path")):
        errors.append("missing graph_path or component_path")
    meshes = params.get("meshes") or params.get("static_meshes")
    if not meshes or not isinstance(meshes, (list, tuple)) or len(meshes) == 0:
        errors.append("missing meshes (non-empty list of static mesh paths)")
    return errors


# --- Animation Blueprint (create + graph mutation) + Control Rig graph --------

def validate_animation_create_anim_blueprint(command_obj: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if command_obj.get("command") != "animation.create_anim_blueprint":
        errors.append("command must be animation.create_anim_blueprint")
    params = resolve_params(command_obj)
    if params is None:
        errors.append("missing params/args object")
        return errors
    if not (params.get("skeleton_path") or params.get("skeleton") or params.get("mesh_path")):
        errors.append("missing skeleton_path or mesh_path")
    if not (params.get("name") or params.get("anim_blueprint_path") or params.get("destination_path")):
        errors.append("missing name or anim_blueprint_path")
    return errors


_ANIM_GRAPH_MUTATIONS = {
    "add_state",
    "add_transition",
    "add_blendspace",
    "add_layered_blend",
    "add_notify",
    "bind_variable",
    "set_entry_state",
    "add_state_machine",
}


def validate_animation_mutate_graph(command_obj: dict[str, Any]) -> list[str]:
    """animation.mutate_graph — state machines, transitions, blendspaces, notifies."""
    errors: list[str] = []
    if command_obj.get("command") != "animation.mutate_graph":
        errors.append("command must be animation.mutate_graph")
    params = resolve_params(command_obj)
    if params is None:
        errors.append("missing params/args object")
        return errors
    if not (params.get("anim_blueprint_path") or params.get("blueprint_path") or params.get("path")):
        errors.append("missing anim_blueprint_path")
    mutations = params.get("mutations")
    if not mutations or not isinstance(mutations, (list, tuple)) or len(mutations) == 0:
        errors.append("missing mutations (non-empty list)")
    else:
        for i, mut in enumerate(mutations):
            if not isinstance(mut, dict):
                errors.append(f"mutation[{i}] must be an object")
                continue
            mtype = mut.get("type")
            if not mtype:
                errors.append(f"mutation[{i}] missing type")
            elif mtype not in _ANIM_GRAPH_MUTATIONS:
                errors.append(
                    f"mutation[{i}] unknown type {mtype!r} "
                    f"(expected one of {sorted(_ANIM_GRAPH_MUTATIONS)})"
                )
    return errors


_CONTROL_RIG_MUTATIONS = {
    "add_node",
    "remove_node",
    "set_pin",
    "add_constraint",
    "add_solver",
    "add_physics_node",
    "connect",
}


def validate_animation_control_rig_mutate(command_obj: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if command_obj.get("command") != "animation.control_rig_mutate":
        errors.append("command must be animation.control_rig_mutate")
    params = resolve_params(command_obj)
    if params is None:
        errors.append("missing params/args object")
        return errors
    if not (params.get("rig_path") or params.get("path")):
        errors.append("missing rig_path")
    mutations = params.get("mutations")
    if not mutations or not isinstance(mutations, (list, tuple)) or len(mutations) == 0:
        errors.append("missing mutations (non-empty list)")
    else:
        for i, mut in enumerate(mutations):
            if not isinstance(mut, dict):
                errors.append(f"mutation[{i}] must be an object")
                continue
            mtype = mut.get("type")
            if not mtype:
                errors.append(f"mutation[{i}] missing type")
            elif mtype not in _CONTROL_RIG_MUTATIONS:
                errors.append(
                    f"mutation[{i}] unknown type {mtype!r} "
                    f"(expected one of {sorted(_CONTROL_RIG_MUTATIONS)})"
                )
    return errors


def validate_animation_retarget_batch(command_obj: dict[str, Any]) -> list[str]:
    """animation.retarget_batch — IK Retargeter batch bake across many anims."""
    errors: list[str] = []
    if command_obj.get("command") != "animation.retarget_batch":
        errors.append("command must be animation.retarget_batch")
    params = resolve_params(command_obj)
    if params is None:
        errors.append("missing params/args object")
        return errors
    if not (params.get("retargeter_path") or params.get("ik_retargeter") or (
        params.get("source_mesh") and params.get("target_mesh")
    )):
        errors.append("missing retargeter_path or source_mesh+target_mesh")
    anims = params.get("anim_paths") or params.get("animations")
    if not anims or not isinstance(anims, (list, tuple)) or len(anims) == 0:
        errors.append("missing anim_paths (non-empty list)")
    return errors


# --- Materials (expression graph + Material Parameter Collection) -------------

def validate_material_add_expression(command_obj: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if command_obj.get("command") != "material.add_expression":
        errors.append("command must be material.add_expression")
    params = resolve_params(command_obj)
    if params is None:
        errors.append("missing params/args object")
        return errors
    if not (params.get("material_path") or params.get("path")):
        errors.append("missing material_path")
    if not (params.get("expression_class") or params.get("expression") or params.get("node")):
        errors.append("missing expression_class")
    return errors


def validate_material_create_parameter_collection(command_obj: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if command_obj.get("command") != "material.create_parameter_collection":
        errors.append("command must be material.create_parameter_collection")
    params = resolve_params(command_obj)
    if params is None:
        errors.append("missing params/args object")
        return errors
    if not (params.get("name") or params.get("collection_path") or params.get("path")):
        errors.append("missing name or collection_path")
    return errors


def validate_material_set_parameter_collection(command_obj: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if command_obj.get("command") != "material.set_parameter_collection":
        errors.append("command must be material.set_parameter_collection")
    params = resolve_params(command_obj)
    if params is None:
        errors.append("missing params/args object")
        return errors
    if not (params.get("collection_path") or params.get("path")):
        errors.append("missing collection_path")
    params_map = params.get("parameters") or params.get("scalars") or params.get("vectors")
    if not params_map or not isinstance(params_map, dict):
        errors.append("missing parameters object")
    return errors


# --- Bulk asset migrate (execute move/rename with redirector fixup) -----------

def validate_asset_migrate(command_obj: dict[str, Any]) -> list[str]:
    """asset.migrate — execute a move/rename with redirector fixup (not just plan)."""
    errors: list[str] = []
    if command_obj.get("command") != "asset.migrate":
        errors.append("command must be asset.migrate")
    params = resolve_params(command_obj)
    if params is None:
        errors.append("missing params/args object")
        return errors
    sources = params.get("source_paths") or params.get("assets") or params.get("asset_paths")
    if not sources or not isinstance(sources, (list, tuple)) or len(sources) == 0:
        errors.append("missing source_paths (non-empty list)")
    if not (params.get("destination_path") or params.get("destination")):
        errors.append("missing destination_path")
    return errors


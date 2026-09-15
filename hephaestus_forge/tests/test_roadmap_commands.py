# Copyright (c) 2024 HephaestusForge. All Rights Reserved.
"""Contract tests for roadmap verbs: builders round-trip through validators.

These lock the UE-free client contract (params key, required fields, mutation
vocabularies) for the landscape / PCG / AnimBP / Control Rig / material /
migrate commands the C++ bridge executes. No ``unreal`` import required.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLUGIN_PY = ROOT / "templates" / "ue_plugin" / "HephaestusBridge" / "Content" / "Python"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(PLUGIN_PY))

from hephaestus.commands import (  # noqa: E402
    build_anim_mutate_graph_command,
    build_asset_migrate_command,
    build_control_rig_mutate_command,
    build_create_anim_blueprint_command,
    build_landscape_import_command,
    build_landscape_import_weightmap_command,
    build_material_add_expression_command,
    build_material_create_parameter_collection_command,
    build_material_set_parameter_collection_command,
    build_pcg_bind_terrain_command,
    build_pcg_bind_vegetation_command,
    build_pcg_create_graph_command,
    build_retarget_batch_command,
)
from remote_command_schema import (  # noqa: E402
    assert_uses_params_key,
    validate_animation_control_rig_mutate,
    validate_animation_create_anim_blueprint,
    validate_animation_mutate_graph,
    validate_animation_retarget_batch,
    validate_asset_migrate,
    validate_landscape_import,
    validate_landscape_import_weightmap,
    validate_material_add_expression,
    validate_material_create_parameter_collection,
    validate_material_set_parameter_collection,
    validate_pcg_bind_terrain,
    validate_pcg_bind_vegetation,
    validate_pcg_create_graph,
)


# --- Landscape ---------------------------------------------------------------

def test_landscape_import_builder_roundtrip():
    cmd = build_landscape_import_command("C:/gaea/Height.png")
    assert_uses_params_key(cmd)
    assert validate_landscape_import(cmd) == []


def test_landscape_import_requires_heightmap():
    assert "missing heightmap_path" in validate_landscape_import(
        {"command": "landscape.import", "params": {}}
    )


def test_landscape_weightmap_builder_roundtrip():
    cmd = build_landscape_import_weightmap_command(
        "/Game/L.L", "C:/gaea/Slope.png", "Rock"
    )
    assert validate_landscape_import_weightmap(cmd) == []


def test_landscape_weightmap_missing_fields():
    errs = validate_landscape_import_weightmap(
        {"command": "landscape.import_weightmap", "params": {}}
    )
    assert "missing weightmap_path" in errs
    assert "missing layer_name" in errs
    assert "missing landscape_path" in errs


# --- PCG ---------------------------------------------------------------------

def test_pcg_create_graph_roundtrip():
    cmd = build_pcg_create_graph_command("BiomeGraph")
    assert validate_pcg_create_graph(cmd) == []


def test_pcg_bind_terrain_roundtrip():
    cmd = build_pcg_bind_terrain_command("/Game/PCG/G.G", "/Game/L.L")
    assert validate_pcg_bind_terrain(cmd) == []


def test_pcg_bind_terrain_missing_landscape():
    assert "missing landscape_path" in validate_pcg_bind_terrain(
        {"command": "pcg.bind_terrain", "params": {"graph_path": "/Game/PCG/G.G"}}
    )


def test_pcg_bind_vegetation_roundtrip():
    cmd = build_pcg_bind_vegetation_command(
        "/Game/PCG/G.G", ["/Game/SM_Tree.SM_Tree"], layer_name="Grass"
    )
    assert validate_pcg_bind_vegetation(cmd) == []


def test_pcg_bind_vegetation_requires_meshes():
    assert "missing meshes (non-empty list of static mesh paths)" in validate_pcg_bind_vegetation(
        {"command": "pcg.bind_vegetation", "params": {"graph_path": "/Game/PCG/G.G", "meshes": []}}
    )


# --- Animation Blueprint / Control Rig / Retarget ----------------------------

def test_create_anim_blueprint_roundtrip():
    cmd = build_create_anim_blueprint_command("/Game/Skel.Skel", "ABP_Hero")
    assert validate_animation_create_anim_blueprint(cmd) == []


def test_anim_mutate_graph_roundtrip():
    cmd = build_anim_mutate_graph_command(
        "/Game/ABP_Hero.ABP_Hero",
        [
            {"type": "add_state_machine", "name": "Locomotion"},
            {"type": "add_state", "name": "Idle"},
            {"type": "add_state", "name": "Run"},
            {"type": "add_transition", "from": "Idle", "to": "Run", "rule": "Speed > 10"},
            {"type": "add_blendspace", "name": "MoveBS"},
            {"type": "bind_variable", "name": "Speed", "type_name": "float"},
        ],
    )
    assert validate_animation_mutate_graph(cmd) == []


def test_anim_mutate_graph_rejects_unknown_type():
    errs = validate_animation_mutate_graph(
        {
            "command": "animation.mutate_graph",
            "params": {
                "anim_blueprint_path": "/Game/ABP.ABP",
                "mutations": [{"type": "explode_everything"}],
            },
        }
    )
    assert any("unknown type" in e for e in errs)


def test_anim_mutate_graph_requires_mutations():
    assert "missing mutations (non-empty list)" in validate_animation_mutate_graph(
        {"command": "animation.mutate_graph", "params": {"anim_blueprint_path": "/Game/ABP.ABP"}}
    )


def test_control_rig_mutate_roundtrip():
    cmd = build_control_rig_mutate_command(
        "/Game/CR_Hero.CR_Hero",
        [
            {"type": "add_node", "node": "FullBodyIK"},
            {"type": "add_constraint", "constraint": "Aim"},
            {"type": "add_physics_node", "node": "PhysicsChain"},
            {"type": "connect", "from": "A.Out", "to": "B.In"},
        ],
    )
    assert validate_animation_control_rig_mutate(cmd) == []


def test_control_rig_mutate_rejects_unknown():
    errs = validate_animation_control_rig_mutate(
        {
            "command": "animation.control_rig_mutate",
            "params": {"rig_path": "/Game/CR.CR", "mutations": [{"type": "nope"}]},
        }
    )
    assert any("unknown type" in e for e in errs)


def test_retarget_batch_roundtrip():
    cmd = build_retarget_batch_command(
        "/Game/RTG_HeroToMannequin.RTG_HeroToMannequin",
        ["/Game/Anims/Run.Run", "/Game/Anims/Idle.Idle"],
    )
    assert validate_animation_retarget_batch(cmd) == []


def test_retarget_batch_requires_anims():
    errs = validate_animation_retarget_batch(
        {"command": "animation.retarget_batch", "params": {"retargeter_path": "/Game/R.R"}}
    )
    assert "missing anim_paths (non-empty list)" in errs


# --- Materials ---------------------------------------------------------------

def test_material_add_expression_roundtrip():
    cmd = build_material_add_expression_command(
        "/Game/M_Ground.M_Ground",
        "MaterialExpressionTextureSample",
        parameters={"Texture": "/Game/T_Albedo.T_Albedo"},
        connect_to="BaseColor",
    )
    assert validate_material_add_expression(cmd) == []


def test_material_add_expression_missing():
    errs = validate_material_add_expression(
        {"command": "material.add_expression", "params": {"material_path": "/Game/M.M"}}
    )
    assert "missing expression_class" in errs


def test_material_mpc_create_and_set_roundtrip():
    create = build_material_create_parameter_collection_command(
        "MPC_World", scalars={"TimeOfDay": 0.5}, vectors={"WindDir": [1, 0, 0]}
    )
    assert validate_material_create_parameter_collection(create) == []
    setc = build_material_set_parameter_collection_command(
        "/Game/Hephaestus/MPC/MPC_World.MPC_World", {"TimeOfDay": 0.8}
    )
    assert validate_material_set_parameter_collection(setc) == []


def test_material_set_mpc_requires_parameters():
    assert "missing parameters object" in validate_material_set_parameter_collection(
        {"command": "material.set_parameter_collection", "params": {"collection_path": "/Game/MPC.MPC"}}
    )


# --- Bulk migrate ------------------------------------------------------------

def test_asset_migrate_plan_roundtrip():
    cmd = build_asset_migrate_command(
        ["/Game/Old/A.A", "/Game/Old/B.B"], "/Game/New", execute=False
    )
    assert validate_asset_migrate(cmd) == []
    assert cmd["params"]["execute"] is False
    assert cmd["params"]["fixup_redirectors"] is True


def test_asset_migrate_execute_flag():
    cmd = build_asset_migrate_command(["/Game/Old/A.A"], "/Game/New", execute=True)
    assert cmd["params"]["execute"] is True
    assert validate_asset_migrate(cmd) == []


def test_asset_migrate_requires_sources_and_dest():
    errs = validate_asset_migrate({"command": "asset.migrate", "params": {}})
    assert "missing source_paths (non-empty list)" in errs
    assert "missing destination_path" in errs

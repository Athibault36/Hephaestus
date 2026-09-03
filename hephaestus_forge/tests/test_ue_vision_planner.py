"""Tests for vision LLM plan parsing (no network / no Unreal required)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ue_agent_loop import WorldSnapshot  # noqa: E402
from ue_vision_planner import (  # noqa: E402
    _extract_json_object,
    _resolve_attach_images,
    _system_prompt_for_goal,
    _vision_caption_enabled,
    plan_dict_to_action,
)


def test_extract_json_from_fences():
    raw = '```json\n{"action":"noop","reason":"done"}\n```'
    obj = _extract_json_object(raw)
    assert obj["action"] == "noop"


def test_system_prompt_gameplay_mode():
    prompt = _system_prompt_for_goal("[gameplay mode] jog forward")
    assert "apply_move" in prompt
    assert "gameplay" in prompt.lower()


def test_plan_spawn_cube():
    snap = WorldSnapshot(lights=1, meshes=0, actor_paths=[])
    action = plan_dict_to_action(
        {"action": "spawn_cube", "reason": "need cube", "x": 10, "y": -20, "z": 100},
        snap,
    )
    assert action.kind == "spawn_cube"
    assert action.command["command"] == "world.spawn_mesh"
    assert action.command["params"]["transform"]["location"]["x"] == 10.0


def test_plan_destroy_rejects_unknown_path():
    snap = WorldSnapshot(actor_paths=["/Temp/PointLight_0"])
    action = plan_dict_to_action(
        {"action": "destroy", "reason": "cleanup", "actor_path": "/Temp/DoesNotExist"},
        snap,
    )
    assert action.kind == "noop"


def test_plan_destroy_accepts_listed_mesh():
    path = "/Temp/UEDPIE.PersistentLevel.StaticMeshActor_1"
    snap = WorldSnapshot(actor_paths=[path])
    action = plan_dict_to_action(
        {"action": "destroy", "reason": "remove cube", "actor_path": path},
        snap,
    )
    assert action.kind == "destroy"
    assert action.command["params"]["actor_path"] == path


def test_plan_set_transform_and_light():
    path = "/Temp/PersistentLevel.PointLight_0"
    mesh = "/Temp/PersistentLevel.StaticMeshActor_1"
    snap = WorldSnapshot(actor_paths=[path, mesh], lights=1, meshes=1)
    move = plan_dict_to_action(
        {"action": "set_transform", "actor_path": mesh, "x": 50, "y": 0, "z": 120, "reason": "nudge"},
        snap,
    )
    assert move.kind == "set_transform"
    light = plan_dict_to_action(
        {"action": "set_light", "actor_path": path, "intensity": 9000, "reason": "brighter"},
        snap,
    )
    assert light.kind == "set_light"
    assert light.command["params"]["intensity"] == 9000.0


def test_plan_spawn_character_and_play_anim():
    snap = WorldSnapshot(lights=1, meshes=0, actor_paths=[])
    spawn = plan_dict_to_action(
        {"action": "spawn_character", "reason": "hero", "x": 100, "y": 0, "z": 90},
        snap,
    )
    assert spawn.kind == "spawn_character"
    assert spawn.command["command"] == "animation.spawn_skeletal_mesh"

    skel = "/Temp/UEDPIE.PersistentLevel.SkeletalMeshActor_0"
    snap2 = WorldSnapshot(actor_paths=[skel], skeletal=1)
    play = plan_dict_to_action(
        {
            "action": "play_anim",
            "actor_path": skel,
            "anim_path": "/Game/Animations/Walk.Walk",
            "reason": "walk",
        },
        snap2,
    )
    assert play.kind == "play_anim"
    assert play.command["params"]["anim_path"] == "/Game/Animations/Walk.Walk"


def test_plan_apply_move_and_montage():
    snap = WorldSnapshot(actor_paths=[])
    move = plan_dict_to_action(
        {"action": "jog", "forward": 1.0, "duration": 3.0, "reason": "run"},
        snap,
    )
    assert move.kind == "apply_move"
    assert move.command["command"] == "world.apply_move_input"
    assert move.command["params"]["forward"] == 1.0

    skel = "/Temp/UEDPIE.PersistentLevel.SkeletalMeshActor_0"
    snap2 = WorldSnapshot(actor_paths=[skel])
    montage = plan_dict_to_action(
        {
            "action": "play_montage",
            "actor_path": skel,
            "montage_path": "/Game/Anims/Run.Run",
            "reason": "montage",
        },
        snap2,
    )
    assert montage.kind == "play_montage"
    assert montage.command["params"]["montage_path"] == "/Game/Anims/Run.Run"


def test_plan_spawn_mesh_custom_path():
    snap = WorldSnapshot(actor_paths=[])
    action = plan_dict_to_action(
        {
            "action": "spawn_mesh",
            "mesh_path": "/Game/Meshes/Dog.Dog",
            "reason": "dog",
        },
        snap,
    )
    assert action.command["params"]["mesh_path"] == "/Game/Meshes/Dog.Dog"


def test_plan_create_shot_and_play_level_sequence():
    snap = WorldSnapshot(actor_paths=[])
    shot = plan_dict_to_action(
        {"action": "create_shot", "x": 100, "y": 0, "z": 200, "duration": 3, "reason": "frame"},
        snap,
    )
    assert shot.kind == "create_shot"
    assert shot.command["command"] == "sequence.create_shot"
    assert shot.command["params"].get("mode") == "free"

    play = plan_dict_to_action(
        {
            "action": "play_level_sequence",
            "sequence_path": "/Game/Cinematics/Intro.Intro",
            "reason": "play",
        },
        snap,
    )
    assert play.command["command"] == "sequence.play"
    assert play.command["params"]["sequence_path"] == "/Game/Cinematics/Intro.Intro"


def test_plan_set_view_frame_from_left():
    snap = WorldSnapshot(
        actor_paths=["/Game/Maps/Test.Test:PersistentLevel.Beverly"],
        skeletal=1,
    )
    action = plan_dict_to_action(
        {
            "action": "set_view",
            "look_at_actor": "/Game/Maps/Test.Test:PersistentLevel.Beverly",
            "distance": 450,
            "yaw_offset": 90,
            "height": 120,
            "mode": "free",
            "reason": "frame from the left",
        },
        snap,
    )
    assert action.kind == "set_view"
    assert action.command["command"] == "world.set_view"
    params = action.command["params"]
    assert params["mode"] == "free"
    assert params["look_at_actor"].endswith("Beverly")
    assert params["distance"] == 450
    assert params["yaw_offset"] == 90


def test_plan_set_view_infers_yaw_from_reason_left():
    snap = WorldSnapshot(actor_paths=["/Temp/Char"])
    action = plan_dict_to_action(
        {
            "action": "camera",
            "look_at_actor": "/Temp/Char",
            "reason": "Frame the character from the left with the camera",
        },
        snap,
    )
    assert action.command["params"]["yaw_offset"] == 90.0
    assert action.command["params"]["mode"] == "free"


def test_plan_create_shot_with_look_at_and_orbit():
    snap = WorldSnapshot(actor_paths=["/Temp/Char"])
    action = plan_dict_to_action(
        {
            "action": "create_shot",
            "look_at_actor": "/Temp/Char",
            "distance": 500,
            "yaw_offset": -90,
            "duration": 2.5,
            "reason": "orbit right",
        },
        snap,
    )
    assert action.kind == "create_shot"
    p = action.command["params"]
    assert p["look_at_actor"] == "/Temp/Char"
    assert p["distance"] == 500
    assert p["yaw_offset"] == -90
    assert p["mode"] == "free"


def test_resolve_attach_images_deepseek_default_off():
    assert _resolve_attach_images("deepseek-ai/deepseek-v4-pro-0813", None) is False


def test_resolve_attach_images_env_override(monkeypatch):
    monkeypatch.setenv("HEPHAESTUS_PLANNER_VISION", "1")
    assert _resolve_attach_images("gpt-4o", None) is True
    assert _resolve_attach_images("deepseek-ai/deepseek-v4-pro-0813", None) is False


def test_vision_caption_env_flag(monkeypatch):
    monkeypatch.delenv("HEPHAESTUS_PLANNER_VISION", raising=False)
    assert _vision_caption_enabled() is False
    monkeypatch.setenv("HEPHAESTUS_PLANNER_VISION", "1")
    assert _vision_caption_enabled() is True


if __name__ == "__main__":
    test_extract_json_from_fences()
    test_plan_spawn_cube()
    test_plan_destroy_rejects_unknown_path()
    test_plan_destroy_accepts_listed_mesh()
    test_plan_set_transform_and_light()
    print("OK")

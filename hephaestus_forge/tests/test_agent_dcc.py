# Copyright (c) 2024 HephaestusForge. All Rights Reserved.
"""Unit tests for agent DCC authoring intent + chat wiring (mocked pipeline)."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agent_dcc import (  # noqa: E402
    infer_dcc_shape,
    last_dcc,
    remember_dcc,
    try_direct_dcc_author,
    wants_dcc_export_only,
    wants_dcc_into_pie,
    wants_spin,
)


def test_infer_shape_cube():
    assert infer_dcc_shape("make a cube and put it in the scene") == "cube"


def test_infer_shape_sphere_alias():
    assert infer_dcc_shape("create a sphere prop") == "uv_sphere"


def test_infer_no_match():
    assert infer_dcc_shape("spawn the dog and walk") is None


def test_into_pie_default_for_make_cube():
    assert wants_dcc_into_pie("make a cube") is True
    assert wants_dcc_into_pie("make a cube and put it in the scene") is True


def test_export_only():
    assert wants_dcc_export_only("export a cube fbx with blender") is True
    assert wants_dcc_into_pie("export a cube fbx with blender") is False


def test_try_direct_dcc_author_into_pie(monkeypatch, tmp_path: Path):
    fake = {
        "success": True,
        "asset_path": "/Game/Hephaestus/DccImports/Hephaestus_cube",
        "actor_path": "/Temp/Foo.StaticMeshActor_0",
        "phase": "done",
        "fbx": str(tmp_path / "c.fbx"),
        "frame": {"success": True, "actor_path": "/Temp/Foo.StaticMeshActor_0"},
    }
    with patch("agent_dcc.author_primitive_to_pie", return_value=fake) as auth:
        out = try_direct_dcc_author(
            "make a cube and frame a shot of it",
            project_root=tmp_path,
        )
    assert out is not None
    assert out["ok"] is True
    assert out["planner"] == "direct_dcc_author"
    assert "framed" in out["reply"].lower() or "Authored" in out["reply"]
    assert auth.call_args.kwargs.get("frame") is True
    assert auth.call_args.kwargs.get("create_shot") is True


def test_spawned_actor_skips_light():
    from agent_dcc import _spawned_actor_path

    path = _spawned_actor_path(
        {
            "spawn_results": [
                {
                    "success": True,
                    "actor_paths": ["/Temp/X.PointLight_0"],
                    "result_json": '{"actor_path":"/Temp/X.PointLight_0"}',
                },
                {
                    "success": True,
                    "actor_paths": ["/Temp/X.StaticMeshActor_0"],
                    "result_json": '{"actor_path":"/Temp/X.StaticMeshActor_0","mesh_path":"/Game/Y"}',
                },
            ]
        }
    )
    assert path and "StaticMeshActor" in path


def test_infer_mesh_color_red():
    from agent_dcc import infer_mesh_color

    c = infer_mesh_color("make a red cube and frame it")
    assert c is not None
    assert c["r"] > c["g"] and c["r"] > c["b"]


def test_try_direct_passes_color(monkeypatch, tmp_path: Path):
    fake = {
        "success": True,
        "asset_path": "/Game/X",
        "actor_path": "/Temp/A",
        "phase": "done",
        "tint": {"success": True},
        "frame": {"success": True},
    }
    with patch("agent_dcc.author_primitive_to_pie", return_value=fake) as auth:
        out = try_direct_dcc_author("make a blue sphere", project_root=tmp_path)
    assert out and out["ok"]
    color = auth.call_args.kwargs.get("color")
    assert color is not None
    assert color["b"] > color["r"]
    assert "tinted" in out["reply"]


def test_try_direct_skips_unrelated():
    assert try_direct_dcc_author("play idle on /Temp/Foo") is None


def test_wants_spin():
    assert wants_spin("make a red cube, frame it, and spin it slowly") is True
    assert wants_spin("make a cube") is False


def test_try_direct_passes_spin(tmp_path: Path):
    fake = {
        "success": True,
        "asset_path": "/Game/X",
        "actor_path": "/Temp/A",
        "phase": "done",
        "spin": {"success": True},
        "frame": {"success": True},
    }
    with patch("agent_dcc.author_primitive_to_pie", return_value=fake) as auth:
        out = try_direct_dcc_author(
            "make a red cube, frame it, and spin it slowly",
            project_root=tmp_path,
        )
    assert out and out["ok"]
    assert auth.call_args.kwargs.get("spin") is True
    assert auth.call_args.kwargs.get("color") is not None
    assert "spun" in out["reply"].lower()
    mem = last_dcc(tmp_path)
    assert mem and mem.get("actor_path") == "/Temp/A"


def test_followup_spin_uses_memory(tmp_path: Path):
    remember_dcc(
        tmp_path,
        {"actor_path": "/Temp/Last.StaticMeshActor_0", "asset_path": "/Game/X", "shape": "cube"},
    )
    with patch("agent_dcc.spin_actor", return_value={"success": True, "actor_path": "/Temp/Last.StaticMeshActor_0"}) as sp:
        out = try_direct_dcc_author("spin it slowly", project_root=tmp_path)
    assert out and out["ok"]
    assert out["planner"] == "direct_dcc_followup"
    assert sp.called
    assert "Spun" in out["reply"]


def test_last_dcc_persists_to_disk(tmp_path: Path):
    from agent_dcc import _LAST_DCC

    remember_dcc(
        tmp_path,
        {"actor_path": "/Temp/Disk.StaticMeshActor_0", "asset_path": "/Game/Y", "shape": "cone"},
    )
    path = tmp_path / ".hephaestus_forge" / "last_dcc.json"
    assert path.is_file()
    # Simulate process restart
    _LAST_DCC.clear()
    mem = last_dcc(tmp_path)
    assert mem and mem["actor_path"] == "/Temp/Disk.StaticMeshActor_0"
    assert mem["shape"] == "cone"


def test_followup_tint_and_spin(tmp_path: Path):
    remember_dcc(
        tmp_path,
        {"actor_path": "/Temp/Combo.StaticMeshActor_0", "asset_path": "/Game/Z", "shape": "cube"},
    )
    with patch("agent_dcc.tint_actor", return_value={"success": True}) as tint:
        with patch("agent_dcc.spin_actor", return_value={"success": True}) as sp:
            out = try_direct_dcc_author("make it blue and spin it", project_root=tmp_path)
    assert out and out["ok"]
    assert tint.called and sp.called
    assert "Tinted" in out["reply"] and "Spun" in out["reply"]


def test_infer_creature_kind():
    from blender_bridge import infer_creature_kind

    assert infer_creature_kind("make a dog") == "quadruped"
    assert infer_creature_kind("create a person") == "humanoid"
    assert infer_creature_kind("make a creature") == "creature"
    assert infer_creature_kind("make a cube") is None


def test_creature_author_uses_blender_kit(tmp_path: Path):
    class FakeExport:
        success = True
        output_path = str(tmp_path / "dog.fbx")
        error = None

        def to_dict(self):
            return {"success": True, "output_path": self.output_path}

    (tmp_path / "dog.fbx").write_bytes(b"fbx")
    imported = {
        "success": True,
        "asset_path": "/Game/Hephaestus/DccImports/dog",
        "actor_path": "/Temp/Dog.SkeletalMeshActor_0",
        "skeletal": True,
        "spawn_results": [
            {
                "success": True,
                "actor_paths": ["/Temp/Dog.SkeletalMeshActor_0"],
            }
        ],
    }
    with patch("agent_dcc.meshy_available", create=True, return_value=False):
        with patch("meshy_bridge.meshy_available", return_value=False):
            with patch("blender_bridge.export_creature_fbx", return_value=FakeExport()):
                with patch("agent_dcc.dcc_import_to_pie", create=True):
                    with patch("dcc_import.dcc_import_to_pie", return_value=imported):
                        with patch("agent_dcc.frame_actor", return_value={"success": True}):
                            out = try_direct_dcc_author(
                                "make a dog and put it in the scene",
                                project_root=tmp_path,
                            )
    assert out and out["ok"]
    assert out["planner"] == "direct_creature_author"
    assert "Authored quadruped" in out["reply"] or "quadruped" in out["reply"].lower()


def test_meshy_opt_in_only(monkeypatch):
    from meshy_bridge import meshy_available

    monkeypatch.setenv("MESHY_API_KEY", "msy_test")
    monkeypatch.delenv("HEPHAESTUS_USE_MESHY", raising=False)
    assert meshy_available() is False
    monkeypatch.setenv("HEPHAESTUS_USE_MESHY", "1")
    assert meshy_available() is True


def test_nim_prop_author_mocked(tmp_path: Path):
    (tmp_path / "chair.fbx").write_bytes(b"fbx")
    fake = {
        "success": True,
        "output_path": str(tmp_path / "chair.fbx"),
        "provider": "nim_blender",
    }
    imported = {
        "success": True,
        "asset_path": "/Game/Hephaestus/DccImports/chair",
        "spawn_results": [{"success": True, "actor_paths": ["/Temp/Chair.StaticMeshActor_0"]}],
    }
    with patch("blender_nim_author.nim_available", return_value=True):
        with patch("blender_nim_author.author_mesh_fbx", return_value=fake):
            with patch("dcc_import.dcc_import_to_pie", return_value=imported):
                with patch("agent_dcc.frame_actor", return_value={"success": True}):
                    out = try_direct_dcc_author(
                        "make a wooden chair and put it in the scene",
                        project_root=tmp_path,
                    )
    assert out and out["ok"]
    assert out["planner"] == "direct_nim_prop_author"
    assert "nim_blender" in out["reply"]


def test_autonomous_runner_uses_dcc(monkeypatch, tmp_path: Path):
    from autonomous_runner import run_autonomous_goal

    chat_shaped = {
        "ok": True,
        "reply": "done",
        "grade": {"met": True, "score": 1.0, "summary": "done", "missing": []},
        "planner": "direct_dcc_author",
        "asset_matches": ["/Game/X"],
        "asset_meta": {"dcc_shape": "cube"},
    }
    with patch("autonomous_runner.try_direct_dcc_author", return_value=chat_shaped):
        report = run_autonomous_goal(
            "make a cube",
            project_root=tmp_path,
            require_nim=True,
        )
    assert report.ok is True
    assert report.planner == "direct_dcc_author"
    assert report.llm_error == ""

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
    try_direct_dcc_author,
    wants_dcc_export_only,
    wants_dcc_into_pie,
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


def test_frame_actor_posts_set_view(monkeypatch):
    from agent_dcc import frame_actor

    calls = []

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        def command(self, body):
            calls.append(body)
            return {"success": True, "result_json": "{}"}

    monkeypatch.setattr("ue_agent_loop.RemoteUeClient", FakeClient)
    out = frame_actor("/Temp/A.StaticMeshActor_0", create_shot=False)
    assert out["success"] is True
    assert calls[0]["command"] == "world.set_view"
    assert calls[0]["params"]["look_at_actor"].endswith("StaticMeshActor_0")


def test_try_direct_skips_unrelated():
    assert try_direct_dcc_author("play idle on /Temp/Foo") is None


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

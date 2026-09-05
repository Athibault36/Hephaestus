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
        "phase": "done",
        "fbx": str(tmp_path / "c.fbx"),
    }
    with patch("agent_dcc.author_primitive_to_pie", return_value=fake):
        out = try_direct_dcc_author("make a cube and put it in the scene", project_root=tmp_path)
    assert out is not None
    assert out["ok"] is True
    assert out["planner"] == "direct_dcc_author"
    assert "/Game/Hephaestus/DccImports" in (out["asset_matches"][0] or "")


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

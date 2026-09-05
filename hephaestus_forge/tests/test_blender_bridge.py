# Copyright (c) 2024 HephaestusForge. All Rights Reserved.
"""Unit / smoke tests for factory blender_bridge (Blender optional for CI)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from blender_bridge import (  # noqa: E402
    PRIMITIVE_SHAPES,
    default_export_dir,
    export_primitive_fbx,
    find_blender,
    ue_import_next_steps,
    _primitive_export_script,
)


def test_default_export_dir_is_target_agnostic(tmp_path: Path):
    out = default_export_dir(tmp_path)
    assert out == tmp_path / ".hephaestus_forge" / "dcc_exports"
    assert "MacroVerse" not in str(out)
    assert "Fresh" not in str(out)


def test_ue_import_next_steps_mentions_pie_guard(tmp_path: Path):
    fbx = tmp_path / "DemoMesh.fbx"
    fbx.write_bytes(b"fake")
    steps = ue_import_next_steps(fbx)
    joined = "\n".join(steps)
    assert "PIE" in joined
    assert "asset.import_fbx" in joined
    assert "DemoMesh" in joined
    assert "spawn-asset" in joined


def test_primitive_export_script_contains_marker():
    script = _primitive_export_script("cube", r"C:\tmp\out.fbx", "MyCube")
    assert "HEPHAESTUS_BLENDER_EXPORT_OK" in script
    assert "primitive_cube_add" in script
    assert "MyCube" in script


def test_export_rejects_unknown_shape():
    result = export_primitive_fbx(shape="torus_knot")
    assert result.success is False
    assert "Unsupported shape" in (result.error or "")


def test_find_blender_respects_explicit_missing(tmp_path: Path):
    missing = tmp_path / "no_blender_here.exe"
    # Without falling through to real PATH when explicit is broken — still may find PATH blender.
    # Explicit missing path is skipped; ensure env override works when file exists.
    fake = tmp_path / "blender.exe"
    fake.write_text("not real", encoding="utf-8")

    def fake_check_output(cmd, **kwargs):
        if str(fake) in cmd[0] or cmd[0] == str(fake):
            return "Blender 9.9.9\n"
        raise FileNotFoundError(cmd)

    with patch("blender_bridge.subprocess.check_output", side_effect=fake_check_output):
        path, ver = find_blender(str(fake), env={})
    assert path == str(fake)
    assert ver == "9.9.9"


def test_export_primitive_fbx_mocked_success(tmp_path: Path):
    fake_blender = tmp_path / "blender.exe"
    fake_blender.write_text("x", encoding="utf-8")
    out_fbx = tmp_path / "exports" / "UnitCube.fbx"

    def fake_run(cmd, **kwargs):
        # Simulate Blender writing the FBX
        out_fbx.parent.mkdir(parents=True, exist_ok=True)
        out_fbx.write_bytes(b"FBX_FAKE")
        return MagicMock(
            returncode=0,
            stdout="HEPHAESTUS_BLENDER_EXPORT_OK\n",
            stderr="",
        )

    with patch("blender_bridge.find_blender", return_value=(str(fake_blender), "4.5.0")):
        with patch("blender_bridge.subprocess.run", side_effect=fake_run):
            result = export_primitive_fbx(
                shape="cube",
                name="UnitCube",
                output_path=out_fbx,
            )
    assert result.success is True
    assert result.output_path
    assert Path(result.output_path).is_file()
    assert result.next_steps
    assert any("PIE" in s for s in result.next_steps)


@pytest.mark.skipif(
    find_blender()[0] is None,
    reason="Blender not installed — skip live smoke",
)
def test_live_blender_export_smoke(tmp_path: Path):
    """Optional live smoke: real Blender background export (skipped in CI without Blender)."""
    result = export_primitive_fbx(
        shape="cube",
        name="LiveSmokeCube",
        project_root=tmp_path,
        timeout_seconds=180,
    )
    assert result.success, result.error or result.stderr[-500:]
    assert Path(result.output_path).is_file()
    assert Path(result.output_path).stat().st_size > 0
    assert "HEPHAESTUS_BLENDER_EXPORT_OK" in result.stdout


def test_all_shapes_have_script_ops():
    for shape in PRIMITIVE_SHAPES:
        script = _primitive_export_script(shape, "/tmp/x.fbx", "Obj")
        assert "HEPHAESTUS_BLENDER_EXPORT_OK" in script
        assert "export_scene.fbx" in script

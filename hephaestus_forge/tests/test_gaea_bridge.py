# Copyright (c) 2024 HephaestusForge. All Rights Reserved.
"""Unit tests for the factory gaea_bridge (Gaea optional for CI)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from gaea_bridge import (  # noqa: E402
    GAEA_GRAPH_EXTENSIONS,
    GaeaBuildResult,
    build_command,
    build_terrain,
    classify_outputs,
    default_build_dir,
    find_gaea,
    ue_landscape_import_next_steps,
)


def _fake_proc(returncode: int = 0, stdout: str = "", stderr: str = ""):
    return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)


def test_find_gaea_env_resolution(tmp_path: Path):
    swarm = tmp_path / "Gaea.Swarm.exe"
    swarm.write_bytes(b"MZ")
    path, version = find_gaea(env={"GAEA_SWARM": str(swarm)})
    assert path == str(swarm)


def test_find_gaea_points_gaea_exe_at_swarm(tmp_path: Path):
    (tmp_path / "Gaea.exe").write_bytes(b"MZ")
    swarm = tmp_path / "Gaea.Swarm.exe"
    swarm.write_bytes(b"MZ")
    path, _ = find_gaea(str(tmp_path / "Gaea.exe"))
    assert Path(path).name == "Gaea.Swarm.exe"


def test_find_gaea_infers_version_from_dir(tmp_path: Path):
    install = tmp_path / "Gaea 2"
    install.mkdir()
    swarm = install / "Gaea.Swarm.exe"
    swarm.write_bytes(b"MZ")
    path, version = find_gaea(str(swarm))
    assert version == "2"


def test_find_gaea_missing_returns_none():
    path, version = find_gaea(env={"PATH": ""})
    assert path is None


def test_build_command_variables_are_trailing():
    cmd = build_command(
        "Gaea.Swarm.exe",
        "T.terrain",
        profile="Final_8K",
        region="Volcano",
        seed=1337,
        ignore_cache=True,
        verbose=True,
        variables={"ErosionStrength": "0.63", "Snowline": "0.42"},
    )
    assert cmd[:3] == ["Gaea.Swarm.exe", "--Filename", "T.terrain"]
    assert "--profile" in cmd and "Final_8K" in cmd
    assert "--region" in cmd and "Volcano" in cmd
    assert "--seed" in cmd and "1337" in cmd
    assert "--ignorecache" in cmd
    assert "--verbose" in cmd
    # -v pairs must be last, after every other switch.
    first_v = cmd.index("-v")
    assert first_v > cmd.index("--verbose")
    assert cmd[first_v : first_v + 2] == ["-v", "ErosionStrength:0.63"]
    assert "Snowline:0.42" in cmd


def test_classify_outputs_height_masks_textures(tmp_path: Path):
    files = [
        tmp_path / "Height.png",
        tmp_path / "Slope.png",
        tmp_path / "Flow.png",
        tmp_path / "Sediment.png",
        tmp_path / "Albedo.png",
        tmp_path / "Normal.png",
        tmp_path / "Unknown.png",
    ]
    for f in files:
        f.write_bytes(b"img")
    heightmap, masks, textures, other = classify_outputs(files)
    assert Path(heightmap).name == "Height.png"
    mask_names = {Path(m).name for m in masks}
    assert {"Slope.png", "Flow.png", "Sediment.png"} <= mask_names
    texture_names = {Path(t).name for t in textures}
    assert {"Albedo.png", "Normal.png"} == texture_names
    assert Path(other[0]).name == "Unknown.png"


def test_classify_prefers_high_bitdepth_height(tmp_path: Path):
    png = tmp_path / "Height.png"
    r16 = tmp_path / "HeightField.r16"
    png.write_bytes(b"img")
    r16.write_bytes(b"img")
    heightmap, masks, _, _ = classify_outputs([png, r16])
    # The r16 is height-capable and should win the heightmap slot.
    assert Path(heightmap).suffix == ".r16"
    # The remaining height-keyworded raster is demoted to a mask.
    assert any(Path(m).name == "Height.png" for m in masks)


def test_build_terrain_rejects_bad_extension(tmp_path: Path):
    bad = tmp_path / "graph.txt"
    bad.write_text("x")
    result = build_terrain(bad)
    assert not result.success
    assert "Unsupported" in (result.error or "")


def test_build_terrain_missing_file(tmp_path: Path):
    result = build_terrain(tmp_path / "missing.terrain")
    assert not result.success
    assert "not found" in (result.error or "")


def test_build_terrain_success_with_mocked_swarm(tmp_path: Path):
    terrain = tmp_path / "World.terrain"
    terrain.write_text("terrain-graph")
    build_dir = tmp_path / "out"
    swarm = tmp_path / "Gaea.Swarm.exe"
    swarm.write_bytes(b"MZ")

    def fake_runner(cmd, **kwargs):
        # Simulate Gaea writing exports into the build folder.
        build_dir.mkdir(parents=True, exist_ok=True)
        (build_dir / "Height.png").write_bytes(b"h")
        (build_dir / "Slope.png").write_bytes(b"s")
        (build_dir / "Albedo.png").write_bytes(b"a")
        return _fake_proc(returncode=0, stdout="Build complete")

    result = build_terrain(
        terrain,
        build_folder=build_dir,
        gaea_executable=str(swarm),
        _runner=fake_runner,
    )
    assert result.success, result.error
    assert Path(result.heightmap).name == "Height.png"
    assert any(Path(m).name == "Slope.png" for m in result.masks)
    assert any(Path(t).name == "Albedo.png" for t in result.textures)
    assert result.outputs
    joined = "\n".join(result.next_steps)
    assert "landscape.import" in joined


def test_build_terrain_success_but_no_exports_fails(tmp_path: Path):
    terrain = tmp_path / "World.terrain"
    terrain.write_text("terrain-graph")
    build_dir = tmp_path / "out"
    swarm = tmp_path / "Gaea.Swarm.exe"
    swarm.write_bytes(b"MZ")

    def fake_runner(cmd, **kwargs):
        return _fake_proc(returncode=0, stdout="done, nothing exported")

    result = build_terrain(
        terrain, build_folder=build_dir, gaea_executable=str(swarm), _runner=fake_runner
    )
    assert not result.success
    assert "no exports" in (result.error or "").lower()


def test_build_terrain_nonzero_exit_fails(tmp_path: Path):
    terrain = tmp_path / "World.terrain"
    terrain.write_text("terrain-graph")
    swarm = tmp_path / "Gaea.Swarm.exe"
    swarm.write_bytes(b"MZ")

    def fake_runner(cmd, **kwargs):
        return _fake_proc(returncode=2, stderr="boom")

    result = build_terrain(
        terrain, build_folder=tmp_path / "out", gaea_executable=str(swarm), _runner=fake_runner
    )
    assert not result.success
    assert "code 2" in (result.error or "")


def test_build_terrain_timeout(tmp_path: Path):
    terrain = tmp_path / "World.terrain"
    terrain.write_text("terrain-graph")
    swarm = tmp_path / "Gaea.Swarm.exe"
    swarm.write_bytes(b"MZ")

    def fake_runner(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd, kwargs.get("timeout", 1))

    result = build_terrain(
        terrain,
        build_folder=tmp_path / "out",
        gaea_executable=str(swarm),
        _runner=fake_runner,
        timeout_seconds=5,
    )
    assert not result.success
    assert "timed out" in (result.error or "")


def test_build_terrain_missing_gaea(tmp_path: Path):
    terrain = tmp_path / "World.terrain"
    terrain.write_text("terrain-graph")
    with patch("gaea_bridge.find_gaea", return_value=(None, None)):
        result = build_terrain(terrain, build_folder=tmp_path / "out")
    assert not result.success
    assert "not found" in (result.error or "")


def test_default_build_dir_target_agnostic(tmp_path: Path):
    terrain = tmp_path / "World.terrain"
    out = default_build_dir(terrain, tmp_path)
    assert out == tmp_path / ".hephaestus_forge" / "gaea_builds" / "World"
    assert "MacroVerse" not in str(out)


def test_result_to_dict_is_json_safe(tmp_path: Path):
    result = GaeaBuildResult(success=True, heightmap="H.png", masks=["S.png"])
    d = result.to_dict()
    assert d["heightmap"] == "H.png"
    assert d["outputs"] == ["H.png", "S.png"]


def test_next_steps_without_height_warns():
    result = GaeaBuildResult(success=True, masks=["Slope.png"])
    steps = ue_landscape_import_next_steps(result)
    assert any("No heightmap" in s for s in steps)

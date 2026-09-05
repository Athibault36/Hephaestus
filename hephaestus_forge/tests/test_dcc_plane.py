# Copyright (c) 2024 HephaestusForge. All Rights Reserved.
"""Unit tests for DCC control plane (mocked HTTP + route handlers)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from hephaestus_forge.dcc_server import route_command, health
from hephaestus_forge.dcc_client import DccClient, dcc_online
from hephaestus_forge.cc5_bridge import export_character_fbx, find_cc5
from hephaestus_forge.dcc_import import resolve_fbx_path, editor_import_fbx


def test_health_honest_blender_flag():
    with patch("hephaestus_forge.dcc_server.find_blender", return_value=(None, None)):
        with patch("hephaestus_forge.dcc_server._cc5_status", return_value={"available": False}):
            h = health()
    assert h["ok"] is True
    assert h["ready"] is False
    assert h["blender"]["available"] is False


def test_health_ready_when_blender_found():
    with patch(
        "hephaestus_forge.dcc_server.find_blender",
        return_value=("C:/Blender/blender.exe", "4.2.0"),
    ):
        with patch("hephaestus_forge.dcc_server._cc5_status", return_value={"available": False}):
            h = health()
    assert h["ready"] is True
    assert h["blender"]["version"] == "4.2.0"


def test_route_unknown_command():
    res = route_command("not.a.command", {})
    assert res["success"] is False
    assert "Unknown" in res["error"]


def test_route_blender_export_fbx(tmp_path: Path):
    fake = MagicMock()
    fake.success = True
    fake.output_path = str(tmp_path / "cube.fbx")
    fake.shape = "cube"
    fake.next_steps = ["stop PIE"]
    fake.error = None
    fake.to_dict.return_value = {
        "success": True,
        "output_path": fake.output_path,
        "shape": "cube",
        "next_steps": ["stop PIE"],
    }
    with patch("hephaestus_forge.dcc_server.export_primitive_fbx", return_value=fake):
        res = route_command(
            "blender.export_fbx",
            {"shape": "cube", "name": "cube", "project_root": str(tmp_path)},
        )
    assert res["success"] is True
    assert res["asset_paths"] == [fake.output_path]


def test_route_blender_exec_missing_script():
    res = route_command("blender.exec", {})
    assert res["success"] is False
    assert "script" in res["error"]


def test_dcc_client_command_posts_params(monkeypatch):
    captured = {}

    class FakeResp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return json.dumps({"success": True, "result_json": "{}"}).encode()

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        captured["body"] = json.loads(req.data.decode())
        return FakeResp()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    client = DccClient("http://127.0.0.1:8084")
    out = client.command("blender.scene_info", {"timeout": 10})
    assert out["success"] is True
    assert captured["url"].endswith("/v1/command")
    assert captured["body"]["command"] == "blender.scene_info"
    assert captured["body"]["params"]["timeout"] == 10


def test_dcc_online_false_when_down(monkeypatch):
    def boom(*a, **k):
        raise OSError("connection refused")

    monkeypatch.setattr("hephaestus_forge.dcc_client.DccClient.health", boom)
    ok, _, detail = dcc_online()
    assert ok is False
    assert "offline" in detail.lower() or "refused" in detail.lower() or "OSError" in detail


def test_cc5_unavailable_clear_error(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("hephaestus_forge.cc5_bridge.find_cc5", lambda env=None: None)
    monkeypatch.setattr("hephaestus_forge.cc5_bridge.find_rlpython", lambda env=None: None)
    res = export_character_fbx(character_name="Hero", project_root=tmp_path)
    assert res["success"] is False
    assert "cc5_unavailable" in (res.get("error") or "")


def test_resolve_fbx_path_latest(tmp_path: Path):
    export = tmp_path / ".hephaestus_forge" / "dcc_exports"
    export.mkdir(parents=True)
    older = export / "a.fbx"
    newer = export / "b.fbx"
    older.write_bytes(b"x")
    newer.write_bytes(b"y")
    import os
    import time

    os.utime(older, (time.time() - 100, time.time() - 100))
    path = resolve_fbx_path(project_root=tmp_path)
    assert path.name == "b.fbx"


def test_editor_import_fbx_posts_editor_api(monkeypatch, tmp_path: Path):
    fbx = tmp_path / "mesh.fbx"
    fbx.write_bytes(b"fbx")
    captured = {}

    monkeypatch.setattr(
        "hephaestus_forge.dcc_import.editor_online",
        lambda: (True, {}, "ok"),
    )

    def fake_post(base, command, params=None, timeout=10.0):
        captured["base"] = base
        captured["command"] = command
        captured["params"] = params
        return {"success": True, "result_json": '{"asset_path":"/Game/Hephaestus/DccImports/mesh"}'}

    monkeypatch.setattr("hephaestus_forge.dcc_import._post_command", fake_post)
    monkeypatch.setattr("hephaestus_forge.dcc_import.editor_api_base", lambda: "http://127.0.0.1:8766")
    res = editor_import_fbx(fbx)
    assert res["success"] is True
    assert captured["command"] == "editor.import_fbx"
    assert "mesh.fbx" in captured["params"]["source_path"]


@pytest.mark.skipif(
    find_cc5() is None,
    reason="CC5 not installed — live skip",
)
def test_live_cc5_detect_only():
    assert find_cc5() is not None


@pytest.mark.skipif(
    True,  # opt-in live Blender; enable by flipping when validating machines
    reason="live Blender smoke is opt-in",
)
def test_live_blender_export_smoke(tmp_path: Path):
    from hephaestus_forge.blender_bridge import export_primitive_fbx, find_blender

    path, _ = find_blender()
    if not path:
        pytest.skip("Blender not installed")
    result = export_primitive_fbx(shape="cube", name="DccSmoke", project_root=tmp_path)
    assert result.success
    assert Path(result.output_path).is_file()

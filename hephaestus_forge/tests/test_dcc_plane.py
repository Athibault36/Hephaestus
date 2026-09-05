# Copyright (c) 2024 HephaestusForge. All Rights Reserved.
"""Unit tests for DCC control plane (mocked HTTP + route handlers)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dcc_server import route_command, health  # noqa: E402
from dcc_client import DccClient, dcc_online  # noqa: E402
from cc5_bridge import export_character_fbx, find_cc5, find_rlpython  # noqa: E402
from dcc_import import resolve_fbx_path, editor_import_fbx  # noqa: E402


def test_health_honest_blender_flag():
    with patch("dcc_server.find_blender", return_value=(None, None)):
        with patch("dcc_server._cc5_status", return_value={"available": False}):
            h = health()
    assert h["ok"] is True
    assert h["ready"] is False
    assert h["blender"]["available"] is False


def test_health_ready_when_blender_found():
    with patch(
        "dcc_server.find_blender",
        return_value=("C:/Blender/blender.exe", "4.2.0"),
    ):
        with patch("dcc_server._cc5_status", return_value={"available": False}):
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
    with patch("dcc_server.export_primitive_fbx", return_value=fake):
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

    monkeypatch.setattr("dcc_client.DccClient.health", boom)
    ok, _, detail = dcc_online()
    assert ok is False
    assert "offline" in detail.lower() or "refused" in detail.lower() or "OSError" in detail


def test_cc5_unavailable_clear_error(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("cc5_bridge.find_cc5", lambda env=None: None)
    monkeypatch.setattr("cc5_bridge.find_rlpython", lambda env=None: None)
    res = export_character_fbx(character_name="Hero", project_root=tmp_path)
    assert res["success"] is False
    assert "cc5_unavailable" in (res.get("error") or "")


def test_install_cc5_openplugin_copies_template(tmp_path: Path, monkeypatch):
    from cc5_bridge import install_cc5_openplugin, openplugin_template_dir

    bin64 = tmp_path / "Bin64"
    bin64.mkdir()
    exe = bin64 / "CharacterCreator.exe"
    exe.write_bytes(b"x")
    template = openplugin_template_dir()
    assert (template / "main.py").is_file()

    monkeypatch.setattr("cc5_bridge.find_cc5", lambda env=None: str(exe))
    res = install_cc5_openplugin(force=True)
    assert res["ok"] is True
    dest = bin64 / "OpenPlugin" / "HephaestusExport" / "main.py"
    assert dest.is_file()
    assert "cc5_jobs" in dest.read_text(encoding="utf-8")

    skip = install_cc5_openplugin(force=False)
    assert skip["ok"] and skip.get("skipped")


def test_find_default_cc5_template(tmp_path: Path, monkeypatch):
    from cc5_bridge import find_default_cc5_template

    bin64 = tmp_path / "Bin64"
    bin64.mkdir()
    exe = bin64 / "CharacterCreator.exe"
    exe.write_bytes(b"x")
    default = tmp_path / "Program" / "Default"
    default.mkdir(parents=True)
    mannequin = default / "Mannequin_Male.ccAvatar"
    mannequin.write_bytes(b"avatar")
    monkeypatch.setattr("cc5_bridge.find_cc5", lambda env=None: str(exe))
    assert find_default_cc5_template() == str(mannequin)

    from cc5_bridge import _export_via_job_queue

    monkeypatch.setattr("cc5_bridge.cc5_jobs_dir", lambda: tmp_path)
    monkeypatch.setattr("cc5_bridge.ensure_cc5_running", lambda **k: {"ok": True, "launched": False})
    fbx = tmp_path / "Hero.fbx"
    res = _export_via_job_queue(character_name="Hero", fbx_path=fbx, timeout_seconds=0.2)
    assert res["success"] is False
    assert "cc5_job_timeout" in (res.get("error") or "")


def test_cc5_job_queue_success(monkeypatch, tmp_path: Path):
    from cc5_bridge import _export_via_job_queue

    monkeypatch.setattr("cc5_bridge.cc5_jobs_dir", lambda: tmp_path)
    monkeypatch.setattr("cc5_bridge.ensure_cc5_running", lambda **k: {"ok": True})

    fbx = tmp_path / "Hero.fbx"

    def write_result_soon(*a, **k):
        # Simulate OpenPlugin: after job file appears, write result + fbx
        import time as _t

        for _ in range(20):
            jobs = list(tmp_path.glob("*.job.json"))
            if jobs:
                job = jobs[0]
                fbx.write_bytes(b"fbx")
                result = job.with_name(job.name.replace(".job.json", ".result.json"))
                result.write_text('{"success": true}', encoding="utf-8")
                job.unlink(missing_ok=True)
                return
            _t.sleep(0.05)

    import threading

    threading.Thread(target=write_result_soon, daemon=True).start()
    res = _export_via_job_queue(character_name="Hero", fbx_path=fbx, timeout_seconds=3.0)
    assert res["success"] is True
    assert res["output_path"] == str(fbx)

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


def test_editor_import_fbx_posts_editor_command(monkeypatch, tmp_path: Path):
    fbx = tmp_path / "mesh.fbx"
    fbx.write_bytes(b"fbx")
    captured = {}

    monkeypatch.setattr(
        "dcc_import.editor_online",
        lambda: (True, {}, "ok"),
    )

    def fake_post(base, command, params=None, timeout=10.0):
        captured["base"] = base
        captured["command"] = command
        captured["params"] = params
        return {"success": True, "result_json": '{"asset_path":"/Game/Hephaestus/DccImports/mesh"}'}

    monkeypatch.setattr("dcc_import._post_command", fake_post)
    monkeypatch.setattr("dcc_import.editor_api_base", lambda: "http://127.0.0.1:8766")
    res = editor_import_fbx(fbx)
    assert res["success"] is True
    assert captured["command"] == "editor.import_fbx"
    assert "mesh.fbx" in captured["params"]["source_path"]


def test_pick_imported_asset_prefers_hero_over_materials():
    from dcc_import import pick_imported_asset_path

    paths = [
        "/Game/Hephaestus/DccImports/Std_Tongue_Pbr_Opacity.Std_Tongue_Pbr_Opacity",
        "/Game/Hephaestus/DccImports/Std_Skin_Head.Std_Skin_Head",
        "/Game/Hephaestus/DccImports/Hero.Hero",
        "/Game/Hephaestus/DccImports/Hero_Skeleton.Hero_Skeleton",
    ]
    chosen, skeletal = pick_imported_asset_path(
        paths,
        preferred_name="Hero",
        fallback=paths[0],
        import_as_skeletal=True,
    )
    assert chosen.endswith("Hero.Hero")
    assert skeletal is True


def test_pick_imported_asset_synthesizes_when_only_materials():
    from dcc_import import pick_imported_asset_path

    paths = [
        "/Game/Hephaestus/DccImports/Std_Tongue_Pbr_Opacity.Std_Tongue_Pbr_Opacity",
    ]
    chosen, skeletal = pick_imported_asset_path(
        paths,
        preferred_name="Hero",
        fallback=paths[0],
        import_as_skeletal=True,
    )
    assert chosen == "/Game/Hephaestus/DccImports/Hero.Hero"
    assert skeletal is True


def test_find_cc5_nested_layout(tmp_path: Path, monkeypatch):
    bin64 = tmp_path / "Character Creator 5" / "Character Creator 5" / "Bin64"
    bin64.mkdir(parents=True)
    exe = bin64 / "CharacterCreator.exe"
    py = bin64 / "CharacterCreatorpy.exe"
    exe.write_bytes(b"x")
    py.write_bytes(b"x")
    monkeypatch.setattr(
        "cc5_bridge._CC5_CANDIDATES",
        (exe,),
    )
    monkeypatch.setattr("cc5_bridge._RLPYTHON_CANDIDATES", ())
    monkeypatch.delenv("CC5_EXECUTABLE", raising=False)
    monkeypatch.delenv("RLPYTHON", raising=False)
    monkeypatch.delenv("CC5_RLPYTHON", raising=False)
    assert find_cc5() == str(exe)
    assert find_rlpython() == str(py)


@pytest.mark.skipif(
    find_cc5() is None,
    reason="CC5 not installed — live skip",
)
def test_live_cc5_detect_only():
    assert find_cc5() is not None
    assert find_rlpython() is not None


@pytest.mark.skipif(
    True,  # opt-in live Blender; enable by flipping when validating machines
    reason="live Blender smoke is opt-in",
)
def test_live_blender_export_smoke(tmp_path: Path):
    from blender_bridge import export_primitive_fbx, find_blender

    path, _ = find_blender()
    if not path:
        pytest.skip("Blender not installed")
    result = export_primitive_fbx(shape="cube", name="DccSmoke", project_root=tmp_path)
    assert result.success
    assert Path(result.output_path).is_file()

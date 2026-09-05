"""Unit tests for editor_control (mocked — no Unreal required)."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import editor_control  # noqa: E402


def test_resolve_uproject(tmp_path: Path):
    up = tmp_path / "Demo.uproject"
    up.write_text("{}", encoding="utf-8")
    assert editor_control.resolve_uproject(tmp_path) == up
    assert editor_control.resolve_uproject(up) == up


def test_open_editor_noop_when_already_matching(tmp_path: Path):
    up = tmp_path / "Demo.uproject"
    up.write_text("{}", encoding="utf-8")
    health = {
        "ok": True,
        "project_name": "Demo",
        "project_dir": str(tmp_path).replace("\\", "/") + "/",
        "port": 8766,
    }
    with patch("editor_control.editor_online", return_value=(True, health, "ok")):
        with patch("editor_control.editor_matches_project", return_value=(True, "match")):
            out = editor_control.open_editor(tmp_path)
    assert out["ok"] is True
    assert out["launched"] is False


def test_open_editor_raises_on_wrong_project(tmp_path: Path):
    up = tmp_path / "Demo.uproject"
    up.write_text("{}", encoding="utf-8")
    with patch("editor_control.editor_online", return_value=(True, {"ok": True}, "ok")):
        with patch(
            "editor_control.editor_matches_project",
            return_value=(False, "PIE is 'Other' but forge target is 'Demo'"),
        ):
            try:
                editor_control.open_editor(tmp_path)
                assert False, "expected RuntimeError"
            except RuntimeError as exc:
                assert "different project" in str(exc).lower() or "Other" in str(exc)


def test_bring_up_plays_when_editor_ready(tmp_path: Path):
    up = tmp_path / "Demo.uproject"
    up.write_text("{}", encoding="utf-8")
    health = {"ok": True, "project_name": "Demo", "project_dir": str(tmp_path)}
    with patch("editor_control.editor_online", return_value=(True, health, "ed")):
        with patch("editor_control.editor_matches_project", return_value=(True, "match")):
            with patch("editor_control.pie_online", return_value=(False, {}, "off")):
                with patch("editor_control.play", return_value={"success": True}):
                    with patch(
                        "editor_control.wait_for_pie",
                        return_value=(True, {"ok": True}, "PIE match"),
                    ):
                        out = editor_control.bring_up(tmp_path, open_if_needed=False)
    assert out["ok"] is True
    assert out["already_pie"] is False


def test_bring_down_stop_only():
    with patch("editor_control.editor_online", return_value=(True, {}, "ed")):
        with patch("editor_control.pie_online", return_value=(True, {}, "pie")):
            with patch("editor_control.stop", return_value={"success": True}):
                out = editor_control.bring_down(quit_editor_flag=False)
    assert out["ok"] is True
    assert out["quit_editor"] is None


def test_find_ue_root_from_env(tmp_path: Path, monkeypatch):
    editor = tmp_path / "Engine" / "Binaries" / "Win64"
    editor.mkdir(parents=True)
    (editor / "UnrealEditor.exe").write_bytes(b"x")
    monkeypatch.setenv("UE_PATH", str(tmp_path))
    assert editor_control.find_ue_root() == tmp_path.resolve()

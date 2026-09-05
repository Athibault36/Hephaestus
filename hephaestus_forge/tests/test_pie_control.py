"""Unit tests for pie_control (mocked HTTP — no UE required)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pie_control  # noqa: E402


class _FakeResp:
    def __init__(self, payload: dict, status: int = 200):
        self.status = status
        self._payload = payload

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_editor_online_true():
    health = {
        "ok": True,
        "service": "hephaestus-editor",
        "port": 8766,
        "pie_active": False,
        "plugin_version": "1.0.1",
    }
    with patch("pie_control.urllib.request.urlopen", return_value=_FakeResp(health)):
        ok, body, detail = pie_control.editor_online()
    assert ok is True
    assert body["service"] == "hephaestus-editor"
    assert "8766" in detail or "online" in detail


def test_editor_online_false_on_error():
    with patch("pie_control.urllib.request.urlopen", side_effect=OSError("refused")):
        ok, body, detail = pie_control.editor_online()
    assert ok is False
    assert body == {}
    assert "offline" in detail.lower() or "refused" in detail.lower()


def test_play_posts_editor_play():
    captured = {}

    def fake_urlopen(req, timeout=10.0):
        captured["url"] = getattr(req, "full_url", None) or req.get_full_url()
        captured["body"] = json.loads(req.data.decode("utf-8"))
        return _FakeResp({"success": True, "error": "", "pie_active": False})

    with patch("pie_control.urllib.request.urlopen", side_effect=fake_urlopen):
        out = pie_control.play()
    assert out["success"] is True
    assert captured["body"]["command"] == "editor.play"
    assert "/v1/command" in captured["url"]


def test_stop_prefers_editor_then_pie():
    # Editor online → stop via editor
    with patch("pie_control.editor_online", return_value=(True, {}, "ok")):
        with patch("pie_control._post_command", return_value={"success": True}) as post:
            out = pie_control.stop()
            assert out["success"] is True
            assert post.call_args[0][1] == "editor.stop"

    # Editor offline, PIE online → stop via PIE
    with patch("pie_control.editor_online", return_value=(False, {}, "off")):
        with patch("pie_control.pie_online", return_value=(True, {}, "pie")):
            with patch("pie_control._post_command", return_value={"success": True}) as post:
                out = pie_control.stop()
                assert out["success"] is True
                assert post.call_args[0][1] == "editor.stop"


def test_wait_for_pie_matches_project():
    health = {
        "ok": True,
        "project_name": "DemoGame",
        "project_dir": "C:/games/DemoGame/",
        "plugin_version": "1.0.1",
    }
    with patch("preflight_health.fetch_ue_health", return_value=health):
        with patch("preflight_health.pie_matches_project", return_value=(True, "match")):
            ok, body, detail = pie_control.wait_for_pie(Path("C:/games/DemoGame"), timeout_s=0.5, poll_s=0.01)
    assert ok is True
    assert body["project_name"] == "DemoGame"
    assert detail == "match"


def test_status_snapshot_keys():
    with patch("pie_control.editor_online", return_value=(True, {"ok": True}, "ed")):
        with patch("pie_control.pie_online", return_value=(False, {}, "pie off")):
            snap = pie_control.status_snapshot()
    assert snap["editor_online"] is True
    assert snap["pie_online"] is False
    assert "editor_api" in snap and "pie_api" in snap

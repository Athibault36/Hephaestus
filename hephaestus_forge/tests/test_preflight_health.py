import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from preflight_health import run_preflight  # noqa: E402
from version import BRIDGE_VERSION  # noqa: E402
from ue_agent_loop import WorldSnapshot  # noqa: E402
from goal_grader import grade_goal  # noqa: E402


def test_preflight_offline_ue(tmp_path):
    report = run_preflight("http://127.0.0.1:1", tmp_path)
    ue = next(c for c in report.checks if c.name == "ue_pie")
    assert ue.ok is False
    assert report.ready is False


def test_preflight_online_ue_with_key(tmp_path):
    forge = tmp_path / ".hephaestus_forge"
    forge.mkdir()
    plugin_dir = tmp_path / "Plugins" / "HephaestusBridge"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "HEPHAESTUS_BRIDGE_VERSION").write_text(f"{BRIDGE_VERSION}\n", encoding="utf-8")
    fake_resp = MagicMock()
    fake_resp.status = 200
    fake_resp.read.return_value = (
        f'{{"ok":true,"service":"hephaestus-remote","port":8765,"plugin_version":"{BRIDGE_VERSION}"}}'
    ).encode()
    fake_resp.__enter__ = lambda s: s
    fake_resp.__exit__ = MagicMock(return_value=False)
    with patch.dict("os.environ", {"NVIDIA_API_KEY": "nvapi-test"}):
        with patch("urllib.request.urlopen", return_value=fake_resp):
            with patch("ue_vision_planner.VisionLLMPlanner") as planner_cls:
                planner_cls.return_value.available = True
                planner_cls.return_value.model = "deepseek-ai/deepseek-v4-pro-0813"
                report = run_preflight("http://127.0.0.1:8765", tmp_path)
    assert report.ready is True
    assert any(c.name == "project" and c.ok for c in report.checks)


def test_grade_camera_framing_requires_set_view():
    snap = WorldSnapshot(lights=1, meshes=1, skeletal=1)
    g = grade_goal("Frame the character from the left", snap, memory=[])
    assert g.met is False
    assert any("camera" in m for m in g.missing)

    g2 = grade_goal(
        "Frame the character from the left",
        snap,
        memory=[{"kind": "set_view", "ok": True, "command": "world.set_view"}],
    )
    assert g2.met is True or "camera" not in " ".join(g2.missing)


def test_preflight_bridge_version_mismatch(tmp_path):
    forge = tmp_path / ".hephaestus_forge"
    forge.mkdir()
    plugin_dir = tmp_path / "Plugins" / "HephaestusBridge"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "HEPHAESTUS_BRIDGE_VERSION").write_text("0.1.0\n", encoding="utf-8")
    report = run_preflight("http://127.0.0.1:1", tmp_path)
    bridge = next(c for c in report.checks if c.name == "bridge_template")
    assert bridge.ok is False
    assert BRIDGE_VERSION in bridge.detail or "sync-plugin" in bridge.detail

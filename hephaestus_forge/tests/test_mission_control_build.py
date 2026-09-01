"""Mission Control build helpers."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from mission_control_build import (  # noqa: E402
    is_vite_build,
    prepare_mission_control_dist,
)


def test_is_vite_build_detects_assets(tmp_path):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "assets").mkdir()
    (dist / "index.html").write_text('<script src="/assets/index-abc.js"></script>', encoding="utf-8")
    assert is_vite_build(dist) is True


def test_is_vite_build_rejects_fallback(tmp_path):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html><body>inline</body></html>", encoding="utf-8")
    assert is_vite_build(dist) is False


def test_prepare_dist_keeps_vite_build(tmp_path):
    mc = tmp_path / "MissionControl" / "dist"
    mc.mkdir(parents=True)
    (mc / "assets").mkdir()
    (mc / "index.html").write_text('<script src="/assets/x.js"></script>', encoding="utf-8")
    calls: list[str] = []

    def _fallback(d: Path, api: str) -> None:
        calls.append("fallback")
        d.mkdir(parents=True, exist_ok=True)
        (d / "index.html").write_text("fallback", encoding="utf-8")

    out = prepare_mission_control_dist(tmp_path, "MissionControl", force_static=False, write_fallback=_fallback)
    assert out == mc
    assert calls == []
    assert "assets" in (mc / "index.html").read_text(encoding="utf-8")


def test_prepare_dist_writes_fallback_when_missing(tmp_path):
    calls: list[str] = []

    def _fallback(d: Path, api: str) -> None:
        calls.append(api)
        d.mkdir(parents=True, exist_ok=True)
        (d / "index.html").write_text("fallback", encoding="utf-8")

    out = prepare_mission_control_dist(tmp_path, "MissionControl", force_static=False, write_fallback=_fallback)
    assert (out / "index.html").read_text(encoding="utf-8") == "fallback"
    assert calls == [""]

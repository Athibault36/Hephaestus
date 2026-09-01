import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from e2e_check import run_e2e_check  # noqa: E402
from mission_control_build import is_vite_build  # noqa: E402


def test_e2e_offline_steps(tmp_path):
    forge = tmp_path / ".hephaestus_forge"
    forge.mkdir()
    report = run_e2e_check(tmp_path, live=False, sync=False)
    assert any(s.name == "factory_template" for s in report.steps)
    assert any(s.name == "target_plugin" for s in report.steps)


def test_is_vite_build_helper(tmp_path):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "assets").mkdir()
    (dist / "index.html").write_text('<script src="/assets/index.js"></script>', encoding="utf-8")
    assert is_vite_build(dist) is True

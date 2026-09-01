import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from doctor import run_doctor, rebuild_checklist  # noqa: E402
from locomotion_fallback import fallback_paths_for_mode  # noqa: E402


def test_rebuild_checklist_includes_sync():
    lines = rebuild_checklist(Path("C:/dev/MyGame"))
    assert any("sync-plugin" in line for line in lines)


def test_run_doctor_offline(tmp_path):
    forge = tmp_path / ".hephaestus_forge"
    forge.mkdir()
    report = run_doctor(tmp_path, live=False)
    assert report.checklist
    assert "e2e" in report.preflight or report.e2e


def test_locomotion_project_override(tmp_path):
    cfg = tmp_path / ".hephaestus_forge"
    cfg.mkdir()
    (cfg / "locomotion.json").write_text(
        '{"walk": ["/Game/Custom/Walk.Walk"]}',
        encoding="utf-8",
    )
    paths = fallback_paths_for_mode("walk", tmp_path)
    assert paths == ("/Game/Custom/Walk.Walk",)

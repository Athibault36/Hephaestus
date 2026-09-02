import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from e2e_check import run_e2e_check  # noqa: E402
from preflight_health import run_preflight  # noqa: E402
from doctor import run_doctor  # noqa: E402


def test_preflight_report_json_roundtrip(tmp_path):
    report = run_preflight("http://127.0.0.1:1", tmp_path)
    payload = report.to_dict()
    text = json.dumps(payload)
    loaded = json.loads(text)
    assert loaded["ready"] is False
    assert "checks" in loaded


def test_e2e_report_json_roundtrip(tmp_path):
    forge = tmp_path / ".hephaestus_forge"
    forge.mkdir()
    report = run_e2e_check(tmp_path, live=False)
    loaded = json.loads(json.dumps(report.to_dict()))
    assert "steps" in loaded
    assert any(s["name"] == "factory_template" for s in loaded["steps"])


def test_doctor_report_json_roundtrip(tmp_path):
    forge = tmp_path / ".hephaestus_forge"
    forge.mkdir()
    report = run_doctor(tmp_path, live=False)
    loaded = json.loads(json.dumps(report.to_dict()))
    assert "checklist" in loaded
    assert loaded["forge_version"] == loaded["bridge_version"]

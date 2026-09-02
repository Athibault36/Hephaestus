import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from operator_gate import run_operator_gate  # noqa: E402
from version import OPERATOR_MILESTONE  # noqa: E402


def test_operator_gate_offline(tmp_path):
    forge = tmp_path / ".hephaestus_forge"
    forge.mkdir()
    report = run_operator_gate(tmp_path, live=False)
    assert report.milestone == OPERATOR_MILESTONE
    assert any(s.name == "forge_version" for s in report.steps)
    payload = report.to_dict()
    assert payload["milestone"] == OPERATOR_MILESTONE

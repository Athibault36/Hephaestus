import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from autonomous_runner import run_autonomous_goal  # noqa: E402
from autonomous_suite import SUITE_SCENARIOS, run_autonomous_suite  # noqa: E402
from version import OPERATOR_MILESTONE  # noqa: E402


def test_autonomous_runner_requires_nim(monkeypatch):
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    monkeypatch.delenv("HEPHAESTUS_LLM_API_KEY", raising=False)
    fake_client = MagicMock()
    fake_client.health.return_value = {"ok": True}
    with patch("autonomous_runner.RemoteUeClient", return_value=fake_client):
        with patch("autonomous_runner.augment_goal_with_assets", return_value=("walk the dog", [], {})):
            with patch("autonomous_runner.VisionLLMPlanner") as planner_cls:
                planner_cls.return_value.available = False
                planner_cls.return_value.last_error = "no key"
                report = run_autonomous_goal("walk the dog", require_nim=True)
    assert report.ok is False
    assert report.llm_error
    assert "nim" in report.llm_error.lower() or "key" in report.llm_error.lower()


def test_suite_scenarios_cover_a_through_g():
    ids = {s.id for s in SUITE_SCENARIOS}
    assert "A" in ids and "B" in ids and "C" in ids and "D" in ids
    assert any(i.startswith("E") for i in ids)
    assert "F" in ids
    assert any(i.startswith("G") for i in ids)


def test_autonomous_suite_offline_infra(tmp_path):
    forge = tmp_path / ".hephaestus_forge"
    forge.mkdir()
    report = run_autonomous_suite(tmp_path, live=False, skip_nim=True, scenario_filter=["C", "D"])
    assert report.milestone == OPERATOR_MILESTONE
    assert len(report.steps) == 2
    assert report.steps[0].scenario_id == "C"

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agent_repair import maybe_repair_after_grade  # noqa: E402
from goal_grader import GradeResult  # noqa: E402


def test_maybe_repair_skipped_without_env(monkeypatch):
    monkeypatch.delenv("HEPHAESTUS_NIM_REPAIR", raising=False)
    loop = MagicMock()
    grade = GradeResult(met=False, score=0.0, summary="x", missing=["walk"])
    extra, out = maybe_repair_after_grade(loop, grade, "walk the dog")
    assert extra == []
    assert out is grade
    loop.run_until_goal.assert_not_called()


def test_maybe_repair_runs_when_enabled(monkeypatch):
    monkeypatch.setenv("HEPHAESTUS_NIM_REPAIR", "1")
    loop = MagicMock()
    loop.run_until_goal.return_value = ([], GradeResult(met=True, score=1.0, summary="ok", missing=[]))
    grade = GradeResult(met=False, score=0.0, summary="x", missing=["walk"])
    extra, out = maybe_repair_after_grade(loop, grade, "walk the dog")
    assert out.met is True
    loop.run_until_goal.assert_called_once()


def test_maybe_repair_heuristic_without_nim(monkeypatch):
    monkeypatch.delenv("HEPHAESTUS_NIM_REPAIR", raising=False)
    monkeypatch.setenv("HEPHAESTUS_HEURISTIC_REPAIR", "1")
    loop = MagicMock()
    loop.run_until_goal.return_value = ([], GradeResult(met=True, score=1.0, summary="ok", missing=[]))
    grade = GradeResult(met=False, score=0.0, summary="x", missing=["walk"])
    extra, out = maybe_repair_after_grade(loop, grade, "walk the dog")
    assert out.met is True
    loop.run_until_goal.assert_called_once()

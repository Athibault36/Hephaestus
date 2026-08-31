"""Tests for JSONL trajectory logging."""

import json
from pathlib import Path

from hephaestus_forge.runtime.logging_jsonl import JsonlTrajectoryLogger
from hephaestus_forge.runtime.orchestrator import TrajectoryEvent


def test_jsonl_logger_writes_session_and_events(tmp_path: Path):
    log_path = tmp_path / "trajectory.jsonl"
    with JsonlTrajectoryLogger(log_path, goal="test goal") as logger:
        logger.on_event(TrajectoryEvent("thought", "planning"))

    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 3
    start = json.loads(lines[0])
    event = json.loads(lines[1])
    end = json.loads(lines[2])
    assert start["kind"] == "session_start"
    assert start["goal"] == "test goal"
    assert event["kind"] == "trajectory"
    assert event["type"] == "thought"
    assert end["kind"] == "session_end"

"""Structured JSONL logging for agent trajectories (Phase 5 observability)."""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, TextIO


def _serialize(obj: Any) -> Any:
    if is_dataclass(obj) and not isinstance(obj, type):
        return asdict(obj)
    if isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_serialize(v) for v in obj]
    return obj


class JsonlTrajectoryLogger:
    """Append-only JSONL writer for :class:`~hephaestus_forge.runtime.orchestrator.TrajectoryEvent`."""

    def __init__(self, path: Path, *, goal: str = ""):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._file: Optional[TextIO] = None
        self._goal = goal

    def open(self) -> "JsonlTrajectoryLogger":
        self._file = self.path.open("a", encoding="utf-8")
        self.write("session_start", {"goal": self._goal})
        return self

    def write(self, kind: str, payload: Dict[str, Any]) -> None:
        if self._file is None:
            return
        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "kind": kind,
            **_serialize(payload),
        }
        self._file.write(json.dumps(record, ensure_ascii=False) + "\n")
        self._file.flush()

    def on_event(self, event: Any) -> None:
        data = event.to_dict() if hasattr(event, "to_dict") else {"content": str(event)}
        self.write("trajectory", data)

    def close(self) -> None:
        if self._file is not None:
            self.write("session_end", {})
            self._file.close()
            self._file = None

    def __enter__(self) -> "JsonlTrajectoryLogger":
        return self.open()

    def __exit__(self, *exc: Any) -> None:
        self.close()

# Copyright (c) 2024 HephaestusForge. All Rights Reserved.
"""In-memory agent session: goal, chat, and step memory."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Optional
from uuid import uuid4

SessionMode = Literal["cinematic", "gameplay", "auto"]


@dataclass
class ChatMessage:
    role: str  # user | assistant | system
    content: str
    ts: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class AgentSession:
    id: str = field(default_factory=lambda: uuid4().hex[:12])
    goal: str = ""
    mode: SessionMode = "auto"
    messages: list[ChatMessage] = field(default_factory=list)
    memory: list[dict[str, Any]] = field(default_factory=list)
    last_grade: dict[str, Any] = field(default_factory=dict)
    project_path: str = ""

    def add_user(self, text: str) -> None:
        text = text.strip()
        if not text:
            return
        self.messages.append(ChatMessage(role="user", content=text))
        if not self.goal:
            self.goal = text

    def add_assistant(self, text: str) -> None:
        self.messages.append(ChatMessage(role="assistant", content=text))

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "goal": self.goal,
            "mode": self.mode,
            "messages": [asdict(m) for m in self.messages[-80:]],
            "memory": self.memory[-40:],
            "last_grade": self.last_grade,
            "project_path": self.project_path,
        }

    def export_bundle(
        self,
        *,
        thoughts: Optional[list[dict[str, Any]]] = None,
        grade_history: Optional[list[dict[str, Any]]] = None,
        autonomous_report: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Full session export for observability / replay (schema v4)."""
        from version import BRIDGE_VERSION, FORGE_VERSION, OPERATOR_MILESTONE

        grades = list(grade_history or [])
        if self.last_grade and self.last_grade not in grades:
            grades.append(self.last_grade)
        bundle: dict[str, Any] = {
            "schema_version": 4,
            "operator_milestone": OPERATOR_MILESTONE,
            "forge_version": FORGE_VERSION,
            "bridge_version": BRIDGE_VERSION,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "session": self.to_dict(),
            "thoughts": thoughts or [],
            "grade_history": grades,
            "command_transcript": self.memory,
        }
        if autonomous_report:
            bundle["autonomous_report"] = autonomous_report
        return bundle


def _sessions_dir(project_root: Optional[Path] = None) -> Path:
    if project_root:
        base = project_root / ".hephaestus_forge" / "sessions"
    else:
        home = os.environ.get("HEPHAESTUS_HOME")
        base = Path(home) if home else Path.home() / ".hephaestus"
        base = base / "sessions"
    base.mkdir(parents=True, exist_ok=True)
    return base


class SessionStore:
    """Per-process session store with optional disk persistence."""

    def __init__(self, project_root: Optional[Path] = None):
        self.project_root = project_root
        self._active: Optional[AgentSession] = None
        self._dir = _sessions_dir(project_root)

    def active(self) -> AgentSession:
        if self._active is None:
            self._active = self._load_latest() or AgentSession(
                project_path=str(self.project_root) if self.project_root else "",
            )
        return self._active

    def reset(self, goal: str = "", mode: SessionMode = "auto") -> AgentSession:
        self._active = AgentSession(
            goal=goal.strip(),
            mode=mode,
            project_path=str(self.project_root) if self.project_root else "",
        )
        self.save(self._active)
        return self._active

    def save(self, session: AgentSession) -> None:
        path = self._dir / f"{session.id}.json"
        path.write_text(json.dumps(session.to_dict(), indent=2) + "\n", encoding="utf-8")

    def _load_latest(self) -> Optional[AgentSession]:
        files = sorted(self._dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not files:
            return None
        try:
            raw = json.loads(files[0].read_text(encoding="utf-8"))
            msgs = [ChatMessage(**m) for m in raw.get("messages", [])]
            return AgentSession(
                id=raw.get("id", uuid4().hex[:12]),
                goal=raw.get("goal", ""),
                mode=raw.get("mode", "auto"),
                messages=msgs,
                memory=raw.get("memory", []),
                last_grade=raw.get("last_grade", {}),
                project_path=raw.get("project_path", ""),
            )
        except (json.JSONDecodeError, OSError, TypeError):
            return None

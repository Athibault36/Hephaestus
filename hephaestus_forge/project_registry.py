# Copyright (c) 2024 HephaestusForge. All Rights Reserved.
"""User-level registry of UE projects that use Hephaestus (factory is repo-local)."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


def _registry_path() -> Path:
    base = os.environ.get("HEPHAESTUS_HOME")
    if base:
        root = Path(base)
    else:
        root = Path.home() / ".hephaestus"
    root.mkdir(parents=True, exist_ok=True)
    return root / "projects.json"


@dataclass
class RegisteredProject:
    path: str
    name: str = ""
    added_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    last_opened: str = ""

    def resolved(self) -> Path:
        return Path(self.path).expanduser().resolve()

    def is_valid(self) -> bool:
        p = self.resolved()
        return p.is_dir() and (p / ".hephaestus_forge").is_dir()


@dataclass
class ProjectRegistry:
    projects: list[RegisteredProject] = field(default_factory=list)
    active_path: str = ""

    @classmethod
    def load(cls) -> ProjectRegistry:
        path = _registry_path()
        if not path.exists():
            return cls()
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return cls()
        projects = [RegisteredProject(**p) for p in raw.get("projects", [])]
        return cls(projects=projects, active_path=raw.get("active_path", ""))

    def save(self) -> None:
        path = _registry_path()
        payload = {
            "projects": [asdict(p) for p in self.projects],
            "active_path": self.active_path,
        }
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    def add(self, project_root: Path, name: Optional[str] = None) -> RegisteredProject:
        project_root = project_root.expanduser().resolve()
        if not (project_root / ".hephaestus_forge").is_dir():
            raise ValueError(f"Not a Hephaestus UE project (missing .hephaestus_forge): {project_root}")
        entry = RegisteredProject(
            path=str(project_root),
            name=name or project_root.name,
            last_opened=datetime.now(timezone.utc).isoformat(),
        )
        self.projects = [p for p in self.projects if p.resolved() != project_root]
        self.projects.insert(0, entry)
        self.active_path = str(project_root)
        self.save()
        return entry

    def set_active(self, project_root: Path) -> None:
        project_root = project_root.expanduser().resolve()
        for p in self.projects:
            if p.resolved() == project_root:
                p.last_opened = datetime.now(timezone.utc).isoformat()
                self.active_path = str(project_root)
                self.save()
                return
        raise ValueError(f"Project not registered: {project_root}")

    def active(self) -> Optional[Path]:
        if not self.active_path:
            return None
        p = Path(self.active_path).expanduser().resolve()
        if p.is_dir() and (p / ".hephaestus_forge").is_dir():
            return p
        return None

    def list_valid(self) -> list[RegisteredProject]:
        valid: list[RegisteredProject] = []
        for p in self.projects:
            if p.is_valid():
                valid.append(p)
        return valid

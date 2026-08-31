"""Lightweight coding agent backed by local llama.cpp OpenAI API."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

import httpx


class DevAgent:
    def __init__(self, base_url: str, repo_root: Path, model: str = "local"):
        self.base_url = base_url.rstrip("/")
        self.repo_root = repo_root.resolve()
        self.model = model

    def _system_prompt(self) -> str:
        persona = self.repo_root / "hephaestus_forge" / "forge_config" / "config.yaml"
        extra = ""
        forge_persona = self.repo_root / ".hephaestus_forge" / "agent_persona.md"
        if forge_persona.exists():
            extra = forge_persona.read_text(encoding="utf-8")[:6000]
        return (
            "You are HEPHAESTUS in GPU dev mode. You program the HephaestusForge agent factory "
            "and HephaestusBridge UE5.8 plugin. Output concrete code changes as fenced blocks "
            "with the filepath on the first line, e.g. ```python:hephaestus_forge/forge.py\n...\n```\n"
            "Prefer minimal, correct diffs. No UE editor on this machine — focus on Python/C++/TS tooling.\n\n"
            + extra
        )

    def _repo_context(self, max_chars: int = 12000) -> str:
        files = [
            self.repo_root / "hephaestus_forge" / "forge.py",
            self.repo_root / "hephaestus_forge" / "cloud" / "brev_client.py",
        ]
        chunks = []
        used = 0
        for f in files:
            if not f.exists():
                continue
            text = f.read_text(encoding="utf-8", errors="replace")
            rel = f.relative_to(self.repo_root).as_posix()
            piece = f"### {rel}\n{text[:4000]}\n"
            if used + len(piece) > max_chars:
                break
            chunks.append(piece)
            used += len(piece)
        return "\n".join(chunks)

    def chat(self, task: str, temperature: float = 0.2, max_tokens: int = 4096) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": self._system_prompt()},
                {
                    "role": "user",
                    "content": f"Repository context:\n{self._repo_context()}\n\nTask:\n{task}",
                },
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        resp = httpx.post(f"{self.base_url}/chat/completions", json=payload, timeout=600.0)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]

    def apply_edits(self, response: str, dry_run: bool = False) -> list[str]:
        """Parse ```lang:path blocks and write files."""
        pattern = re.compile(r"```(?:\w+)?:([^\n`]+)\n(.*?)```", re.DOTALL)
        applied = []
        for match in pattern.finditer(response):
            rel_path = match.group(1).strip()
            content = match.group(2)
            if rel_path.startswith("/") or ".." in rel_path:
                continue
            dest = self.repo_root / rel_path
            if dry_run:
                applied.append(f"[dry-run] {rel_path}")
            else:
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(content if content.endswith("\n") else content + "\n", encoding="utf-8")
                applied.append(rel_path)
        return applied

    def run_task(self, task: str, apply: bool = False) -> tuple[str, list[str]]:
        response = self.chat(task)
        edits = self.apply_edits(response, dry_run=not apply)
        return response, edits

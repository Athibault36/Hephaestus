# Copyright (c) 2024 HephaestusForge. All Rights Reserved.
"""
Run Nemotron-3 Ultra and Nemotron-3.5 Lightning in parallel for coding tasks.

Ultra → architecture / plan / review
Lightning → concrete implementation draft

Both share the same NIM base URL and NVIDIA_API_KEY.
"""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass, field
from typing import Any, Optional

import httpx

try:
    from hephaestus_forge.cloud.nim_client import DEFAULT_CHAT_MODEL, DEFAULT_FAST_MODEL
except ImportError:  # script / package layout
    from cloud.nim_client import DEFAULT_CHAT_MODEL, DEFAULT_FAST_MODEL  # type: ignore

DEFAULT_NIM_URL = "https://integrate.api.nvidia.com/v1"

ULTRA_SYSTEM = """You are HEPHAESTUS Ultra (Nemotron-3 Ultra).
Produce a concise architecture / plan for the coding task.
Output markdown with: Goal, Approach, Files to touch, Risks, Acceptance checks.
Do not dump full file bodies unless a tiny stub is essential."""

LIGHTNING_SYSTEM = """You are HEPHAESTUS Lightning (Nemotron-3.5 Lightning).
Produce a concrete implementation draft for the coding task.
Prefer complete file patches using fenced blocks marked with paths, e.g.
```python:hephaestus_forge/foo.py
...
```
Keep changes minimal and match existing project style."""


@dataclass
class ParallelResult:
    ultra_model: str
    lightning_model: str
    ultra_text: str
    lightning_text: str
    ultra_error: str = ""
    lightning_error: str = ""
    merged_markdown: str = ""
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return bool(self.ultra_text or self.lightning_text)


class ParallelNemotronCoder:
    """Concurrent Ultra + Lightning chat completions against NVIDIA NIM."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = DEFAULT_NIM_URL,
        ultra_model: str = DEFAULT_CHAT_MODEL,
        lightning_model: str = DEFAULT_FAST_MODEL,
        timeout: float = 180.0,
    ):
        self.api_key = (
            api_key
            or os.environ.get("NVIDIA_API_KEY")
            or os.environ.get("HEPHAESTUS_LLM_API_KEY")
            or ""
        )
        self.base_url = base_url.rstrip("/")
        self.ultra_model = ultra_model
        self.lightning_model = lightning_model
        self.timeout = timeout

    def available(self) -> bool:
        return bool(self.api_key)

    async def run(self, task: str, context: str = "") -> ParallelResult:
        user = task if not context else f"{task}\n\n## Context\n{context}"
        ultra_task = asyncio.create_task(
            self._complete(self.ultra_model, ULTRA_SYSTEM, user)
        )
        lightning_task = asyncio.create_task(
            self._complete(self.lightning_model, LIGHTNING_SYSTEM, user)
        )
        (ultra_text, ultra_err), (light_text, light_err) = await asyncio.gather(
            ultra_task, lightning_task
        )
        merged = self._merge(task, ultra_text, light_text, ultra_err, light_err)
        return ParallelResult(
            ultra_model=self.ultra_model,
            lightning_model=self.lightning_model,
            ultra_text=ultra_text,
            lightning_text=light_text,
            ultra_error=ultra_err,
            lightning_error=light_err,
            merged_markdown=merged,
            raw={"task": task},
        )

    def run_sync(self, task: str, context: str = "") -> ParallelResult:
        return asyncio.run(self.run(task, context=context))

    async def _complete(self, model: str, system: str, user: str) -> tuple[str, str]:
        payload = {
            "model": model,
            "temperature": 0.2,
            "max_tokens": 4096,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "chat_template_kwargs": {
                "enable_thinking": False,
                "force_nonempty_content": True,
            },
        }
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                )
                if resp.status_code >= 400:
                    return "", f"HTTP {resp.status_code}: {resp.text[:400]}"
                data = resp.json()
                msg = data["choices"][0]["message"]["content"]
                if isinstance(msg, list):
                    msg = "".join(
                        p.get("text", "") if isinstance(p, dict) else str(p) for p in msg
                    )
                return str(msg), ""
        except Exception as exc:
            return "", f"{type(exc).__name__}: {exc}"

    @staticmethod
    def _merge(
        task: str,
        ultra: str,
        lightning: str,
        ultra_err: str,
        light_err: str,
    ) -> str:
        parts = [
            f"# Parallel Nemotron coding result",
            f"",
            f"**Task:** {task}",
            f"",
            f"## Ultra ({DEFAULT_CHAT_MODEL})",
        ]
        parts.append(ultra if ultra else f"_Error:_ {ultra_err or 'empty'}")
        parts.extend(["", f"## Lightning ({DEFAULT_FAST_MODEL})"])
        parts.append(lightning if lightning else f"_Error:_ {light_err or 'empty'}")
        parts.append("")
        return "\n".join(parts)


def parallel_code(task: str, context: str = "") -> ParallelResult:
    """Sync entrypoint for CLI / scripts."""
    return ParallelNemotronCoder().run_sync(task, context=context)

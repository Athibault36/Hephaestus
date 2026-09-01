# Copyright (c) 2024 HephaestusForge. All Rights Reserved.
"""Optional orchestrator backends for agent goals."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable, Optional

AvatarFn = Callable[[str, Optional[int], Optional[str]], None]
ThoughtFn = Callable[[str, str, dict[str, Any]], None]


def run_agent(
    message: str,
    *,
    project_root: Optional[Path] = None,
    remote_api: str = "http://127.0.0.1:8765",
    max_steps: int = 20,
    mode: str = "auto",
    reset: bool = False,
    on_thought: Optional[ThoughtFn] = None,
    on_avatar: Optional[AvatarFn] = None,
) -> dict[str, Any]:
    """
    Dispatch to the configured orchestrator.

    HEPHAESTUS_ORCHESTRATOR=langgraph uses the phased LangGraph runner when available;
    otherwise defaults to agent_chat.run_chat.
    """
    backend = (os.environ.get("HEPHAESTUS_ORCHESTRATOR") or "default").strip().lower()
    if backend == "langgraph":
        from langgraph_runner import run_langgraph_goal

        return run_langgraph_goal(
            message,
            project_root=project_root,
            remote_api=remote_api,
            max_steps=max_steps,
            mode=mode,
            reset=reset,
            on_thought=on_thought,
            on_avatar=on_avatar,
        )

    from agent_chat import run_chat

    return run_chat(
        message,
        project_root=project_root,
        remote_api=remote_api,
        max_steps=max_steps,
        mode=mode,
        reset=reset,
        on_thought=on_thought,
        on_avatar=on_avatar,
    )

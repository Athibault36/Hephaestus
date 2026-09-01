# Copyright (c) 2024 HephaestusForge. All Rights Reserved.
"""Chat-driven agent runs for Mission Control."""

from __future__ import annotations

import re
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable, Optional

from agent_asset import augment_goal_with_assets, search_project_assets, spawn_asset_in_view
from agent_session import AgentSession, SessionStore
from goal_grader import grade_goal
from ue_agent_loop import ObserveActLoop, RemoteUeClient
from ue_vision_planner import VisionLLMPlanner

AvatarFn = Callable[[str, Optional[int], Optional[str]], None]
ThoughtFn = Callable[[str, str, dict[str, Any]], None]

# One store per project path (in-process)
_STORES: dict[str, SessionStore] = {}


from locomotion_fallback import infer_locomotion_mode

_DIRECT_LOCOMOTION = re.compile(
    r"^play\s+(idle|walk|run)\s+(?:animation\s+)?on\s+(/Temp/\S+)\s*$",
    re.IGNORECASE,
)
_DIRECT_AUDIO = re.compile(
    r"^play\s+(?:test\s+)?audio(?:\s+clock\s+(\S+))?\s*$",
    re.IGNORECASE,
)
_DIRECT_SEARCH = re.compile(
    r"^search\s+assets?(?:\s+for)?\s+(.+)$",
    re.IGNORECASE,
)


def _try_direct_locomotion(message: str, client: RemoteUeClient) -> Optional[dict[str, Any]]:
    match = _DIRECT_LOCOMOTION.match((message or "").strip())
    if not match:
        return None
    mode = match.group(1).lower()
    actor_path = match.group(2)
    result = client.command({
        "command": "animation.play_locomotion",
        "params": {"actor_path": actor_path, "mode": mode, "loop": True},
    })
    ok = bool(result.get("success"))
    reply = (
        f"Playing {mode} on {actor_path}."
        if ok
        else f"Could not play {mode} on {actor_path}: {result.get('error', 'command failed')}"
    )
    return {
        "ok": ok,
        "reply": reply,
        "grade": {
            "met": ok,
            "score": 1.0 if ok else 0.0,
            "summary": reply,
            "missing": [] if ok else ["animation not playing"],
        },
        "planner": "direct_locomotion",
        "llm_available": False,
        "llm_error": "",
        "asset_matches": [],
        "asset_meta": {"direct_locomotion": mode, "actor_path": actor_path},
        "thoughts": [],
        "steps": [],
    }


def _try_direct_audio(message: str, client: RemoteUeClient) -> Optional[dict[str, Any]]:
    match = _DIRECT_AUDIO.match((message or "").strip())
    if not match:
        return None
    clock = (match.group(1) or "test").strip()
    result = client.command({
        "command": "audio.play_quartz",
        "params": {"clock": clock, "timeline": "default"},
    })
    ok = bool(result.get("success"))
    reply = (
        f"Played test audio (clock={clock})."
        if ok
        else f"Audio command failed: {result.get('error', 'unknown')}"
    )
    return {
        "ok": ok,
        "reply": reply,
        "grade": {
            "met": ok,
            "score": 1.0 if ok else 0.0,
            "summary": reply,
            "missing": [] if ok else ["audio not played"],
        },
        "planner": "direct_audio",
        "llm_available": False,
        "llm_error": "",
        "asset_matches": [],
        "asset_meta": {"direct_audio": clock},
        "thoughts": [],
        "steps": [],
    }


def _try_direct_search(message: str, client: RemoteUeClient) -> Optional[dict[str, Any]]:
    match = _DIRECT_SEARCH.match((message or "").strip())
    if not match:
        return None
    query = match.group(1).strip()
    paths = search_project_assets(client, query, limit=12)
    if paths:
        reply = "Asset matches:\n" + "\n".join(f"- {p}" for p in paths)
        ok = True
        grade_met = True
        missing: list[str] = []
    else:
        reply = f"No /Game assets matched '{query}'."
        ok = False
        grade_met = False
        missing = ["named asset not spawned yet"]
    return {
        "ok": ok,
        "reply": reply,
        "grade": {
            "met": grade_met,
            "score": 1.0 if grade_met else 0.0,
            "summary": reply,
            "missing": missing,
        },
        "planner": "direct_search",
        "llm_available": False,
        "llm_error": "",
        "asset_matches": paths,
        "asset_meta": {"search_query": query},
        "thoughts": [],
        "steps": [],
    }


def get_store(project_root: Optional[Path] = None) -> SessionStore:
    key = str(project_root.resolve()) if project_root else ""
    if key not in _STORES:
        _STORES[key] = SessionStore(project_root=project_root)
    return _STORES[key]


def run_chat(
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
    store = get_store(project_root)
    if reset:
        session = store.reset(goal=message.strip(), mode=mode if mode in ("cinematic", "gameplay", "auto") else "auto")  # type: ignore[arg-type]
    else:
        session = store.active()
        session.add_user(message)
        if mode in ("cinematic", "gameplay", "auto"):
            session.mode = mode  # type: ignore[assignment]

    goal = session.goal or message.strip()
    bare_asset = re.match(r"^(/Game/\S+)$", message.strip())
    client = RemoteUeClient(remote_api, timeout=60.0)

    if bare_asset:
        spawn_results = spawn_asset_in_view(client, bare_asset.group(1))
        ok = all(r.get("success") for r in spawn_results) if spawn_results else False
        reply = (
            f"Spawned {bare_asset.group(1)} in front of the camera."
            if ok
            else f"Tried to spawn {bare_asset.group(1)} but a command failed."
        )
        session.add_assistant(reply)
        store.save(session)
        return {
            "ok": ok,
            "reply": reply,
            "goal": goal,
            "grade": {"met": ok, "score": 1.0 if ok else 0.0, "summary": reply, "missing": []},
            "planner": "direct_spawn",
            "llm_available": False,
            "llm_error": "",
            "asset_matches": [bare_asset.group(1)],
            "asset_meta": {"direct_spawn": True},
            "session": session.to_dict(),
            "thoughts": [],
            "steps": [],
        }

    direct_loco = _try_direct_locomotion(message, client)
    if direct_loco:
        session.memory.append({
            "kind": "play_locomotion",
            "command": "animation.play_locomotion",
            "actor_path": direct_loco["asset_meta"].get("actor_path"),
            "ok": direct_loco["ok"],
        })
        session.add_assistant(direct_loco["reply"])
        session.last_grade = direct_loco["grade"]
        store.save(session)
        return {
            **direct_loco,
            "goal": goal,
            "session": session.to_dict(),
        }

    direct_audio = _try_direct_audio(message, client)
    if direct_audio:
        session.memory.append({"command": "audio.play_quartz", "ok": direct_audio["ok"]})
        session.add_assistant(direct_audio["reply"])
        session.last_grade = direct_audio["grade"]
        store.save(session)
        return {**direct_audio, "goal": goal, "session": session.to_dict()}

    direct_search = _try_direct_search(message, client)
    if direct_search:
        session.add_assistant(direct_search["reply"])
        session.last_grade = direct_search["grade"]
        store.save(session)
        return {**direct_search, "goal": goal, "session": session.to_dict()}

    if session.mode == "cinematic":
        goal = f"[cinematic mode] {goal}"
    elif session.mode == "gameplay":
        goal = f"[gameplay mode] {goal}"

    goal, asset_matches, asset_meta = augment_goal_with_assets(client, goal)
    if len(asset_matches) == 1 and "direct_spawn" not in asset_meta:
        try:
            spawn_asset_in_view(client, asset_matches[0])
            asset_meta["prefetch_spawn"] = asset_matches[0]
        except Exception:
            pass
    thoughts: list[dict[str, Any]] = []

    def _thought(kind: str, content: str, metadata: dict[str, Any]) -> None:
        thoughts.append({"kind": kind, "content": content, "metadata": metadata})
        if on_thought:
            on_thought(kind, content, metadata)

    llm = VisionLLMPlanner(goal=goal, asset_hints=asset_matches)
    use_llm = llm.available
    loop = ObserveActLoop(
        client=client,
        on_thought=_thought,
        on_avatar=on_avatar or (lambda *a, **k: None),
        planner=(llm.decide if use_llm else None),
        goal=goal,
        asset_hints=asset_matches,
    )
    loop.memory = list(session.memory)

    _thought("plan", f"Starting: {goal[:200]}", {"mode": session.mode})
    step_budget = max(max_steps, 16) if asset_matches else max_steps
    results, grade = loop.run_until_goal(max_steps=step_budget)
    try:
        from agent_repair import maybe_repair_after_grade

        extra_results, grade = maybe_repair_after_grade(loop, grade, goal, on_thought=_thought)
        if extra_results:
            results.extend(extra_results)
    except ImportError:
        pass
    session.memory = loop.memory
    session.last_grade = {
        "met": grade.met,
        "score": grade.score,
        "summary": grade.summary,
        "missing": grade.missing,
    }

    if grade.met:
        reply = f"Done. {grade.summary}"
    elif grade.missing and "needs concrete criteria or asset path" in grade.missing:
        if asset_matches:
            reply = (
                f"I found assets in your project that might match, but need a pick or clearer ask:\n"
                + "\n".join(f"- {p}" for p in asset_matches[:8])
                + f"\n\n{grade.summary}"
            )
        else:
            reply = (
                f"I can't deliver '{session.goal or message}' yet — no matching /Game asset found. "
                f"{grade.summary}"
            )
    elif not use_llm:
        reply = (
            f"I used the offline heuristic (DeepSeek unavailable — set NVIDIA_API_KEY). "
            f"{grade.summary}"
        )
    elif llm.last_error:
        reply = f"Hit an LLM error: {llm.last_error}. {grade.summary}"
    else:
        reply = f"Still working toward your goal. {grade.summary}"

    session.add_assistant(reply)
    store.save(session)

    return {
        "ok": grade.met and all(r.ok for r in results) if results else False,
        "reply": reply,
        "goal": goal,
        "grade": session.last_grade,
        "planner": llm.model if use_llm else "heuristic",
        "llm_available": use_llm,
        "llm_error": llm.last_error or ("" if use_llm else "NVIDIA_API_KEY not set"),
        "vision_caption": llm.last_vision_caption or "",
        "asset_matches": asset_matches,
        "asset_meta": asset_meta,
        "session": session.to_dict(),
        "thoughts": thoughts[-40:],
        "steps": [
            {
                "step": r.step,
                "kind": r.action.kind,
                "reason": r.action.reason,
                "ok": r.ok,
                "lights": r.reobservation.lights,
                "meshes": r.reobservation.meshes,
            }
            for r in results
        ],
    }

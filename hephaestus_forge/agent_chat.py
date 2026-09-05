# Copyright (c) 2024 HephaestusForge. All Rights Reserved.
"""Chat-driven agent runs for Mission Control."""

from __future__ import annotations

import re
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable, Optional

from agent_asset import search_project_assets, spawn_asset_in_view
from agent_session import AgentSession, SessionStore
from ue_agent_loop import RemoteUeClient

try:
    from agent_dcc import try_direct_dcc_author
except ImportError:
    from hephaestus_forge.agent_dcc import try_direct_dcc_author  # type: ignore

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
    params: dict[str, Any] = {"actor_path": actor_path, "mode": mode, "loop": True}
    # Prefer a project walk/idle/run AnimSequence when mannequin fallbacks are missing.
    anim_hits = search_project_assets(client, mode, asset_class="AnimSequence", limit=8)
    if not anim_hits:
        anim_hits = [
            p for p in search_project_assets(client, mode, limit=12)
            if "anim" in p.lower() or p.lower().endswith(f"_{mode}.{mode}") or f"_{mode}." in p.lower()
        ]
    if anim_hits:
        params["anim_path"] = anim_hits[0]
    result = client.command({
        "command": "animation.play_locomotion",
        "params": params,
    })
    if not result.get("success") and params.get("anim_path"):
        result = client.command({
            "command": "animation.play_sequence",
            "params": {
                "actor_path": actor_path,
                "anim_path": params["anim_path"],
                "loop": True,
            },
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
        "asset_meta": {
            "direct_locomotion": mode,
            "actor_path": actor_path,
            "anim_path": params.get("anim_path", ""),
        },
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

    direct_dcc = try_direct_dcc_author(message, project_root=project_root)
    if direct_dcc:
        session.memory.append({
            "kind": "dcc_author",
            "shape": (direct_dcc.get("asset_meta") or {}).get("dcc_shape"),
            "ok": direct_dcc["ok"],
            "asset_path": (direct_dcc.get("asset_matches") or [None])[0],
        })
        session.add_assistant(direct_dcc["reply"])
        session.last_grade = direct_dcc["grade"]
        store.save(session)
        return {**direct_dcc, "goal": goal, "session": session.to_dict()}

    if session.mode == "cinematic":
        goal = f"[cinematic mode] {goal}"
    elif session.mode == "gameplay":
        goal = f"[gameplay mode] {goal}"

    try:
        from autonomous_runner import run_autonomous_goal
    except ImportError:
        from hephaestus_forge.autonomous_runner import run_autonomous_goal  # type: ignore

    report = run_autonomous_goal(
        goal,
        project_root=project_root,
        remote_api=remote_api,
        max_steps=max_steps,
        repair=True,
        mode="auto",
        require_nim=True,
        session_memory=list(session.memory),
        on_thought=on_thought,
        on_avatar=on_avatar,
    )
    session.memory = report.memory
    session.last_grade = report.grade
    session.last_autonomous_report = report.to_dict()

    if report.ok:
        reply = f"Done. {report.grade.get('summary', '')}"
    elif report.grade.get("missing") and "needs concrete criteria or asset path" in report.grade.get("missing", []):
        if report.asset_matches:
            reply = (
                "I found assets in your project that might match, but need a pick or clearer ask:\n"
                + "\n".join(f"- {p}" for p in report.asset_matches[:8])
                + f"\n\n{report.grade.get('summary', '')}"
            )
        else:
            reply = (
                f"I can't deliver '{session.goal or message}' yet — no matching /Game asset found. "
                f"{report.grade.get('summary', '')}"
            )
    elif not report.llm_available:
        reply = f"NIM planner required: {report.llm_error}. {report.grade.get('summary', '')}"
    elif report.llm_error:
        reply = f"Hit an LLM error: {report.llm_error}. {report.grade.get('summary', '')}"
    else:
        reply = f"Still working toward your goal. {report.grade.get('summary', '')}"

    session.add_assistant(reply)
    store.save(session)

    return {
        "ok": report.ok,
        "reply": reply,
        "goal": report.goal,
        "grade": session.last_grade,
        "planner": report.planner,
        "llm_available": report.llm_available,
        "llm_error": report.llm_error,
        "vision_caption": "",
        "asset_matches": report.asset_matches,
        "asset_meta": report.asset_meta,
        "session": session.to_dict(),
        "thoughts": report.thoughts,
        "steps": report.steps,
        "autonomous_report": report.to_dict(),
    }

# Copyright (c) 2024 HephaestusForge. All Rights Reserved.
"""
Agent path: author a Blender primitive FBX via DCC :8084, then import/spawn in PIE.

Plain-language goals like "make a cube and put it in the scene" should deliver
in-viewport without the operator running forge blender / dcc-import by hand.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Optional

try:
    from blender_bridge import PRIMITIVE_SHAPES
except ImportError:
    from hephaestus_forge.blender_bridge import PRIMITIVE_SHAPES  # type: ignore

# make/create/export a cube|sphere|... (prop|mesh)? and optionally place in scene/PIE
_DCC_AUTHOR = re.compile(
    r"\b(?:make|create|author|export|build)\b.{0,40}\b("
    + "|".join(re.escape(s) for s in PRIMITIVE_SHAPES)
    + r"|sphere|box)\b",
    re.IGNORECASE,
)
_CHARACTER_AUTHOR = re.compile(
    r"\b(?:make|create|export|author)\b.{0,40}\b(?:character|avatar|cc5|humanoid)\b"
    r"|\bcc5\b.{0,20}\bexport\b",
    re.IGNORECASE,
)
_PLACE_IN_SCENE = re.compile(
    r"\b(?:put|place|spawn|drop|import)\b.{0,40}\b(?:scene|pie|viewport|world|shot|view)\b"
    r"|\bin\s+(?:the\s+)?(?:scene|pie|viewport|world)\b"
    r"|\binto\s+(?:ue|unreal|pie)\b",
    re.IGNORECASE,
)
_EXPORT_ONLY = re.compile(
    r"\b(?:export|save)\b.{0,30}\b(?:fbx|blender)\b|\bblender\b.{0,30}\bexport\b",
    re.IGNORECASE,
)
_WANT_FRAME = re.compile(
    r"\b(?:frame|framing|shot|cinematic|look\s*at|camera)\b",
    re.IGNORECASE,
)
_WANT_SEQUENCE_SHOT = re.compile(
    r"\b(?:create\s+(?:a\s+)?shot|level\s*sequence|sequencer)\b",
    re.IGNORECASE,
)
_WANT_SPIN = re.compile(
    r"\b(?:spin|rotate|turn|twirl)\b",
    re.IGNORECASE,
)
_WANT_ORBIT = re.compile(
    r"\b(?:orbit|circle\s+(?:around|it)|camera\s+orbit)\b",
    re.IGNORECASE,
)
_FOLLOWUP_ONLY = re.compile(
    r"^\s*(?:please\s+)?(?:"
    r"spin(?:\s+it)?(?:\s+slowly)?|"
    r"orbit(?:\s+it)?|"
    r"frame(?:\s+it)?(?:\s+a\s+shot)?|"
    r"make\s+it\s+(\w+)|"
    r"tint(?:\s+it)?(?:\s+(\w+))?|"
    r"look\s+at\s+it"
    r")\s*[.!?]?\s*$",
    re.IGNORECASE,
)

# In-process last DCC delivery (per project key)
_LAST_DCC: dict[str, dict[str, Any]] = {}


def _project_key(project_root: Optional[Path]) -> str:
    return str(Path(project_root).resolve()) if project_root else ""


def remember_dcc(project_root: Optional[Path], meta: dict[str, Any]) -> None:
    key = _project_key(project_root)
    _LAST_DCC[key] = {
        "actor_path": meta.get("actor_path"),
        "asset_path": meta.get("asset_path"),
        "shape": meta.get("shape") or meta.get("dcc_shape"),
        "fbx": meta.get("fbx"),
    }


def last_dcc(project_root: Optional[Path] = None) -> Optional[dict[str, Any]]:
    return _LAST_DCC.get(_project_key(project_root)) or None


def wants_spin(message: str) -> bool:
    return bool(_WANT_SPIN.search(message or ""))


def wants_orbit(message: str) -> bool:
    return bool(_WANT_ORBIT.search(message or ""))


def infer_spin_duration(message: str) -> float:
    text = (message or "").lower()
    if "slow" in text:
        return 4.0
    if "fast" in text:
        return 1.2
    return 2.5


def spin_actor(
    actor_path: str,
    *,
    remote_api: str = "http://127.0.0.1:8765",
    duration: float = 2.5,
    revolutions: float = 1.0,
    steps: int = 16,
) -> dict[str, Any]:
    """
    Rotate a StaticMeshActor in place via stepped world.set_transform yaw updates.
    """
    import json
    import time

    try:
        from ue_agent_loop import RemoteUeClient
    except ImportError:
        from hephaestus_forge.ue_agent_loop import RemoteUeClient  # type: ignore

    client = RemoteUeClient(remote_api, timeout=30.0)
    # Discover current transform via world.get_actor when available.
    loc = {"x": 0.0, "y": 0.0, "z": 100.0}
    scale = {"x": 2.0, "y": 2.0, "z": 2.0}
    listed = client.command({
        "command": "world.get_actor",
        "params": {"actor_path": actor_path},
    })
    if listed.get("success"):
        try:
            inner = json.loads(listed.get("result_json") or "{}")
            t = inner.get("transform") or inner
            if isinstance(t.get("location"), dict):
                loc = {k: float(t["location"].get(k, loc[k])) for k in ("x", "y", "z")}
            if isinstance(t.get("scale"), dict):
                scale = {k: float(t["scale"].get(k, scale[k])) for k in ("x", "y", "z")}
            elif isinstance(inner.get("location"), dict):
                loc = {k: float(inner["location"].get(k, loc[k])) for k in ("x", "y", "z")}
        except (json.JSONDecodeError, TypeError, ValueError):
            pass

    steps = max(4, int(steps))
    dt = max(duration, 0.4) / steps
    yaw_step = (360.0 * revolutions) / steps
    results: list[dict[str, Any]] = []
    for i in range(steps + 1):
        yaw = yaw_step * i
        res = client.command({
            "command": "world.set_transform",
            "params": {
                "actor_path": actor_path,
                "transform": {
                    "location": loc,
                    "rotation": {"pitch": 0.0, "yaw": yaw, "roll": 0.0},
                    "scale": scale,
                },
            },
        })
        results.append(res)
        if i < steps:
            time.sleep(dt)
    ok = any(r.get("success") for r in results)
    return {
        "success": ok,
        "error": "" if ok else (results[-1].get("error") if results else "spin failed"),
        "steps": len(results),
        "actor_path": actor_path,
        "duration": duration,
    }


def orbit_camera(
    actor_path: str,
    *,
    remote_api: str = "http://127.0.0.1:8765",
    duration: float = 3.0,
    steps: int = 12,
    distance: float = 450.0,
) -> dict[str, Any]:
    """Orbit free camera around actor by sweeping yaw_offset."""
    import time

    try:
        from ue_agent_loop import RemoteUeClient
    except ImportError:
        from hephaestus_forge.ue_agent_loop import RemoteUeClient  # type: ignore

    client = RemoteUeClient(remote_api, timeout=30.0)
    steps = max(4, int(steps))
    dt = max(duration, 0.5) / steps
    results: list[dict[str, Any]] = []
    for i in range(steps + 1):
        yaw = (360.0 * i) / steps
        res = client.command({
            "command": "world.set_view",
            "params": {
                "mode": "free",
                "look_at_actor": actor_path,
                "distance": distance,
                "yaw_offset": yaw,
                "height": 120.0,
            },
        })
        results.append(res)
        if i < steps:
            time.sleep(dt)
    ok = any(r.get("success") for r in results)
    return {
        "success": ok,
        "error": "" if ok else (results[-1].get("error") if results else "orbit failed"),
        "steps": len(results),
        "actor_path": actor_path,
    }

_COLOR_NAMES: dict[str, tuple[float, float, float]] = {
    "red": (0.85, 0.12, 0.12),
    "green": (0.15, 0.75, 0.2),
    "blue": (0.15, 0.35, 0.9),
    "yellow": (0.95, 0.85, 0.15),
    "orange": (0.95, 0.45, 0.1),
    "purple": (0.55, 0.2, 0.85),
    "pink": (0.95, 0.4, 0.7),
    "cyan": (0.15, 0.85, 0.9),
    "white": (0.95, 0.95, 0.95),
    "black": (0.05, 0.05, 0.05),
    "gray": (0.45, 0.45, 0.45),
    "grey": (0.45, 0.45, 0.45),
    "gold": (0.85, 0.7, 0.2),
}


def infer_mesh_color(message: str) -> Optional[dict[str, float]]:
    """Parse a named color from the goal (e.g. 'red cube')."""
    text = (message or "").lower()
    # Prefer "a red cube" / "red sphere" adjacent to shape words
    for name, rgb in _COLOR_NAMES.items():
        if re.search(rf"\b{name}\b", text):
            return {"r": rgb[0], "g": rgb[1], "b": rgb[2], "a": 1.0}
    return None


def tint_actor(
    actor_path: str,
    color: dict[str, float],
    *,
    remote_api: str = "http://127.0.0.1:8765",
) -> dict[str, Any]:
    """world.set_mesh_color on a StaticMeshActor."""
    try:
        from ue_agent_loop import RemoteUeClient
    except ImportError:
        from hephaestus_forge.ue_agent_loop import RemoteUeClient  # type: ignore

    client = RemoteUeClient(remote_api, timeout=30.0)
    res = client.command({
        "command": "world.set_mesh_color",
        "params": {"actor_path": actor_path, "color": color},
    })
    return {
        "success": bool(res.get("success")),
        "error": "" if res.get("success") else (res.get("error") or "set_mesh_color failed"),
        "result": res,
        "color": color,
        "actor_path": actor_path,
    }


def wants_frame_shot(message: str) -> bool:
    """True when the user asked to frame/camera the result (also default for into-PIE)."""
    return bool(_WANT_FRAME.search(message or ""))


def _spawned_actor_path(import_result: dict[str, Any]) -> Optional[str]:
    """Pull StaticMesh/Skeletal actor_path from dcc_import spawn_results."""
    import json

    for item in import_result.get("spawn_results") or []:
        if not isinstance(item, dict) or not item.get("success"):
            continue
        paths = item.get("actor_paths") or []
        for p in paths:
            if p and "PointLight" not in str(p):
                return str(p)
        try:
            inner = json.loads(item.get("result_json") or "{}")
        except json.JSONDecodeError:
            continue
        ap = inner.get("actor_path")
        if ap and "PointLight" not in str(ap):
            return str(ap)
    return None


def frame_actor(
    actor_path: str,
    *,
    remote_api: str = "http://127.0.0.1:8765",
    create_shot: bool = False,
    distance: float = 450.0,
) -> dict[str, Any]:
    """world.set_view look-at + optional sequence.create_shot."""
    try:
        from ue_agent_loop import RemoteUeClient
    except ImportError:
        from hephaestus_forge.ue_agent_loop import RemoteUeClient  # type: ignore

    client = RemoteUeClient(remote_api, timeout=30.0)
    view = client.command({
        "command": "world.set_view",
        "params": {
            "mode": "free",
            "look_at_actor": actor_path,
            "distance": distance,
            "yaw_offset": 35.0,
            "height": 100.0,
        },
    })
    out: dict[str, Any] = {"set_view": view, "actor_path": actor_path}
    if create_shot and view.get("success"):
        shot = client.command({
            "command": "sequence.create_shot",
            "params": {
                "look_at_actor": actor_path,
                "duration": 2.0,
                "name": "HephaestusDccShot",
            },
        })
        out["create_shot"] = shot
    out["success"] = bool(view.get("success"))
    out["error"] = "" if out["success"] else (view.get("error") or "set_view failed")
    return out


def infer_dcc_shape(message: str) -> Optional[str]:
    """Return primitive shape key if the message asks to author a Blender mesh."""
    match = _DCC_AUTHOR.search(message or "")
    if not match:
        return None
    raw = match.group(1).lower().replace("-", "_")
    if raw in ("sphere",):
        return "uv_sphere"
    if raw in ("box",):
        return "cube"
    if raw in PRIMITIVE_SHAPES:
        return raw
    return None


def wants_dcc_into_pie(message: str) -> bool:
    """True when the goal authors a primitive and should land it in UE/PIE (default)."""
    if not infer_dcc_shape(message):
        return False
    text = message or ""
    if _PLACE_IN_SCENE.search(text):
        return True
    # Export-only language without place → do not import
    if _EXPORT_ONLY.search(text):
        return False
    # "make a cube" / "create a prop mesh" → deliver in PIE (studio default)
    return True


def wants_dcc_export_only(message: str) -> bool:
    shape = infer_dcc_shape(message)
    if not shape:
        return False
    text = message or ""
    if _PLACE_IN_SCENE.search(text):
        return False
    return bool(_EXPORT_ONLY.search(text))


def author_primitive_to_pie(
    *,
    project_root: Optional[Path],
    shape: str,
    name: Optional[str] = None,
    frame: bool = True,
    create_shot: bool = False,
    color: Optional[dict[str, float]] = None,
    spin: bool = False,
    orbit: bool = False,
    motion_duration: float = 2.5,
    remote_api: str = "http://127.0.0.1:8765",
) -> dict[str, Any]:
    """
    DCC export → editor.import_fbx → PIE → spawn → optional tint/frame/spin/orbit.
    """
    try:
        from dcc_client import dcc_online, start_dcc_server, DccClient
    except ImportError:
        from hephaestus_forge.dcc_client import dcc_online, start_dcc_server, DccClient  # type: ignore
    try:
        from dcc_import import dcc_import_to_pie
    except ImportError:
        from hephaestus_forge.dcc_import import dcc_import_to_pie  # type: ignore

    ok, _, detail = dcc_online()
    if not ok:
        started = start_dcc_server()
        if not started.get("ok"):
            return {
                "success": False,
                "error": started.get("error") or detail or "DCC server failed to start",
                "phase": "dcc_start",
            }

    asset_name = name or f"Hephaestus_{shape}"
    params: dict[str, Any] = {"shape": shape, "name": asset_name}
    if project_root:
        params["project_root"] = str(Path(project_root).resolve())

    export = DccClient(timeout=180.0).command("blender.export_fbx", params)
    if not export.get("success"):
        return {
            "success": False,
            "error": export.get("error") or "blender.export_fbx failed",
            "phase": "export",
            "export": export,
        }

    fbx = export.get("output_path") or (export.get("asset_paths") or [None])[0]
    imported = dcc_import_to_pie(
        project_root=Path(project_root).resolve() if project_root else None,
        fbx=fbx,
        name=asset_name,
        spawn=True,
    )
    if not imported.get("success"):
        return {
            "success": False,
            "error": imported.get("error") or "",
            "phase": "import",
            "shape": shape,
            "name": asset_name,
            "fbx": fbx,
            "asset_path": imported.get("asset_path"),
            "export": export,
            "import": imported,
        }

    actor_path = _spawned_actor_path(imported)
    tint_result: Optional[dict[str, Any]] = None
    if color and actor_path:
        tint_result = tint_actor(actor_path, color, remote_api=remote_api)
        if not tint_result.get("success"):
            return {
                "success": False,
                "error": tint_result.get("error") or "tint failed",
                "phase": "tint",
                "shape": shape,
                "name": asset_name,
                "fbx": fbx,
                "asset_path": imported.get("asset_path"),
                "actor_path": actor_path,
                "export": export,
                "import": imported,
                "tint": tint_result,
            }

    frame_result: Optional[dict[str, Any]] = None
    if frame and actor_path:
        frame_result = frame_actor(
            actor_path,
            remote_api=remote_api,
            create_shot=create_shot,
        )
        if not frame_result.get("success"):
            return {
                "success": False,
                "error": frame_result.get("error") or "framing failed",
                "phase": "frame",
                "shape": shape,
                "name": asset_name,
                "fbx": fbx,
                "asset_path": imported.get("asset_path"),
                "actor_path": actor_path,
                "export": export,
                "import": imported,
                "tint": tint_result,
                "frame": frame_result,
            }

    spin_result: Optional[dict[str, Any]] = None
    if spin and actor_path:
        spin_result = spin_actor(
            actor_path,
            remote_api=remote_api,
            duration=motion_duration,
        )
        if not spin_result.get("success"):
            return {
                "success": False,
                "error": spin_result.get("error") or "spin failed",
                "phase": "spin",
                "shape": shape,
                "name": asset_name,
                "fbx": fbx,
                "asset_path": imported.get("asset_path"),
                "actor_path": actor_path,
                "export": export,
                "import": imported,
                "tint": tint_result,
                "frame": frame_result,
                "spin": spin_result,
            }

    orbit_result: Optional[dict[str, Any]] = None
    if orbit and actor_path:
        orbit_result = orbit_camera(
            actor_path,
            remote_api=remote_api,
            duration=motion_duration,
        )
        if not orbit_result.get("success"):
            return {
                "success": False,
                "error": orbit_result.get("error") or "orbit failed",
                "phase": "orbit",
                "shape": shape,
                "name": asset_name,
                "fbx": fbx,
                "asset_path": imported.get("asset_path"),
                "actor_path": actor_path,
                "export": export,
                "import": imported,
                "tint": tint_result,
                "frame": frame_result,
                "spin": spin_result,
                "orbit": orbit_result,
            }

    out = {
        "success": True,
        "error": "",
        "phase": "done",
        "shape": shape,
        "name": asset_name,
        "fbx": fbx,
        "asset_path": imported.get("asset_path"),
        "actor_path": actor_path,
        "export": export,
        "import": imported,
        "tint": tint_result,
        "frame": frame_result,
        "spin": spin_result,
        "orbit": orbit_result,
    }
    return out


def try_direct_dcc_followup(
    message: str,
    *,
    project_root: Optional[Path] = None,
    remote_api: str = "http://127.0.0.1:8765",
) -> Optional[dict[str, Any]]:
    """Handle spin/orbit/frame/tint on the last remembered DCC actor (no re-export)."""
    if not _FOLLOWUP_ONLY.match((message or "").strip()):
        # Also allow short phrases that aren't only-followup regex but reference "it"
        text = (message or "").strip().lower()
        if not any(w in text for w in ("spin", "orbit", "frame it", "make it", "tint")):
            return None
        if infer_dcc_shape(message):
            return None  # full author path handles combined goals

    remembered = last_dcc(project_root)
    actor = (remembered or {}).get("actor_path")
    if not actor:
        return None

    color = infer_mesh_color(message)
    # "make it blue" → color only
    if color and re.search(r"\bmake\s+it\b|\btint\b", message or "", re.I):
        tint = tint_actor(actor, color, remote_api=remote_api)
        ok = bool(tint.get("success"))
        reply = f"Tinted {actor}." if ok else f"Tint failed: {tint.get('error')}"
        return _chat_result(ok, reply, str((remembered or {}).get("shape") or ""), planner="direct_dcc_followup", asset_path=str((remembered or {}).get("asset_path") or ""), meta={"tint": tint, "actor_path": actor})

    if wants_orbit(message):
        orb = orbit_camera(actor, remote_api=remote_api, duration=infer_spin_duration(message))
        ok = bool(orb.get("success"))
        reply = f"Orbited camera around {actor}." if ok else f"Orbit failed: {orb.get('error')}"
        return _chat_result(ok, reply, str((remembered or {}).get("shape") or ""), planner="direct_dcc_followup", asset_path=str((remembered or {}).get("asset_path") or ""), meta={"orbit": orb, "actor_path": actor})

    if wants_spin(message):
        sp = spin_actor(actor, remote_api=remote_api, duration=infer_spin_duration(message))
        ok = bool(sp.get("success"))
        reply = f"Spun {actor}." if ok else f"Spin failed: {sp.get('error')}"
        return _chat_result(ok, reply, str((remembered or {}).get("shape") or ""), planner="direct_dcc_followup", asset_path=str((remembered or {}).get("asset_path") or ""), meta={"spin": sp, "actor_path": actor})

    if wants_frame_shot(message) or re.search(r"\bframe\b", message or "", re.I):
        fr = frame_actor(actor, remote_api=remote_api, create_shot="shot" in (message or "").lower())
        ok = bool(fr.get("success"))
        reply = f"Framed {actor}." if ok else f"Frame failed: {fr.get('error')}"
        return _chat_result(ok, reply, str((remembered or {}).get("shape") or ""), planner="direct_dcc_followup", asset_path=str((remembered or {}).get("asset_path") or ""), meta={"frame": fr, "actor_path": actor})

    return None


def try_direct_cc5_author(
    message: str,
    *,
    project_root: Optional[Path] = None,
) -> Optional[dict[str, Any]]:
    """Character Creator export → same import/spawn/frame path when CC5 is available."""
    if not _CHARACTER_AUTHOR.search(message or ""):
        return None
    try:
        from cc5_bridge import export_character_fbx, cc5_available
    except ImportError:
        from hephaestus_forge.cc5_bridge import export_character_fbx, cc5_available  # type: ignore
    try:
        from dcc_import import dcc_import_to_pie
    except ImportError:
        from hephaestus_forge.dcc_import import dcc_import_to_pie  # type: ignore

    if not cc5_available():
        return _chat_result(
            False,
            "cc5_unavailable - install Character Creator 5 / rlpython, or set RLPYTHON.",
            "character",
            planner="direct_cc5_author",
        )

    name = "Character"
    m = re.search(r"\bnamed\s+(\w+)\b", message or "", re.I)
    if m:
        name = m.group(1)
    export = export_character_fbx(character_name=name, project_root=project_root)
    if not export.get("success"):
        return _chat_result(
            False,
            export.get("error") or "cc5 export failed",
            "character",
            planner="direct_cc5_author",
            meta={"export": export},
        )
    fbx = export.get("output_path")
    imported = dcc_import_to_pie(project_root=project_root, fbx=fbx, name=name, spawn=True)
    if not imported.get("success"):
        return _chat_result(
            False,
            imported.get("error") or "import failed",
            "character",
            planner="direct_cc5_author",
            meta={"export": export, "import": imported},
        )
    actor = _spawned_actor_path(imported)
    frame_res = None
    if actor:
        frame_res = frame_actor(actor, create_shot=False)
    meta = {
        "shape": "character",
        "asset_path": imported.get("asset_path"),
        "actor_path": actor,
        "fbx": fbx,
        "export": export,
        "import": imported,
        "frame": frame_res,
    }
    remember_dcc(project_root, meta)
    ok = True
    reply = f"Exported CC5 character to {imported.get('asset_path')} and spawned in view."
    if frame_res and frame_res.get("success"):
        reply += f" Framed {actor}."
    return _chat_result(ok, reply, "character", planner="direct_cc5_author", asset_path=str(imported.get("asset_path") or ""), meta=meta)


def try_direct_dcc_author(
    message: str,
    *,
    project_root: Optional[Path] = None,
) -> Optional[dict[str, Any]]:
    """
    If message matches DCC authoring intent, run the pipeline and return a chat-shaped dict.
    """
    cc5 = try_direct_cc5_author(message, project_root=project_root)
    if cc5 is not None:
        return cc5

    # Follow-ups on last actor first (spin it / make it blue) — no Blender.
    follow = try_direct_dcc_followup(message, project_root=project_root)
    if follow is not None and not infer_dcc_shape(message):
        return follow

    shape = infer_dcc_shape(message)
    if not shape:
        return try_direct_dcc_followup(message, project_root=project_root)

    export_only = wants_dcc_export_only(message)
    if export_only:
        try:
            from dcc_client import dcc_online, start_dcc_server, DccClient
        except ImportError:
            from hephaestus_forge.dcc_client import (  # type: ignore
                dcc_online,
                start_dcc_server,
                DccClient,
            )
        ok, _, detail = dcc_online()
        if not ok:
            started = start_dcc_server()
            if not started.get("ok"):
                reply = f"Could not start DCC: {started.get('error') or detail}"
                return _chat_result(False, reply, shape, planner="direct_dcc_export")
        name = f"Hephaestus_{shape}"
        params: dict[str, Any] = {"shape": shape, "name": name}
        if project_root:
            params["project_root"] = str(Path(project_root).resolve())
        export = DccClient(timeout=180.0).command("blender.export_fbx", params)
        ok = bool(export.get("success"))
        path = export.get("output_path") or ""
        reply = (
            f"Exported {shape} FBX to {path}."
            if ok
            else f"Blender export failed: {export.get('error', 'unknown')}"
        )
        return _chat_result(
            ok,
            reply,
            shape,
            planner="direct_dcc_export",
            asset_path=path,
            meta={"export": export, "fbx": path},
        )

    if not wants_dcc_into_pie(message):
        return None

    do_frame = True
    do_shot = bool(_WANT_SEQUENCE_SHOT.search(message or "")) or (
        wants_frame_shot(message) and "shot" in (message or "").lower()
    )
    color = infer_mesh_color(message)
    do_spin = wants_spin(message)
    do_orbit = wants_orbit(message)
    result = author_primitive_to_pie(
        project_root=project_root,
        shape=shape,
        frame=do_frame,
        create_shot=do_shot,
        color=color,
        spin=do_spin,
        orbit=do_orbit,
        motion_duration=infer_spin_duration(message),
    )
    ok = bool(result.get("success"))
    if ok:
        remember_dcc(project_root, result)
        bits = [
            f"Authored {shape} in Blender",
            f"imported to {result.get('asset_path')}",
            "spawned in camera frustum",
        ]
        if result.get("tint") and (result["tint"] or {}).get("success"):
            bits.append("tinted")
        if result.get("frame") and (result["frame"] or {}).get("success"):
            bits.append(f"framed {result.get('actor_path')}")
            if (result["frame"] or {}).get("create_shot"):
                bits.append("created a shot")
        if result.get("spin") and (result["spin"] or {}).get("success"):
            bits.append("spun")
        if result.get("orbit") and (result["orbit"] or {}).get("success"):
            bits.append("orbited camera")
        reply = ", ".join(bits) + "."
    else:
        reply = (
            f"DCC authoring failed at {result.get('phase')}: "
            f"{result.get('error') or 'unknown'}"
        )
    return _chat_result(
        ok,
        reply,
        shape,
        planner="direct_dcc_author",
        asset_path=str(result.get("asset_path") or ""),
        meta=result,
    )


def _chat_result(
    ok: bool,
    reply: str,
    shape: str,
    *,
    planner: str,
    asset_path: str = "",
    meta: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    return {
        "ok": ok,
        "reply": reply,
        "grade": {
            "met": ok,
            "score": 1.0 if ok else 0.0,
            "summary": reply,
            "missing": [] if ok else ["dcc asset not in pie"],
        },
        "planner": planner,
        "llm_available": False,
        "llm_error": "",
        "asset_matches": [asset_path] if asset_path else [],
        "asset_meta": {"dcc_shape": shape, **(meta or {})},
        "thoughts": [],
        "steps": [],
    }

# Copyright (c) 2024 HephaestusForge. All Rights Reserved.
"""
Agent path: author a Blender primitive FBX via DCC :8084, then import/spawn in PIE.

Plain-language goals like "make a cube and put it in the scene" should deliver
in-viewport without the operator running forge blender / dcc-import by hand.
"""

from __future__ import annotations

import json
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
    r"\b(?:make|create|export|author|build)\b.{0,60}\b(?:"
    r"character|avatar|cc5|humanoid|person|people|human|"
    r"dog|cat|wolf|fox|horse|animal|creature|monster|beast|dragon|alien|"
    r"man|woman|npc"
    r")\b"
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
    r"make\s+it\s+(\w+)(?:\s+and\s+spin(?:\s+it)?(?:\s+slowly)?)?|"
    r"tint(?:\s+it)?(?:\s+(\w+))?|"
    r"look\s+at\s+it|"
    r"make\s+it\s+(\w+)\s+and\s+(?:spin|orbit|frame)(?:\s+it)?"
    r")\s*[.!?]?\s*$",
    re.IGNORECASE,
)

# In-process last DCC delivery (per project key); also mirrored to disk
_LAST_DCC: dict[str, dict[str, Any]] = {}


def _project_key(project_root: Optional[Path]) -> str:
    return str(Path(project_root).resolve()) if project_root else ""


def _last_dcc_path(project_root: Optional[Path]) -> Optional[Path]:
    if not project_root:
        return None
    return Path(project_root).resolve() / ".hephaestus_forge" / "last_dcc.json"


def remember_dcc(project_root: Optional[Path], meta: dict[str, Any]) -> None:
    key = _project_key(project_root)
    payload = {
        "actor_path": meta.get("actor_path"),
        "asset_path": meta.get("asset_path"),
        "shape": meta.get("shape") or meta.get("dcc_shape"),
        "fbx": meta.get("fbx"),
    }
    _LAST_DCC[key] = payload
    disk = _last_dcc_path(project_root)
    if disk is None:
        return
    try:
        disk.parent.mkdir(parents=True, exist_ok=True)
        disk.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except OSError:
        pass


def last_dcc(project_root: Optional[Path] = None) -> Optional[dict[str, Any]]:
    key = _project_key(project_root)
    if key in _LAST_DCC:
        return _LAST_DCC[key]
    disk = _last_dcc_path(project_root)
    if disk and disk.is_file():
        try:
            data = json.loads(disk.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get("actor_path"):
                _LAST_DCC[key] = data
                return data
        except (OSError, json.JSONDecodeError, TypeError):
            return None
    return None


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


def animate_authored_actor(
    actor_path: str,
    *,
    remote_api: str = "http://127.0.0.1:8765",
    mode: str = "idle",
) -> dict[str, Any]:
    """
    Best-effort motion after DCC spawn: locomotion idle/walk, else short transform nudge.
    """
    try:
        from ue_agent_loop import RemoteUeClient
    except ImportError:
        from hephaestus_forge.ue_agent_loop import RemoteUeClient  # type: ignore

    client = RemoteUeClient(remote_api, timeout=30.0)
    loco = client.command({
        "command": "animation.play_locomotion",
        "params": {"actor_path": actor_path, "mode": mode, "loop": True},
    })
    if loco.get("success"):
        return {"success": True, "method": "play_locomotion", "mode": mode, "result": loco}

    # Transform "alive" motion — small forward walk
    import json as _json

    loc = {"x": 0.0, "y": 0.0, "z": 100.0}
    got = client.command({"command": "world.get_actor", "params": {"actor_path": actor_path}})
    if got.get("success"):
        try:
            inner = _json.loads(got.get("result_json") or "{}")
            t = inner.get("transform") or inner
            if isinstance(t.get("location"), dict):
                loc = {k: float(t["location"].get(k, loc[k])) for k in ("x", "y", "z")}
        except (TypeError, ValueError, _json.JSONDecodeError):
            pass
    target = {"x": loc["x"] + 120.0, "y": loc["y"], "z": loc["z"]}
    move = client.command({
        "command": "animation.play_transform_sequence",
        "params": {
            "actor_path": actor_path,
            "target_location": target,
            "duration": 2.0,
        },
    })
    return {
        "success": bool(move.get("success")),
        "method": "play_transform_sequence" if move.get("success") else "none",
        "mode": mode,
        "locomotion": loco,
        "result": move,
        "error": "" if move.get("success") else (move.get("error") or loco.get("error") or "animate failed"),
    }


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
    bits: list[str] = []
    meta: dict[str, Any] = {"actor_path": actor}
    ok = True

    # Tint when asked (make it blue / tint red) — may combine with spin/orbit/frame
    if color and re.search(r"\bmake\s+it\b|\btint\b", message or "", re.I):
        tint = tint_actor(actor, color, remote_api=remote_api)
        meta["tint"] = tint
        if tint.get("success"):
            bits.append(f"Tinted {actor}")
        else:
            ok = False
            bits.append(f"Tint failed: {tint.get('error')}")

    if wants_orbit(message):
        orb = orbit_camera(actor, remote_api=remote_api, duration=infer_spin_duration(message))
        meta["orbit"] = orb
        if orb.get("success"):
            bits.append(f"Orbited camera around {actor}")
        else:
            ok = False
            bits.append(f"Orbit failed: {orb.get('error')}")
    elif wants_spin(message):
        sp = spin_actor(actor, remote_api=remote_api, duration=infer_spin_duration(message))
        meta["spin"] = sp
        if sp.get("success"):
            bits.append(f"Spun {actor}")
        else:
            ok = False
            bits.append(f"Spin failed: {sp.get('error')}")

    if wants_frame_shot(message) or re.search(r"\bframe(?:\s+it)?\b", message or "", re.I):
        # Skip if the only match was "frame" inside a longer author phrase that we shouldn't hit here
        fr = frame_actor(actor, remote_api=remote_api, create_shot="shot" in (message or "").lower())
        meta["frame"] = fr
        if fr.get("success"):
            bits.append(f"Framed {actor}")
        else:
            ok = False
            bits.append(f"Frame failed: {fr.get('error')}")

    if not bits:
        return None

    reply = ". ".join(bits) + "."
    return _chat_result(
        ok,
        reply,
        str((remembered or {}).get("shape") or ""),
        planner="direct_dcc_followup",
        asset_path=str((remembered or {}).get("asset_path") or ""),
        meta=meta,
    )


def try_direct_cc5_author(
    message: str,
    *,
    project_root: Optional[Path] = None,
) -> Optional[dict[str, Any]]:
    """
    Author a person / animal / creature into PIE.

    Priority: CC5 (humanoid + installed) → NIM→Blender → Blender kits.
    Meshy only when HEPHAESTUS_USE_MESHY=1 (optional paid path).
    """
    if not _CHARACTER_AUTHOR.search(message or ""):
        return None

    try:
        from blender_bridge import infer_creature_kind, export_creature_fbx
    except ImportError:
        from hephaestus_forge.blender_bridge import infer_creature_kind, export_creature_fbx  # type: ignore
    try:
        from dcc_import import dcc_import_to_pie
    except ImportError:
        from hephaestus_forge.dcc_import import dcc_import_to_pie  # type: ignore

    kind = infer_creature_kind(message) or "creature"
    name = f"Hephaestus_{kind}"
    m = re.search(r"\bnamed\s+(\w+)\b", message or "", re.I)
    if m:
        name = m.group(1)

    provider = "blender_creature"
    fbx: Optional[str] = None
    export_meta: dict[str, Any] = {}
    skeletal = True

    # 1) CC5 for people when installed
    if kind == "humanoid":
        try:
            from cc5_bridge import export_character_fbx, cc5_available
        except ImportError:
            from hephaestus_forge.cc5_bridge import export_character_fbx, cc5_available  # type: ignore
        if cc5_available():
            try:
                from cc5_appearance import infer_appearance, appearance_summary
            except ImportError:
                from hephaestus_forge.cc5_appearance import infer_appearance, appearance_summary  # type: ignore
            plan = infer_appearance(message or "", character_name=name)
            export = export_character_fbx(
                character_name=name,
                project_root=project_root,
                # Create avatar + Free Resource morphs + Unreal FBX can take several minutes
                timeout_seconds=300,
                prompt=message or "",
                appearance=plan,
            )
            export_meta["cc5"] = export
            export_meta["appearance"] = plan
            if export.get("success") and export.get("output_path"):
                fbx = str(export["output_path"])
                provider = "cc5"
                export_meta["appearance_summary"] = appearance_summary(plan)

    # 2) NIM → Blender complex mesh (free path with NVIDIA_API_KEY)
    if fbx is None:
        try:
            from blender_nim_author import author_mesh_fbx, nim_available
        except ImportError:
            try:
                from hephaestus_forge.blender_nim_author import author_mesh_fbx, nim_available  # type: ignore
            except ImportError:
                author_mesh_fbx = None  # type: ignore
                nim_available = lambda: False  # type: ignore
        if nim_available() and author_mesh_fbx:
            prompt = (message or "").strip() or f"a stylized {kind}"
            nim_out = author_mesh_fbx(prompt, name=name, project_root=project_root)
            export_meta["nim_blender"] = {
                k: nim_out.get(k)
                for k in ("success", "error", "output_path", "provider", "gen", "stderr_tail")
            }
            if nim_out.get("success") and nim_out.get("output_path"):
                fbx = str(nim_out["output_path"])
                provider = "nim_blender"
                # NIM meshes may be static or rigged — still try skeletal import
                skeletal = kind in ("humanoid", "quadruped", "creature")

    # 3) Optional Meshy (paid) — opt-in only
    if fbx is None:
        try:
            from meshy_bridge import meshy_available, generate_and_download
        except ImportError:
            try:
                from hephaestus_forge.meshy_bridge import meshy_available, generate_and_download  # type: ignore
            except ImportError:
                meshy_available = lambda: False  # type: ignore
                generate_and_download = None  # type: ignore
        if meshy_available() and generate_and_download:
            prompt = (message or "").strip() or f"a stylized {kind}"
            gen = generate_and_download(prompt, project_root=project_root, name=name)
            export_meta["meshy"] = gen
            if gen.get("success") and gen.get("output_path"):
                path = Path(str(gen["output_path"]))
                if path.suffix.lower() == ".fbx":
                    fbx = str(path)
                    provider = "meshy"

    # 4) Blender creature kit fallback (always available if Blender is)
    if fbx is None:
        result = export_creature_fbx(kind=kind, name=name, project_root=project_root)
        export_meta["blender"] = result.to_dict() if hasattr(result, "to_dict") else result
        if not result.success:
            return _chat_result(
                False,
                result.error or "creature authoring failed",
                kind,
                planner="direct_creature_author",
                meta={"provider": provider, "export": export_meta},
            )
        fbx = result.output_path
        provider = "blender_creature"
        skeletal = True

    imported = dcc_import_to_pie(
        project_root=project_root,
        fbx=fbx,
        name=name,
        spawn=True,
        import_as_skeletal=skeletal,
        force_skeletal_spawn=skeletal,
    )
    if not imported.get("success"):
        return _chat_result(
            False,
            imported.get("error") or "import failed",
            kind,
            planner="direct_creature_author",
            meta={"provider": provider, "export": export_meta, "import": imported},
        )

    actor = _spawned_actor_path(imported)
    frame_res = None
    anim_res = None
    if actor:
        frame_res = frame_actor(actor, create_shot=False)
        # People / animals should move after landing
        anim_mode = "walk" if wants_spin(message) or "walk" in (message or "").lower() else "idle"
        anim_res = animate_authored_actor(actor, mode=anim_mode)
    meta = {
        "shape": kind,
        "kind": kind,
        "provider": provider,
        "asset_path": imported.get("asset_path"),
        "actor_path": actor,
        "fbx": fbx,
        "skeletal": imported.get("skeletal"),
        "export": export_meta,
        "import": imported,
        "frame": frame_res,
        "animate": anim_res,
    }
    remember_dcc(project_root, meta)
    reply = (
        f"Authored {kind} via {provider}, imported to {imported.get('asset_path')}, "
        f"spawned in camera frustum"
    )
    if frame_res and frame_res.get("success"):
        reply += f", framed {actor}"
    if anim_res and anim_res.get("success"):
        reply += f", animated ({anim_res.get('method')}/{anim_res.get('mode')})"
    if provider == "cc5" and export_meta.get("appearance_summary"):
        reply += f" [{export_meta['appearance_summary']}]"
    reply += "."
    return _chat_result(
        True,
        reply,
        kind,
        planner="direct_creature_author",
        asset_path=str(imported.get("asset_path") or ""),
        meta=meta,
    )


_PROP_AUTHOR = re.compile(
    r"\b(?:make|create|build|author)\b.{0,40}\b(?:a|an)\s+"
    r"(?!cube\b|sphere\b|cylinder\b|cone\b|plane\b|box\b)"
    r"((?:[\w\-]+\s+){0,3}[\w\-]+?)"
    r"(?=\s+and\b|\s+with\b|\s+in\b|\s+into\b|\s+for\b|[.,!?]|$)",
    re.IGNORECASE,
)


def try_direct_nim_prop_author(
    message: str,
    *,
    project_root: Optional[Path] = None,
) -> Optional[dict[str, Any]]:
    """NIM→Blender for props / complex meshes that are not primitives or creatures."""
    if infer_dcc_shape(message):
        return None
    try:
        from blender_bridge import infer_creature_kind
    except ImportError:
        from hephaestus_forge.blender_bridge import infer_creature_kind  # type: ignore
    if infer_creature_kind(message):
        return None
    if not _PROP_AUTHOR.search(message or ""):
        return None
    if wants_dcc_export_only(message):
        return None

    try:
        from blender_nim_author import author_mesh_fbx, nim_available
    except ImportError:
        from hephaestus_forge.blender_nim_author import author_mesh_fbx, nim_available  # type: ignore
    try:
        from dcc_import import dcc_import_to_pie
    except ImportError:
        from hephaestus_forge.dcc_import import dcc_import_to_pie  # type: ignore

    if not nim_available():
        return _chat_result(
            False,
            "nim_unavailable — set NVIDIA_API_KEY for Blender prop authoring "
            "(or use make a cube / install CC5 for people).",
            "prop",
            planner="direct_nim_prop_author",
        )

    m = _PROP_AUTHOR.search(message or "")
    noun = (m.group(1) if m else "prop").strip()
    name = "Hephaestus_" + re.sub(r"[^\w\-]+", "_", noun)[:40]
    out = author_mesh_fbx(message.strip(), name=name, project_root=project_root)
    if not out.get("success"):
        return _chat_result(
            False,
            out.get("error") or "NIM Blender authoring failed",
            "prop",
            planner="direct_nim_prop_author",
            meta={"export": out},
        )

    imported = dcc_import_to_pie(
        project_root=project_root,
        fbx=out.get("output_path"),
        name=name,
        spawn=True,
        import_as_skeletal=False,
        force_skeletal_spawn=False,
    )
    if not imported.get("success"):
        return _chat_result(
            False,
            imported.get("error") or "import failed",
            "prop",
            planner="direct_nim_prop_author",
            meta={"export": out, "import": imported},
        )

    actor = _spawned_actor_path(imported)
    frame_res = frame_actor(actor, create_shot=False) if actor else None
    meta = {
        "shape": "prop",
        "kind": noun,
        "provider": "nim_blender",
        "asset_path": imported.get("asset_path"),
        "actor_path": actor,
        "fbx": out.get("output_path"),
        "export": out,
        "import": imported,
        "frame": frame_res,
    }
    remember_dcc(project_root, meta)
    reply = f"Authored {noun} via nim_blender, imported to {imported.get('asset_path')}, spawned in camera frustum"
    if frame_res and frame_res.get("success"):
        reply += f", framed {actor}"
    reply += "."
    return _chat_result(
        True,
        reply,
        "prop",
        planner="direct_nim_prop_author",
        asset_path=str(imported.get("asset_path") or ""),
        meta=meta,
    )


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
        prop = try_direct_nim_prop_author(message, project_root=project_root)
        if prop is not None:
            return prop
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

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
    remote_api: str = "http://127.0.0.1:8765",
) -> dict[str, Any]:
    """
    DCC export → editor.import_fbx → PIE → spawn → optional tint → optional frame.

    Ensures DCC :8084 is up when possible.
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

    return {
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
    }


def try_direct_dcc_author(
    message: str,
    *,
    project_root: Optional[Path] = None,
) -> Optional[dict[str, Any]]:
    """
    If message matches DCC authoring intent, run the pipeline and return a chat-shaped dict.
    """
    shape = infer_dcc_shape(message)
    if not shape:
        return None

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

    # Author + land in PIE; frame by default (studio delivery). Explicit shot language
    # also creates a short Level Sequence beat when the bridge supports it.
    do_frame = True
    do_shot = bool(_WANT_SEQUENCE_SHOT.search(message or "")) or (
        wants_frame_shot(message) and "shot" in (message or "").lower()
    )
    color = infer_mesh_color(message)
    result = author_primitive_to_pie(
        project_root=project_root,
        shape=shape,
        frame=do_frame,
        create_shot=do_shot,
        color=color,
    )
    ok = bool(result.get("success"))
    if ok:
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

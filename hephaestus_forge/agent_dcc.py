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
) -> dict[str, Any]:
    """
    DCC export → editor.import_fbx → PIE → spawn in frustum.

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
    return {
        "success": bool(imported.get("success")),
        "error": imported.get("error") or "",
        "phase": "import" if not imported.get("success") else "done",
        "shape": shape,
        "name": asset_name,
        "fbx": fbx,
        "asset_path": imported.get("asset_path"),
        "export": export,
        "import": imported,
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

    # Author + land in PIE (default for make-a-cube style goals)
    result = author_primitive_to_pie(project_root=project_root, shape=shape)
    ok = bool(result.get("success"))
    if ok:
        reply = (
            f"Authored {shape} in Blender, imported to {result.get('asset_path')}, "
            f"and spawned it in the camera view."
        )
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

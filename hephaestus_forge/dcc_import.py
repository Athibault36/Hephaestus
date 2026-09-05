# Copyright (c) 2024 HephaestusForge. All Rights Reserved.
"""
Orchestrate DCC FBX → editor import → PIE → spawn in camera frustum.

Must stop PIE before AssetTools import (editor.import_fbx on :8766).
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Optional

try:
    from blender_bridge import default_export_dir
except ImportError:
    from hephaestus_forge.blender_bridge import default_export_dir  # type: ignore

try:
    from pie_control import (
        editor_api_base,
        editor_online,
        pie_api_base,
        pie_online,
        play,
        stop,
        wait_for_pie,
        _post_command,
    )
except ImportError:
    from hephaestus_forge.pie_control import (  # type: ignore
        editor_api_base,
        editor_online,
        pie_api_base,
        pie_online,
        play,
        stop,
        wait_for_pie,
        _post_command,
    )


def pick_imported_asset_path(
    paths: list[Any],
    *,
    preferred_name: str = "",
    fallback: str = "",
    import_as_skeletal: bool = False,
) -> tuple[str, bool]:
    """
    Choose the spawnable mesh from editor.import_fbx asset_paths.

    Character FBX imports emit many materials/textures; prefer the mesh whose
    leaf matches preferred_name (FBX stem), never a PBR/material leaf.
    """
    preferred = (preferred_name or "").strip()
    preferred_l = preferred.lower()

    def _leaf(p: str) -> str:
        return p.split(".")[-1] if "." in p else p.rsplit("/", 1)[-1]

    def _is_junk(p: str) -> bool:
        leaf = _leaf(p).lower()
        if leaf.endswith("skeleton") or leaf.endswith("_skeleton"):
            return True
        if leaf.endswith("physicsasset") or "physicsasset" in leaf:
            return True
        markers = (
            "material",
            "_mat",
            "opacity",
            "_normal",
            "_orm",
            "_mask",
            "roughness",
            "metallic",
            "specular",
            "std_tongue",
            "std_eye",
            "std_skin",
            "std_cornea",
            "std_tear",
            "pbr_",
        )
        if any(m in leaf for m in markers):
            if preferred_l and leaf == preferred_l:
                return False
            return True
        # CC5 material convention: Std_*
        if leaf.startswith("std_"):
            return True
        return False

    cleaned: list[str] = []
    for raw in paths or []:
        ps = str(raw or "").strip()
        if ps and not _is_junk(ps):
            cleaned.append(ps)

    skeletal = bool(import_as_skeletal)
    chosen = ""

    if preferred_l:
        for p in cleaned:
            if _leaf(p).lower() == preferred_l:
                chosen = p
                break
        if not chosen:
            for p in cleaned:
                if preferred_l in _leaf(p).lower():
                    chosen = p
                    break

    fb = str(fallback or "").strip()
    if not chosen and fb and not _is_junk(fb):
        chosen = fb
        skeletal = skeletal or "SkeletalMesh" in fb

    if not chosen and cleaned:
        chosen = cleaned[0]

    if (not chosen or _is_junk(chosen)) and preferred:
        parent = "/Game/Hephaestus/DccImports"
        if fb.startswith("/Game/"):
            parent = "/".join(fb.split("/")[:-1]) or parent
        elif cleaned and cleaned[0].startswith("/Game/"):
            parent = "/".join(cleaned[0].split("/")[:-1]) or parent
        chosen = f"{parent}/{preferred}.{preferred}"
        skeletal = True

    if chosen and (preferred_l and _leaf(chosen).lower() == preferred_l):
        skeletal = skeletal or import_as_skeletal

    return chosen, bool(skeletal or import_as_skeletal)


def resolve_fbx_path(
    fbx: Optional[str | Path] = None,
    *,
    project_root: Optional[Path] = None,
    name: Optional[str] = None,
) -> Path:
    if fbx:
        path = Path(fbx).resolve()
        if not path.is_file():
            raise FileNotFoundError(f"FBX not found: {path}")
        return path
    export_dir = default_export_dir(project_root)
    if name:
        candidate = export_dir / f"{name}.fbx"
        if candidate.is_file():
            return candidate.resolve()
        # allow name without extension already handled; try stem match
        for p in export_dir.glob("*.fbx"):
            if p.stem.lower() == name.lower():
                return p.resolve()
        raise FileNotFoundError(f"No FBX named {name!r} under {export_dir}")
    fbxs = sorted(export_dir.glob("*.fbx"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not fbxs:
        raise FileNotFoundError(f"No FBX files under {export_dir}")
    return fbxs[0].resolve()


def editor_import_fbx(
    source_path: Path | str,
    *,
    destination_path: str = "/Game/Hephaestus/DccImports",
    destination_name: Optional[str] = None,
    import_as_skeletal: bool = False,
    timeout: float = 120.0,
) -> dict[str, Any]:
    """Call editor.import_fbx on :8766 (WITH_EDITOR AssetTools; refuses if PIE active)."""
    src = str(Path(source_path).resolve())
    name = destination_name or Path(src).stem
    ok, _, detail = editor_online()
    if not ok:
        return {
            "success": False,
            "error": f"Editor API offline ({detail}). Open project / forge up first.",
        }
    return _post_command(
        editor_api_base(),
        "editor.import_fbx",
        {
            "source_path": src,
            "file_path": src,
            "destination_path": destination_path,
            "destination_name": name,
            "import_as_skeletal": bool(import_as_skeletal),
            "skeletal": bool(import_as_skeletal),
        },
        timeout=timeout,
    )


def dcc_import_to_pie(
    *,
    project_root: Optional[Path] = None,
    fbx: Optional[str | Path] = None,
    name: Optional[str] = None,
    destination_path: str = "/Game/Hephaestus/DccImports",
    spawn: bool = True,
    with_light: bool = True,
    wait_pie_s: float = 45.0,
    import_as_skeletal: bool = False,
    force_skeletal_spawn: bool = False,
) -> dict[str, Any]:
    """
    Full loop: resolve FBX → stop PIE → editor.import_fbx → play → spawn in view.
    """
    steps: list[dict[str, Any]] = []
    try:
        fbx_path = resolve_fbx_path(fbx, project_root=project_root, name=name)
    except FileNotFoundError as exc:
        return {"success": False, "error": str(exc), "steps": steps}

    steps.append({"step": "resolve_fbx", "ok": True, "path": str(fbx_path)})

    # Stop PIE if up — wait until both :8765 is down and editor reports pie_active=false
    pie_up, _, _ = pie_online(timeout=1.0)
    if pie_up:
        try:
            stop_res = stop()
        except RuntimeError as exc:
            stop_res = {"success": False, "error": str(exc)}
        steps.append({"step": "editor.stop", "ok": bool(stop_res.get("success")), "result": stop_res})
        deadline = time.time() + 30.0
        while time.time() < deadline:
            up, _, _ = pie_online(timeout=0.8)
            ed_ok, ed_health, _ = editor_online(timeout=0.8)
            pie_flag = bool((ed_health or {}).get("pie_active")) if ed_ok else False
            if not up and not pie_flag:
                break
            time.sleep(0.5)
        time.sleep(0.75)  # settle after End Play teardown
    else:
        steps.append({"step": "editor.stop", "ok": True, "skipped": True})

    import_res = editor_import_fbx(
        fbx_path,
        destination_path=destination_path,
        destination_name=fbx_path.stem,
        import_as_skeletal=import_as_skeletal,
    )
    steps.append({"step": "editor.import_fbx", "ok": bool(import_res.get("success")), "result": import_res})
    if not import_res.get("success"):
        return {
            "success": False,
            "error": import_res.get("error") or "editor.import_fbx failed",
            "steps": steps,
            "fbx": str(fbx_path),
        }

    asset_path = ""
    skeletal = False
    try:
        inner = json.loads(import_res.get("result_json") or "{}")
        bridge_path = str(inner.get("asset_path") or inner.get("path") or "")
        skeletal = bool(inner.get("skeletal"))
        paths = inner.get("asset_paths") or []
        preferred = fbx_path.stem
        if isinstance(paths, list) and paths:
            asset_path, sk2 = pick_imported_asset_path(
                paths,
                preferred_name=preferred,
                fallback=bridge_path,
                import_as_skeletal=import_as_skeletal,
            )
            skeletal = skeletal or sk2
        elif bridge_path:
            asset_path, sk2 = pick_imported_asset_path(
                [bridge_path],
                preferred_name=preferred,
                fallback=bridge_path,
                import_as_skeletal=import_as_skeletal,
            )
            skeletal = skeletal or sk2
        if not asset_path:
            asset_path = f"{destination_path.rstrip('/')}/{fbx_path.stem}.{fbx_path.stem}"
            skeletal = True
    except json.JSONDecodeError:
        asset_path = ""
    if not asset_path:
        asset_path = f"{destination_path.rstrip('/')}/{fbx_path.stem}.{fbx_path.stem}"

    play_res = play()
    wait_ok, wait_health, wait_detail = wait_for_pie(project_root, timeout_s=wait_pie_s)
    start_ok = bool(play_res.get("success")) and wait_ok
    steps.append(
        {
            "step": "editor.play",
            "ok": start_ok,
            "play": play_res,
            "wait": wait_detail,
            "health": wait_health,
        }
    )
    if not start_ok:
        return {
            "success": False,
            "error": play_res.get("error") or wait_detail or "Failed to start PIE after import",
            "steps": steps,
            "asset_path": asset_path,
            "fbx": str(fbx_path),
        }

    spawn_results: list[Any] = []
    if spawn:
        try:
            from ue_agent_loop import RemoteUeClient
        except ImportError:
            from hephaestus_forge.ue_agent_loop import RemoteUeClient  # type: ignore
        try:
            from agent_asset import spawn_asset_in_view
        except ImportError:
            from hephaestus_forge.agent_asset import spawn_asset_in_view  # type: ignore

        client = RemoteUeClient(pie_api_base())
        spawn_results = spawn_asset_in_view(
            client,
            asset_path,
            with_light=with_light,
            force_skeletal=bool(force_skeletal_spawn or skeletal or import_as_skeletal),
        )
        ok_spawn = bool(spawn_results) and any(
            r.get("success") for r in spawn_results if isinstance(r, dict)
        )
        steps.append({"step": "spawn_asset", "ok": ok_spawn, "results": spawn_results, "asset_path": asset_path})
        if not ok_spawn:
            return {
                "success": False,
                "error": f"Imported {asset_path} but spawn in view failed",
                "steps": steps,
                "asset_path": asset_path,
                "fbx": str(fbx_path),
                "skeletal": skeletal,
            }

    return {
        "success": True,
        "fbx": str(fbx_path),
        "asset_path": asset_path,
        "skeletal": skeletal or import_as_skeletal,
        "steps": steps,
        "spawn_results": spawn_results,
    }

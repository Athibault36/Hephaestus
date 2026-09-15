# Copyright (c) 2024 HephaestusForge. All Rights Reserved.
"""
Hephaestus DCC control plane — UE-like HTTP API for Blender (and later CC5).

Default: http://127.0.0.1:8084
  GET  /v1/health
  POST /v1/command  {"command":"blender.export_fbx"|"blender.exec"|"blender.scene_info"|"cc5.export", "params":{...}}
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import uvicorn

# Factory-root .env (MESHY_API_KEY, etc.) when DCC is started outside `forge`.
try:
    from dotenv import load_dotenv

    _factory_env = Path(__file__).resolve().parent.parent / ".env"
    if _factory_env.is_file():
        load_dotenv(_factory_env, override=False)
except ImportError:
    pass

try:
    from blender_bridge import (
        default_export_dir,
        export_creature_fbx,
        export_primitive_fbx,
        find_blender,
        ue_import_next_steps,
    )
except ImportError:
    from hephaestus_forge.blender_bridge import (  # type: ignore
        default_export_dir,
        export_creature_fbx,
        export_primitive_fbx,
        find_blender,
        ue_import_next_steps,
    )

try:
    from version import FORGE_VERSION
except ImportError:
    from hephaestus_forge.version import FORGE_VERSION  # type: ignore

DEFAULT_HOST = os.environ.get("DCC_BRIDGE_HOST") or os.environ.get("HEPHAESTUS_DCC_HOST") or "127.0.0.1"
DEFAULT_PORT = int(os.environ.get("DCC_BRIDGE_PORT") or os.environ.get("HEPHAESTUS_DCC_PORT") or "8084")

app = FastAPI(title="Hephaestus DCC Bridge", version=FORGE_VERSION)


def _blender_status() -> dict[str, Any]:
    path, version = find_blender()
    return {
        "available": bool(path),
        "path": path,
        "version": version,
    }


def _cc5_status() -> dict[str, Any]:
    try:
        from cc5_bridge import find_cc5, cc5_available
    except ImportError:
        try:
            from hephaestus_forge.cc5_bridge import find_cc5, cc5_available  # type: ignore
        except ImportError:
            return {"available": False, "path": None, "detail": "cc5_bridge not loaded"}
    path = find_cc5()
    return {
        "available": cc5_available(),
        "path": path,
        "detail": "ready" if path else "Character Creator 5 / rlpython not found",
    }


def _gaea_status() -> dict[str, Any]:
    try:
        from gaea_bridge import find_gaea
    except ImportError:
        try:
            from hephaestus_forge.gaea_bridge import find_gaea  # type: ignore
        except ImportError:
            return {"available": False, "path": None, "detail": "gaea_bridge not loaded"}
    path, version = find_gaea()
    return {
        "available": bool(path),
        "path": path,
        "version": version,
        "detail": "ready" if path else "Gaea Build Swarm not found (set GAEA_SWARM)",
    }


@app.get("/health")
@app.get("/v1/health")
def health() -> dict[str, Any]:
    blender = _blender_status()
    cc5 = _cc5_status()
    gaea = _gaea_status()
    return {
        "ok": True,
        "service": "hephaestus-dcc",
        "port": DEFAULT_PORT,
        "forge_version": FORGE_VERSION,
        "blender": blender,
        "cc5": cc5,
        "gaea": gaea,
        # Honest: available only when Blender is actually found
        "ready": bool(blender.get("available")),
    }


def _handle_blender_export_creature(params: dict[str, Any]) -> dict[str, Any]:
    project_root = params.get("project_root") or params.get("project")
    root = Path(project_root).resolve() if project_root else None
    kind = str(params.get("kind") or params.get("creature") or params.get("shape") or "humanoid")
    name = str(params.get("name") or f"Hephaestus_{kind}")
    output_path = params.get("output_path") or params.get("output")
    result = export_creature_fbx(
        kind=kind,
        name=name,
        project_root=root,
        output_path=Path(output_path) if output_path else None,
        blender_executable=params.get("blender_executable"),
        timeout_seconds=int(params.get("timeout") or 180),
    )
    out = result.to_dict()
    out["success"] = result.success
    out["kind"] = result.shape
    if result.success and result.output_path:
        out["result_json"] = json.dumps(
            {
                "output_path": result.output_path,
                "kind": result.shape,
                "skeletal": True,
                "next_steps": result.next_steps,
            }
        )
        out["asset_paths"] = [result.output_path]
    else:
        out["error"] = result.error or "creature export failed"
        out["result_json"] = "{}"
    return out


def _handle_blender_export_fbx(params: dict[str, Any]) -> dict[str, Any]:
    project_root = params.get("project_root") or params.get("project")
    root = Path(project_root).resolve() if project_root else None
    shape = str(params.get("shape") or "cube")
    name = str(params.get("name") or "HephaestusPrimitive")
    output_path = params.get("output_path") or params.get("output")
    result = export_primitive_fbx(
        shape=shape,
        name=name,
        project_root=root,
        output_path=Path(output_path) if output_path else None,
        blender_executable=params.get("blender_executable"),
        timeout_seconds=int(params.get("timeout") or 120),
    )
    out = result.to_dict()
    out["success"] = result.success
    if result.success and result.output_path:
        out["result_json"] = json.dumps(
            {
                "output_path": result.output_path,
                "shape": result.shape,
                "next_steps": result.next_steps,
            }
        )
        out["asset_paths"] = [result.output_path]
    else:
        out["error"] = result.error or "export failed"
        out["result_json"] = "{}"
    return out


def _handle_blender_exec(params: dict[str, Any]) -> dict[str, Any]:
    script = params.get("script") or params.get("python") or ""
    if not script.strip():
        return {"success": False, "error": "params.script required", "result_json": "{}"}
    blender_path, blender_version = find_blender(params.get("blender_executable"))
    if not blender_path:
        return {
            "success": False,
            "error": "Blender not found",
            "blender_path": None,
            "result_json": "{}",
        }
    timeout = int(params.get("timeout") or 120)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as fh:
        fh.write(script)
        script_path = fh.name
    try:
        proc = subprocess.run(
            [blender_path, "--background", "--python", script_path],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        ok = proc.returncode == 0
        return {
            "success": ok,
            "error": "" if ok else (proc.stderr or f"exit {proc.returncode}")[:2000],
            "blender_path": blender_path,
            "blender_version": blender_version,
            "return_code": proc.returncode,
            "stdout_tail": (proc.stdout or "")[-2000:],
            "stderr_tail": (proc.stderr or "")[-2000:],
            "result_json": json.dumps({"return_code": proc.returncode}),
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": f"Blender timed out after {timeout}s", "result_json": "{}"}
    finally:
        try:
            Path(script_path).unlink(missing_ok=True)
        except OSError:
            pass


def _handle_blender_scene_info(params: dict[str, Any]) -> dict[str, Any]:
    """Lightweight probe: Blender version + optional empty-scene object count via expr."""
    blender_path, blender_version = find_blender(params.get("blender_executable"))
    if not blender_path:
        return {"success": False, "error": "Blender not found", "result_json": "{}"}
    script = (
        "import bpy\n"
        "objs = [o.name for o in bpy.data.objects]\n"
        "print('HEPHAESTUS_SCENE_OBJECTS=' + str(len(objs)))\n"
        "print('HEPHAESTUS_SCENE_NAMES=' + ','.join(objs[:32]))\n"
    )
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as fh:
        fh.write(script)
        script_path = fh.name
    try:
        proc = subprocess.run(
            [blender_path, "--background", "--python", script_path],
            capture_output=True,
            text=True,
            timeout=int(params.get("timeout") or 60),
        )
        count = 0
        names: list[str] = []
        for line in (proc.stdout or "").splitlines():
            if line.startswith("HEPHAESTUS_SCENE_OBJECTS="):
                try:
                    count = int(line.split("=", 1)[1])
                except ValueError:
                    pass
            if line.startswith("HEPHAESTUS_SCENE_NAMES="):
                names = [n for n in line.split("=", 1)[1].split(",") if n]
        payload = {
            "blender_path": blender_path,
            "blender_version": blender_version,
            "object_count": count,
            "object_names": names,
        }
        return {
            "success": proc.returncode == 0,
            "error": "" if proc.returncode == 0 else (proc.stderr or "")[:1000],
            "result_json": json.dumps(payload),
            **payload,
        }
    finally:
        try:
            Path(script_path).unlink(missing_ok=True)
        except OSError:
            pass


def _handle_meshy_generate(params: dict[str, Any]) -> dict[str, Any]:
    try:
        from meshy_bridge import generate_and_download, meshy_available
    except ImportError:
        from hephaestus_forge.meshy_bridge import generate_and_download, meshy_available  # type: ignore
    if not meshy_available():
        return {
            "success": False,
            "error": "meshy_unavailable — set MESHY_API_KEY",
            "result_json": "{}",
        }
    project_root = params.get("project_root") or params.get("project")
    root = Path(project_root).resolve() if project_root else None
    prompt = str(params.get("prompt") or params.get("text") or "").strip()
    if not prompt:
        return {"success": False, "error": "params.prompt required", "result_json": "{}"}
    return generate_and_download(
        prompt,
        project_root=root,
        name=str(params.get("name") or "HephaestusMeshy"),
        art_style=str(params.get("art_style") or "realistic"),
        timeout_s=float(params.get("timeout") or 600),
    )


def _handle_cc5_export(params: dict[str, Any]) -> dict[str, Any]:
    try:
        from cc5_bridge import export_character_fbx
    except ImportError:
        from hephaestus_forge.cc5_bridge import export_character_fbx  # type: ignore
    project_root = params.get("project_root") or params.get("project")
    root = Path(project_root).resolve() if project_root else None
    result = export_character_fbx(
        character_name=str(params.get("character_name") or params.get("name") or "Character"),
        project_root=root,
        output_path=Path(params["output_path"]) if params.get("output_path") else None,
        include_morphs=bool(params.get("include_morphs", True)),
        timeout_seconds=int(params.get("timeout") or 180),
    )
    return result


def _gaea_build_result(params: dict[str, Any]):
    """Shared Gaea build invocation used by gaea.build / gaea.export_mask."""
    try:
        from gaea_bridge import build_terrain
    except ImportError:
        from hephaestus_forge.gaea_bridge import build_terrain  # type: ignore
    terrain = params.get("terrain_file") or params.get("terrain") or params.get("file")
    if not terrain:
        return None, {
            "success": False,
            "error": "params.terrain_file required (.terrain or .tor)",
            "result_json": "{}",
        }
    project_root = params.get("project_root") or params.get("project")
    root = Path(project_root).resolve() if project_root else None
    variables = params.get("variables") if isinstance(params.get("variables"), dict) else None
    seed = params.get("seed")
    result = build_terrain(
        terrain,
        project_root=root,
        build_folder=params.get("build_folder"),
        profile=params.get("profile"),
        region=params.get("region"),
        seed=int(seed) if seed is not None else None,
        ignore_cache=bool(params.get("ignore_cache", False)),
        verbose=bool(params.get("verbose", False)),
        variables=variables,
        vars_file=params.get("vars_file"),
        gaea_executable=params.get("gaea_executable"),
        destination_path=str(params.get("destination_path") or "/Game/Hephaestus/Landscapes"),
        timeout_seconds=int(params.get("timeout") or 1800),
    )
    return result, None


def _handle_gaea_build(params: dict[str, Any]) -> dict[str, Any]:
    result, err = _gaea_build_result(params)
    if err is not None:
        return err
    out = result.to_dict()
    out["success"] = result.success
    if result.success:
        out["result_json"] = json.dumps(
            {
                "heightmap": result.heightmap,
                "masks": result.masks,
                "textures": result.textures,
                "build_folder": result.build_folder,
                "next_steps": result.next_steps,
            }
        )
        out["asset_paths"] = result.outputs
        out["next_steps"] = result.next_steps
    else:
        out["error"] = result.error or "gaea build failed"
        out["result_json"] = "{}"
    return out


def _handle_gaea_export_mask(params: dict[str, Any]) -> dict[str, Any]:
    """Build (if needed) and surface just the weightmap masks for UE paint layers."""
    result, err = _gaea_build_result(params)
    if err is not None:
        return err
    out = result.to_dict()
    out["success"] = result.success and bool(result.masks)
    if out["success"]:
        out["result_json"] = json.dumps(
            {"masks": result.masks, "build_folder": result.build_folder}
        )
        out["asset_paths"] = list(result.masks)
    else:
        out["error"] = result.error or "no weightmap masks exported by the Gaea graph"
        out["result_json"] = "{}"
    return out


def route_command(command: str, params: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    params = params or {}
    cmd = (command or "").strip()
    if cmd in ("blender.export_fbx", "blender.export", "blender-export"):
        return _handle_blender_export_fbx(params)
    if cmd in (
        "blender.export_creature",
        "blender.creature",
        "blender.export_character",
        "creature.export",
    ):
        return _handle_blender_export_creature(params)
    if cmd in ("blender.exec", "blender.execute", "blender.run"):
        return _handle_blender_exec(params)
    if cmd in ("blender.scene_info", "blender.scene"):
        return _handle_blender_scene_info(params)
    if cmd in ("cc5.export", "cc5.export_character", "cc5-export"):
        return _handle_cc5_export(params)
    if cmd in ("meshy.generate", "meshy.text_to_3d", "meshy-generate"):
        return _handle_meshy_generate(params)
    if cmd in ("gaea.build", "gaea.build_terrain", "gaea.import_landscape", "gaea-build"):
        return _handle_gaea_build(params)
    if cmd in ("gaea.export_mask", "gaea.export_masks", "gaea.masks"):
        return _handle_gaea_export_mask(params)
    return {
        "success": False,
        "error": (
            f"Unknown DCC command '{cmd}' "
            "(use blender.export_fbx, blender.export_creature, blender.exec, "
            "blender.scene_info, cc5.export, meshy.generate, gaea.build, gaea.export_mask)"
        ),
        "result_json": "{}",
    }


@app.post("/v1/command")
async def command(request: Request) -> JSONResponse:
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(
            {"success": False, "error": "Invalid JSON body", "result_json": "{}"},
            status_code=400,
        )
    if not isinstance(body, dict):
        return JSONResponse(
            {"success": False, "error": "Body must be a JSON object", "result_json": "{}"},
            status_code=400,
        )
    cmd = body.get("command") or ""
    params = body.get("params") or body.get("args") or {}
    if not isinstance(params, dict):
        params = {}
    result = route_command(str(cmd), params)
    status = 200 if result.get("success") else 400
    # Normalize UE-like envelope
    envelope = {
        "success": bool(result.get("success")),
        "error": result.get("error") or "",
        "result_json": result.get("result_json") or "{}",
        "command": cmd,
        "command_id": result.get("command_id") or "",
        "actor_paths": result.get("actor_paths") or [],
        "asset_paths": result.get("asset_paths") or [],
    }
    # Include useful extras for clients
    for key in (
        "output_path",
        "blender_path",
        "blender_version",
        "shape",
        "next_steps",
        "object_count",
        "cc5_path",
        "gaea_path",
        "gaea_version",
        "heightmap",
        "masks",
        "textures",
        "build_folder",
    ):
        if key in result:
            envelope[key] = result[key]
    return JSONResponse(envelope, status_code=status)


def run_server(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> None:
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    run_server()

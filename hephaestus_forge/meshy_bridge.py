# Copyright (c) 2024 HephaestusForge. All Rights Reserved.
"""
Meshy text-to-3D bridge — preferred generative path when MESHY_API_KEY is set.

Downloads GLB/FBX into .hephaestus_forge/dcc_exports for the same import → PIE loop.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Optional

try:
    from blender_bridge import default_export_dir, ue_import_next_steps
except ImportError:
    from hephaestus_forge.blender_bridge import default_export_dir, ue_import_next_steps  # type: ignore

DEFAULT_BASE = "https://api.meshy.ai"


def meshy_api_key(env: Optional[dict] = None) -> str:
    environ = env if env is not None else os.environ
    return (environ.get("MESHY_API_KEY") or environ.get("HEPHAESTUS_MESHY_API_KEY") or "").strip()


def meshy_available(env: Optional[dict] = None) -> bool:
    return bool(meshy_api_key(env))


def _request(
    method: str,
    url: str,
    *,
    api_key: str,
    body: Optional[dict] = None,
    timeout: float = 60.0,
) -> dict[str, Any]:
    data = None
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
    }
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1000]
        raise RuntimeError(f"Meshy HTTP {exc.code}: {detail}") from exc


def generate_and_download(
    prompt: str,
    *,
    project_root: Optional[Path] = None,
    name: str = "HephaestusMeshy",
    art_style: str = "realistic",
    poll_s: float = 5.0,
    timeout_s: float = 600.0,
    env: Optional[dict] = None,
) -> dict[str, Any]:
    """
    Text → Meshy preview task → poll → download model into dcc_exports.

    Returns success envelope with output_path (glb/fbx/obj depending on Meshy).
    """
    key = meshy_api_key(env)
    if not key:
        return {
            "success": False,
            "error": "meshy_unavailable — set MESHY_API_KEY for generative characters/creatures",
            "output_path": None,
        }

    base = (os.environ.get("MESHY_API_BASE") or DEFAULT_BASE).rstrip("/")
    # Meshy OpenAPI text-to-3D preview (v2-compatible path used by template)
    try:
        created = _request(
            "POST",
            f"{base}/openapi/v2/text-to-3d",
            api_key=key,
            body={
                "mode": "preview",
                "prompt": prompt,
                "art_style": art_style,
                "should_remesh": True,
            },
            timeout=60.0,
        )
    except RuntimeError as exc:
        # Fall back to legacy endpoint from template
        try:
            created = _request(
                "POST",
                f"{base}/openapi/generate",
                api_key=key,
                body={
                    "mode": "preview",
                    "prompt": prompt,
                    "art_style": art_style,
                    "topology": "quad",
                    "target_polycount": 12000,
                    "symmetry": True,
                    "generate_uvs": True,
                },
                timeout=60.0,
            )
        except RuntimeError as exc2:
            return {"success": False, "error": str(exc2) or str(exc), "output_path": None}

    task_id = str(created.get("result") or created.get("id") or created.get("task_id") or "")
    if not task_id:
        return {
            "success": False,
            "error": f"Meshy did not return a task id: {created}",
            "output_path": None,
            "raw": created,
        }

    deadline = time.time() + timeout_s
    status_payload: dict[str, Any] = {}
    while time.time() < deadline:
        try:
            status_payload = _request(
                "GET",
                f"{base}/openapi/v2/text-to-3d/{task_id}",
                api_key=key,
                timeout=30.0,
            )
        except RuntimeError:
            status_payload = _request(
                "GET",
                f"{base}/openapi/status/{task_id}",
                api_key=key,
                timeout=30.0,
            )
        st = str(status_payload.get("status") or status_payload.get("state") or "").upper()
        if st in ("SUCCEEDED", "SUCCESS", "DONE", "COMPLETED"):
            break
        if st in ("FAILED", "ERROR", "CANCELED", "CANCELLED"):
            return {
                "success": False,
                "error": f"Meshy task failed: {status_payload.get('task_error') or status_payload}",
                "task_id": task_id,
                "output_path": None,
            }
        time.sleep(poll_s)
    else:
        return {
            "success": False,
            "error": f"Meshy timed out after {timeout_s}s (task {task_id})",
            "task_id": task_id,
            "output_path": None,
        }

    model_urls = (
        status_payload.get("model_urls")
        or (status_payload.get("result") or {}).get("model_urls")
        or {}
    )
    if isinstance(model_urls, dict):
        url = (
            model_urls.get("fbx")
            or model_urls.get("glb")
            or model_urls.get("obj")
            or model_urls.get("usdz")
        )
        ext = "fbx" if model_urls.get("fbx") else ("glb" if model_urls.get("glb") else "obj")
    else:
        url = None
        ext = "glb"
    if not url and isinstance(status_payload.get("model_url"), str):
        url = status_payload["model_url"]
        ext = "glb"

    if not url:
        return {
            "success": False,
            "error": f"Meshy succeeded but no model URL: {status_payload}",
            "task_id": task_id,
            "output_path": None,
        }

    out_dir = default_export_dir(project_root)
    out_dir.mkdir(parents=True, exist_ok=True)
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in name) or "HephaestusMeshy"
    out_path = out_dir / f"{safe}.{ext}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "HephaestusForge/1.0"})
        with urllib.request.urlopen(req, timeout=120.0) as resp:
            out_path.write_bytes(resp.read())
    except Exception as exc:
        return {
            "success": False,
            "error": f"Download failed: {exc}",
            "task_id": task_id,
            "output_path": None,
        }

    return {
        "success": True,
        "error": "",
        "task_id": task_id,
        "output_path": str(out_path.resolve()),
        "prompt": prompt,
        "next_steps": ue_import_next_steps(out_path) if ext == "fbx" else [
            "GLB/OBJ landed in dcc_exports — convert to FBX via Blender or import with Interchange",
        ],
        "result_json": json.dumps({"output_path": str(out_path.resolve()), "task_id": task_id}),
        "asset_paths": [str(out_path.resolve())],
    }

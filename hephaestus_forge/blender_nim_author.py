# Copyright (c) 2024 HephaestusForge. All Rights Reserved.
"""
NIM → Blender Python → FBX authoring (Meshy-free complex meshes).

Uses NVIDIA_API_KEY / HEPHAESTUS_LLM_API_KEY to generate a bpy script, runs Blender
headless, exports FBX under .hephaestus_forge/dcc_exports.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Optional

try:
    from blender_bridge import BlenderExportResult, default_export_dir, find_blender, ue_import_next_steps
except ImportError:
    from hephaestus_forge.blender_bridge import (  # type: ignore
        BlenderExportResult,
        default_export_dir,
        find_blender,
        ue_import_next_steps,
    )

try:
    from cloud.nim_client import (
        DEFAULT_PLANNER_MODEL,
        chat_template_kwargs_for_model,
        resolve_model_alias,
    )
except ImportError:
    try:
        from hephaestus_forge.cloud.nim_client import (  # type: ignore
            DEFAULT_PLANNER_MODEL,
            chat_template_kwargs_for_model,
            resolve_model_alias,
        )
    except ImportError:
        DEFAULT_PLANNER_MODEL = "nvidia/nemotron-3-ultra-550b-a55b"

        def resolve_model_alias(model: str) -> str:
            return model

        def chat_template_kwargs_for_model(model: str) -> dict:
            return {}

DEFAULT_NIM_URL = "https://integrate.api.nvidia.com/v1"

_SYSTEM = """You write Blender 4.x Python (bpy) that builds a single stylized 3D asset.
Rules:
- Output ONLY executable Python code. No markdown fences, no prose.
- Start by deleting all objects in the scene.
- Build the asset from mesh primitives and/or extruded geometry; keep polycount modest (<8k tris).
- Name the main mesh object exactly: {object_name}
- Scale for Unreal: object roughly 1-2 Blender units tall unless the prompt says otherwise.
- Do NOT use addons that may be missing. Stick to bpy.ops.mesh.* and bpy.data.
- End by selecting the mesh (and armature if any) and exporting FBX with:
  bpy.ops.export_scene.fbx(filepath=r"{out_path}", use_selection=True,
    apply_scale_options='FBX_SCALE_ALL', axis_forward='-Z', axis_up='Y',
    add_leaf_bones=False, bake_anim=False)
- Then print exactly: HEPHAESTUS_BLENDER_EXPORT_OK
- Then print: HEPHAESTUS_BLENDER_EXPORT_PATH= plus the filepath
"""


def _ensure_factory_dotenv() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if env_path.is_file():
        load_dotenv(env_path, override=False)


_ensure_factory_dotenv()


def nim_available(env: Optional[dict] = None) -> bool:
    environ = env if env is not None else os.environ
    return bool(
        (environ.get("NVIDIA_API_KEY") or environ.get("HEPHAESTUS_LLM_API_KEY") or "").strip()
    )


def _extract_python(text: str) -> str:
    raw = (text or "").strip()
    fence = re.search(r"```(?:python)?\s*([\s\S]*?)```", raw, re.I)
    if fence:
        raw = fence.group(1).strip()
    # Drop leading prose lines until an import or bpy
    lines = raw.splitlines()
    start = 0
    for i, line in enumerate(lines):
        s = line.strip()
        if s.startswith("import ") or s.startswith("from ") or s.startswith("bpy"):
            start = i
            break
    return "\n".join(lines[start:]).strip()


def generate_bpy_script(
    prompt: str,
    *,
    object_name: str,
    output_fbx: str,
    model: Optional[str] = None,
    timeout: float = 120.0,
) -> dict[str, Any]:
    """Ask NIM for a bpy export script. Returns {success, script, error, raw}."""
    if not nim_available():
        return {
            "success": False,
            "error": "nim_unavailable — set NVIDIA_API_KEY for Blender mesh authoring",
            "script": "",
            "raw": "",
        }

    api_key = (
        os.environ.get("HEPHAESTUS_LLM_API_KEY") or os.environ.get("NVIDIA_API_KEY") or ""
    ).strip()
    base = (
        os.environ.get("HEPHAESTUS_LLM_URL") or DEFAULT_NIM_URL
    ).rstrip("/")
    model_id = resolve_model_alias(
        model
        or os.environ.get("HEPHAESTUS_BLENDER_MODEL")
        or os.environ.get("HEPHAESTUS_LLM_MODEL")
        or DEFAULT_PLANNER_MODEL
    )
    out = str(Path(output_fbx).resolve()).replace("\\", "/")
    safe_name = re.sub(r"[^\w\-]+", "_", object_name) or "HephaestusMesh"
    system = _SYSTEM.format(object_name=safe_name, out_path=out)
    user = f"Asset brief: {prompt.strip()}\nObject name must be: {safe_name}\nFBX path: {out}"

    payload: dict[str, Any] = {
        "model": model_id,
        "temperature": 0.2,
        "max_tokens": 3500,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    tmpl = chat_template_kwargs_for_model(model_id)
    if tmpl:
        payload["chat_template_kwargs"] = tmpl

    req = urllib.request.Request(
        f"{base}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:800]
        return {"success": False, "error": f"NIM HTTP {exc.code}: {detail}", "script": "", "raw": ""}
    except Exception as exc:
        return {"success": False, "error": str(exc), "script": "", "raw": ""}

    try:
        raw = data["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError):
        return {"success": False, "error": f"Bad NIM response: {data}", "script": "", "raw": ""}

    script = _extract_python(raw)
    if "bpy" not in script or "export_scene.fbx" not in script:
        return {
            "success": False,
            "error": "NIM did not return a valid bpy FBX export script",
            "script": script,
            "raw": raw[:2000],
        }
    # Ensure markers exist even if model forgot
    if "HEPHAESTUS_BLENDER_EXPORT_OK" not in script:
        script += (
            f'\nprint("HEPHAESTUS_BLENDER_EXPORT_OK")\n'
            f'print("HEPHAESTUS_BLENDER_EXPORT_PATH=" + r"{out}")\n'
        )
    return {"success": True, "error": "", "script": script, "raw": raw[:2000], "model": model_id}


def run_bpy_export(
    script: str,
    *,
    output_fbx: Path,
    blender_executable: Optional[str] = None,
    timeout_seconds: int = 180,
) -> BlenderExportResult:
    blender_path, blender_version = find_blender(blender_executable)
    if not blender_path:
        return BlenderExportResult(
            success=False,
            error="Blender not found. Install Blender 4.x or set BLENDER_EXECUTABLE.",
        )
    output_fbx.parent.mkdir(parents=True, exist_ok=True)
    script_file: Optional[Path] = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as fh:
            fh.write(script)
            script_file = Path(fh.name)
        proc = subprocess.run(
            [blender_path, "--background", "--python", str(script_file)],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
        ok_marker = "HEPHAESTUS_BLENDER_EXPORT_OK" in (proc.stdout or "")
        file_ok = output_fbx.is_file() and output_fbx.stat().st_size > 0
        success = proc.returncode == 0 and ok_marker and file_ok
        error = None
        if not success:
            if proc.returncode != 0:
                error = f"Blender exited {proc.returncode}: {(proc.stderr or '')[-800]}"
            elif not ok_marker:
                error = "Blender finished without HEPHAESTUS_BLENDER_EXPORT_OK"
            elif not file_ok:
                error = f"FBX missing or empty: {output_fbx}"
        return BlenderExportResult(
            success=success,
            blender_path=blender_path,
            blender_version=blender_version,
            output_path=str(output_fbx.resolve()) if success else str(output_fbx),
            shape="nim_mesh",
            stdout=proc.stdout or "",
            stderr=proc.stderr or "",
            return_code=proc.returncode,
            error=error,
            next_steps=ue_import_next_steps(output_fbx) if success else [],
        )
    except subprocess.TimeoutExpired:
        return BlenderExportResult(
            success=False,
            blender_path=blender_path,
            blender_version=blender_version,
            output_path=str(output_fbx),
            shape="nim_mesh",
            error=f"Timeout after {timeout_seconds}s",
        )
    finally:
        if script_file is not None:
            try:
                script_file.unlink(missing_ok=True)
            except OSError:
                pass


def author_mesh_fbx(
    prompt: str,
    *,
    name: str = "HephaestusMesh",
    project_root: Optional[Path] = None,
    output_path: Optional[Path] = None,
    timeout_seconds: int = 180,
) -> dict[str, Any]:
    """Full NIM → Blender → FBX. Returns success envelope with output_path."""
    out_dir = default_export_dir(project_root)
    out_dir.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^\w\-]+", "_", name) or "HephaestusMesh"
    fbx_path = Path(output_path) if output_path else out_dir / f"{safe}.fbx"

    gen = generate_bpy_script(prompt, object_name=safe, output_fbx=str(fbx_path))
    if not gen.get("success"):
        return {
            "success": False,
            "error": gen.get("error") or "NIM bpy generation failed",
            "output_path": None,
            "provider": "nim_blender",
            "gen": gen,
        }

    result = run_bpy_export(gen["script"], output_fbx=fbx_path, timeout_seconds=timeout_seconds)
    out = result.to_dict()
    out["success"] = result.success
    out["provider"] = "nim_blender"
    out["gen"] = {"model": gen.get("model"), "raw_tail": (gen.get("raw") or "")[-500:]}
    if result.success:
        out["output_path"] = result.output_path
        out["result_json"] = json.dumps({"output_path": result.output_path, "provider": "nim_blender"})
        out["asset_paths"] = [result.output_path]
    else:
        out["error"] = result.error or "Blender export failed"
        # Include stderr for operators
        out["stderr_tail"] = (result.stderr or "")[-1000:]
    return out

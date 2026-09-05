# Copyright (c) 2024 HephaestusForge. All Rights Reserved.
"""
Factory-side Blender bridge: find Blender, export primitive meshes to FBX on disk.

Does not import into Unreal. AssetTools FBX import is refused during PIE —
use editor-time import (or stop Play) after export. See ue_import_next_steps().
"""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

# Shapes supported by the background primitive exporter.
PRIMITIVE_SHAPES = ("cube", "uv_sphere", "cylinder", "cone", "plane")

_WINDOWS_BLENDER_DIRS = (
    "Blender 4.5",
    "Blender 4.4",
    "Blender 4.3",
    "Blender 4.2",
    "Blender 4.1",
    "Blender 4.0",
)


@dataclass
class BlenderExportResult:
    """Outcome of a forge → Blender → on-disk asset export."""

    success: bool
    blender_path: Optional[str] = None
    blender_version: Optional[str] = None
    output_path: Optional[str] = None
    shape: Optional[str] = None
    stdout: str = ""
    stderr: str = ""
    return_code: int = -1
    error: Optional[str] = None
    next_steps: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "blender_path": self.blender_path,
            "blender_version": self.blender_version,
            "output_path": self.output_path,
            "shape": self.shape,
            "return_code": self.return_code,
            "error": self.error,
            "next_steps": list(self.next_steps),
            "stdout_tail": (self.stdout or "")[-2000:],
            "stderr_tail": (self.stderr or "")[-2000:],
        }


def find_blender(
    explicit: Optional[str] = None,
    *,
    env: Optional[dict] = None,
) -> Tuple[Optional[str], Optional[str]]:
    """
    Locate a Blender executable and its version string.

    Order: BLENDER_EXECUTABLE / explicit → PATH `blender` → common Windows install dirs.
    Returns (path_or_None, version_or_None).
    """
    environ = env if env is not None else os.environ
    candidates: List[object] = []

    if explicit:
        candidates.append(Path(explicit) if not isinstance(explicit, Path) else explicit)
    env_path = (environ.get("BLENDER_EXECUTABLE") or "").strip()
    if env_path:
        candidates.append(Path(env_path))
    candidates.append("blender")

    if os.name == "nt":
        pf = Path(environ.get("ProgramFiles", r"C:\Program Files"))
        for folder in _WINDOWS_BLENDER_DIRS:
            candidates.append(pf / "Blender Foundation" / folder / "blender.exe")

    candidates.extend(
        [
            Path("/usr/bin/blender"),
            Path("/Applications/Blender.app/Contents/MacOS/Blender"),
        ]
    )

    seen: set[str] = set()
    for path in candidates:
        try:
            if isinstance(path, Path):
                key = str(path.resolve()) if path.exists() else str(path)
                if key in seen:
                    continue
                seen.add(key)
                if not path.exists():
                    continue
                cmd = [str(path), "--version"]
                exe = str(path)
            else:
                if path in seen:
                    continue
                seen.add(str(path))
                cmd = [str(path), "--version"]
                exe = str(path)

            output = subprocess.check_output(
                cmd,
                text=True,
                stderr=subprocess.DEVNULL,
                timeout=30,
            ).strip()
            version = output.splitlines()[0].replace("Blender ", "").strip() if output else None
            return exe, version
        except Exception:
            continue

    return None, None


def default_export_dir(project_root: Optional[Path] = None) -> Path:
    """
    Target-agnostic DCC export directory under an adopted UE project, or factory cwd fallback.

    Preferred: {project}/.hephaestus_forge/dcc_exports
    Fallback:  {cwd}/.hephaestus_forge/dcc_exports
    """
    root = Path(project_root).resolve() if project_root else Path.cwd().resolve()
    return root / ".hephaestus_forge" / "dcc_exports"


def ue_import_next_steps(
    fbx_path: str | Path,
    *,
    destination_path: str = "/Game/Hephaestus/DccImports",
) -> List[str]:
    """Document editor-time UE import after Blender export (PIE-safe: no AssetTools during Play)."""
    src = str(Path(fbx_path).resolve()).replace("\\", "/")
    name = Path(fbx_path).stem
    import_json = (
        '{"command":"asset.import_fbx","params":{'
        f'"source_path":"{src}",'
        f'"destination_path":"{destination_path}",'
        f'"destination_name":"{name}"'
        "}}"
    )
    return [
        "Stop PIE if Play is active - AssetTools FBX import is refused during PIE.",
        f"Editor-time import (Remote API while not playing): forge command --json '{import_json}'",
        "Or Content Browser -> Import -> pick the FBX under .hephaestus_forge/dcc_exports.",
        f"After import, start PIE and spawn: forge spawn-asset {destination_path}/{name}",
        "Do not call asset.import_fbx while PIE is running.",
    ]


def _primitive_export_script(shape: str, output_fbx: str, object_name: str) -> str:
    """Blender Python that clears the scene, adds a primitive, and exports FBX."""
    if shape not in PRIMITIVE_SHAPES:
        raise ValueError(f"Unsupported shape {shape!r}; choose from {PRIMITIVE_SHAPES}")

    ops = {
        "cube": "bpy.ops.mesh.primitive_cube_add(size=1.0)",
        "uv_sphere": "bpy.ops.mesh.primitive_uv_sphere_add(radius=0.5)",
        "cylinder": "bpy.ops.mesh.primitive_cylinder_add(radius=0.5, depth=1.0)",
        "cone": "bpy.ops.mesh.primitive_cone_add(radius1=0.5, depth=1.0)",
        "plane": "bpy.ops.mesh.primitive_plane_add(size=1.0)",
    }[shape]

    # Escape backslashes for embedding in an r-string path inside the script.
    out = str(Path(output_fbx).resolve()).replace("\\", "/")
    name = re.sub(r"[^\w\-]+", "_", object_name) or "HephaestusExport"

    return f"""
import bpy

bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)

{ops}
obj = bpy.context.active_object
obj.name = {name!r}
bpy.ops.object.select_all(action='DESELECT')
obj.select_set(True)
bpy.context.view_layer.objects.active = obj

# UE expects centimeters; Blender is meters — apply FBX unit conversion.
bpy.ops.export_scene.fbx(
    filepath=r"{out}",
    use_selection=True,
    apply_scale_options='FBX_SCALE_ALL',
    axis_forward='-Z',
    axis_up='Y',
    add_leaf_bones=False,
)
print("HEPHAESTUS_BLENDER_EXPORT_OK")
print("HEPHAESTUS_BLENDER_EXPORT_PATH=" + r"{out}")
"""


def export_primitive_fbx(
    *,
    shape: str = "cube",
    name: str = "HephaestusPrimitive",
    project_root: Optional[Path] = None,
    output_dir: Optional[Path] = None,
    output_path: Optional[Path] = None,
    blender_executable: Optional[str] = None,
    timeout_seconds: int = 120,
) -> BlenderExportResult:
    """
    Run Blender in background to create a primitive mesh and write an FBX on disk.

    Output lands under {project}/.hephaestus_forge/dcc_exports by default (target-agnostic).
    """
    shape_key = shape.strip().lower().replace("-", "_").replace(" ", "_")
    if shape_key == "sphere":
        shape_key = "uv_sphere"
    if shape_key not in PRIMITIVE_SHAPES:
        return BlenderExportResult(
            success=False,
            error=f"Unsupported shape {shape!r}; choose from {PRIMITIVE_SHAPES}",
            next_steps=[],
        )

    blender_path, blender_version = find_blender(blender_executable)
    if not blender_path:
        return BlenderExportResult(
            success=False,
            error=(
                "Blender not found. Install Blender 4.x, add it to PATH, "
                "or set BLENDER_EXECUTABLE."
            ),
            next_steps=[
                "Install Blender 4.x from https://www.blender.org/download/",
                "Or set env BLENDER_EXECUTABLE to the full path of blender.exe",
                "Then re-run: forge blender-export",
            ],
        )

    out_dir = Path(output_dir) if output_dir else default_export_dir(project_root)
    out_dir.mkdir(parents=True, exist_ok=True)
    if output_path:
        fbx_path = Path(output_path)
        fbx_path.parent.mkdir(parents=True, exist_ok=True)
    else:
        safe = re.sub(r"[^\w\-]+", "_", name) or "HephaestusPrimitive"
        fbx_path = out_dir / f"{safe}.fbx"

    script = _primitive_export_script(shape_key, str(fbx_path), name)
    script_file: Optional[Path] = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".py",
            delete=False,
            encoding="utf-8",
        ) as fh:
            fh.write(script)
            script_file = Path(fh.name)

        cmd: Sequence[str] = [
            blender_path,
            "--background",
            "--python",
            str(script_file),
        ]
        proc = subprocess.run(
            list(cmd),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
        ok_marker = "HEPHAESTUS_BLENDER_EXPORT_OK" in (proc.stdout or "")
        file_ok = fbx_path.is_file() and fbx_path.stat().st_size > 0
        success = proc.returncode == 0 and ok_marker and file_ok
        error = None
        if not success:
            if proc.returncode != 0:
                error = f"Blender exited with code {proc.returncode}"
            elif not ok_marker:
                error = "Blender finished without HEPHAESTUS_BLENDER_EXPORT_OK marker"
            elif not file_ok:
                error = f"Expected FBX missing or empty: {fbx_path}"

        next_steps = ue_import_next_steps(fbx_path) if success else []
        return BlenderExportResult(
            success=success,
            blender_path=blender_path,
            blender_version=blender_version,
            output_path=str(fbx_path.resolve()) if success else str(fbx_path),
            shape=shape_key,
            stdout=proc.stdout or "",
            stderr=proc.stderr or "",
            return_code=proc.returncode,
            error=error,
            next_steps=next_steps,
        )
    except subprocess.TimeoutExpired:
        return BlenderExportResult(
            success=False,
            blender_path=blender_path,
            blender_version=blender_version,
            output_path=str(fbx_path),
            shape=shape_key,
            error=f"Timeout after {timeout_seconds}s",
        )
    except Exception as exc:
        return BlenderExportResult(
            success=False,
            blender_path=blender_path,
            blender_version=blender_version,
            output_path=str(fbx_path) if "fbx_path" in locals() else None,
            shape=shape_key,
            error=str(exc),
        )
    finally:
        if script_file is not None:
            try:
                script_file.unlink(missing_ok=True)
            except OSError:
                pass

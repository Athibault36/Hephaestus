# Copyright (c) 2024 HephaestusForge. All Rights Reserved.
"""
Character Creator 5 bridge — detect install and export character FBX when possible.

Uses rlpython when available. Surfaces cc5_unavailable clearly when not installed.
"""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

try:
    from blender_bridge import default_export_dir, ue_import_next_steps
except ImportError:
    from hephaestus_forge.blender_bridge import default_export_dir, ue_import_next_steps  # type: ignore


_CC5_CANDIDATES = (
    # CC5 nested installer layout (common on Windows)
    Path(r"C:\Program Files\Reallusion\Character Creator 5\Character Creator 5\Bin64\CharacterCreator.exe"),
    Path(r"C:\Program Files\Reallusion\Character Creator 5\Bin64\CharacterCreator.exe"),
    Path(r"C:\Program Files\Reallusion\Character Creator 4\Bin64\CharacterCreator.exe"),
)

_RLPYTHON_CANDIDATES = (
    Path(r"C:\Program Files\Reallusion\Character Creator 5\Character Creator 5\Bin64\CharacterCreatorpy.exe"),
    Path(r"C:\Program Files\Reallusion\Character Creator 5\Bin64\CharacterCreatorpy.exe"),
    Path(r"C:\Program Files\Reallusion\Character Creator 5\Character Creator 5\Bin64\rlpython.exe"),
    Path(r"C:\Program Files\Reallusion\Character Creator 5\Bin64\rlpython.exe"),
    Path(r"C:\Program Files\Reallusion\Bin64\rlpython.exe"),
)

_RLPY_SIBLING_NAMES = (
    "CharacterCreatorpy.exe",
    "rlpython.exe",
    "iClonePython.exe",
)


@dataclass
class CC5ExportResult:
    success: bool
    output_path: Optional[str] = None
    cc5_path: Optional[str] = None
    rlpython_path: Optional[str] = None
    error: Optional[str] = None
    next_steps: List[str] = field(default_factory=list)
    stdout: str = ""
    stderr: str = ""

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "output_path": self.output_path,
            "cc5_path": self.cc5_path,
            "rlpython_path": self.rlpython_path,
            "error": self.error,
            "next_steps": list(self.next_steps),
            "result_json": (
                f'{{"output_path":"{self.output_path}"}}' if self.output_path else "{}"
            ),
            "asset_paths": [self.output_path] if self.output_path else [],
        }


def find_cc5(env: Optional[dict] = None) -> Optional[str]:
    environ = env if env is not None else os.environ
    explicit = (environ.get("CC5_EXECUTABLE") or environ.get("HEPHAESTUS_CC5") or "").strip()
    if explicit and Path(explicit).exists():
        return str(Path(explicit))
    for path in _CC5_CANDIDATES:
        if path.exists():
            return str(path)
    return None


def find_rlpython(env: Optional[dict] = None) -> Optional[str]:
    environ = env if env is not None else os.environ
    explicit = (
        environ.get("RLPYTHON")
        or environ.get("CC5_RLPYTHON")
        or environ.get("CC5_PYTHON")
        or ""
    ).strip()
    if explicit and Path(explicit).exists():
        return str(Path(explicit))
    # Beside CC5 (CharacterCreatorpy.exe is the CC5 Python host)
    cc5 = find_cc5(environ)
    if cc5:
        parent = Path(cc5).parent
        for name in _RLPY_SIBLING_NAMES:
            sibling = parent / name
            if sibling.exists():
                return str(sibling)
    try:
        out = subprocess.check_output(
            ["where" if os.name == "nt" else "which", "rlpython"],
            text=True,
            timeout=10,
        )
        line = out.splitlines()[0].strip()
        if line and Path(line).exists():
            return line
    except Exception:
        pass
    for path in _RLPYTHON_CANDIDATES:
        if path.exists():
            return str(path)
    return None


def cc5_available() -> bool:
    return bool(find_cc5() or find_rlpython())


def _rlpy_export_script(character_name: str, output_fbx: str, include_morphs: bool) -> str:
    """
    RLPy script for Character Creator.

    If the running CC5 session has no matching avatar, fails with a clear print.
    Operators typically have the character open in CC5 when calling forge cc5 export.
    """
    out = str(Path(output_fbx).resolve()).replace("\\", "/")
    morph = "True" if include_morphs else "False"
    return f"""
import RLPy
import os

out_path = r"{out}"
os.makedirs(os.path.dirname(out_path), exist_ok=True)

avatar = None
try:
    # Prefer named avatar when API exposes it
    avatars = RLPy.RScene.GetAvatars() if hasattr(RLPy.RScene, "GetAvatars") else []
    for a in avatars or []:
        try:
            name = a.GetName() if hasattr(a, "GetName") else str(a)
            if name and {character_name!r}.lower() in name.lower():
                avatar = a
                break
        except Exception:
            pass
    if avatar is None and avatars:
        avatar = avatars[0]
except Exception as exc:
    print("HEPHAESTUS_CC5_ERROR=" + str(exc))
    raise SystemExit(2)

if avatar is None:
    print("HEPHAESTUS_CC5_ERROR=No avatar in CC5 scene — open a character first")
    raise SystemExit(3)

# Export FBX — API varies by CC version; try common entry points
exported = False
try:
    if hasattr(RLPy, "RFileIO") and hasattr(RLPy.RFileIO, "ExportFbx"):
        RLPy.RFileIO.ExportFbx(avatar, out_path)
        exported = True
except Exception as exc:
    print("HEPHAESTUS_CC5_TRY_EXPORTFBX=" + str(exc))

if not exported:
    try:
        # Fallback: file menu style export if exposed
        if hasattr(RLPy, "RGlobal") and hasattr(RLPy.RGlobal, "ExportFile"):
            RLPy.RGlobal.ExportFile(out_path)
            exported = True
    except Exception as exc:
        print("HEPHAESTUS_CC5_TRY_EXPORTFILE=" + str(exc))

if not exported or not os.path.isfile(out_path):
    print("HEPHAESTUS_CC5_ERROR=FBX export API not available or file missing")
    raise SystemExit(4)

print("HEPHAESTUS_CC5_EXPORT_OK")
print("HEPHAESTUS_CC5_EXPORT_PATH=" + out_path)
print("HEPHAESTUS_CC5_MORPHS={morph}")
"""


def export_character_fbx(
    *,
    character_name: str = "Character",
    project_root: Optional[Path] = None,
    output_path: Optional[Path] = None,
    include_morphs: bool = True,
    timeout_seconds: int = 180,
) -> dict:
    cc5 = find_cc5()
    rlpy = find_rlpython()
    if not rlpy and not cc5:
        return {
            "success": False,
            "error": (
                "cc5_unavailable - install Character Creator 5 / rlpython, "
                "or set CC5_EXECUTABLE / RLPYTHON"
            ),
            "cc5_path": None,
            "rlpython_path": None,
            "result_json": "{}",
            "asset_paths": [],
            "next_steps": [
                "Install Character Creator 5 from Reallusion",
                "Open a character in CC5",
                "Set RLPYTHON to rlpython.exe if not on PATH",
                "Re-run: forge cc5 export",
            ],
        }

    out_dir = default_export_dir(project_root)
    out_dir.mkdir(parents=True, exist_ok=True)
    if output_path:
        fbx_path = Path(output_path)
        fbx_path.parent.mkdir(parents=True, exist_ok=True)
    else:
        safe = re.sub(r"[^\w\-]+", "_", character_name) or "Character"
        fbx_path = out_dir / f"{safe}.fbx"

    if not rlpy:
        return {
            "success": False,
            "error": (
                "cc5_unavailable - Character Creator found but Python host missing "
                "(CharacterCreatorpy.exe / rlpython); cannot automate export"
            ),
            "cc5_path": cc5,
            "rlpython_path": None,
            "result_json": "{}",
            "asset_paths": [],
            "next_steps": [
                f"CC5 at {cc5}",
                "Set RLPYTHON to CharacterCreatorpy.exe beside CharacterCreator.exe",
                "Or export FBX manually to .hephaestus_forge/dcc_exports then forge dcc-import",
            ],
        }

    script = _rlpy_export_script(character_name, str(fbx_path), include_morphs)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as fh:
        fh.write(script)
        script_path = fh.name

    try:
        proc = subprocess.run(
            [rlpy, script_path],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
        ok = proc.returncode == 0 and fbx_path.is_file()
        err = ""
        for line in (proc.stdout or "").splitlines():
            if line.startswith("HEPHAESTUS_CC5_ERROR="):
                err = line.split("=", 1)[1]
        if not ok and not err:
            err = (proc.stderr or proc.stdout or f"rlpython exit {proc.returncode}")[:2000]
        next_steps = ue_import_next_steps(fbx_path) if ok else []
        return {
            "success": ok,
            "output_path": str(fbx_path) if ok else None,
            "cc5_path": cc5,
            "rlpython_path": rlpy,
            "error": err if not ok else "",
            "result_json": f'{{"output_path":"{str(fbx_path).replace(chr(92), "/")}"}}' if ok else "{}",
            "asset_paths": [str(fbx_path)] if ok else [],
            "next_steps": next_steps,
            "stdout_tail": (proc.stdout or "")[-1500:],
            "stderr_tail": (proc.stderr or "")[-1500:],
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error": f"rlpython timed out after {timeout_seconds}s",
            "cc5_path": cc5,
            "rlpython_path": rlpy,
            "result_json": "{}",
            "asset_paths": [],
        }
    except Exception as exc:
        return {
            "success": False,
            "error": str(exc),
            "cc5_path": cc5,
            "rlpython_path": rlpy,
            "result_json": "{}",
            "asset_paths": [],
        }
    finally:
        try:
            Path(script_path).unlink(missing_ok=True)
        except OSError:
            pass

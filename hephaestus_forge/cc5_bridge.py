# Copyright (c) 2024 HephaestusForge. All Rights Reserved.
"""
Character Creator 5 bridge — detect install and export character FBX when possible.

Uses rlpython when available. Surfaces cc5_unavailable clearly when not installed.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import time
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


def cc5_jobs_dir() -> Path:
    home = Path(os.environ.get("HEPHAESTUS_HOME") or (Path.home() / ".hephaestus"))
    d = home / "cc5_jobs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def find_default_cc5_template(
    env: Optional[dict] = None,
    *,
    preference: str = "",
) -> Optional[str]:
    """Path to a built-in mannequin / neutral avatar for auto-create."""
    environ = env if env is not None else os.environ
    explicit = (environ.get("CC5_TEMPLATE") or environ.get("HEPHAESTUS_CC5_TEMPLATE") or "").strip()
    if explicit and Path(explicit).is_file():
        return explicit
    cc5 = find_cc5(environ)
    if not cc5:
        return None
    root = Path(cc5).resolve().parent.parent  # Bin64 → Character Creator 5
    pref = (preference or "").lower()
    body = Path("Resource") / "CCHeadshot" / "ccAvatarBodyType"
    # NeutralAvatar first — Headshot body-types can hang on load in some CC5 setups
    order: list[Path] = [
        Path("Program") / "CCBaseData" / "NeutralAvatar" / "HD" / "RL_CC3_Plus.ccAvatar",
        Path("Program") / "CCBaseData" / "NeutralAvatar" / "RL_CC3_Plus.ccAvatar",
        Path("Program") / "CCBaseData" / "NeutralAvatar" / "RL_G6_Standard_Series.ccAvatar",
    ]
    if pref == "female":
        order += [
            body / "RL_CC3_Plus Female.ccAvatar",
            body / "RL_CC3_Plus Male.ccAvatar",
        ]
    else:
        order += [
            body / "RL_CC3_Plus Male.ccAvatar",
            body / "RL_CC3_Plus Female.ccAvatar",
        ]
    order += [
        body / "RL_CC3_Plus.ccAvatar",
        Path("Program") / "Default" / "Mannequin_Male.ccAvatar",
        Path("Program") / "Default" / "Mannequin_Female.ccAvatar",
        Path("Program") / "Default" / "DefDummyForMotion.iAvatar",
    ]
    for rel in order:
        cand = root / rel
        if cand.is_file():
            return str(cand)
    return None


def openplugin_template_dir() -> Path:
    return Path(__file__).resolve().parent / "templates" / "cc5_openplugin" / "HephaestusExport"


def install_cc5_openplugin(*, force: bool = False) -> dict:
    """
    Copy HephaestusExport OpenPlugin into CC5 Bin64/OpenPlugin.
    May require admin if Program Files is locked.
    Always stages a copy under ~/.hephaestus/cc5_openplugin_staging for manual install.
    """
    src = openplugin_template_dir()
    if not (src / "main.py").is_file():
        return {"ok": False, "error": f"Template missing: {src}"}

    home = Path(os.environ.get("HEPHAESTUS_HOME") or (Path.home() / ".hephaestus"))
    staging = home / "cc5_openplugin_staging" / "HephaestusExport"
    try:
        staging.mkdir(parents=True, exist_ok=True)
        (staging / "main.py").write_text((src / "main.py").read_text(encoding="utf-8"), encoding="utf-8")
    except OSError:
        staging = src

    cc5 = find_cc5()
    if not cc5:
        return {
            "ok": False,
            "error": "CC5 not found",
            "staged_path": str(staging),
            "next_steps": [
                "Install Character Creator 5 or set CC5_EXECUTABLE",
                f"Then copy {staging} → {{CC5}}/Bin64/OpenPlugin/HephaestusExport",
            ],
        }
    dest = Path(cc5).parent / "OpenPlugin" / "HephaestusExport"
    try:
        dest.mkdir(parents=True, exist_ok=True)
        target = dest / "main.py"
        if target.is_file() and not force:
            return {
                "ok": True,
                "path": str(dest),
                "skipped": True,
                "detail": "already installed",
                "staged_path": str(staging),
            }
        target.write_text((src / "main.py").read_text(encoding="utf-8"), encoding="utf-8")
        return {"ok": True, "path": str(dest), "skipped": False, "staged_path": str(staging)}
    except PermissionError as exc:
        return {
            "ok": False,
            "error": f"Permission denied writing {dest}: {exc}",
            "staged_path": str(staging),
            "next_steps": [
                f"As Admin, copy {staging} → {dest}",
                "Restart Character Creator after install",
            ],
        }
    except OSError as exc:
        return {"ok": False, "error": str(exc), "staged_path": str(staging)}


def ensure_cc5_running(*, wait_s: float = 8.0) -> dict:
    """Launch CharacterCreator.exe if no process is running (best-effort)."""
    cc5 = find_cc5()
    if not cc5:
        return {"ok": False, "error": "CC5 not found", "launched": False}
    try:
        import psutil  # type: ignore

        for proc in psutil.process_iter(["name"]):
            name = (proc.info.get("name") or "").lower()
            if "charactercreator" in name and "py" not in name:
                return {"ok": True, "launched": False, "detail": "already running"}
    except Exception:
        # Fallback: tasklist
        try:
            out = subprocess.check_output(
                ["tasklist", "/FI", "IMAGENAME eq CharacterCreator.exe"],
                text=True,
                timeout=10,
            )
            if "CharacterCreator.exe" in out:
                return {"ok": True, "launched": False, "detail": "already running"}
        except Exception:
            pass

    try:
        subprocess.Popen(
            [cc5],
            cwd=str(Path(cc5).parent),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        time.sleep(max(2.0, wait_s))
        return {"ok": True, "launched": True, "path": cc5}
    except Exception as exc:
        return {"ok": False, "error": str(exc), "launched": False}


def _export_via_job_queue(
    *,
    character_name: str,
    fbx_path: Path,
    timeout_seconds: float,
    appearance: Optional[dict] = None,
    prompt: str = "",
) -> dict:
    """Write a job for the CC5 OpenPlugin and poll for .result.json."""
    jobs = cc5_jobs_dir()
    job_id = f"export_{int(time.time() * 1000)}"
    job_path = jobs / f"{job_id}.job.json"
    result_path = jobs / f"{job_id}.result.json"

    plan = appearance
    if plan is None:
        try:
            from cc5_appearance import infer_appearance
        except ImportError:
            from hephaestus_forge.cc5_appearance import infer_appearance  # type: ignore

        plan = infer_appearance(prompt or "", character_name=character_name)

    payload = {
        "character_name": character_name,
        "output_path": str(fbx_path.resolve()),
        "created_at": time.time(),
        "prompt": prompt or plan.get("prompt") or "",
        "appearance": plan,
        "force_new": True,
    }
    pref = str(plan.get("template_preference") or plan.get("gender") or "")
    template = find_default_cc5_template(preference=pref)
    if template:
        payload["template_path"] = template
    job_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    ensure_cc5_running()
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        # Accept both export_id.result.json and legacy export_id.job.result.json
        candidates = [
            result_path,
            jobs / f"{job_id}.job.result.json",
        ]
        for candidate in candidates:
            if not candidate.is_file():
                continue
            try:
                result = json.loads(candidate.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                result = {"success": False, "error": "corrupt result json"}
            try:
                candidate.unlink(missing_ok=True)
            except OSError:
                pass
            ok = bool(result.get("success")) and fbx_path.is_file()
            return {
                "success": ok,
                "output_path": str(fbx_path) if ok else None,
                "error": "" if ok else (result.get("error") or "CC5 job failed"),
                "method": "openplugin_job",
                "result": result,
                "appearance": plan,
            }
        time.sleep(1.0)
    # cleanup stale job
    try:
        job_path.unlink(missing_ok=True)
    except OSError:
        pass
    return {
        "success": False,
        "output_path": None,
        "error": (
            "cc5_job_timeout — keep Character Creator running with HephaestusExport "
            "OpenPlugin installed (forge cc5 install-plugin); Hephaestus auto-creates "
            "a mannequin if the scene is empty, then retry"
        ),
        "method": "openplugin_job",
        "job_path": str(job_path),
    }


def export_character_fbx(
    *,
    character_name: str = "Character",
    project_root: Optional[Path] = None,
    output_path: Optional[Path] = None,
    include_morphs: bool = True,
    timeout_seconds: int = 300,
    prompt: str = "",
    appearance: Optional[dict] = None,
) -> dict:
    cc5 = find_cc5()
    rlpy = find_rlpython()
    if not rlpy and not cc5:
        return {
            "success": False,
            "error": (
                "cc5_unavailable - install Character Creator 5 / CharacterCreatorpy, "
                "or set CC5_EXECUTABLE / RLPYTHON"
            ),
            "cc5_path": None,
            "rlpython_path": None,
            "result_json": "{}",
            "asset_paths": [],
            "next_steps": [
                "Install Character Creator 5 from Reallusion",
                "forge cc5 install-plugin",
                "Re-run: forge cc5 export  (auto-loads a mannequin if scene empty)",
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

    # Preferred: GUI OpenPlugin job queue (CharacterCreatorpy cannot host RLPy headless)
    install_cc5_openplugin(force=False)
    job = _export_via_job_queue(
        character_name=character_name,
        fbx_path=fbx_path,
        timeout_seconds=float(timeout_seconds),
        appearance=appearance,
        prompt=prompt,
    )
    if job.get("success"):
        next_steps = ue_import_next_steps(fbx_path)
        return {
            "success": True,
            "output_path": str(fbx_path),
            "cc5_path": cc5,
            "rlpython_path": rlpy,
            "error": "",
            "result_json": f'{{"output_path":"{str(fbx_path).replace(chr(92), "/")}"}}',
            "asset_paths": [str(fbx_path)],
            "next_steps": next_steps,
            "method": "openplugin_job",
            "appearance": job.get("appearance") or appearance,
            "alter": (job.get("result") or {}).get("appearance"),
        }

    # CharacterCreatorpy crashes headless (access violation). Opt-in only for diagnostics.
    if rlpy and (os.environ.get("HEPHAESTUS_CC5_HEADLESS") or "").strip() in ("1", "true", "yes"):
        script = _rlpy_export_script(character_name, str(fbx_path), include_morphs)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as fh:
            fh.write(script)
            script_path = fh.name
        try:
            proc = subprocess.run(
                [rlpy, script_path],
                capture_output=True,
                text=True,
                timeout=min(30, timeout_seconds),
                cwd=str(Path(rlpy).parent),
            )
            ok = proc.returncode == 0 and fbx_path.is_file()
            if ok:
                return {
                    "success": True,
                    "output_path": str(fbx_path),
                    "cc5_path": cc5,
                    "rlpython_path": rlpy,
                    "error": "",
                    "result_json": f'{{"output_path":"{str(fbx_path).replace(chr(92), "/")}"}}',
                    "asset_paths": [str(fbx_path)],
                    "next_steps": ue_import_next_steps(fbx_path),
                    "method": "charactercreatorpy",
                }
        except Exception:
            pass
        finally:
            try:
                Path(script_path).unlink(missing_ok=True)
            except OSError:
                pass

    return {
        "success": False,
        "output_path": None,
        "cc5_path": cc5,
        "rlpython_path": rlpy,
        "error": job.get("error")
        or (
            "cc5_gui_required — CharacterCreatorpy cannot export headless. "
            "Install OpenPlugin (forge cc5 install-plugin), open a character in CC5, retry."
        ),
        "result_json": "{}",
        "asset_paths": [],
        "next_steps": [
            "forge cc5 install-plugin  (may need Admin once)",
            "Keep Character Creator running (Hephaestus auto-loads a mannequin)",
            "Retry make a person / forge cc5 export",
            "Or fall through to NIM→Blender humanoid automatically",
        ],
        "method": job.get("method") or "failed",
    }

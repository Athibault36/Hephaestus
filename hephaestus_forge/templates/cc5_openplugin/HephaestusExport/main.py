# Copyright (c) 2024 HephaestusForge. All Rights Reserved.
"""
Hephaestus CC5 OpenPlugin — watches ~/.hephaestus/cc5_jobs for export requests.

Install once into:
  {CC5}/Bin64/OpenPlugin/HephaestusExport/main.py

When the scene has no avatar, loads a default mannequin automatically.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path


def _jobs_dir() -> Path:
    home = Path(os.environ.get("HEPHAESTUS_HOME") or (Path.home() / ".hephaestus"))
    d = home / "cc5_jobs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _cc5_program_root() -> Path:
    """Bin64/OpenPlugin/HephaestusExport → …/Character Creator 5/"""
    here = Path(__file__).resolve()
    # …/Bin64/OpenPlugin/HephaestusExport/main.py → parents[3] = Character Creator 5 root
    try:
        return here.parents[3]
    except IndexError:
        return here.parent


def _default_avatar_candidates(name_hint: str = "") -> list[Path]:
    """Built-in CC5 templates Hephaestus can load without user interaction."""
    root = _cc5_program_root()
    default_dir = root / "Program" / "Default"
    neutral = root / "Program" / "CCBaseData" / "NeutralAvatar"
    hint = (name_hint or "").lower()
    female = any(w in hint for w in ("female", "woman", "girl", "lady"))
    male_first = [
        default_dir / "Mannequin_Male.ccAvatar",
        default_dir / "Mannequin_Female.ccAvatar",
    ]
    female_first = [
        default_dir / "Mannequin_Female.ccAvatar",
        default_dir / "Mannequin_Male.ccAvatar",
    ]
    ordered = female_first if female else male_first
    extras = [
        default_dir / "DefDummyForMotion.iAvatar",
        neutral / "RL_CC3_Plus.ccAvatar",
        root / "Program" / "Assets" / "Creator" / "Default.ccProject",
    ]
    # Job may pass an explicit template
    return [p for p in ordered + extras if p]


def _list_avatars():
    import RLPy

    try:
        if hasattr(RLPy.RScene, "GetAvatars"):
            raw = RLPy.RScene.GetAvatars()
            # Some builds require EAvatarType_All
            if raw is None and hasattr(RLPy, "EAvatarType_All"):
                raw = RLPy.RScene.GetAvatars(RLPy.EAvatarType_All)
            return list(raw or [])
    except TypeError:
        try:
            import RLPy as _rl

            return list(_rl.RScene.GetAvatars(_rl.EAvatarType_All) or [])
        except Exception:
            return []
    except Exception:
        return []
    return []


def _load_template(path: Path):
    """Load avatar/project template into the current scene. Returns avatar or None."""
    import RLPy

    path_str = str(path)
    print(f"HephaestusExport: loading template {path_str}")
    obj = None
    try:
        if hasattr(RLPy.RFileIO, "LoadObject"):
            obj = RLPy.RFileIO.LoadObject(path_str)
    except Exception as exc:
        print(f"HephaestusExport LoadObject: {exc}")
        obj = None
    if obj is None:
        try:
            if hasattr(RLPy.RFileIO, "LoadFile"):
                RLPy.RFileIO.LoadFile(path_str)
        except Exception as exc:
            print(f"HephaestusExport LoadFile: {exc}")
            return None
    # Prefer returned object if it's an avatar; else take first in scene
    avatars = _list_avatars()
    if obj is not None and avatars:
        # Newly loaded is often last
        return avatars[-1]
    if avatars:
        return avatars[-1]
    return obj


def _ensure_avatar(name_hint: str = "", template_path: str = ""):
    """Return an avatar, creating/loading a default mannequin if the scene is empty."""
    avatars = _list_avatars()
    avatar = None
    if name_hint:
        for a in avatars:
            try:
                n = a.GetName() if hasattr(a, "GetName") else str(a)
                if n and name_hint.lower() in n.lower():
                    avatar = a
                    break
            except Exception:
                pass
    if avatar is None and avatars:
        avatar = avatars[0]

    if avatar is not None:
        return avatar, "existing"

    candidates: list[Path] = []
    if template_path and Path(template_path).is_file():
        candidates.append(Path(template_path))
    candidates.extend(_default_avatar_candidates(name_hint))

    errors: list[str] = []
    for path in candidates:
        if not path.is_file():
            continue
        loaded = _load_template(path)
        if loaded is not None:
            try:
                if name_hint and hasattr(loaded, "SetName"):
                    loaded.SetName(name_hint)
            except Exception:
                pass
            return loaded, f"created:{path.name}"
        errors.append(path.name)

    return None, "create_failed:" + ",".join(errors or ["no templates found"])


def _export_avatar(avatar, out_path: str) -> tuple[bool, str]:
    import RLPy

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    try:
        if hasattr(RLPy.RScene, "SelectObject"):
            RLPy.RScene.SelectObject(avatar)
        elif hasattr(RLPy.RScene, "SetSelectedObjects"):
            RLPy.RScene.SetSelectedObjects([avatar])
    except Exception as exc:
        print(f"HephaestusExport select: {exc}")

    attempts: list[str] = []

    def _ok() -> bool:
        return os.path.isfile(out_path) and os.path.getsize(out_path) > 0

    # Canonical RLPy signature (iClone / CC):
    # ExportFbxFile(avatar, path, opts, opts2, opts3, tex_size, tex_fmt, motion_path)
    if hasattr(RLPy.RFileIO, "ExportFbxFile"):
        try:
            opt = getattr(RLPy, "EExportFbxOptions__None", 0)
            opt2 = getattr(RLPy, "EExportFbxOptions2__None", 0)
            opt3 = getattr(RLPy, "EExportFbxOptions3__None", 0)
            for flag in (
                "EExportFbxOptions_AutoSkinRigidMesh",
                "EExportFbxOptions_ExportRootMotion",
                "EExportFbxOptions_ZeroMotionRoot",
                "EExportFbxOptions_EmbedTexture",
            ):
                if hasattr(RLPy, flag):
                    opt = opt | getattr(RLPy, flag)
            for flag in (
                "EExportFbxOptions2_UnrealEngine4BoneAxis",
                "EExportFbxOptions2_RenameDuplicateBoneName",
                "EExportFbxOptions2_RenameDuplicateMaterialName",
                "EExportFbxOptions2_RenameBoneRootToGameType",
                "EExportFbxOptions2_ExtraWordForUnityAndUnreal",
                "EExportFbxOptions2_UnrealIkBone",
                "EExportFbxOptions2_UnrealPreset",
            ):
                if hasattr(RLPy, flag):
                    opt2 = opt2 | getattr(RLPy, flag)
            tex_size = getattr(RLPy, "EExportTextureSize_Original", 0)
            tex_fmt = getattr(RLPy, "EExportTextureFormat_Default", 0)
            RLPy.RFileIO.ExportFbxFile(
                avatar,
                out_path,
                opt,
                opt2,
                opt3,
                tex_size,
                tex_fmt,
                "",
            )
            if _ok():
                return True, "ExportFbxFile(unreal_preset)"
            attempts.append("ExportFbxFile(unreal_preset): no file")
        except Exception as exc:
            attempts.append(f"ExportFbxFile(unreal_preset): {exc}")

        # Minimal positional fallback
        try:
            RLPy.RFileIO.ExportFbxFile(avatar, out_path)
            if _ok():
                return True, "ExportFbxFile(avatar,path)"
            attempts.append("ExportFbxFile(avatar,path): no file")
        except Exception as exc:
            attempts.append(f"ExportFbxFile(avatar,path): {exc}")

    if hasattr(RLPy.RFileIO, "ExportFbx"):
        settings = None
        if hasattr(RLPy, "RFbxExport"):
            try:
                settings = RLPy.RFbxExport()
            except Exception as exc:
                attempts.append(f"RFbxExport(): {exc}")
        for label, args in (
            ("ExportFbx(path,settings)", (out_path, settings) if settings is not None else None),
            ("ExportFbx(avatar,path)", (avatar, out_path)),
        ):
            if args is None:
                continue
            try:
                RLPy.RFileIO.ExportFbx(*args)
                if _ok():
                    return True, label
                attempts.append(f"{label}: no file")
            except Exception as exc:
                attempts.append(f"{label}: {exc}")

    methods = [
        m
        for m in dir(RLPy.RFileIO)
        if "xport" in m.lower() or "fbx" in m.lower() or "save" in m.lower()
    ]
    return False, " | ".join(attempts + [f"RFileIO methods: {methods}"])


def _process_job(job_path: Path) -> None:
    try:
        job = json.loads(job_path.read_text(encoding="utf-8"))
    except Exception as exc:
        _write_result(job_path, False, error=f"bad job json: {exc}")
        return

    out_path = str(job.get("output_path") or "")
    name_hint = str(job.get("character_name") or "")
    template_path = str(job.get("template_path") or "")
    if not out_path:
        _write_result(job_path, False, error="output_path required")
        return

    avatar, how = _ensure_avatar(name_hint=name_hint, template_path=template_path)
    if avatar is None:
        _write_result(
            job_path,
            False,
            error=(
                "Could not create CC5 character automatically "
                f"({how}). Check Program/Default mannequin templates."
            ),
        )
        return

    ok, export_how = _export_avatar(avatar, out_path)
    if ok:
        _write_result(job_path, True, output_path=out_path, created=how, export=export_how)
    else:
        _write_result(
            job_path,
            False,
            error=f"ExportFbx failed — {export_how}",
            created=how,
            export=export_how,
        )


def _write_result(job_path: Path, success: bool, **extra) -> None:
    result = {"success": success, "job": job_path.name, **extra}
    # Job: export_123.job.json → Result: export_123.result.json
    stem = job_path.name
    if stem.endswith(".job.json"):
        out_name = stem[: -len(".job.json")] + ".result.json"
    else:
        out_name = job_path.stem + ".result.json"
    out = job_path.parent / out_name
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    try:
        job_path.unlink(missing_ok=True)
    except OSError:
        pass
    print(f"HephaestusExport result -> {out} success={success}")


def _poll_once() -> None:
    jobs = _jobs_dir()
    for job in sorted(jobs.glob("*.job.json")):
        print(f"HephaestusExport processing {job.name}")
        _process_job(job)


# Timer / thread handle kept alive for the CC5 session
_timer = None
_poll_thread = None


def initialize_plugin() -> None:
    """CC5 OpenPlugin entrypoint — start a lightweight poll loop."""
    global _timer, _poll_thread
    import threading

    print("HephaestusExport: plugin loaded — watching ~/.hephaestus/cc5_jobs")

    started = False
    for qt_mod in ("PySide6.QtCore", "PySide2.QtCore", "PySide.QtCore"):
        try:
            import importlib

            QtCore = importlib.import_module(qt_mod)  # type: ignore
            app_timer = QtCore.QTimer()
            app_timer.setInterval(1500)
            app_timer.timeout.connect(_poll_once)
            app_timer.start()
            _timer = app_timer
            started = True
            print(f"HephaestusExport: polling via {qt_mod}")
            break
        except Exception:
            continue

    if not started:

        def _loop():
            while True:
                try:
                    _poll_once()
                except Exception as exc:
                    print(f"HephaestusExport poll error: {exc}")
                time.sleep(1.5)

        _poll_thread = threading.Thread(target=_loop, name="HephaestusExportPoll", daemon=True)
        _poll_thread.start()
        print("HephaestusExport: polling via background thread")

    try:
        import RLPy

        RLPy.RUi.AddMenu("Hephaestus", RLPy.EMenu_Plugins)
    except Exception:
        pass

    _poll_once()

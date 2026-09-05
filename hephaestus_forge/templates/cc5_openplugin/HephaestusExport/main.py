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


def _default_avatar_candidates(name_hint: str = "", preference: str = "") -> list[Path]:
    """Prefer reliable NeutralAvatar first; optional gendered Headshot body types."""
    root = _cc5_program_root()
    default_dir = root / "Program" / "Default"
    neutral = root / "Program" / "CCBaseData" / "NeutralAvatar"
    body = root / "Resource" / "CCHeadshot" / "ccAvatarBodyType"
    hint = (name_hint or "").lower()
    pref = (preference or "").lower()
    female = pref == "female" or any(w in hint for w in ("female", "woman", "girl", "lady"))
    young = any(w in hint for w in ("child", "kid", "baby"))

    # Known-good NeutralAvatar (loads without modal). Body-types can hang on some installs.
    morph_bases = [
        neutral / "HD" / "RL_CC3_Plus.ccAvatar",
        neutral / "RL_CC3_Plus.ccAvatar",
        neutral / "RL_G6_Standard_Series.ccAvatar",
        neutral / "RL_CharacterCreator_Base_Std_G3.ccAvatar",
    ]
    gendered = []
    if young:
        gendered.append(body / "RL_CC3_Plus Baby.ccAvatar")
    if female:
        gendered += [body / "RL_CC3_Plus Female.ccAvatar", body / "RL_CC3_Plus Male.ccAvatar"]
    else:
        gendered += [body / "RL_CC3_Plus Male.ccAvatar", body / "RL_CC3_Plus Female.ccAvatar"]
    mannequins = (
        [default_dir / "Mannequin_Female.ccAvatar", default_dir / "Mannequin_Male.ccAvatar"]
        if female
        else [default_dir / "Mannequin_Male.ccAvatar", default_dir / "Mannequin_Female.ccAvatar"]
    )
    # Neutral first for reliability; gendered second for when they load cleanly
    return morph_bases + gendered + mannequins + [default_dir / "DefDummyForMotion.iAvatar"]


def _list_avatars():
    import RLPy

    try:
        if hasattr(RLPy.RScene, "GetAvatars"):
            raw = RLPy.RScene.GetAvatars()
            if raw is None and hasattr(RLPy, "EAvatarType_All"):
                raw = RLPy.RScene.GetAvatars(RLPy.EAvatarType_All)
            return list(raw or [])
    except TypeError:
        try:
            return list(RLPy.RScene.GetAvatars(RLPy.EAvatarType_All) or [])
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
    avatars = _list_avatars()
    if avatars:
        return avatars[-1]
    return obj


def _clear_avatars() -> int:
    """Remove existing avatars so each job can create a fresh character."""
    import RLPy

    removed = 0
    for avatar in list(_list_avatars()):
        try:
            if hasattr(RLPy.RScene, "DeleteObject"):
                RLPy.RScene.DeleteObject(avatar)
            elif hasattr(RLPy.RScene, "RemoveObject"):
                RLPy.RScene.RemoveObject(avatar)
            else:
                break
            removed += 1
        except Exception as exc:
            print(f"HephaestusExport clear avatar: {exc}")
    return removed


def _apply_scale_shape(avatar, appearance: dict) -> dict:
    """
    Visibly alter the character when body morph packs aren't installed:
    non-uniform scale from traits (tall/short/muscular/thin/heavy).
    """
    import RLPy

    traits = {str(t).lower() for t in ((appearance or {}).get("traits") or [])}
    morphs = (appearance or {}).get("morphs") or {}
    sx = sy = sz = 1.0

    # Height from trait or morph needle
    h = float(morphs.get("height") or 0.0)
    if "tall" in traits or h < -0.2:
        sy *= 1.08 + min(0.12, abs(h) * 0.1)
    elif "short" in traits or h > 0.2:
        sy *= 0.92 - min(0.08, abs(h) * 0.08)

    if "muscular" in traits:
        sx *= 1.08
        sz *= 1.08
        sy *= 1.02
    elif "thin" in traits:
        sx *= 0.92
        sz *= 0.92
    elif "heavy" in traits:
        sx *= 1.12
        sz *= 1.12
        sy *= 0.98
    else:
        # Seeded mild variation from unused morph weights
        m = float(morphs.get("muscle") or 0.0)
        t = float(morphs.get("thin") or 0.0)
        hv = float(morphs.get("heavy") or 0.0)
        sx *= 1.0 + m * 0.06 - t * 0.05 + hv * 0.07
        sz *= 1.0 + m * 0.06 - t * 0.05 + hv * 0.07

    # Clamp
    sx = max(0.82, min(1.25, sx))
    sy = max(0.82, min(1.25, sy))
    sz = max(0.82, min(1.25, sz))
    if abs(sx - 1.0) < 0.01 and abs(sy - 1.0) < 0.01 and abs(sz - 1.0) < 0.01:
        return {"scaled": False, "scale": [1.0, 1.0, 1.0]}

    errors: list[str] = []
    try:
        # RIObject.SetScale if present
        if hasattr(avatar, "SetScale"):
            avatar.SetScale(RLPy.RVector3(sx, sy, sz) if hasattr(RLPy, "RVector3") else (sx, sy, sz))
            return {"scaled": True, "scale": [sx, sy, sz], "method": "SetScale"}
    except Exception as exc:
        errors.append(f"SetScale:{exc}")

    try:
        if hasattr(avatar, "LocalScaled") or hasattr(avatar, "SetLocalScale"):
            meth = getattr(avatar, "SetLocalScale", None) or getattr(avatar, "LocalScaled", None)
            if callable(meth):
                meth(sx, sy, sz)
                return {"scaled": True, "scale": [sx, sy, sz], "method": "LocalScale"}
    except Exception as exc:
        errors.append(f"LocalScale:{exc}")

    try:
        # Transform control
        ctrl = avatar.GetControl("Transform") if hasattr(avatar, "GetControl") else None
        if ctrl is not None and hasattr(ctrl, "SetData"):
            # Best-effort; APIs vary by build
            data = ctrl.GetData() if hasattr(ctrl, "GetData") else None
            if data is not None and hasattr(data, "SetScale"):
                data.SetScale(RLPy.RVector3(sx, sy, sz))
                ctrl.SetData(data)
                return {"scaled": True, "scale": [sx, sy, sz], "method": "TransformControl"}
    except Exception as exc:
        errors.append(f"Transform:{exc}")

    try:
        wt = avatar.WorldTransform() if hasattr(avatar, "WorldTransform") else None
        if wt is not None:
            if hasattr(wt, "SetScale"):
                wt.SetScale(RLPy.RVector3(sx, sy, sz) if hasattr(RLPy, "RVector3") else sx)
            if hasattr(avatar, "SetWorldTransform"):
                avatar.SetWorldTransform(wt)
                return {"scaled": True, "scale": [sx, sy, sz], "method": "WorldTransform"}
    except Exception as exc:
        errors.append(f"WorldTransform:{exc}")

    return {"scaled": False, "scale": [sx, sy, sz], "errors": errors}


def _load_outfit(avatar, appearance: dict) -> dict:
    """Best-effort load of default cloth/hair templates onto the character."""
    import RLPy

    root = _cc5_program_root()
    cloth_dir = root / "Program" / "CCBaseData" / "AutoSkin" / "RL_CC3_Plus"
    loaded: list[str] = []
    errors: list[str] = []
    # Prefer a full-body or dress for female; cloak/other for variety by seed
    gender = str((appearance or {}).get("gender") or "")
    seed = str((appearance or {}).get("seed") or "x")
    picks = []
    if gender == "female":
        picks = ["Dress.ccCloth", "Hair.ccHair", "Shoe.ccShoes"]
    else:
        picks = ["Full_Body.ccCloth", "Hair.ccHair", "Shoe.ccShoes"]
    # Mild variety
    if abs(hash(seed)) % 2 == 0 and (cloth_dir / "Cloak.ccCloth").is_file():
        picks.insert(0, "Cloak.ccCloth")

    for name in picks:
        path = cloth_dir / name
        if not path.is_file():
            continue
        try:
            obj = RLPy.RFileIO.LoadObject(str(path))
            if obj is not None:
                loaded.append(name)
                try:
                    if hasattr(RLPy, "RCloth") and hasattr(RLPy.RCloth, "Conform"):
                        RLPy.RCloth.Conform(obj, avatar)
                except Exception as exc:
                    errors.append(f"conform {name}:{exc}")
        except Exception as exc:
            errors.append(f"load {name}:{exc}")
    return {"loaded": loaded, "errors": errors}


def _load_content_assets(avatar, appearance: dict) -> dict:
    """
    Apply Free Resource packs (ccAvatarPreset / ccSlider / ccSkin) from the plan.

    Paths come from hephaestus_forge.cc5_appearance.resolve_content_assets.
    """
    import RLPy

    loaded: list[str] = []
    errors: list[str] = []
    paths = list((appearance or {}).get("content_assets") or [])
    if not paths:
        return {"loaded": [], "errors": [], "skipped": True}

    for raw in paths:
        path = Path(str(raw))
        if not path.is_file():
            errors.append(f"missing:{path.name}")
            continue
        try:
            obj = RLPy.RFileIO.LoadObject(str(path))
            if obj is None:
                errors.append(f"null:{path.name}")
                continue
            loaded.append(path.name)
            # Cloth-like assets may need conform; presets/skins usually apply in-place
            try:
                suf = path.suffix.lower()
                if suf in (".cccloth", ".ccshoes", ".cchair") and hasattr(RLPy, "RCloth"):
                    if hasattr(RLPy.RCloth, "Conform"):
                        RLPy.RCloth.Conform(obj, avatar)
            except Exception as exc:
                errors.append(f"conform {path.name}:{exc}")
        except Exception as exc:
            errors.append(f"load {path.name}:{exc}")

    try:
        flags = RLPy.EObjectModifiedType_Attribute
        if hasattr(RLPy, "EObjectModifiedType_Transform"):
            flags = flags | RLPy.EObjectModifiedType_Transform
        RLPy.RGlobal.ObjectModified(avatar, flags)
    except Exception as exc:
        errors.append(f"modified:{exc}")

    return {"loaded": loaded, "errors": errors, "count": len(paths)}


def _apply_morphs(avatar, appearance: dict) -> dict:
    """
    Alter shaping morphs from an appearance plan when morph packs are installed.
    """
    import re
    import RLPy

    applied: list[str] = []
    missed: list[str] = []
    morphs = (appearance or {}).get("morphs") or {}
    if not morphs:
        return {"applied": [], "missed": [], "morph_count": 0}

    try:
        shaping = avatar.GetAvatarShapingComponent()
    except Exception as exc:
        return {"applied": [], "missed": list(morphs.keys()), "error": str(exc), "morph_count": 0}
    if shaping is None:
        return {"applied": [], "missed": list(morphs.keys()), "error": "no shaping component", "morph_count": 0}

    catalog: dict[str, object] = {}
    try:
        categories = shaping.GetShapingMorphCatergoryNames()
    except Exception:
        try:
            categories = shaping.GetShapingMorphCategoryNames()
        except Exception as exc:
            return {"applied": [], "missed": list(morphs.keys()), "error": f"categories: {exc}", "morph_count": 0}

    cat_summary: dict[str, int] = {}
    for cat in categories or []:
        try:
            ids = list(shaping.GetShapingMorphIDs(cat) or [])
            names = list(shaping.GetShapingMorphDisplayNames(cat) or [])
        except Exception:
            continue
        cat_l = str(cat).strip().lower()
        cat_summary[str(cat)] = len(names)
        for i, name in enumerate(names):
            if i >= len(ids):
                break
            key = str(name).strip().lower()
            catalog[key] = ids[i]
            catalog[f"{cat_l}/{key}"] = ids[i]
            leaf = key.rsplit("/", 1)[-1].strip()
            if leaf and leaf not in catalog:
                catalog[leaf] = ids[i]

    useful: list[str] = []
    try:
        home = Path(os.environ.get("HEPHAESTUS_HOME") or (Path.home() / ".hephaestus"))
        non_micro = sorted(
            k
            for k in catalog
            if not any(x in k for x in ("eyeocclusion", "eo ", "/eo ", "tear line", "tearline", "tl "))
        )
        useful = [
            k
            for k in non_micro
            if any(
                t in k
                for t in (
                    "height",
                    "muscle",
                    "body",
                    "thin",
                    "heavy",
                    "age",
                    "jaw",
                    "nose",
                    "brow",
                    "cheek",
                    "mouth",
                    "chin",
                    "slacker",
                    "athletic",
                    "face",
                    "character",
                    "head",
                    "neck",
                    "shoulder",
                    "chest",
                    "waist",
                    "hip",
                    "arm",
                    "leg",
                )
            )
        ][:200]
        (home / "cc5_morphs_sample.json").write_text(
            json.dumps(
                {
                    "count": len(catalog),
                    "categories": cat_summary,
                    "non_micro_n": len(non_micro),
                    "non_micro_sample": non_micro[:80],
                    "useful": useful,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
    except Exception:
        useful = []

    def _find_id(needle: str):
        n = needle.strip().lower()
        words = [w for w in re.split(r"[^a-z0-9]+", n) if len(w) > 2]
        best = None
        best_score = 0
        for k, v in catalog.items():
            if any(x in k for x in ("eyeocclusion", "eo ", "/eo ", "tearline", "tl ")):
                continue
            score = 0
            if n == k:
                return v
            if n in k:
                score = 500 - min(len(k), 400)
            elif words:
                hits = sum(1 for w in words if w in k)
                if not hits:
                    continue
                score = hits * 40
            else:
                continue
            if any(t in k for t in ("full body", "character", "actor/body", "body/", "head/", "face")):
                score += 80
            if score > best_score:
                best_score = score
                best = v
        return best if best_score >= 40 else None

    for name, weight in morphs.items():
        mid = _find_id(str(name))
        if mid is None:
            missed.append(str(name))
            continue
        try:
            shaping.SetShapingMorphWeight(mid, float(weight))
            applied.append(f"{name}={float(weight):.2f}")
        except Exception as exc:
            missed.append(f"{name}({exc})")

    try:
        flags = RLPy.EObjectModifiedType_Attribute
        if hasattr(RLPy, "EObjectModifiedType_Transform"):
            flags = flags | RLPy.EObjectModifiedType_Transform
        RLPy.RGlobal.ObjectModified(avatar, flags)
    except Exception as exc:
        print(f"HephaestusExport ObjectModified: {exc}")

    return {
        "applied": applied,
        "missed": missed,
        "morph_count": len(catalog),
        "categories": cat_summary,
        "sample_useful": useful[:40],
        "body_morph_pack": any(
            "body" in str(c).lower() or "character" in str(c).lower() or "actor/" in str(c).lower()
            for c in cat_summary
            if "parts" not in str(c).lower()
        ),
    }


def _apply_appearance(avatar, appearance: dict) -> dict:
    """Create a distinct character: content packs + scale + morphs + outfit."""
    if not appearance:
        return {"skipped": True}
    # Free Resource presets/sliders/skins first (when installed), then fine morphs/scale
    content = _load_content_assets(avatar, appearance)
    scale = _apply_scale_shape(avatar, appearance)
    morphs = _apply_morphs(avatar, appearance)
    outfit = _load_outfit(avatar, appearance)
    return {
        "traits": list(appearance.get("traits") or []),
        "gender": appearance.get("gender"),
        "content": content,
        "scale": scale,
        "morphs": morphs,
        "outfit": outfit,
        "applied": [f"content:{n}" for n in (content.get("loaded") or [])]
        + list(morphs.get("applied") or [])
        + ([f"scale={scale.get('scale')}"] if scale.get("scaled") else [])
        + [f"outfit:{n}" for n in (outfit.get("loaded") or [])],
        "missed": list(morphs.get("missed") or []) + list(content.get("errors") or []),
        "morph_count": morphs.get("morph_count") or 0,
    }


def _ensure_avatar(name_hint: str = "", template_path: str = "", preference: str = "", force_new: bool = True):
    """Return an avatar, creating/loading a default mannequin if needed."""
    if force_new:
        _clear_avatars()

    avatars = _list_avatars()
    avatar = None
    if not force_new:
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
    candidates.extend(_default_avatar_candidates(name_hint, preference))

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
    appearance = job.get("appearance") if isinstance(job.get("appearance"), dict) else {}
    preference = str(
        appearance.get("template_preference")
        or appearance.get("gender")
        or job.get("template_preference")
        or ""
    )
    force_new = bool(appearance.get("force_new", True) if appearance else job.get("force_new", True))
    if not out_path and str(job.get("action") or "") != "probe":
        _write_result(job_path, False, error="output_path required")
        return

    # Diagnostic probe — dump avatar API surface after loading a base
    if str(job.get("action") or "") == "probe":
        appearance = job.get("appearance") if isinstance(job.get("appearance"), dict) else {}
        preference = str(appearance.get("template_preference") or "male")
        avatar, how = _ensure_avatar(
            name_hint="Probe",
            template_path=str(job.get("template_path") or ""),
            preference=preference,
            force_new=True,
        )
        info = {"created": how, "methods": [], "scale_try": None}
        if avatar is not None:
            info["methods"] = sorted(
                m for m in dir(avatar) if any(t in m.lower() for t in ("scale", "transform", "control", "set", "world", "local"))
            )[:80]
            info["scale_try"] = _apply_scale_shape(avatar, appearance or {"traits": ["tall", "muscular"], "morphs": {"height": -0.8}})
            info["type"] = type(avatar).__name__
        _write_result(job_path, avatar is not None, **info)
        return

    avatar, how = _ensure_avatar(
        name_hint=name_hint,
        template_path=template_path,
        preference=preference,
        force_new=force_new,
    )
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

    alter = _apply_appearance(avatar, appearance) if appearance else {"applied": [], "skipped": True}

    ok, export_how = _export_avatar(avatar, out_path)
    if ok:
        _write_result(
            job_path,
            True,
            output_path=out_path,
            created=how,
            export=export_how,
            appearance=alter,
        )
    else:
        _write_result(
            job_path,
            False,
            error=f"ExportFbx failed — {export_how}",
            created=how,
            export=export_how,
            appearance=alter,
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
        try:
            log = Path(os.environ.get("HEPHAESTUS_HOME") or (Path.home() / ".hephaestus")) / "cc5_plugin.log"
            with log.open("a", encoding="utf-8") as fh:
                fh.write(f"poll {job.name} {time.time()}\n")
        except Exception:
            pass
        try:
            _process_job(job)
        except Exception as exc:
            try:
                _write_result(job, False, error=f"plugin exception: {exc}")
            except Exception:
                print(f"HephaestusExport fatal: {exc}")


# Timer / thread handle kept alive for the CC5 session
_timer = None
_poll_thread = None


def initialize_plugin() -> None:
    """CC5 OpenPlugin entrypoint — start a lightweight poll loop."""
    global _timer, _poll_thread
    import threading

    try:
        log = Path(os.environ.get("HEPHAESTUS_HOME") or (Path.home() / ".hephaestus")) / "cc5_plugin.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("a", encoding="utf-8") as fh:
            fh.write(f"initialize_plugin {time.time()}\n")
    except Exception:
        pass

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

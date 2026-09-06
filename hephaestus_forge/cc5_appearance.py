# Copyright (c) 2024 HephaestusForge. All Rights Reserved.
"""Infer CC5 appearance plans from natural-language prompts."""

from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path
from typing import Any, Optional


def _stable_unit(seed: str, salt: str = "") -> float:
    """Deterministic 0..1 from seed."""
    h = hashlib.sha256(f"{seed}|{salt}".encode("utf-8")).hexdigest()
    return int(h[:8], 16) / 0xFFFFFFFF


def _signed_unit(seed: str, salt: str) -> float:
    """Deterministic -1..1."""
    return _stable_unit(seed, salt) * 2.0 - 1.0


def content_library_roots() -> list[Path]:
    """Candidate Reallusion content roots (Public Documents + D: subst remaps)."""
    roots: list[Path] = []
    public = Path(os.environ.get("PUBLIC") or r"C:\Users\Public")
    for candidate in (
        public / "Documents" / "Reallusion",
        Path(r"D:\Reallusion"),
        Path(r"C:\Users\Public\Documents\Reallusion"),
    ):
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        if resolved.is_dir() and resolved not in roots:
            roots.append(resolved)
    return roots


def _cc5_characters_dir() -> Optional[Path]:
    for root in content_library_roots():
        p = root / "Reallusion Templates" / "Reallusion 3D" / "CC5 Characters"
        if p.is_dir():
            return p
    return None


def _first_existing(paths: list[Path]) -> Optional[Path]:
    for p in paths:
        if p.is_file():
            return p
    return None


def resolve_content_assets(plan: dict[str, Any]) -> list[str]:
    """
    Pick installed Free Resource files (presets / embed morphs / skins) for a plan.

    Safe when packs are missing: returns only paths that exist on disk.
    """
    base = _cc5_characters_dir()
    if base is None:
        return []

    gender = str(plan.get("gender") or "male").lower()
    traits = {str(t).lower() for t in (plan.get("traits") or [])}
    seed = str(plan.get("seed") or "x")
    out: list[Path] = []

    preset_dir = base / "Avatar Preset" / "Full Body Morph"
    if gender == "female":
        body_preset = _first_existing(
            [
                preset_dir / "HD Ariana.ccAvatarPreset",
                preset_dir / "HD Neutral F.ccAvatarPreset",
                preset_dir / "Stylized" / "HD Mila.ccAvatarPreset",
            ]
        )
    else:
        body_preset = _first_existing(
            [
                preset_dir / "HD Aaron.ccAvatarPreset",
                preset_dir / "HD Neutral M.ccAvatarPreset",
                preset_dir / "Stylized" / "HD Gibro.ccAvatarPreset",
            ]
        )
    if body_preset:
        out.append(body_preset)

    embed = base / "Actor" / "Avatar Control" / "CC Embed Morphs"
    # One full-body muscular/skinny slider only. Loading every regional slider
    # plus morph-category weights stacks deformations into spaghetti skins.
    if "muscular" in traits and gender != "female":
        p = embed / "Male Muscular" / "Male Muscular Body.ccSlider"
        if p.is_file():
            out.append(p)
    elif "thin" in traits and gender != "female":
        p = embed / "Male Skinny" / "Male Skinny Body.ccSlider"
        if p.is_file():
            out.append(p)

    char_dir = embed / "CC5 Characters"
    if char_dir.is_dir():
        prefix = "HD Ariana" if gender == "female" else "HD Aaron"
        if abs(hash(seed)) % 3 == 0 and gender == "female":
            if (char_dir / "HD Mila_Body Shape.ccSlider").is_file():
                prefix = "HD Mila"
        elif abs(hash(seed)) % 3 == 1 and gender != "female":
            if (char_dir / "HD Gibro_Body Shape.ccSlider").is_file():
                prefix = "HD Gibro"
        # Never load *_Body Ratio.ccSlider here — stacking Ratio content with
        # height morphs collapses the mesh. Height uses one Ratio morph in OpenPlugin.
        # Skip Body Shape when tall/short so Ratio morph is the sole body-proportion driver.
        suffixes = ("_Head Shape.ccSlider",)
        if "tall" not in traits and "short" not in traits:
            suffixes = ("_Body Shape.ccSlider",) + suffixes
        for suffix in suffixes:
            p = char_dir / f"{prefix}{suffix}"
            if p.is_file():
                out.append(p)

    skin_dirs = [
        base / "Skin" / "Overall" / "CC5 Human 2K",
        base / "Skin" / "Overall" / "CC5 Stylized 2K",
    ]
    if gender == "female":
        # Ariana/Neutral F Overall skins are often absent; prefer installed Mila first
        skin_names = ["HD Mila_2K.ccSkin", "HD Ariana_2K.ccSkin", "HD Neutral F_2K.ccSkin"]
    else:
        skin_names = ["HD Aaron_2K.ccSkin", "HD Neutral M_2K.ccSkin", "HD Gibro_2K.ccSkin"]
    for d in skin_dirs:
        hit = False
        for name in skin_names:
            p = d / name
            if p.is_file():
                out.append(p)
                hit = True
                break
        if hit:
            break

    # Wearables stay in resolve_wearable_assets — body packs only here so older
    # OpenPlugin builds apply morphs before AutoSkin clothes (avoids floating gear).

    seen: set[str] = set()
    paths: list[str] = []
    for p in out:
        try:
            key = str(p.resolve())
        except OSError:
            key = str(p)
        if key in seen:
            continue
        seen.add(key)
        paths.append(str(p))
    return paths


def resolve_wearable_assets(plan: dict[str, Any]) -> list[str]:
    """Free Resource cloth/hair for OpenPlugin builds that load wearables after morphs."""
    base = _cc5_characters_dir()
    if base is None:
        return []
    gender = str(plan.get("gender") or "male").lower()
    seed = str(plan.get("seed") or "x")
    prompt = str(plan.get("prompt") or "")
    picks = _resolve_outfit_paths(base, gender=gender, seed=seed, prompt=prompt)
    picks.extend(_autoskin_gap_fills(picks, gender=gender))
    # Deduplicate while preserving order
    seen: set[str] = set()
    out: list[str] = []
    for p in picks:
        if not p.is_file():
            continue
        key = str(p.resolve()) if p.exists() else str(p)
        if key in seen:
            continue
        seen.add(key)
        out.append(str(p))
    return out


def _cc5_program_root() -> Optional[Path]:
    """Character Creator 5 install root (…/Character Creator 5/)."""
    try:
        from cc5_bridge import find_cc5
    except ImportError:
        try:
            from hephaestus_forge.cc5_bridge import find_cc5  # type: ignore
        except ImportError:
            find_cc5 = None  # type: ignore
    if find_cc5:
        exe = find_cc5()
        if exe:
            # …/Bin64/CharacterCreator.exe → parents[1] = Character Creator 5 root
            return Path(exe).resolve().parents[1]
    for candidate in (
        Path(r"C:\Program Files\Reallusion\Character Creator 5\Character Creator 5"),
        Path(r"D:\Program Files\Reallusion\Character Creator 5\Character Creator 5"),
    ):
        if candidate.is_dir():
            return candidate
    return None


def _autoskin_gap_fills(already: list[Path], *, gender: str) -> list[Path]:
    """
    Aaron Outfit Set is pants+shoes only — fill shirt/hair/shoes from AutoSkin when missing.

    Uses Program/.../AutoSkin/RL_CC3_Plus (present on standard CC5 installs).
    """
    names = " ".join(p.name.lower() for p in already)
    root = _cc5_program_root()
    if root is None:
        return []
    cloth_dir = root / "Program" / "CCBaseData" / "AutoSkin" / "RL_CC3_Plus"
    if not cloth_dir.is_dir():
        return []
    fills: list[Path] = []
    has_top = any(
        k in names
        for k in ("full_body", "dress", "apron", "sweater", "shirt", "top", "halter", "jacket")
    )
    has_hair = ".rlhair" in names or ".cchair" in names or "hair.cc" in names
    has_shoes = ".ccshoes" in names or "sneaker" in names or "boot" in names or "heel" in names
    if not has_top:
        top = cloth_dir / ("Dress.ccCloth" if gender == "female" else "Full_Body.ccCloth")
        if top.is_file():
            fills.append(top)
    if not has_hair:
        hair = cloth_dir / "Hair.ccHair"
        if hair.is_file():
            fills.append(hair)
    if not has_shoes:
        shoe = cloth_dir / "Shoe.ccShoes"
        if shoe.is_file():
            fills.append(shoe)
    return fills


def _resolve_outfit_paths(
    base: Path, *, gender: str, seed: str, prompt: str = ""
) -> list[Path]:
    """Pick one clothing set + hair when Free Resource files exist."""
    picks: list[Path] = []
    cloth_root = base / "Cloth" / "Others"
    text = f"{prompt} {seed}".lower()
    want_work = bool(re.search(r"\b(work|apron|gibro|lab|uniform)\b", text))
    if gender == "female":
        set_dirs = [
            cloth_root / "Ariana Party Set",
            cloth_root / "Mila Outfit Set",
        ]
    elif want_work:
        set_dirs = [
            cloth_root / "Gibro Work Set",
            cloth_root / "Aaron Outfit Set",
        ]
    else:
        # Aaron trousers+sneakers conform reliably; Gibro apron/boots often float
        # when loaded before morphs on older Program Files OpenPlugin builds.
        set_dirs = [
            cloth_root / "Aaron Outfit Set",
            cloth_root / "Gibro Work Set",
        ]
    existing_sets = [d for d in set_dirs if d.is_dir()]
    if existing_sets:
        # Prefer first existing (Aaron for sporty/default male)
        chosen = existing_sets[0]
        if want_work and len(existing_sets) > 1:
            chosen = existing_sets[abs(hash(seed)) % len(existing_sets)]
        cloth_files = sorted(chosen.rglob("*.ccCloth"))
        shoe_files = sorted(chosen.rglob("*.ccShoes"))
        # Cap cloth pieces — skip accessories like glasses that export unbound
        for bucket in (cloth_files[:2], shoe_files[:1]):
            picks.extend(bucket)

    hair_root = base / "Hair" / "Group" / "Hair"
    hair_candidates: list[Path] = []
    if hair_root.is_dir():
        hair_candidates.extend(sorted(hair_root.glob("*.rlHair")))
        hair_candidates.extend(sorted(hair_root.glob("*.ccHair")))
    if gender == "female":
        prefer = ("pixie", "wave", "bob", "long")
    else:
        prefer = ("slick", "short", "classic", "fade")
    hair_pick: Optional[Path] = None
    for pref in prefer:
        for h in hair_candidates:
            if pref in h.stem.lower():
                hair_pick = h
                break
        if hair_pick:
            break
    if hair_pick is None and hair_candidates:
        hair_pick = hair_candidates[abs(hash(seed)) % len(hair_candidates)]
    if hair_pick:
        picks.append(hair_pick)

    # Eyebrows (subtle)
    brow_dir = base / "Hair" / "Group" / "Eyebrows" / ("HD Brows_F" if gender == "female" else "HD Brows_M")
    if brow_dir.is_dir():
        brows = sorted(brow_dir.glob("*.rlHair")) + sorted(brow_dir.glob("*.ccHair"))
        if brows:
            picks.append(brows[0])

    return picks


def infer_appearance(
    prompt: str = "",
    *,
    character_name: str = "Character",
) -> dict[str, Any]:
    """
    Build an appearance plan for the CC5 OpenPlugin.

    Morph keys are display-name needles (matched case-insensitively / substring).
    Weights are typically -1..1 for CC shaping sliders.
    """
    text = f"{prompt or ''} {character_name or ''}".strip().lower()
    seed = f"{character_name}|{prompt}".strip() or "hephaestus"

    female = bool(
        re.search(
            r"\b(female|woman|girl|lady|she|her|actress|queen|mother|sister)\b",
            text,
        )
    )
    male = bool(
        re.search(
            r"\b(male|man|boy|guy|he|him|actor|king|father|brother)\b",
            text,
        )
    )
    if female and not male:
        gender = "female"
    elif male and not female:
        gender = "male"
    else:
        gender = "female" if _stable_unit(seed, "gender") > 0.55 else "male"

    morphs: dict[str, float] = {}
    traits: list[str] = []

    # Height — CC "Character Height" is inverted (negative = taller)
    if re.search(r"\b(tall|towering|giant|lanky)\b", text):
        morphs["height"] = -0.75 - 0.2 * _stable_unit(seed, "tall")
        traits.append("tall")
    elif re.search(r"\b(short|petite|tiny|small)\b", text):
        morphs["height"] = 0.55 + 0.25 * _stable_unit(seed, "short")
        traits.append("short")
    else:
        morphs["height"] = _signed_unit(seed, "height") * 0.45

    if re.search(r"\b(muscular|buff|strong|ripped|bodybuilder|athletic)\b", text):
        morphs["muscle"] = 0.7 + 0.3 * _stable_unit(seed, "muscle")
        morphs["bodybuilder"] = 0.35 + 0.3 * _stable_unit(seed, "bb")
        morphs["athletic"] = 0.5 + 0.3 * _stable_unit(seed, "ath")
        traits.append("muscular")
    elif re.search(r"\b(thin|skinny|slim|slender|lean)\b", text):
        morphs["thin"] = 0.65 + 0.3 * _stable_unit(seed, "thin")
        morphs["slender"] = 0.5 + 0.3 * _stable_unit(seed, "slen")
        morphs["muscle"] = -0.2
        traits.append("thin")
    elif re.search(r"\b(heavy|fat|large|stocky|bulky|overweight)\b", text):
        morphs["heavy"] = 0.55 + 0.35 * _stable_unit(seed, "heavy")
        morphs["overweight"] = 0.4 + 0.3 * _stable_unit(seed, "ow")
        traits.append("heavy")
    else:
        morphs["muscle"] = _signed_unit(seed, "m") * 0.55
        morphs["thin"] = max(0.0, _signed_unit(seed, "t") * 0.4)
        morphs["heavy"] = max(0.0, _signed_unit(seed, "h") * 0.35)
        morphs["athletic"] = max(0.0, _signed_unit(seed, "a") * 0.5)

    if re.search(r"\b(old|elderly|aged|senior)\b", text):
        morphs["age"] = 0.7 + 0.25 * _stable_unit(seed, "age")
        traits.append("old")
    elif re.search(r"\b(young|teen|youth|kid|child)\b", text):
        morphs["age"] = -0.4
        morphs["young"] = 0.6
        traits.append("young")
    else:
        morphs["age"] = _signed_unit(seed, "age") * 0.35

    for label, salt, amp in (
        ("face width", "fw", 0.4),
        ("jaw", "jaw", 0.45),
        ("nose", "nose", 0.4),
        ("eye width", "eyes", 0.35),
        ("brow", "brow", 0.35),
        ("cheek", "cheek", 0.4),
        ("mouth", "mouth", 0.35),
        ("chin", "chin", 0.4),
        ("slacker", "slack", 0.5),
    ):
        morphs[label] = _signed_unit(seed, salt) * amp

    if re.search(r"\b(angry|fierce|mean)\b", text):
        morphs["brow"] = 0.6
        morphs["jaw"] = 0.5
        traits.append("fierce")
    if re.search(r"\b(friendly|soft|gentle)\b", text):
        morphs["slacker"] = 0.4
        morphs["jaw"] = -0.3
        traits.append("soft")

    plan: dict[str, Any] = {
        "gender": gender,
        "template_preference": "female" if gender == "female" else "male",
        "morphs": morphs,
        "traits": traits,
        "seed": seed,
        "prompt": prompt or "",
        "character_name": character_name,
        "force_new": True,
    }
    plan["content_assets"] = resolve_content_assets(plan)
    plan["wearable_assets"] = resolve_wearable_assets(plan)
    # Older Program Files OpenPlugin only reads content_assets and loads them
    # before morphs. Append wearables after body packs so muscular/skin apply
    # first; live OpenPlugin still prefers wearable_assets after morphs.
    if plan["wearable_assets"]:
        body = list(plan["content_assets"])
        wear = list(plan["wearable_assets"])
        plan["content_assets"] = body + [p for p in wear if p not in body]
    return plan


def appearance_summary(plan: Optional[dict[str, Any]]) -> str:
    if not plan:
        return ""
    bits = [str(plan.get("gender") or "")]
    traits = plan.get("traits") or []
    bits.extend(str(t) for t in traits[:4])
    assets = plan.get("content_assets") or []
    wear = plan.get("wearable_assets") or []
    if assets:
        bits.append(f"{len(assets)} content packs")
    if wear:
        bits.append(f"{len(wear)} wearables")
    return ", ".join(b for b in bits if b)

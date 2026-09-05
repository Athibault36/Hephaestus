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
    if "muscular" in traits and gender != "female":
        muscle_dir = embed / "Male Muscular"
        for name in (
            "Male Muscular Body.ccSlider",
            "Male Muscular Chest A.ccSlider",
            "Male Muscular Arm.ccSlider",
            "Male Muscular Shoulder.ccSlider",
            "Male Muscular Abs.ccSlider",
            "Male Muscular Thigh.ccSlider",
        ):
            p = muscle_dir / name
            if p.is_file():
                out.append(p)
    elif "thin" in traits and gender != "female":
        skinny_dir = embed / "Male Skinny"
        for name in (
            "Male Skinny Body.ccSlider",
            "Male Skinny Chest.ccSlider",
            "Male Skinny Arm.ccSlider",
            "Male Skinny Thigh.ccSlider",
        ):
            p = skinny_dir / name
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
        for suffix in ("_Body Shape.ccSlider", "_Body Ratio.ccSlider", "_Head Shape.ccSlider"):
            p = char_dir / f"{prefix}{suffix}"
            if p.is_file():
                out.append(p)

    skin_dirs = [
        base / "Skin" / "Overall" / "CC5 Human 2K",
        base / "Skin" / "Overall" / "CC5 Stylized 2K",
    ]
    if gender == "female":
        skin_names = ["HD Ariana_2K.ccSkin", "HD Mila_2K.ccSkin", "HD Neutral F_2K.ccSkin"]
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
    return plan


def appearance_summary(plan: Optional[dict[str, Any]]) -> str:
    if not plan:
        return ""
    bits = [str(plan.get("gender") or "")]
    traits = plan.get("traits") or []
    bits.extend(str(t) for t in traits[:4])
    assets = plan.get("content_assets") or []
    if assets:
        bits.append(f"{len(assets)} content packs")
    return ", ".join(b for b in bits if b)

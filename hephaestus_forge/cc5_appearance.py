# Copyright (c) 2024 HephaestusForge. All Rights Reserved.
"""Infer CC5 appearance plans from natural-language prompts."""

from __future__ import annotations

import hashlib
import re
from typing import Any, Optional


def _stable_unit(seed: str, salt: str = "") -> float:
    """Deterministic 0..1 from seed."""
    h = hashlib.sha256(f"{seed}|{salt}".encode("utf-8")).hexdigest()
    return int(h[:8], 16) / 0xFFFFFFFF


def _signed_unit(seed: str, salt: str) -> float:
    """Deterministic -1..1."""
    return _stable_unit(seed, salt) * 2.0 - 1.0


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
        # Name/seed tie-break when unspecified
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
        # Unique body from seed so every name differs
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

    # Face / head variety from seed (needles matched if present in CC)
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

    return {
        "gender": gender,
        "template_preference": "female" if gender == "female" else "male",
        "morphs": morphs,
        "traits": traits,
        "seed": seed,
        "prompt": prompt or "",
        "character_name": character_name,
        "force_new": True,
    }


def appearance_summary(plan: Optional[dict[str, Any]]) -> str:
    if not plan:
        return ""
    bits = [str(plan.get("gender") or "")]
    traits = plan.get("traits") or []
    bits.extend(str(t) for t in traits[:4])
    return ", ".join(b for b in bits if b)

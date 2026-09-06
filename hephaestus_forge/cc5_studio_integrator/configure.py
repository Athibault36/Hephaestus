# Copyright (c) 2024 HephaestusForge. All Rights Reserved.
"""Character configuration (morphs, clothing, materials plan)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from .audit import audit_log
from .session import get_session


def configure_character(params_dict: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """
    Build / merge a CC5 appearance plan for the next export.

    Accepted keys (all optional):
      prompt, character_name, morphs, traits, gender, content_assets, wearable_assets,
      force_new, features (dict: clothing/hair/physics — best-effort flags for OpenPlugin)
    """
    params = dict(params_dict or {})
    try:
        from cc5_appearance import infer_appearance, appearance_summary
    except ImportError:
        from hephaestus_forge.cc5_appearance import infer_appearance, appearance_summary  # type: ignore

    name = str(params.get("character_name") or params.get("name") or "Character")
    prompt = str(params.get("prompt") or "")
    plan = infer_appearance(prompt, character_name=name)

    if params.get("gender"):
        plan["gender"] = str(params["gender"]).lower()
        plan["template_preference"] = plan["gender"]
    if isinstance(params.get("morphs"), dict):
        plan.setdefault("morphs", {}).update({str(k): float(v) for k, v in params["morphs"].items()})
    if params.get("traits"):
        traits = list(plan.get("traits") or [])
        for t in params["traits"]:
            if t not in traits:
                traits.append(t)
        plan["traits"] = traits
    if params.get("content_assets"):
        plan["content_assets"] = list(params["content_assets"])
    if params.get("wearable_assets"):
        plan["wearable_assets"] = list(params["wearable_assets"])
        # Keep PF-compat: body + wear in content_assets
        body = [p for p in (plan.get("content_assets") or []) if Path(str(p)).suffix.lower() not in (
            ".cccloth", ".ccshoes", ".cchair", ".ccgloves", ".rlhair"
        )]
        plan["content_assets"] = body + list(plan["wearable_assets"])
    if "force_new" in params:
        plan["force_new"] = bool(params["force_new"])

    features = params.get("features") or {}
    plan["features"] = {
        "clothing": features.get("clothing", True),
        "hair": features.get("hair", True),
        "physics": features.get("physics", False),
        "facial_rig": features.get("facial_rig", True),
    }

    sess = get_session()
    sess_cfg = sess.get("config") if isinstance(sess.get("config"), dict) else {}
    sess_cfg = dict(sess_cfg)
    sess_cfg["appearance"] = plan
    # mutate live session store
    try:
        from . import session as session_mod

        session_mod._SESSION["config"] = sess_cfg
        session_mod._persist()
    except Exception:
        pass

    out = {
        "ok": True,
        "appearance": plan,
        "summary": appearance_summary(plan),
        "morph_count": len(plan.get("morphs") or {}),
        "content_count": len(plan.get("content_assets") or []),
        "wearable_count": len(plan.get("wearable_assets") or []),
    }
    audit_log("configure_character", ok=True, detail={"summary": out["summary"], "name": name})
    return out

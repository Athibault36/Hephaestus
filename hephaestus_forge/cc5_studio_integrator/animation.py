# Copyright (c) 2024 HephaestusForge. All Rights Reserved.
"""Animation generation — UE PIE side (CC5 does not stream clips to studio)."""

from __future__ import annotations

from typing import Any, Optional

from .audit import audit_log
from .capabilities import CAPABILITIES


def generate_animation(
    clip_name: str = "idle",
    blend_params: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """
    Play / capture animation on the last authored actor in UE PIE.

    clip_name: idle | walk | spin (mapped to HephaestusBridge commands)
    blend_params: optional actor_path, frames, project hints

    CC5-native clip streaming is unsupported — see capabilities matrix.
    """
    if not CAPABILITIES["animation_playback_ue"]["supported"]:
        err = "ue_animation_unavailable"
        audit_log("generate_animation", ok=False, error=err)
        return {"ok": False, "error": err}

    params = dict(blend_params or {})
    actor_path = params.get("actor_path") or params.get("actor")
    mode = (clip_name or "idle").strip().lower()
    if mode in ("walk", "locomotion", "run"):
        mode = "walk"
    elif mode in ("spin", "turn"):
        mode = "spin"
    else:
        mode = "idle"

    if not actor_path:
        err = "actor_path required — pass blend_params['actor_path'] from export/import result"
        audit_log("generate_animation", ok=False, error=err)
        return {
            "ok": False,
            "error": err,
            "hint": "export_asset(import_to_ue=True) then generate_animation(..., blend_params={actor_path: ...})",
        }

    try:
        from agent_dcc import animate_authored_actor
    except ImportError:
        from hephaestus_forge.agent_dcc import animate_authored_actor  # type: ignore

    result = animate_authored_actor(str(actor_path), mode=mode)
    ok = bool(result and result.get("success"))
    audit_log(
        "generate_animation",
        ok=ok,
        detail={"clip": mode, "actor_path": actor_path, "result": result},
        error="" if ok else str((result or {}).get("error") or "animate_failed"),
    )
    return {
        "ok": ok,
        "clip_name": mode,
        "actor_path": actor_path,
        "result": result,
        "backend": "ue58_hephaestus_bridge",
        "cc5_native": False,
    }

# Copyright (c) 2024 HephaestusForge. All Rights Reserved.
"""Honest capability matrix for CC5 ↔ Hephaestus studio control."""

from __future__ import annotations

from typing import Any

# Locked to the OpenPlugin + UE Remote API surface we actually ship.
CC5_COMPAT = "Character Creator 5 (RLPy via HephaestusExport OpenPlugin)"
UE_COMPAT = "Unreal Engine 5.8 (HephaestusBridge Remote API :8765/:8766)"
INTEGRATOR_VERSION = "1.0.0"

CAPABILITIES: dict[str, dict[str, Any]] = {
    "spawn_configure_export": {
        "supported": True,
        "via": "OpenPlugin job queue + appearance plan (morphs, Free Resource, AutoSkin fills)",
    },
    "morph_targets_rw": {
        "supported": True,
        "via": "appearance['morphs'] applied in CC5 OpenPlugin (_apply_morphs)",
        "notes": "Write via job; read-back is alter summary, not live morph stream",
    },
    "material_pbr_override": {
        "supported": "partial",
        "via": "CC5 .fbm sidecars + HephaestusBridge BindFbmTextures (Diffuse/Normal/Opacity/Metallic/Roughness)",
        "notes": "No arbitrary shader graph rewrite inside CC5 from studio",
    },
    "clothing_layers": {
        "supported": True,
        "via": "content_assets / wearable_assets (.ccCloth/.ccShoes/.rlHair) + AutoSkin gap fills",
    },
    "bone_transforms_rw": {
        "supported": False,
        "notes": "CC5 RLPy does not expose full bone R/W for studio; pose in UE after import",
    },
    "physics_sim_interrupt": {
        "supported": False,
        "notes": "Cannot interrupt CC5 PhysX threads from outside; disable features via appearance flags only",
    },
    "ui_lock_override": {
        "supported": "partial",
        "via": "dialog_control.auto_dismiss (Apply Material, unsaved project, export prompts)",
        "notes": "Does not freeze entire CC5 UI; dismisses blocking modals",
    },
    "animation_playback_cc5": {
        "supported": False,
        "notes": "Walk/idle authored in UE PIE via HephaestusBridge after FBX import",
    },
    "animation_playback_ue": {
        "supported": True,
        "via": "animation.play_transform_sequence / locomotion commands on :8765",
    },
    "export_fbx": {
        "supported": True,
        "via": "OpenPlugin ExportFbxFile + .fbm sidecar",
    },
    "export_usdz_gltf": {
        "supported": False,
        "notes": "Out of scope for Hephaestus UE path; FBX → UE native is the studio format",
    },
    "unity_backend": {
        "supported": False,
        "notes": "Hephaestus targets UE 5.8 only",
    },
    "batch_50_parallel": {
        "supported": False,
        "notes": "CC5 GUI is single-instance; queue jobs serially (async poll OK)",
    },
    "audit_log": {
        "supported": True,
        "via": "~/.hephaestus/cc5_audit/*.jsonl",
    },
    "config_rollback": {
        "supported": "partial",
        "via": "session snapshot JSON; re-apply appearance on next configure/export",
    },
}


def capability_report() -> dict[str, Any]:
    return {
        "integrator_version": INTEGRATOR_VERSION,
        "cc5_compat": CC5_COMPAT,
        "ue_compat": UE_COMPAT,
        "capabilities": CAPABILITIES,
    }

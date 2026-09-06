# Copyright (c) 2024 HephaestusForge. All Rights Reserved.
"""
# CC5 Studio Integrator (Hephaestus)

Programmatic Character Creator 5 control for the Hephaestus AI animation studio
(Unreal Engine 5.8). This module is the **studio-facing API**; the implementation
uses the HephaestusExport OpenPlugin job queue + HephaestusBridge Remote API.

## Architecture

```
Studio scripts / forge chat
        │
        ▼
cc5_studio_integrator (this package)
        │
        ├─► cc5_appearance (morph / cloth / hair plans)
        ├─► cc5_bridge OpenPlugin jobs (~/.hephaestus/cc5_jobs)
        ├─► dialog_control (Apply Material, unsaved project, …)
        └─► dcc_import + agent_dcc (UE FBX import, height scale, idle/walk)
                │
                ▼
        HephaestusBridge :8765/:8766  (UE 5.8 PIE)
```

## Dependencies

| Component | Version / notes |
|-----------|-----------------|
| Python | 3.10+ |
| Character Creator 5 | Installed; OpenPlugin live copy under `~/.hephaestus/cc5_openplugin_live/` |
| Unreal Engine | 5.8 + HephaestusBridge ≥ 1.0.9 |
| Host OS | Windows (dialog control / CC5) |

## Entry points

```python
from hephaestus_forge.cc5_studio_integrator import (
    initialize_cc5_session,
    configure_character,
    export_asset,
    generate_animation,
    terminate_cc5_session,
    detach_cc5_control,
    capability_report,
)

initialize_cc5_session("ue58", {"project_root": r"C:\\dev\\MyGame", "dismiss_dialogs": True})
configure_character({
    "prompt": "tall muscular man named Atlas",
    "character_name": "Atlas",
    "morphs": {"muscle": 0.9, "jaw": 0.4, "nose": 0.2},
})
result = export_asset("fbx", import_to_ue=True, timeout_seconds=600)
actor = ((result.get("import") or {}).get("actor_path")
         or ((result.get("import") or {}).get("spawn_results") or [{}])[-1].get("actor_paths", [None])[0])
generate_animation("idle", {"actor_path": actor})
terminate_cc5_session()
```

## Capability matrix (honest)

See `capability_report()` — highlights:

| Requirement from mega-briefs | Status |
|------------------------------|--------|
| Morph targets R/W via plan | Yes (OpenPlugin) |
| Cloth / hair Free Resource | Yes |
| PBR textures into UE MICs | Yes (.fbm Diffuse/Normal/Opacity/Metallic/Roughness) |
| FBX export + validation JSON | Yes |
| UE idle/walk after import | Yes |
| Full bone R/W inside CC5 | **No** (use UE after import) |
| USDZ / glTF / Unity | **No** (UE 5.8 path only) |
| 50 parallel CC5 instances | **No** (single GUI; serial jobs) |
| <2s per character authoring | **No** (typical 60–600s) |
| Lock entire CC5 UI | Partial (modal dismiss only) |

## Troubleshooting

1. **`cc5_job_timeout`** — Keep Character Creator running; ensure OpenPlugin loaded (`forge cc5 install-plugin`). Dialog watch should dismiss **Apply Material**.
2. **`live_updated_program_files_locked`** — Live plugin updates under `~/.hephaestus/cc5_openplugin_live/`. One-time writable bootstrap under Program Files unlocks no-Admin updates (never elevate from Hephaestus).
3. **Pale skin in PIE** — Require sibling `.fbm` with Diffuse maps; bridge ≥ 1.0.9.
4. **Spaghetti mesh** — Never use Body Ratio for height; use uniform PIE scale (already wired).

## Extension points

- Add export formats: extend `export_asset` only after a real converter exists.
- Richer morph read-back: extend OpenPlugin alter payload.
- CI: `pytest hephaestus_forge/tests/test_cc5_studio_integrator.py`.

## Emergency stop

```python
from hephaestus_forge.cc5_studio_integrator import detach_cc5_control
detach_cc5_control("operator_interrupt")
```

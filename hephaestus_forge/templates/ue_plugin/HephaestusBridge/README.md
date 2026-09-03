# HephaestusBridge (UE 5.8)

Runtime plugin exposing the Hephaestus Remote API on **PIE port 8765**.

## Sync from factory

```powershell
forge sync-plugin C:\path\to\YourGame
```

Rebuild **Development Editor** after sync. Version in `/v1/health` comes from `HephaestusVersion.h` (kept in sync by `forge sync-plugin`).

## Endpoints (PIE)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/v1/health` | Service + `plugin_version` |
| POST | `/v1/command` | Bridge verbs (`params` object) |
| GET | `/v1/frame` | Latest captured viewport PNG |

## Supported command families (v1.0)

- **world.*** — list/spawn/edit actors, move input, pawn state, **camera**
  - `world.get_view` — PIE camera location / rotation / forward
  - `world.set_view` — position view (`mode`: `free` default = dedicated CameraActor + SetViewTarget; `pawn` = teleport player). Optional `look_at_actor`, `distance`, `yaw_offset`, `height` for orbit framing.
- **vision.capture_frame** — PNG to `Saved/Hephaestus/`
- **animation.*** — locomotion, montage
- **asset.*** — create_material, create_instance, search (import/reimport deferred)
- **sequence.*** — create_shot (animated free camera; same orbit params), play
- **audio.*** — play_quartz; create_metasound needs existing `source_path`
- **blueprint.compile** — compile only; mutation verbs stubbed
- **pcg.*** — spatial query

After C++ camera changes: `forge sync-plugin <target>`, rebuild HephaestusBridge, **restart editor**, Play (PIE).

## Stubbed (post-1.0)

These log and return `success: false`:

- Blueprint property/function mutation
- Animation retarget / sequence edit
- Rendering compute graph
- FBX import pipeline (validation-only path in suite F)
- WebRTC stream / hardware H.264 encode

## Dependencies

Enable in `.uplugin`: **PythonScriptPlugin**, **MetaSound**.

## Docs

- Factory: https://github.com/Athibault36/Hephaestus
- Production guide: `docs/PRODUCTION.md` in factory repo

# Release v0.1.1

## Operator batch

- `forge doctor` — checklist + e2e + preflight
- `forge e2e` / `forge adopt --e2e-sync`
- Bridge capability matrix preflight (locomotion, sequencer, list_actors, montage)
- Mission Control React: outliner menu, asset filters, preflight banner, SSE reconnect
- Session export schema v2 (thoughts + command transcript)
- Per-target `.hephaestus_forge/locomotion.json` overrides

## Manual step (required for live PIE)

```powershell
forge sync-plugin <PATH-TO-UE-PROJECT>
# Rebuild HephaestusBridge in UE 5.8, disable Live Coding, Play (PIE)
forge doctor <PATH-TO-UE-PROJECT>
```

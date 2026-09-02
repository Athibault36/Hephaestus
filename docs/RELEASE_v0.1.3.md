# Release v0.1.3

## Operator batch (v0.3 + v0.4)

- **Mission Control direct chat:** `play test audio`, `search assets for …`
- **Grading:** audio, material, camera, creature asset matching
- **CLI JSON:** `forge health --json`, `forge e2e --json`, `forge doctor --json`
- **Bridge:** blueprint diff/validation, retarget mesh validation, rendering + PCG param checks
- **Heuristic loop:** audio + material goals without LLM
- **Preflight / E2E:** reimport, PCG spatial query probes

## Manual step

```powershell
forge sync-plugin <PATH-TO-UE-PROJECT>
# UE 5.8: rebuild HephaestusBridge (v0.1.3), Play (PIE)
forge doctor <PATH-TO-UE-PROJECT> --json
```

See [OPERATOR_V0_3.md](OPERATOR_V0_3.md) and [LIVE_E2E.md](LIVE_E2E.md).

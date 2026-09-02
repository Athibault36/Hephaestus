# Release v0.1.9 — operator v0.9

## Production gate

```powershell
forge gate <PATH-TO-UE-PROJECT>
forge gate <PATH-TO-UE-PROJECT> --json
```

Exit `0` when offline blockers pass and (when PIE is up) preflight is ready.

## Shipped since v0.1.3

- Session export **schema v3** with `operator_milestone`
- `HEPHAESTUS_HEURISTIC_REPAIR` for non-NIM repair loops
- Displacement grading + PCG `mutations` array
- `audio.play_metasound` command alias
- Mission Control shows **forge version** + milestone pill
- [OPERATOR_V0_9.md](OPERATOR_V0_9.md) acceptance criteria

## Manual step

```powershell
forge sync-plugin <PATH-TO-UE-PROJECT>
# UE 5.8: rebuild HephaestusBridge v0.1.9, Play (PIE)
forge gate <PATH-TO-UE-PROJECT> --json
```

# Release v1.0.0 — autonomous operator

## Autonomous CLI

```powershell
forge run <PATH-TO-UE-PROJECT> "your goal"
forge autonomous-suite <PATH-TO-UE-PROJECT> --json
```

## Shipped

- `autonomous_runner` — unified NIM-required goal runner with repair loop
- `forge run` + `forge autonomous-suite` (operator A–G)
- Mission Control chat uses same runner
- Session export schema **v4** + `autonomous_report`
- Planner actions: `create_material`, `asset_search`, `play_audio`
- [OPERATOR_V1.md](OPERATOR_V1.md)

## Manual step

```powershell
forge sync-plugin <PATH-TO-UE-PROJECT>
# UE 5.8: rebuild HephaestusBridge 1.0.0, Play (PIE)
forge autonomous-suite <PATH-TO-UE-PROJECT> --json
```

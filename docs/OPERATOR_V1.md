# Operator v1.0 — autonomous acceptance

NIM-required autonomous operator. Builds on [OPERATOR_V0_9.md](OPERATOR_V0_9.md).

## Commands

```powershell
pip install -e .
export NVIDIA_API_KEY=nvapi-...

forge run <PATH-TO-UE-PROJECT> "spawn a dog and make it walk"
forge run <PATH-TO-UE-PROJECT> "frame the shot" --json

forge autonomous-suite <PATH-TO-UE-PROJECT>
forge autonomous-suite <PATH-TO-UE-PROJECT> --scenario A --scenario B --json
forge autonomous-suite <PATH-TO-UE-PROJECT> --offline   # infra C/D only
```

Mission Control chat uses the same autonomous runner (repair on by default).

## Scenarios A–G

| ID | Type | Requirement |
|----|------|-------------|
| A | Autonomous | Spawn creature → walk → grade |
| B | Autonomous | Cinematic framing |
| C | Infra | Mission Control dist present |
| D | Infra | `forge gate` blockers pass |
| E1–E4 | Direct | spawn / locomotion / audio / search |
| F | Autonomous | Material + reimport validation recovery |
| G1–G4 | Autonomous | material / audio / camera / displacement grading |

## Policy

- **NIM required** — no silent heuristic fallback on autonomous paths
- **Repair loop** — forced on autonomous path when grade fails
- Session export **schema v4** includes `autonomous_report`

## Live checklist

[docs/LIVE_E2E.md](LIVE_E2E.md)

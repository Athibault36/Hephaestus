# Operator v1.0 — autonomous acceptance

NIM-required autonomous operator. Builds on [OPERATOR_V0_9.md](OPERATOR_V0_9.md).

## Commands

```powershell
pip install -e .
export NVIDIA_API_KEY=nvapi-...

# Engage PIE without clicking Play (requires bridge ≥ 1.0.1)
forge up <PATH-TO-UE-PROJECT>          # opens editor if needed, then PIE
# or: forge pie start <PATH-TO-UE-PROJECT>  # when editor already open

forge run <PATH-TO-UE-PROJECT> "spawn a dog and make it walk"
forge run <PATH-TO-UE-PROJECT> "frame the shot" --json

forge autonomous-suite <PATH-TO-UE-PROJECT>
forge autonomous-suite <PATH-TO-UE-PROJECT> --scenario A --scenario B --json
forge autonomous-suite <PATH-TO-UE-PROJECT> --offline   # infra C/D only

forge down                             # stop PIE
forge down --quit-editor               # stop PIE + quit Unreal
```

Mission Control chat uses the same autonomous runner (repair on by default).

## PIE ports

| Port | When | Commands |
|------|------|----------|
| `:8766` | Editor open | `forge up` / `forge pie start` / `stop` / `status` |
| `:8765` | PIE running | world / animation / suite |

Hands-off: `forge up <project>` launches the editor (via `UE_PATH`) if needed, then starts PIE. `forge down [--quit-editor]` tears down.

See [ENV_FLAGS.md](ENV_FLAGS.md).

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

- **NIM required** — no silent heuristic fallback on autonomous paths (`forge run`, `forge autonomous-suite`, MC chat, `/agent/loop`)
- **Repair loop** — forced on autonomous path when grade fails
- Session export **schema v4** includes `autonomous_report`

## Failure modes

| Symptom | Meaning | Action |
|---------|---------|--------|
| `llm_error` in JSON | No API key or NIM unreachable | Set `NVIDIA_API_KEY`, retry |
| Gate `preflight_ue_pie` fail | PIE not running | `forge pie start <project>` or Play in UE |
| Editor `:8766` offline | Plugin not rebuilt / editor closed | Rebuild HephaestusBridge 1.0.1+, restart editor |
| `plugin_version` mismatch | Stale DLL or header | `forge sync-plugin`, rebuild, restart editor |
| `mission_control_dist` fail | No Vite build | `forge observe` (auto-build) or `forge build-mc` |
| Grade `missing: ["nim_planner"]` | Autonomous path without NIM | Expected — not a bug |

## Heuristic planner (dev only)

`forge loop --planner heuristic` or `--planner auto` without API key uses local heuristics. **Not** used for production acceptance.

## Live checklist

[docs/LIVE_E2E.md](LIVE_E2E.md) · [docs/PRODUCTION.md](PRODUCTION.md)

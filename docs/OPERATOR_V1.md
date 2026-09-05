# Operator v1.0 — autonomous acceptance

Builds on [OPERATOR_V0_9.md](OPERATOR_V0_9.md). Live PIE delivery via HephaestusBridge **≥ 1.0.1**.

## Commands

```powershell
pip install -e .
# NVIDIA_API_KEY in factory .env or user env (required for NIM-only goals)

forge up <PATH-TO-UE-PROJECT>          # launch editor if needed → PIE
forge autonomous-suite <PATH-TO-UE-PROJECT>
forge autonomous-suite <PATH-TO-UE-PROJECT> --scenario A --scenario E2 --json
forge autonomous-suite <PATH-TO-UE-PROJECT> --offline   # infra C/D only
forge down                             # stop PIE
forge down --quit-editor               # stop PIE + quit Unreal
```

Mission Control chat uses the autonomous runner (repair on by default) for plain-language goals.

## PIE ports

| Port | When | Commands |
|------|------|----------|
| `:8766` | Editor open | `forge up` / `forge pie start` / `stop` / `status` |
| `:8765` | PIE running | world / animation / suite |

Identity: `/v1/health` includes `project_name` / `project_dir`. Suite and health **refuse** a mismatched PIE vs forge target.

See [ENV_FLAGS.md](ENV_FLAGS.md).

## Suite scenarios (code truth)

CLI summary: `ok=True/False` with **passed** / **skipped** / **failed** counts.

| ID | Kind | What it does |
|----|------|----------------|
| C | infra | Mission Control `dist` present |
| D | infra | `forge gate` offline blockers |
| A | direct | Spawn SK + walk (`anim` if AnimSequence found, else **transform** displace) |
| B | direct | Cinematic framing (`world.set_view` look-at) |
| E1 | direct | Spawn StaticMesh (Cube / project mesh) |
| E2 | direct | Same locomotion path as A |
| E3 | direct | Test audio |
| E4 | direct | `asset.search` skeletal / character |
| F | direct | Material create + expected reimport failure |
| G1 | direct | Create material |
| G2 | direct | Audio grade path |
| G3 | direct | Camera grade path |
| G4 | direct | Displacement / locomotion (same as E2) |
| H1 | direct | `world.get_view` |
| H2 | direct | Create material |
| I1 | direct | Spawn spotlight |
| I2 | direct | `world.list_actors` |

**Transform fallback:** blank / Engine-only targets often have `DefaultSkeletalMesh` but no walk `AnimSequence`. A/E2/G4 then use `animation.play_transform_sequence` and still **pass** (not soft-skip). Report `mode: anim | transform`.

**NIM:** Not required for the direct suite paths above. Still required for `forge run` / MC chat autonomous goals — surface `llm_error`, never silent heuristic fallback when NIM was requested.

## Dual-target proof (validation only)

Any adopted UE 5.8 project works. On a workstation you may prove:

| Target style | Expectation |
|--------------|-------------|
| Blank / Engine-only (e.g. fresh `forge init` game) | Suite green; A/E2/G4 often `mode=transform` |
| Content-rich (project `/Game` characters + walk anims) | Suite green; A/E2/G4 prefer `mode=anim` |

Do not hardcode one game into factory docs as “the” project — use `<PATH-TO-UE-PROJECT>`.

## Policy

- **NIM required** on autonomous chat / `forge run` paths — no silent heuristic fallback
- **Repair loop** — on by default for autonomous goals when grade fails
- Session export **schema v4** includes `autonomous_report`
- Engine SK search includes EditorMeshes (`DefaultSkeletalMesh`), EngineMeshes, etc.

## Failure modes

| Symptom | Meaning | Action |
|---------|---------|--------|
| `llm_error` in JSON | No API key or NIM unreachable | Set `NVIDIA_API_KEY`, retry |
| Gate / suite PIE fail | PIE offline or wrong project | `forge up <project>` |
| Editor `:8766` offline | Plugin not rebuilt / editor closed | `forge sync-plugin`, rebuild 1.0.1+, `forge editor open` / `forge up` |
| `plugin_version` mismatch | Stale DLL | rebuild HephaestusBridge, full editor restart |
| `mission_control_dist` fail | No Vite build | `forge observe` or `forge build-mc` |
| Identity mismatch | Another project's PIE on `:8765` | `forge down --quit-editor`, `forge up` correct target |

## Heuristic planner (dev only)

`forge loop --planner heuristic` or `--planner auto` without API key uses local heuristics. **Not** used for production acceptance.

## Live checklist

[docs/LIVE_E2E.md](LIVE_E2E.md) · [docs/PRODUCTION.md](PRODUCTION.md)

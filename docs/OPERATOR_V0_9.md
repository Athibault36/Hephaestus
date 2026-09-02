# Operator v0.9 — production gate

Final operator milestone before live game targets. Builds on [OPERATOR_V0_2.md](OPERATOR_V0_2.md), [OPERATOR_V0_3.md](OPERATOR_V0_3.md), and [ROADMAP_V0_9.md](ROADMAP_V0_9.md).

## Gate command

```powershell
pip install -e .
forge gate <PATH-TO-UE-PROJECT>           # human output via doctor
forge gate <PATH-TO-UE-PROJECT> --json    # machine-readable gate report
forge doctor <target> --json
forge e2e <target> --json
```

Exit `0` = gate passed (offline blockers + preflight when PIE is up).

## Scenarios A–G (carry-forward)

| ID | Scenario | v0.9 requirement |
|----|----------|------------------|
| A | Spawn creature → walk → grade | Heuristic + grading + repair hints |
| B | Cinematic shot | `sequence.create_shot` + camera grade |
| C | Mission Control | MC dist optional; preflight banner + forge version |
| D | Packaging | `pip install -e .`, pytest + build-mc CI |
| E | Direct chat | spawn / locomotion / audio / search |
| F | Asset pipeline | import/reimport/export validation errors |
| G | Grading | audio, material, camera, displacement |

## v0.4–v0.8 increments (shipped in 0.1.4–0.1.8)

- **v0.4:** Session export schema **v3**; PCG `mutations` array on `pcg.mutate_graph`
- **v0.5:** `HEPHAESTUS_HEURISTIC_REPAIR`; walk displacement grading
- **v0.6:** `audio.play_metasound` alias; subsystem init messages
- **v0.7:** `forge gate`; Mission Control shows factory version
- **v0.8:** `operator_gate` unit tests; ENV_FLAGS for repair flags

## Live checklist

[docs/LIVE_E2E.md](LIVE_E2E.md) — sync, rebuild, PIE, self-hosted workflow.

## Not in v0.9 (post-1.0)

- Full editor FBX import pipeline
- IK retarget graph execution
- Blueprint graph mutation (add_function body)
- MetaSound procedural graph authoring
- Hosted live E2E on GitHub-hosted runners

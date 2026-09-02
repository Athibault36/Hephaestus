# Autonomous Operator v1.0 — Design Spec

**Date:** 2026-09-01  
**Status:** Approved  
**Milestone:** `OPERATOR_MILESTONE=v1.0` · forge/bridge `1.0.0`

## Goal

Ship a **NIM-required autonomous operator** that runs scenarios **A–G** end-to-end with **repair loop** on failure, via **CLI** (`forge run`, `forge autonomous-suite`) and **Mission Control** chat.

## Requirements (locked)

| Decision | Choice |
|----------|--------|
| Scope | Operator scenarios A–G (C/D as prerequisites) |
| Planner | NIM required — fail with `llm_error`, no silent heuristic fallback |
| Entry | CLI + Mission Control |
| Failure | Repair loop (`maybe_repair_after_grade` forced on autonomous path) |

## Architecture

```
forge run / forge autonomous-suite / MC chat
        │
        ▼
  autonomous_runner.run_autonomous_goal()
        │
        ├─ VisionLLMPlanner (required)
        ├─ ObserveActLoop.run_until_goal()
        ├─ maybe_repair_after_grade(force=True)
        └─ AutonomousReport + session export v4
```

## CLI

- `forge run <target> "goal"` — single goal; `--json`, `--max-steps`, `--no-repair`
- `forge autonomous-suite <target>` — scripted A–G; `--scenario A`, `--json`, `--offline` (skip live NIM goals)

## Out of scope

Full FBX import, IK retarget execution, blueprint graph mutation, MetaSound graph authoring.

# Hephaestus environment flags

| Variable | Default | Purpose |
|----------|---------|---------|
| `NVIDIA_API_KEY` / `HEPHAESTUS_LLM_API_KEY` | — | NIM / DeepSeek planner API key |
| `HEPHAESTUS_ORCHESTRATOR` | `default` | Set to `langgraph` for phased LangGraph runner |
| `HEPHAESTUS_PLANNER_VISION` | off | `1` / `true` to caption viewport before planning |
| `HEPHAESTUS_VISION_MODEL` | Nemotron vision default | Caption model when vision planner is on |
| `HEPHAESTUS_HOME` | `~/.hephaestus` | Session store when no project root is bound |
| `HEPHAESTUS_NIM_REPAIR` | off | `1` to run a short repair loop when grading fails |
| `HEPHAESTUS_NIM_PARALLEL_REPAIR` | off | `1` to fetch a NIM parallel hint before repair loop |
| `HEPHAESTUS_HEURISTIC_REPAIR` | off | `1` to run repair loop without requiring NIM (heuristic follow-up) |

## Operator gate (v0.9)

```powershell
forge gate <PATH-TO-UE-PROJECT>
forge gate <PATH-TO-UE-PROJECT> --json
```

## Autonomous operator (v1.0)

```powershell
forge run <PATH-TO-UE-PROJECT> "spawn a dog and walk"
forge autonomous-suite <PATH-TO-UE-PROJECT> --json
```

Requires `NVIDIA_API_KEY`. Repair loop is on by default for `forge run` and MC chat.

## Audio / MetaSound commands

| Command | Params | Notes |
|---------|--------|-------|
| `audio.create_metasound` | `source_path`, `name` | Loads an existing MetaSound asset (`source_path` required) |
| `audio.synthesize` | `sound_path` | Loads an existing `SoundWave` (procedural synth deferred) |
| `audio.play_quartz` | `clock`, `timeline` | Plays test cue when Quartz graph not bound |

## NIM model IDs (planner)

- Planner (default): `deepseek-ai/deepseek-v4-pro-0813`
- Ultra (legacy): `nvidia/nemotron-3-ultra-550b-a55b`
- Lightning: `nvidia/nemotron-3.5-lightning-30b-a3b`

Dead aliases (`nvidia/nemotron-3-ultra`, `nvidia/nemotron-3-8b`) are remapped in `NIMClient`.

## Per-target locomotion overrides

Place `.hephaestus_forge/locomotion.json`:

```json
{
  "idle": ["/Game/MyAnims/Idle.Idle"],
  "walk": ["/Game/MyAnims/Walk.Walk"],
  "run": ["/Game/MyAnims/Run.Run"]
}
```

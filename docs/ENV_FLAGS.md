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
| `HEPHAESTUS_EDITOR_API` | `http://127.0.0.1:8766` | Editor control plane for `forge pie start` / `stop` / `editor.import_fbx` |
| `HEPHAESTUS_UE_API` | `http://127.0.0.1:8765` | PIE world API (commands / frame) |
| `HEPHAESTUS_DCC_API` | `http://127.0.0.1:8084` | DCC control plane (Blender/CC5) for `forge dcc` / `forge blender` |

## PIE engage / disengage (bridge ≥ 1.0.1)

Editor must have HephaestusBridge rebuilt. Preferred hands-off flow:

```powershell
# One shot: launch editor (if needed) → wait :8766 → start PIE → start DCC :8084
forge up <PATH-TO-UE-PROJECT>
forge up <PATH-TO-UE-PROJECT> --no-dcc   # skip Blender/CC5 plane

forge autonomous-suite <PATH-TO-UE-PROJECT> --json

forge down                 # stop PIE, keep editor
forge down --quit-editor   # stop PIE and quit UnrealEditor
```

Lower-level commands:

```powershell
forge editor open <PATH-TO-UE-PROJECT>
forge pie status
forge pie start <PATH-TO-UE-PROJECT>
forge pie stop
```

| Variable | Default | Purpose |
|----------|---------|---------|
| `UE_PATH` | auto-detect | Engine root for `forge editor open` / `forge up` |
| `HEPHAESTUS_EDITOR_API` | `http://127.0.0.1:8766` | Editor control plane |
| `HEPHAESTUS_UE_API` | `http://127.0.0.1:8765` | PIE world API |
| `HEPHAESTUS_DCC_API` | `http://127.0.0.1:8084` | DCC Blender/CC5 plane |
| `BLENDER_EXECUTABLE` | auto-detect | Override Blender path |
| `CC5_EXECUTABLE` / `RLPYTHON` | auto-detect | Character Creator + `CharacterCreatorpy.exe` (or rlpython) |
| `MESHY_API_KEY` | — | Only used when `HEPHAESTUS_USE_MESHY=1` (optional paid path) |
| `HEPHAESTUS_USE_MESHY` | off | Set `1` to enable Meshy; default is NIM→Blender + CC5 |

| Port | Lifetime | Role |
|------|----------|------|
| **8766** | Editor open (`-HephaestusEditorPort=` override) | `editor.play` / `editor.stop` / `editor.import_fbx` |
| **8765** | Only while PIE (`-HephaestusRemotePort=`) | World / animation / vision commands |
| **8084** | `forge dcc start` or `forge up` | `blender.export_fbx` / `blender.exec` / `cc5.export` |

```powershell
forge dcc start
forge blender export <PATH-TO-UE-PROJECT> --shape cube
forge dcc-import <PATH-TO-UE-PROJECT> --name HephaestusPrimitive
forge cc5 export <PATH-TO-UE-PROJECT> --name Character
```

### Studio utterances (chat / Mission Control / `forge run`)

These go through the agent DCC path (no NIM required for primitives):

| Utterance | Result |
|-----------|--------|
| `make a cube` | Blender export → import → spawn in frustum → frame |
| `make a red cube, frame it, and spin it slowly` | tint + frame + in-place spin |
| `make a blue sphere` | colored UV sphere in PIE |
| `spin it` / `make it blue` / `make it blue and spin it` | follow-up on last DCC actor (session + `.hephaestus_forge/last_dcc.json`) |
| `orbit it` | camera orbit around last DCC actor |
| `make a dog` / `make a person` / `make a creature` | CC5 (people) → NIM→Blender → Blender kits; Meshy only if `HEPHAESTUS_USE_MESHY=1` |
| `make a wooden chair` / other props | NIM→Blender bpy → import → spawn → frame |
| `export a cube fbx with blender` | export only (no import) |

Mission Control: **Author into PIE** builds the same style of goal from shape/color/spin controls.

Dual-target smoke (any two adopted UE 5.8 projects with PIE live):

```powershell
forge health <PATH-A>
forge run <PATH-A> "make a red cube, frame it, and spin it slowly"
forge run <PATH-B> "make a cube"
```

`editor.stop` / `pie.stop` also work on `:8765` while PIE is live.

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

- Planner / Ultra (default): `nvidia/nemotron-3-ultra-550b-a55b`
- Optional DeepSeek: `deepseek-ai/deepseek-v4-pro-0813`
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

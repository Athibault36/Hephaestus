# Hephaestus — Agent Guide

Local-first **UE5.8 autonomous agent factory**. Public repo: https://github.com/Athibault36/Hephaestus

## What matters

- **Remote API (PIE)**: `http://127.0.0.1:8765` — `GET /v1/health`, `POST /v1/command`, `GET /v1/frame`
- **Mission Control**: `forge observe` on `:3000` — proxies `/v1/*`, serves `/agent/loop` (Nemotron planner)
- **Canonical command body**: always prefer `"params"` (also accept `"args"`). Nested `transform.location.{x,y,z}` or flat `location` arrays both work after the bridge fix.
- **Spawns**: place actors **in front of the camera** (`world.get_view` → along `forward`). World origin is behind the default PIE pawn looking −X.
- **NIM coding models (both, in parallel)**:
  - Ultra: `nvidia/nemotron-3-ultra-550b-a55b` — architecture, hard multi-file design
  - Lightning: `nvidia/nemotron-3.5-lightning-30b-a3b` — fast edits, impl drafts
  - Dead ids (404): `nvidia/nemotron-3-ultra`, `nvidia/nemotron-3-8b` — aliases remap in `NIMClient`

## Auth

- Coding / NIM: `NVIDIA_API_KEY` (or `HEPHAESTUS_LLM_API_KEY`)
- Cursor OpenAI-compatible models: project `.~cursorconfig.json` (gitignored; see `.~cursorconfig.json.example`)

## How to work in this repo

1. Prefer **Context7 MCP** for library/UE/API docs before guessing signatures.
2. Prefer **UE MCP (`user-ue58-python`)** when verifying live PIE / world state while editing the bridge.
3. For regressions / “it broke again”: use **ce-debug** (diagnose before shotgun fixes).
4. For executing a written plan: use **ce-work** / **ce-plan** as appropriate.
5. For dual-model coding: `python hephaestus_forge/forge.py nim-parallel --task "..."` runs Ultra + Lightning concurrently.

## Layout

| Path | Role |
|------|------|
| `hephaestus_forge/forge.py` | CLI: init, observe, loop, cloud, gpu-dev, nim-parallel |
| `hephaestus_forge/ue_agent_loop.py` | Observe → act loop |
| `hephaestus_forge/ue_vision_planner.py` | Nemotron UE planner |
| `hephaestus_forge/cloud/nim_client.py` | NIM client + model aliases |
| `hephaestus_forge/cloud/parallel_nim.py` | Parallel Ultra + Lightning coding |
| `hephaestus_forge/templates/ue_plugin/HephaestusBridge/` | Plugin template (sync to UE project) |
| Live plugin | `...\Unreal Projects\test\Plugins\HephaestusBridge\` |

## Hard rules

- Do **not** silently fall back to heuristic when the user asked for LLM/Nemotron — surface `llm_error`.
- Do **not** commit `.~cursorconfig.json` or API keys.
- After C++ bridge changes: close Live Coding / UE, rebuild, restart PIE, restart `forge observe` if `/agent/*` 404s.
- Keep Mission Control / Python clients sending `params` (not only `args`).

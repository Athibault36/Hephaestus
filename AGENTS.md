# Hephaestus — Agent Guide

Local-first **UE5.8 autonomous agent factory**. Public repo: https://github.com/Athibault36/Hephaestus

## Factory vs target project

Hephaestus is **not** tied to one game. The git repo is the **factory**; any UE 5.8 project can be a **target**.

| | Factory (this repo) | Target (your UE game) |
|--|---------------------|------------------------|
| Location | e.g. `C:\dev\Hephaestus` | Any path, e.g. `C:\dev\MyGame` |
| Contains | `hephaestus_forge/`, plugin **template**, tests, CLI | `.hephaestus_forge/`, `Plugins/HephaestusBridge/`, `MissionControl/` |
| Created by | `git clone` | `forge init` (new) or `forge adopt` (existing `.uproject`) |

```powershell
# Adopt an existing UE game
forge adopt C:\dev\MyGame

# Or scaffold a new agent project
forge init MyAgentGame --path C:\dev

# Sync plugin template after bridge changes in the factory repo
forge sync-plugin C:\dev\MyGame

# Desktop app (project picker + Mission Control)
forge desktop
forge desktop C:\dev\MyGame
```

Registered targets are stored in `%USERPROFILE%\.hephaestus\projects.json`.

## What matters

- **Remote API (PIE)**: `http://127.0.0.1:8765` — `GET /v1/health`, `POST /v1/command`, `GET /v1/frame`
- **Mission Control / Desktop**: `forge observe` or `forge desktop` on `:3000` — proxies `/v1/*`, serves `/agent/loop`
- **Canonical command body**: always prefer `"params"` (also accept `"args"`). Nested `transform.location.{x,y,z}` or flat `location` arrays both work.
- **Spawns**: place actors **in front of the camera** (`world.get_view` → along `forward`). World origin is behind the default PIE pawn looking −X.
- **NIM coding models (both, in parallel)**:
  - Planner (default): `deepseek-ai/deepseek-v4-pro-0813`
  - Ultra (legacy planner): `nvidia/nemotron-3-ultra-550b-a55b`
  - Lightning: `nvidia/nemotron-3.5-lightning-30b-a3b`
  - Dead ids (404): `nvidia/nemotron-3-ultra`, `nvidia/nemotron-3-8b` — aliases remap in `NIMClient`

## Auth

- Coding / NIM: `NVIDIA_API_KEY` (or `HEPHAESTUS_LLM_API_KEY`)
- Cursor OpenAI-compatible models: add manually in **Cursor Settings → Models** (see `docs/CURSOR_NIM_MODELS.md`). Repo `.~cursorconfig.json` is a reference copy (gitignored).

## How to work in this repo

1. Prefer **Context7 MCP** for library/UE/API docs before guessing signatures.
2. Prefer **UE MCP (`user-ue58-python`)** when verifying live PIE / world state while editing the bridge.
3. For regressions: **ce-debug** before multi-file speculative edits.
4. For dual-model coding: `forge nim-parallel --task "..."`
5. Edit the **plugin template** in this repo, then `forge sync-plugin <target>` — do not treat one dev project as canonical.

## Layout

| Path | Role |
|------|------|
| `hephaestus_forge/forge.py` | CLI: init, adopt, desktop, observe, loop, sync-plugin, nim-parallel |
| `hephaestus_forge/desktop_app.py` | Desktop shell (pywebview + project registry) |
| `hephaestus_forge/project_registry.py` | `~/.hephaestus/projects.json` |
| `hephaestus_forge/plugin_sync.py` | Template → `{target}/Plugins/HephaestusBridge` |
| `hephaestus_forge/ue_agent_loop.py` | Observe → act loop |
| `hephaestus_forge/templates/ue_plugin/HephaestusBridge/` | Plugin **template** (source of truth) |
| `{target}/Plugins/HephaestusBridge/` | Plugin **instance** in a UE project |

## Hard rules

- Do **not** silently fall back to heuristic when the user asked for LLM/Nemotron — surface `llm_error`.
- Do **not** commit `.~cursorconfig.json` or API keys.
- Do **not** hardcode paths to a single UE project in docs or scripts.
- After C++ bridge changes: sync template → target, rebuild plugin, restart PIE, restart `forge observe` / desktop.
- Keep clients sending `params` (not only `args`).

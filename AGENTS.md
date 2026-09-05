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
  - Planner / Ultra (default): `nvidia/nemotron-3-ultra-550b-a55b`
  - Lightning: `nvidia/nemotron-3.5-lightning-30b-a3b`
  - Optional: `deepseek-ai/deepseek-v4-pro-0813` (aliases `deepseek-v4-pro`, etc.)
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
| `hephaestus_forge/dcc_server.py` | DCC control plane `:8084` (`blender.*` / `cc5.export`) |
| `hephaestus_forge/agent_dcc.py` | Chat/autonomous: author → import → frame/spin; last-actor memory; people/animals/creatures |
| `hephaestus_forge/meshy_bridge.py` | Optional Meshy text-to-3D when `MESHY_API_KEY` is set |
| `hephaestus_forge/dcc_client.py` | HTTP client + `forge dcc start` |
| `hephaestus_forge/dcc_import.py` | Stop PIE → `editor.import_fbx` → Play → spawn |
| `hephaestus_forge/cc5_bridge.py` | CC5/rlpython detect + character FBX export |
| `hephaestus_forge/blender_bridge.py` | One-shot Blender primitive → FBX under `dcc_exports` |
| `hephaestus_forge/forge.py` | CLI: init, adopt, desktop, observe, loop, sync-plugin, nim-parallel, dcc, blender, cc5, dcc-import |
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

## Learned User Preferences

- Prefer long autonomous coding runs: minimize check-ins and clarifying questions; execute an approved plan end-to-end until finished or truly blocked.
- Product framing: plain-language AI animation studio that delivers inside UE PIE (spawn, animate, frame shots)—not sketches, plans, or handoffs.
- Never treat Hephaestus as tied to one UE game; keep the factory reusable across any UE 5.8 target.
- Prefer Nemotron 3 Ultra for coding this repo (Cursor/NIM), with Lightning in parallel when dual-model; DeepSeek is optional/fallback, not the default coding brain.
- Desktop app (`forge desktop`) is desired, including a polymorphic avatar that can change at the agent’s discretion.
- Persist NIM/API keys locally (factory `.env` or Windows user env) so they are not re-entered each session.
- When UE plugin rebuilds hit Visual Studio/.NET automation errors, bypass unnecessary .NET tooling and rebuild the C++ HephaestusBridge only.

## Learned Workspace Facts

- Factory repo path is `C:\dev\Hephaestus` (kept off OneDrive).
- UE 5.8 engine is commonly installed at `C:\Program Files\Epic Games\UE_5.8`.
- A frequent local validation target is `C:\Unreal Projects\MacroVerse` (example only—not canonical).
- After bridge C++ changes: `forge sync-plugin` → disable Live Coding → rebuild HephaestusBridge → full editor restart → PIE → restart `forge observe` / desktop.
- UE 5.8 may open .NET 10 automation projects; if VS reports NETSDK1209, build the C++ plugin only instead of the full automation solution.
- Factory `.env` (gitignored) supplies `NVIDIA_API_KEY` / `HEPHAESTUS_LLM_API_KEY` for forge health, observe, and autonomous suites.
- Cinematic camera control goes through bridge `world.get_view` / `world.set_view` (including free/look-at modes), not pawn-at-origin assumptions.
- Operator validation entrypoints include `forge health`, `forge gate`, and `forge autonomous-suite` against an adopted target with PIE live.

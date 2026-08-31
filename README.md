# Hephaestus

**HephaestusForge** is a local-first agent factory and runtime for autonomous Unreal Engine 5.8 development. It connects a Python agent loop to a live UE editor through the **HephaestusBridge** plugin, with Mission Control dashboard, voice console, and forge CLI tooling.

## Quick start

```bash
# Clone and install (Python 3.10+)
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Run tests
pytest -q

# Scaffold a project (interactive system scan)
hephaestus_forge init MyProject

# Attach forge to an existing UE project
hephaestus_forge attach /path/to/MyGame.uproject

# Compile the HephaestusBridge plugin (Windows + UE5.8)
hephaestus_forge compile /path/to/MyGame.uproject

# Check toolchain and services
hephaestus_forge health

# Run the agent against a live editor
hephaestus_forge agent --goal "Spawn a cube at the origin" --stream
```

See [docs/USER_GUIDE.md](docs/USER_GUIDE.md) for the full clone → attach → compile → agent walkthrough.
See [docs/COMMAND_API.md](docs/COMMAND_API.md) for the HTTP bridge and tool reference.

## Architecture

| Layer | Role |
| --- | --- |
| `hephaestus_forge/runtime/` | Python agent runtime: UE HTTP client, tools, LLM loop, Mission Control bridge |
| `hephaestus_forge/templates/ue_plugin/` | HephaestusBridge UE5.8 C++ plugin (command handler + HTTP server) |
| `hephaestus_forge/templates/mission_control/` | React dashboard (viewport, chain-of-thought, voice, metrics) |
| `hephaestus_forge/forge.py` | CLI: init, attach, compile, deploy, health, agent |

The agent observes via `vision.capture_frame`, reasons with an OpenAI-compatible LLM, and acts through typed tools (`world.*`, `asset.*`, `blueprint.*`, etc.).

## Configuration

Project settings live in `.hephaestus_forge/config.yaml` after `init`. Key sections:

- `network.ue_bridge_port` — UE HTTP bridge (default `8099`)
- `network.webrtc_port` — Mission Control Socket.IO bridge (default `8081`)
- `models.inference` — LLM host/port
- `security.bridge_token` — optional shared token for bridge auth (`HEPHAESTUS_BRIDGE_TOKEN` env)

Template defaults: `hephaestus_forge/forge_config/config.yaml`.

## Mission Control

```bash
cd hephaestus_forge/templates/mission_control
cp .env.example .env   # optional: tune ports
npm install && npm run dev
```

Open http://127.0.0.1:3000. The viewport panel polls `capture_frame` → `GET /frame/:id` from the UE bridge (via Vite proxy in dev).

## Docs

- [User guide](docs/USER_GUIDE.md) — onboarding
- [Production roadmap](docs/ROADMAP.md) — milestones and gates
- [Windows plugin compile](docs/plugin_setup_windows.md) — first engine bring-up
- [M1 compile checklist](docs/M1_CHECKLIST.md) — step-by-step verification on Windows

## Development

```bash
pytest -q
ruff check --select F hephaestus_forge tests
mypy hephaestus_forge/runtime
cd hephaestus_forge/templates/mission_control && npm run build
```

## Status

Python runtime and dashboard are testable on Linux without the engine. Plugin compile and the first live observe→act loop require **Windows 11 + UE 5.8 + GPU** (see roadmap Phase 1).

## License

Proprietary — see repository owner for terms.

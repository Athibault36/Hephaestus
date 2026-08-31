# HephaestusForge User Guide

This guide walks a new operator from clone to a running agent loop. Steps marked **[G]** require Windows with Unreal Engine 5.8 installed.

## Prerequisites

| Component | Required | Notes |
| --- | --- | --- |
| Python 3.10+ | Yes | CLI and agent runtime |
| Node.js 20+ | Yes | Mission Control dashboard |
| UE 5.8 + VS 2022 | For live loop **[G]** | Plugin compile and editor |
| NVIDIA GPU | Recommended | Local LLM serving |

## 1. Clone and install

```bash
git clone https://github.com/Athibault36/Hephaestus.git
cd Hephaestus
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest -q                   # expect all tests green
```

## 2. Initialize or attach a project

**New project:**

```bash
hephaestus_forge init MyGame
cd MyGame
```

**Existing UE project:**

```bash
hephaestus_forge attach C:/Projects/MyGame/MyGame.uproject
```

Both commands create `.hephaestus_forge/config.yaml` with detected paths, ports, and model settings.

## 3. Compile the plugin **[G]**

On Windows with UE 5.8:

```bash
hephaestus_forge compile C:/Projects/MyGame/MyGame.uproject
```

This copies `HephaestusBridge` under `Plugins/` if needed and builds the editor target. See [plugin_setup_windows.md](plugin_setup_windows.md) for troubleshooting.

Verify the bridge:

```bash
curl http://127.0.0.1:8099/health
```

## 4. Configure ports (optional)

Edit `.hephaestus_forge/config.yaml`:

```yaml
network:
  ue_bridge_port: 8099
  webrtc_port: 8081
  dashboard_port: 3000

security:
  localhost_only: true
  require_auth: false
  bridge_token: ""   # or set HEPHAESTUS_BRIDGE_TOKEN
```

Mission Control reads `hephaestus_forge/templates/mission_control/.env.example` for dashboard-side overrides.

## 5. Start services

**Health check (before deploy):**

```bash
hephaestus_forge health
```

**Full deploy** (editor + LLM + TTS + vision + dashboard — **[G]** for UE):

```bash
hephaestus_forge deploy
```

**Dashboard only** (Linux-testable UI):

```bash
cd hephaestus_forge/templates/mission_control
npm install && npm run dev
```

## 6. Run the agent

With UE editor running and HephaestusBridge loaded:

```bash
hephaestus_forge agent \
  --goal "Spawn a StaticMeshActor at 0,0,200 and capture a viewport frame" \
  --stream
```

- `--stream` starts the Socket.IO bridge on port `8081` (configurable via `network.webrtc_port`).
- Mission Control shows chain-of-thought, actors, tool latency, and viewport frames.
- Tools include `world.*`, `vision.*`, and extended families (`asset.*`, `blueprint.*`, …) — C++ handlers must be compiled for engine-side effects.

### Environment overrides

| Variable | Purpose |
| --- | --- |
| `HEPHAESTUS_UE_URL` | UE bridge base URL |
| `HEPHAESTUS_LLM_URL` | OpenAI-compatible LLM base URL |
| `HEPHAESTUS_BRIDGE_TOKEN` | Shared auth token for bridge requests |
| `HEPHAESTUS_BRIDGE_PORT` | Mission Control Socket.IO port |

## 7. Voice (optional)

Enroll your voice profile, then run always-on speaker-verified sessions:

```bash
hephaestus_forge voice enroll --samples ./voice_samples/
hephaestus_forge voice session --stream
```

See Mission Control **Voice Console** for live status (no push-to-talk).

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| `UE bridge not reachable` | Start editor with plugin; check `ue_bridge_port` |
| Agent exits immediately | Ensure LLM at `models.inference.port` (default 8080) |
| Viewport blank in dashboard | UE must answer `/health`; polling uses `capture_frame` + `/frame/:id` |
| `health` shows WARN for services | Normal before `deploy`; start missing services or ignore non-critical checks |

## Next steps

- [ROADMAP.md](ROADMAP.md) — production milestones
- [COMMAND_API.md](COMMAND_API.md) — HTTP bridge and tool reference
- [plugin_setup_windows.md](plugin_setup_windows.md) — first Windows compile
- GitHub issue #2 — agent-runtime MVP tracking

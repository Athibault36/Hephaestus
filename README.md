# Hephaestus

Local-first **UE 5.8 autonomous agent factory**. The git repo is the **factory**; any `.uproject` can be a **target**.

[![Python tests](https://github.com/Athibault36/Hephaestus/actions/workflows/pytest.yml/badge.svg)](https://github.com/Athibault36/Hephaestus/actions/workflows/pytest.yml)

## Quick start

```powershell
git clone https://github.com/Athibault36/Hephaestus.git
cd Hephaestus
pip install -e .

forge adopt C:\path\to\YourGame
forge sync-plugin C:\path\to\YourGame
# UE 5.8: rebuild HephaestusBridge, disable Live Coding, Play (PIE)

$env:NVIDIA_API_KEY = "nvapi-..."
forge gate C:\path\to\YourGame --json
forge observe C:\path\to\YourGame
```

## Production operator (v1.0)

| Command | Purpose |
|---------|---------|
| `forge gate` | Production gate — plugin version, PIE, E2E probes, MC dist |
| `forge run` | Single autonomous NIM goal |
| `forge autonomous-suite` | Scenarios A–G acceptance |
| `forge observe` | Mission Control on `:3000` (auto-builds React UI when npm present) |
| `forge desktop` | Project picker + shell (`pip install hephaestus-forge[desktop]`) |
| `forge doctor` / `forge e2e` | Preflight + live bridge probes |

**NIM required** on autonomous paths — set `NVIDIA_API_KEY` (or `HEPHAESTUS_LLM_API_KEY`). No silent heuristic fallback on `forge run`, suite, or MC chat.

Remote API (PIE): `http://127.0.0.1:8765` — `GET /v1/health`, `POST /v1/command`, `GET /v1/frame`

## Docs

| Doc | Content |
|-----|---------|
| [AGENTS.md](AGENTS.md) | Factory vs target, models, agent rules |
| [docs/PRODUCTION.md](docs/PRODUCTION.md) | **Deployment guide** |
| [docs/OPERATOR_V1.md](docs/OPERATOR_V1.md) | Autonomous acceptance A–G |
| [docs/OPERATOR_V0_9.md](docs/OPERATOR_V0_9.md) | Production gate (v0.9) |
| [docs/ENV_FLAGS.md](docs/ENV_FLAGS.md) | Environment variables |
| [docs/LIVE_E2E.md](docs/LIVE_E2E.md) | Live PIE + self-hosted CI |
| [CHANGELOG.md](CHANGELOG.md) | Release history |

## Requirements

- **UE 5.8** target project
- **Python 3.10+**
- **Node.js 18+** (Mission Control UI; optional if using static fallback)
- **NVIDIA NIM API key** (autonomous operator)

## License

MIT — see [LICENSE](LICENSE).

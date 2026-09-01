# Hephaestus

Local-first **UE 5.8 autonomous agent factory**. The git repo is the factory; any `.uproject` can be a target.

## Quick start

```powershell
git clone https://github.com/Athibault36/Hephaestus.git
cd Hephaestus
pip install -e .

forge adopt C:\path\to\YourGame
forge sync-plugin C:\path\to\YourGame
# UE 5.8: rebuild HephaestusBridge, Play (PIE)

forge doctor C:\path\to\YourGame
forge observe C:\path\to\YourGame
```

## Docs

- [AGENTS.md](AGENTS.md) — factory vs target, models, rules
- [docs/ENV_FLAGS.md](docs/ENV_FLAGS.md) — environment variables
- [docs/OPERATOR_V0_2.md](docs/OPERATOR_V0_2.md) — acceptance scenarios

## Remote API (PIE)

`http://127.0.0.1:8765` — `GET /v1/health`, `POST /v1/command`, `GET /v1/frame`

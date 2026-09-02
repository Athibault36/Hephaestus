# Changelog

All notable changes to Hephaestus Forge are documented here.

## [1.0.0] — 2026-09-02

### Added
- **Autonomous operator v1.0**: `forge run`, `forge autonomous-suite` (scenarios A–G), NIM-required planner, repair loop
- Mission Control chat routes through `autonomous_runner` with session export schema v4
- `forge gate` — unified production operator gate (offline + live PIE)
- `forge desktop` — project picker + native shell (optional `pywebview`)
- Plugin sync keeps `HephaestusVersion.h` aligned with factory `BRIDGE_VERSION`
- Production docs: `LICENSE`, `CHANGELOG.md`, `docs/PRODUCTION.md`, plugin README
- GitHub Release workflow on `v*` tags

### Fixed
- UE 5.8 compile errors in HephaestusBridge (SetRaw, FString keys, sequence playback)
- Bridge HTTP 400 JSON parsing in gate/e2e probes
- Health `plugin_version` mismatch when C++ macro lagged version file
- **`forge` CLI ModuleNotFoundError** after `pip install -e .` (package bootstrap puts flat modules on `sys.path`)

### Policy
- Autonomous paths (`forge run`, `forge autonomous-suite`, MC chat, `/agent/loop`) require `NVIDIA_API_KEY` — no silent heuristic fallback

## [0.1.9] — Operator v0.9

- `forge gate`, operator milestone v0.9, production preflight checklist

## Earlier

See [docs/RELEASE_v0.1.1.md](docs/RELEASE_v0.1.1.md) through [docs/RELEASE_v1.0.0.md](docs/RELEASE_v1.0.0.md) for incremental release notes.

# Release v0.1.2

## Operator batch

- Version bump: factory + bridge template **0.1.2**
- **Asset commands:** `asset.create_material`, `asset.export`, `asset.import` (disk validation), `asset.create_instance` (transient MID)
- **Audio:** MetaSound module linked; `audio.create_metasound` loads by `source_path`; `audio.synthesize` loads `SoundWave`
- **Preflight / E2E:** probes for assets, audio, blueprint compile, sequence shots
- **Agent repair:** optional `HEPHAESTUS_NIM_PARALLEL_REPAIR` NIM hints
- **Packaging:** root `README.md` for `pip install -e .`
- **CI:** self-hosted **Live E2E** workflow (`workflow_dispatch`) — see [LIVE_E2E.md](LIVE_E2E.md)

## Manual step (required for live PIE)

```powershell
forge sync-plugin <PATH-TO-UE-PROJECT>
# UE 5.8: rebuild HephaestusBridge (MetaSound dep), disable Live Coding, Play (PIE)
forge doctor <PATH-TO-UE-PROJECT>
forge e2e <PATH-TO-UE-PROJECT>
```

## Self-hosted CI

Actions → **Live E2E (self-hosted)** → provide `project_root` with PIE already running on the runner.

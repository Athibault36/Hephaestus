# Live E2E operator checklist

Run this on a **target UE 5.8 project** after syncing the factory plugin template.

## 1. Sync and rebuild

```powershell
forge sync-plugin C:\path\to\YourGame
```

In UE 5.8:

1. Open the target `.uproject`
2. **Tools → Refresh Visual Studio Project** (if needed)
3. Build **HephaestusBridge** (disable Live Coding for C++ changes)
4. **Play (PIE)** with the bridge enabled

## 2. Factory checks (no LLM)

```powershell
forge doctor C:\path\to\YourGame
forge e2e C:\path\to\YourGame
```

`forge e2e` runs offline steps (template version, plugin sync) plus live probes when PIE is online:

| Step | Command probed |
|------|----------------|
| `list_actors_details` | `world.list_actors` + `include_details` |
| `capture_frame` | `vision.capture_frame` |
| `asset_create_material` | `asset.create_material` |
| `asset_search` | `asset.search` |
| `asset_create_instance` | `asset.create_instance` (transient MID) |
| `sequence_create_shot` | `sequence.create_shot` + `ease_in_out` |
| `audio_create_metasound` | `audio.create_metasound` (registered; needs `source_path` to load) |

Preflight also probes locomotion, montage, audio quartz, blueprint compile, and asset verbs.

## Self-hosted CI

Use when a Windows machine already has UE 5.8 + PIE running with HephaestusBridge.

### Runner setup

1. Install [GitHub Actions self-hosted runner](https://docs.github.com/en/actions/hosting-your-own-runners) on the UE workstation.
2. Label the runner `self-hosted` (default).
3. Ensure `pip`, Python 3.11+, and network access to `127.0.0.1:8765` from the runner process.
4. Adopt the target once: `forge adopt C:\path\to\YourGame`

### Manual workflow

GitHub → **Actions** → **Live E2E (self-hosted)** → **Run workflow**

| Input | Example |
|-------|---------|
| `project_root` | `C:\dev\MyAgentGame` |
| `api` | `http://127.0.0.1:8765` |
| `sync` | `true` to copy plugin template before probes |

The job runs `forge doctor` then `forge e2e` (live probes). It uploads `live-e2e-report.json` as an artifact.

### Local equivalent

```powershell
forge doctor C:\path\to\YourGame --api http://127.0.0.1:8765
forge e2e C:\path\to\YourGame --api http://127.0.0.1:8765
forge health C:\path\to\YourGame --json   # machine-readable preflight
forge e2e C:\path\to\YourGame --json     # machine-readable E2E report
```

## 3. Mission Control

```powershell
forge build-mc C:\path\to\YourGame
forge observe C:\path\to\YourGame
```

Open `http://127.0.0.1:3000` — preflight banner should be green when plugin version matches factory.

## 4. Acceptance scenarios

See [OPERATOR_V1.md](OPERATOR_V1.md) for autonomous scenarios A–G and [OPERATOR_V0_9.md](OPERATOR_V0_9.md) for the production gate.

```powershell
forge gate C:\path\to\YourGame --json
forge autonomous-suite C:\path\to\YourGame --json
```

## CI vs live

GitHub Actions runs **pytest** and **Mission Control `npm run build`** on every PR.

For live PIE validation, use the **Live E2E (self-hosted)** workflow (see [Self-hosted CI](#self-hosted-ci) above) or run `forge e2e` locally.

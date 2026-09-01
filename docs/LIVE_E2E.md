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
| `sequence_create_shot` | `sequence.create_shot` + `ease_in_out` |

Preflight also probes locomotion, montage, audio, and blueprint compile registration.

## 3. Mission Control

```powershell
forge build-mc C:\path\to\YourGame
forge observe C:\path\to\YourGame
```

Open `http://127.0.0.1:3000` — preflight banner should be green when plugin version matches factory.

## 4. Acceptance scenarios

See [OPERATOR_V0_2.md](OPERATOR_V0_2.md) for spawn→walk grading, cinematic shots, and packaging.

## CI vs live

GitHub Actions runs **pytest** and **Mission Control `npm run build`** only. Live PIE E2E requires a local UE editor session (self-hosted runner optional).

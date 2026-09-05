# Production deployment guide

Hephaestus **1.0.0** is a local-first UE 5.8 operator factory. This guide covers shipping to a production workstation or team runner.

## Prerequisites

| Requirement | Notes |
|-------------|--------|
| **Windows 10/11** | Primary platform for UE 5.8 editor + PIE |
| **Unreal Engine 5.8** | Target game project with HephaestusBridge enabled |
| **Python 3.10+** | `pip install -e .` from factory repo |
| **Node.js 18+** | Mission Control React build (auto-runs on `forge observe` when npm is present) |
| **NVIDIA_API_KEY** | Required for autonomous operator (`forge run`, suite, MC chat) |

Optional: `pip install hephaestus-forge[desktop]` for `forge desktop` native window (`pywebview`).

## One-time target setup

```powershell
git clone https://github.com/Athibault36/Hephaestus.git
cd Hephaestus
pip install -e .

forge adopt "C:\path\to\YourGame"
forge sync-plugin "C:\path\to\YourGame"
```

In UE 5.8:

1. Enable **HephaestusBridge** + **MetaSound**
2. Rebuild **Development Editor** (disable Live Coding for C++ changes)
3. Engage PIE — either press **Play**, or from forge (bridge ≥ 1.0.1):

```powershell
forge pie start "C:\path\to\YourGame"
```

Editor control listens on `http://127.0.0.1:8766`; PIE world API on `http://127.0.0.1:8765`.

Verify:

```powershell
curl http://127.0.0.1:8766/v1/health
# expect "service":"hephaestus-editor"
curl http://127.0.0.1:8765/v1/health
# expect "plugin_version":"1.0.1"
forge pie stop
```

## Production gate (required)

```powershell
$env:NVIDIA_API_KEY = "nvapi-..."
forge gate "C:\path\to\YourGame" --json
```

Exit **0** = ready. Non-zero = fix blockers (version skew, PIE offline, missing MC dist).

## Autonomous acceptance

```powershell
forge autonomous-suite "C:\path\to\YourGame" --json
```

Scenarios A–G: spawn/walk, cinematic, infra, direct verbs, material recovery, grading. See [OPERATOR_V1.md](OPERATOR_V1.md).

## Mission Control

```powershell
forge observe "C:\path\to\YourGame"
```

Opens `http://127.0.0.1:3000`. Vite build runs automatically when npm is installed and no dist exists.

## Environment

| Variable | Purpose |
|----------|---------|
| `NVIDIA_API_KEY` | NIM planner (required for v1 autonomous) |
| `HEPHAESTUS_LLM_API_KEY` | Alias for above |
| `HEPHAESTUS_PLANNER_VISION=1` | Viewport captions in planner |

Full list: [ENV_FLAGS.md](ENV_FLAGS.md).

## Bridge command coverage (v1.0)

| Area | Status |
|------|--------|
| World spawn/edit, locomotion, montage | **Supported** |
| Camera: `world.get_view` / `world.set_view` (free CameraActor by default), orbit `look_at_actor`+`distance`+`yaw_offset` | **Supported** |
| Assets: create material/instance, search | **Supported** |
| Sequencer: create_shot (animated free cam), play | **Supported** |
| Audio: quartz play, metasound (needs `source_path`) | **Partial** |
| Vision: PNG frame capture | **Supported** |
| Blueprint mutation, IK retarget, FBX import | **Stub** (returns false; post-1.0) |
| WebRTC / hardware encode | **Stub** |

After bridge C++ camera changes: `forge sync-plugin <UE_PROJECT>`, rebuild plugin, **full editor restart**, then Play.

Plugin details: [templates/ue_plugin/HephaestusBridge/README.md](../hephaestus_forge/templates/ue_plugin/HephaestusBridge/README.md).

## CI / team runners

- **Every PR**: pytest + Mission Control `npm run build` (GitHub Actions)
- **Live validation**: self-hosted workflow — [LIVE_E2E.md](LIVE_E2E.md)

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `plugin_version` 0.1.1 vs factory 1.0.0 | `forge sync-plugin`, rebuild plugin, **restart editor** |
| `llm_error` / planner unavailable | Set `NVIDIA_API_KEY` |
| Gate fails `mission_control_dist` | `forge observe` (auto-build) or `forge build-mc` |
| Commands work but gate fails version | Full editor restart after C++ rebuild |

## Security note

Remote API (`:8765`) and Mission Control (`:3000`) bind **localhost** only. Do not expose to untrusted networks without adding auth.

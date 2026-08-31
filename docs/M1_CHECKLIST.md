# M1 — First plugin compile checklist (Windows + UE 5.8)

Use this on the **first** Windows compile attempt. Check each box before moving on.

## Before you build

- [ ] UE 5.8 installed; `UE_PATH` or `system.ue_path` in config points to it
- [ ] Visual Studio 2022 with **Desktop + Game C++** workloads
- [ ] `hephaestus_forge attach` or `init` has run; `.hephaestus_forge/config.yaml` exists
- [ ] Plugin under `<Project>/Plugins/HephaestusBridge` (or run `forge compile` which auto-copies)
- [ ] `HephaestusBridge` enabled in `.uproject` Plugins array
- [ ] Python env: `pip install -e ".[dev]"` and `pytest -q` passes on your machine

## Dry run

```powershell
hephaestus_forge compile C:\path\to\Project\Project.uproject --dry-run
```

- [ ] Command shows `<Project>Editor Win64 Development` and correct `-project=` path

## Build

```powershell
hephaestus_forge compile C:\path\to\Project\Project.uproject
```

- [ ] UnrealBuildTool exits 0
- [ ] No missing module errors for HTTPServer, ImageWrapper, PixelStreaming (enable in .uplugin if needed)

## Editor smoke test

1. Open the project in Unreal Editor.
2. Enable **HephaestusBridge** in Edit → Plugins if not already on.
3. Play in Editor (PIE) or run standalone with `-game`.

```powershell
curl http://127.0.0.1:8099/health
```

- [ ] Returns `{"status":"ok","commands":27}` (or current tool count from `build_default_registry()`)

## Validation smoke test

```powershell
curl -X POST http://127.0.0.1:8099/command -H "Content-Type: application/json" -d "{\"command\":\"world.spawn_actor\",\"params\":{\"class_path\":\"evil/path\"}}"
```

- [ ] Returns `success: false` with class_path prefix denied (ValidateCommand wired in C++)

## Observability (optional)

When `observability.metrics.enabled: true` in config:

```powershell
curl http://127.0.0.1:9090/metrics
```

- [ ] Prometheus text exposition responds after `forge deploy --services-only` or `forge agent`

## Agent smoke test

```powershell
hephaestus_forge agent --goal "Spawn a StaticMeshActor and capture a frame" --stream
```

- [ ] UE bridge reachable
- [ ] LLM responds (local llama-server or `--use-nim` with `NVIDIA_API_KEY`)
- [ ] Mission Control shows chain-of-thought and a viewport frame

## Auth (optional)

Set in config or env:

```
HEPHAESTUS_BRIDGE_TOKEN=your-secret
HEPHAESTUS_REQUIRE_AUTH=1
```

Restart editor; verify unauthenticated `POST /command` returns 401 and authenticated requests succeed.

## If compile fails

1. Note the **first** linker or missing-module error (not the cascade).
2. Check `HephaestusBridge.Build.cs` optional deps — gate behind `WITH_*` if a subsystem is unavailable.
3. Compare engine plugin versions (PixelStreaming, WebRTC) with your UE 5.8 build.
4. File the error + `forge compile --dry-run` output in the GitHub issue.

See also: [plugin_setup_windows.md](plugin_setup_windows.md), [COMMAND_API.md](COMMAND_API.md).

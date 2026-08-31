# M1 — First plugin compile checklist (Windows + UE 5.8)

Use this on the **first** Windows compile attempt. Check each box before moving on.

## Before you build

- [ ] UE 5.8 installed; `UE_PATH` or `system.ue_path` in config points to it
- [ ] Visual Studio 2022 with **Desktop + Game C++** workloads
- [ ] `hephaestus_forge attach` or `init` has run; `.hephaestus_forge/config.yaml` exists
- [ ] Plugin under `<Project>/Plugins/HephaestusBridge` (or run `forge compile` which auto-copies)
- [ ] `HephaestusBridge` enabled in `.uproject` Plugins array
- [ ] Python env: `pip install -e ".[dev]"` and `pytest -q` passes on your machine
- [ ] Pull latest `cursor/agent-runtime-mvp-be50` (or merge PR #2) — Build.cs defaults are first-compile friendly

## First-compile defaults (important)

By default the plugin **does not** require PixelStreaming, WebRTC, OpenCV, MetaSound, or ThirdParty LLM libs.

- Leave `HEPHAESTUS_FULL_BUILD` **unset** for the first successful compile.
- Only set `HEPHAESTUS_FULL_BUILD=1` after M1 is green and you want streaming/OpenCV.

```powershell
# Optional: force full optional stack later
# setx HEPHAESTUS_FULL_BUILD "1"
```

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
- [ ] If a **missing module** error appears (PCG, ControlRig, Niagara, …): enable that engine plugin, or note the first error and paste it into the PR

## Editor smoke test

1. Open the project in Unreal Editor.
2. Enable **HephaestusBridge** in Edit → Plugins if not already on.
3. Play in Editor (PIE) or run standalone with `-game`.

```powershell
curl http://127.0.0.1:8099/health
```

- [ ] Returns `{"status":"ok","commands":27}` (or current tool count)

## Validation smoke test

```powershell
curl -X POST http://127.0.0.1:8099/command -H "Content-Type: application/json" -d "{\"command\":\"world.spawn_actor\",\"params\":{\"class_path\":\"evil/path\"}}"
```

- [ ] Returns `success: false` with class_path prefix denied (`ValidateCommand` wired)

## Agent smoke test

```powershell
hephaestus_forge agent --goal "Spawn a StaticMeshActor and capture a frame" --stream
```

- [ ] UE bridge reachable
- [ ] LLM responds (local llama-server or `--use-nim` with `NVIDIA_API_KEY`)
- [ ] Mission Control shows chain-of-thought and a viewport frame

## Auth (optional)

```
HEPHAESTUS_BRIDGE_TOKEN=your-secret
HEPHAESTUS_REQUIRE_AUTH=1
```

Restart editor; verify unauthenticated `POST /command` returns 401.

## Observability (optional)

When `observability.metrics.enabled: true`:

```powershell
curl http://127.0.0.1:9090/metrics
```

## If compile fails

1. Note the **first** linker or missing-module error (not the cascade).
2. Confirm `HEPHAESTUS_FULL_BUILD` is **not** set.
3. Enable missing engine plugins (PCG / ControlRig / Niagara) in the Epic launcher / `.uproject`.
4. Compare `HephaestusBridge.Build.cs` against the missing module name.
5. Paste the first error + `forge compile --dry-run` output into the GitHub PR/issue.

See also: [plugin_setup_windows.md](plugin_setup_windows.md), [COMMAND_API.md](COMMAND_API.md).

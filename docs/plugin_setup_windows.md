# Compiling the HephaestusBridge plugin on Windows

Exact steps to build the `HephaestusBridge` UE5.8 plugin and connect the Python
agent runtime. Windows is the primary target (the plugin depends on
PixelStreaming, WebRTC, and NVENC-oriented modules).

## 1. Prerequisites

| Requirement | Notes |
| --- | --- |
| Unreal Engine 5.8 | Installed via the Epic Games Launcher (`C:\Program Files\Epic Games\UE_5.8`) or built from source. |
| Visual Studio 2022 | Workloads: **Desktop development with C++** and **Game development with C++**. Include MSVC v143, Windows 10/11 SDK, and .NET desktop build tools. |
| .NET SDK 8+ | Required by UnrealBuildTool. |
| Python 3.10+ | For the `hephaestus_forge` CLI and agent runtime. |

Set an environment variable so the tooling can find the engine (matches
`resolve_ue_root` in `hephaestus_forge/ue_build.py`):

```powershell
setx UE_PATH "C:\Program Files\Epic Games\UE_5.8"
```

`forge compile` also reads `system.ue_path` from `.hephaestus_forge/config.yaml`
if `UE_PATH` is not set.

## 2. Project and plugin layout

A scaffolded project (`hephaestus_forge init <Project>`) looks like:

```
<Project>/
  <Project>.uproject
  UE5_Plugin_Source/HephaestusBridge/   <- plugin sources copied by the scaffold
```

Unreal only auto-discovers plugins under `<Project>/Plugins/`. Before compiling,
place the plugin there (copy, or use a directory junction so edits stay in one
place):

```powershell
cd <Project>
mkdir Plugins
# Junction keeps a single source of truth:
mklink /J Plugins\HephaestusBridge UE5_Plugin_Source\HephaestusBridge
```

Confirm the plugin is enabled in `<Project>.uproject`:

```json
"Plugins": [ { "Name": "HephaestusBridge", "Enabled": true } ]
```

## 3. Compile

### Option A — the forge CLI (recommended)

```powershell
hephaestus_forge compile <Project>            # builds the <Project>Editor target
hephaestus_forge compile <Project> --dry-run  # print the exact command first
hephaestus_forge compile <Project> --clean    # clean rebuild
```

`forge compile` locates the `.uproject`, resolves the engine, and builds the
project's **editor target** (which compiles all modules, including
`HephaestusBridge`).

### Option B — UnrealBuildTool directly

The command `forge compile --dry-run` prints is exactly:

```bat
"C:\Program Files\Epic Games\UE_5.8\Engine\Build\BatchFiles\Build.bat" ^
  HephaestusEditor Win64 Development ^
  -project="C:\path\to\<Project>\<Project>.uproject" -waitmutex
```

(Replace `HephaestusEditor` with `<Project>Editor` if your project is not named
`Hephaestus`.)

### Option C — Visual Studio

1. Right-click `<Project>.uproject` → **Generate Visual Studio project files**.
2. Open the generated `.sln`.
3. Set configuration to **Development Editor** / **Win64**.
4. Build the `<Project>` target (or press F5 to build and launch the editor).

## 4. Run and connect the agent

After the editor is running with the plugin loaded, the plugin's HTTP bridge
(`HephaestusHttpServer`) listens on port **8099** by default (override with the
`HEPHAESTUS_UE_PORT` environment variable).

Check readiness and drive the agent from Python:

```powershell
hephaestus_forge health <Project>                 # ue-bridge should read OK
hephaestus_forge agent --goal "Spawn a cube at the origin"
# Point the client at a non-default port/host if needed:
set HEPHAESTUS_UE_URL=http://127.0.0.1:8099
```

The agent loop (`hephaestus_forge/runtime/orchestrator.py`) calls tools such as
`world.spawn_actor` and `vision.capture_frame`, which POST command envelopes to
the bridge's `/command` endpoint.

## 5. Troubleshooting

| Symptom | Fix |
| --- | --- |
| `Unable to find plugin 'HephaestusBridge'` | Ensure it lives under `<Project>/Plugins/HephaestusBridge` (step 2) and is enabled in the `.uproject`. |
| `UnrealBuildTool not found` / `Build.bat` missing | Fix `UE_PATH` / `system.ue_path`; verify the engine install is complete. |
| Missing module errors (PixelStreaming, WebRTC, OpenCV) | Leave `HEPHAESTUS_FULL_BUILD` unset (default). Those are optional until after M1. |
| Missing module errors (PCG, ControlRig, Niagara) | Enable the matching engine plugins in UE 5.8 / `.uproject`. |
| Long first build | Expected — the plugin pulls in rendering, PCG, Niagara, audio, and media modules. Subsequent incremental builds are fast. |
| `forge health` shows `ue-bridge` WARN | The editor/plugin is not running yet, or the port differs — start UE and/or set `HEPHAESTUS_UE_PORT` / `HEPHAESTUS_UE_URL`. |

# HephaestusBridge — HTTP Command API

The UE plugin exposes a local HTTP server (default `http://127.0.0.1:8099`).
The Python agent uses `hephaestus_forge.runtime.ue_client.UEClient` to call it.

Configure via `.hephaestus_forge/config.yaml`:

```yaml
network:
  ue_bridge_port: 8099
security:
  require_auth: false
  bridge_token: ""   # or HEPHAESTUS_BRIDGE_TOKEN env
```

Environment variables passed to the UE editor at deploy time:

| Variable | Purpose |
| --- | --- |
| `HEPHAESTUS_UE_PORT` | Listen port (default 8099) |
| `HEPHAESTUS_BRIDGE_TOKEN` | Shared secret for mutation endpoints |
| `HEPHAESTUS_REQUIRE_AUTH` | `1` to require token on POST/GET frame |

## Authentication

When auth is enabled, mutation endpoints require header:

```
X-Hephaestus-Token: <token>
```

Protected routes: `POST /command`, `POST /batch`, `GET /frame/:id`.

Discovery routes stay open: `GET /health`, `GET /commands`.

## Endpoints

### `GET /health`

```json
{"status": "ok", "commands": 26}
```

### `GET /commands`

```json
{"commands": ["world.spawn_actor", "vision.capture_frame", "..."]}
```

### `POST /command`

Request:

```json
{
  "command": "world.spawn_actor",
  "params": {
    "action": "spawn_actor",
    "class_path": "/Script/Engine.StaticMeshActor",
    "transform": {
      "location": {"x": 0, "y": 0, "z": 100},
      "rotation": {"pitch": 0, "yaw": 0, "roll": 0},
      "scale": {"x": 1, "y": 1, "z": 1}
    }
  }
}
```

Response (`FHephaestusCommandResult`):

```json
{
  "success": true,
  "error_message": "",
  "result_json": "{\"actor_path\":\"/Game/.../Actor_1\"}",
  "actor_references": ["/Game/.../Actor_1"],
  "asset_references": [],
  "execution_time_ms": 1.2,
  "command_id": "cmd_1"
}
```

### `POST /batch`

```json
{
  "commands": [
    {"command": "world.spawn_actor", "params": {"action": "spawn_actor", "class_path": "..."}},
    {"command": "vision.capture_frame", "params": {"action": "capture_frame"}}
  ]
}
```

Returns `{"results": [ ... ]}` in order.

### `GET /frame/:id`

Returns PNG bytes for a captured viewport frame (`Content-Type: image/png`).

Typical flow: `vision.capture_frame` → read `frame_id` from `result_json` → `GET /frame/{id}`.

## Command families

All commands use `"params": {"action": "<action>", ...}` unless noted.

### world.*

| Command | Action | Key params |
| --- | --- | --- |
| `world.spawn_actor` | `spawn_actor` | `class_path`, `transform`, optional `label` |
| `world.destroy_actor` | `destroy_actor` | `actor_path` |
| `world.query_spatial` | `query_spatial` | optional `bounds`, `filter_class` |

### vision.*

| Command | Action | Key params |
| --- | --- | --- |
| `vision.capture_frame` | `capture_frame` | optional `format`, `resolution` |

### asset.*

| Command | Action | Key params |
| --- | --- | --- |
| `asset.create_material` | `create_material` | `material_desc` |
| `asset.import` | `import` | `file_path`, `destination_path` |
| `asset.reimport` | `reimport` | `asset_path` |
| `asset.export` | `export` | `asset_path`, `file_path` |
| `asset.create_instance` | `create_instance` | `parent_material` |

### blueprint.*

| Command | Action | Key params |
| --- | --- | --- |
| `blueprint.compile` | `compile` | `blueprint_path` |
| `blueprint.add_function` | `add_function` | `blueprint_path`, `function_name` |
| `blueprint.set_property` | `set_property` | `blueprint_path`, `property_name`, `value` |
| `blueprint.diff` | `diff` | `blueprint_path` |

### rendering.*

| Command | Action | Key params |
| --- | --- | --- |
| `rendering.add_pass` | `add_pass` | `pass_name` |
| `rendering.create_shader_params` | `create_shader_params` | `material_path` |
| `rendering.dispatch_compute` | `dispatch_compute` | `shader_path` |

### pcg.*

| Command | Action | Key params |
| --- | --- | --- |
| `pcg.mutate_graph` | `mutate_graph` | `graph_path` |
| `pcg.set_metadata` | `set_metadata` | `target_path`, `metadata` |
| `pcg.query_spatial` | `query_spatial` | optional `bounds`, `filter_tag` |

### animation.*

| Command | Action | Key params |
| --- | --- | --- |
| `animation.create_control_rig` | `create_control_rig` | `skeletal_mesh_path` |
| `animation.retarget` | `retarget` | `source_skeleton`, `target_skeleton`, `sequence_path` |
| `animation.edit_sequence` | `edit_sequence` | `sequence_path` |
| `animation.livelink_connect` | `livelink_connect` | `source_name` |

### audio.*

| Command | Action | Key params |
| --- | --- | --- |
| `audio.create_metasound` | `create_metasound` | `asset_path` |
| `audio.play_quartz` | `play_quartz` | `clock_name` |
| `audio.synthesize` | `synthesize` | `metasound_path` |

## Python tool registry

Agent tools mirror these commands. List schemas:

```bash
hephaestus_forge agent --goal "dry" --dry-run
```

Or in code:

```python
from hephaestus_forge.runtime import build_default_registry
registry = build_default_registry()
print(registry.names())  # 26 tools
```

## Error codes (HTTP)

| Code | Meaning |
| --- | --- |
| 401 | Missing or wrong `X-Hephaestus-Token` |
| 413 | Request body > 1 MiB |
| 503 | Command handler unavailable or auth misconfigured |
| 404 | No frame available at `/frame/:id` |

Command-level failures return HTTP 200 with `"success": false` in the JSON body.

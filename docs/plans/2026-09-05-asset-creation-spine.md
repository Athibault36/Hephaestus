# Asset creation spine (people / animals / creatures)

**Product bar:** An animation studio creates the assets it needs. Utterances like `make a dog`, `make a person`, `make a creature` must **author → import → spawn → frame** in PIE — not only search Content Browser.

## Providers (priority)

1. **CC5** (people / humanoids when installed)
2. **NIM → Blender bpy** (complex meshes / animals / props — uses `NVIDIA_API_KEY`)
3. **Blender creature kits** (offline stylized fallback)
4. **Meshy** — opt-in only (`HEPHAESTUS_USE_MESHY=1` + `MESHY_API_KEY`)

## First vertical (this build)

- Blender `export_creature_fbx` for `humanoid` / `quadruped` / `creature`
- `editor.import_fbx` prefers skeletal mesh when armature present
- Agent routes character/animal/creature language onto this path
- Meshy wired behind the same import loop when key present

## Success

`forge run <target> "make a dog and put it in the scene"` delivers a visible authored actor in frustum without a content pack.

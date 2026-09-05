# Asset creation spine (people / animals / creatures)

**Product bar:** An animation studio creates the assets it needs. Utterances like `make a dog`, `make a person`, `make a creature` must **author → import → spawn → frame** in PIE — not only search Content Browser.

## Providers (priority)

1. **Meshy** (when `MESHY_API_KEY`) — text → textured mesh → FBX/GLB in `dcc_exports`
2. **CC5** (when installed) — character export (existing)
3. **Blender creature kits** (always if Blender present) — authored mesh + armature FBX (stylized stand-in until gen/CC5)

## First vertical (this build)

- Blender `export_creature_fbx` for `humanoid` / `quadruped` / `creature`
- `editor.import_fbx` prefers skeletal mesh when armature present
- Agent routes character/animal/creature language onto this path
- Meshy wired behind the same import loop when key present

## Success

`forge run <target> "make a dog and put it in the scene"` delivers a visible authored actor in frustum without a content pack.

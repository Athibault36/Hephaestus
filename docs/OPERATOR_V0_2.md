# Operator v0.2 acceptance criteria

## Scenario A — spawn creature → walk → grade

1. PIE online with synced v0.1.1+ plugin
2. Goal: `Spawn a dog in front of the camera and make it walk`
3. Agent spawns skeletal mesh, plays locomotion, grade reports walk animation or displacement
4. `forge e2e <target>` live steps pass

## Scenario B — cinematic shot

1. Goal: `Frame the character in a cinematic shot from the left`
2. `sequence.create_shot` with `look_at_actor` succeeds
3. Grade: camera repositioned / shot created

## Scenario C — Mission Control

1. `forge build-mc <target>` then `forge observe <target>`
2. React UI: outliner context menu, asset search, agent chat, export session JSON v2
3. Preflight banner when plugin version mismatch

## Scenario D — packaging

1. `pip install -e .` from repo root
2. `forge doctor <target>` prints checklist + e2e + preflight
3. CI: pytest + Mission Control `npm run build`

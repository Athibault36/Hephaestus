# Operator v0.3 acceptance criteria

Builds on [OPERATOR_V0_2.md](OPERATOR_V0_2.md) and [RELEASE_v0.1.2.md](RELEASE_v0.1.2.md).

## Scenario E — direct Mission Control chat

| User message | Expected planner |
|--------------|------------------|
| `/Game/Meshes/Dog.Dog` | `direct_spawn` |
| `play idle animation on /Temp/...Actor_0` | `direct_locomotion` |
| `play test audio` | `direct_audio` |
| `search assets for dog` | `direct_search` |

## Scenario F — asset pipeline validation

1. `asset.reimport` with missing path → clear error (not unknown command)
2. `asset.create_instance` with engine default parent → transient MID success
3. `animation.retarget` without meshes → param error

## Scenario G — grading extensions

Goals mentioning **audio**, **material**, or **camera** require matching command memory or scene evidence before `grade.met`.

## Live checklist

See [LIVE_E2E.md](LIVE_E2E.md).

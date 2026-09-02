import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from goal_grader import grade_goal  # noqa: E402
from ue_agent_loop import WorldSnapshot  # noqa: E402


def test_grade_vague_dog_goal_not_auto_met():
    snap = WorldSnapshot(lights=2, meshes=5, skeletal=3)
    g = grade_goal("A dog", snap, memory=[])
    assert g.met is False
    assert "concrete" in g.summary.lower() or "asset" in g.summary.lower()


def test_grade_seed_goal_met():
    snap = WorldSnapshot(lights=1, meshes=3)
    g = grade_goal("Seed a lit test scene with a few cubes, then idle.", snap)
    assert g.met is True


def test_grade_missing_lights():
    snap = WorldSnapshot(lights=0, meshes=3)
    g = grade_goal("lit scene with cubes", snap)
    assert g.met is False
    assert any("lights" in m for m in g.missing)


def test_grade_jog_requires_pawn_speed():
    snap = WorldSnapshot(pawn_state={"speed": 0.0, "is_moving": False})
    g = grade_goal("jog forward for a few seconds", snap, memory=[{"kind": "apply_move", "ok": True}])
    assert g.met is False
    assert any("pawn" in m for m in g.missing)

    snap2 = WorldSnapshot(pawn_state={"speed": 120.0, "is_moving": True})
    g2 = grade_goal("jog forward for a few seconds", snap2, memory=[{"kind": "apply_move", "ok": True}])
    assert g2.met is True


def test_grade_few_cubes():
    snap = WorldSnapshot(lights=1, meshes=1)
    g = grade_goal("a few cubes", snap)
    assert g.met is False


def test_grade_camera_framing_accepts_create_shot():
    snap = WorldSnapshot(lights=1, meshes=1, skeletal=1)
    g = grade_goal("Frame the character from the left", snap, memory=[])
    assert g.met is False
    assert any("camera" in m for m in g.missing)

    g2 = grade_goal(
        "Frame the character from the left",
        snap,
        memory=[{"kind": "create_shot", "ok": True, "command": "sequence.create_shot"}],
    )
    assert "camera" not in " ".join(g2.missing)


def test_grade_creature_requires_asset_match():
    snap = WorldSnapshot(lights=1, meshes=0, skeletal=1, actor_details=[{"mesh_path": "/Game/Props/Chair.Chair"}])
    g = grade_goal("spawn a dog", snap, memory=[])
    assert g.met is False


def test_grade_audio_requires_play_command():
    snap = WorldSnapshot(lights=1, meshes=1)
    g = grade_goal("play background music", snap, memory=[])
    assert g.met is False
    assert any("audio" in m for m in g.missing)

    g2 = grade_goal(
        "play background music",
        snap,
        memory=[{"command": "audio.play_quartz", "ok": True}],
    )
    assert "audio" not in " ".join(g2.missing)


def test_grade_material_requires_create_command():
    snap = WorldSnapshot(lights=1, meshes=1)
    g = grade_goal("create a metallic material", snap, memory=[])
    assert g.met is False
    assert any("material" in m for m in g.missing)

    g2 = grade_goal(
        "create a metallic material",
        snap,
        memory=[{"command": "asset.create_material", "ok": True}],
    )
    assert "material" not in " ".join(g2.missing)


def test_grade_displacement_requires_move_or_speed():
    snap = WorldSnapshot(pawn_state={"speed": 0.0})
    g = grade_goal("verify displacement after walk forward", snap, memory=[])
    assert g.met is False
    assert any("displacement" in m for m in g.missing)

    g2 = grade_goal(
        "verify displacement after walk forward",
        snap,
        memory=[{"kind": "apply_move", "ok": True}],
    )
    assert "displacement" not in " ".join(g2.missing)


def test_grade_idle_accepts_successful_play_locomotion_memory():
    actor = "/Temp/UEDPIE_0.PersistentLevel.SkeletalMeshActor_0"
    snap = WorldSnapshot(
        lights=1,
        meshes=0,
        skeletal=1,
        actor_details=[{"actor_path": actor, "anim_playing": False}],
    )
    memory = [{
        "kind": "play_locomotion",
        "command": "animation.play_locomotion",
        "actor_path": actor,
        "ok": True,
    }]
    g = grade_goal(f"play idle animation on {actor}", snap, memory=memory)
    assert g.met is True


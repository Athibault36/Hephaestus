import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from goal_grader import grade_goal  # noqa: E402
from locomotion_fallback import infer_locomotion_mode, pick_fallback_anim_path  # noqa: E402
from ue_agent_loop import WorldSnapshot  # noqa: E402


def test_infer_locomotion_mode_idle():
    assert infer_locomotion_mode("play idle animation on actor") == "idle"


def test_infer_locomotion_mode_run():
    assert infer_locomotion_mode("make the dog run in place") == "run"


def test_pick_fallback_idle_path():
    path = pick_fallback_anim_path("hold idle pose")
    assert path and "Idle" in path


def test_grade_idle_on_named_actor():
    actor = "/Temp/UEDPIE_0.PersistentLevel.SkeletalMeshActor_0"
    snap = WorldSnapshot(
        lights=1,
        meshes=0,
        skeletal=1,
        actor_details=[{"actor_path": actor, "anim_playing": True}],
    )
    g = grade_goal(f"play idle animation on {actor}", snap, memory=[])
    assert g.met is True

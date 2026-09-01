import sys
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agent_asset import augment_goal_with_assets, _goal_tokens  # noqa: E402


def test_goal_tokens_filters_stopwords():
    assert "dog" in _goal_tokens("A dog in the scene")
    assert "the" not in _goal_tokens("the dog")


def test_augment_single_match():
    client = MagicMock()
    client.command.return_value = {
        "success": True,
        "result_json": '{"assets":["/Game/Animals/Dog.Dog"],"count":1}',
    }
    goal, matches, meta = augment_goal_with_assets(client, "A dog")
    assert len(matches) == 1
    assert "Spawn static mesh" in goal or "Spawn skeletal mesh" in goal
    assert meta["matches"]


def test_rank_asset_paths_prefers_token_overlap():
    from agent_asset import _rank_asset_paths

    ranked = _rank_asset_paths(
        "spawn a dog",
        ["/Game/Props/Chair.Chair", "/Game/Creatures/Dog.SK_Dog"],
    )
    assert ranked[0] == "/Game/Creatures/Dog.SK_Dog"

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from version import BRIDGE_VERSION, FORGE_VERSION, OPERATOR_MILESTONE  # noqa: E402


def test_version_constants():
    assert FORGE_VERSION == BRIDGE_VERSION
    assert FORGE_VERSION.count(".") == 2
    assert OPERATOR_MILESTONE == "v0.9"

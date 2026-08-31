# Copyright (c) 2024 HephaestusForge. All Rights Reserved.
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cloud.nim_client import DEFAULT_CHAT_MODEL, DEFAULT_FAST_MODEL, MODEL_ALIASES, NIMClient  # noqa: E402


def test_resolve_dead_ultra_alias():
    assert NIMClient.resolve_model("nvidia/nemotron-3-ultra") == DEFAULT_CHAT_MODEL


def test_resolve_dead_8b_alias():
    assert NIMClient.resolve_model("nvidia/nemotron-3-8b") == DEFAULT_FAST_MODEL


def test_canonical_ids_passthrough():
    assert NIMClient.resolve_model(DEFAULT_CHAT_MODEL) == DEFAULT_CHAT_MODEL
    assert NIMClient.resolve_model(DEFAULT_FAST_MODEL) == DEFAULT_FAST_MODEL


def test_aliases_cover_legacy_names():
    assert "nvidia/nemotron-3-ultra" in MODEL_ALIASES
    assert "nvidia/nemotron-3-8b" in MODEL_ALIASES


if __name__ == "__main__":
    test_resolve_dead_ultra_alias()
    test_resolve_dead_8b_alias()
    test_canonical_ids_passthrough()
    test_aliases_cover_legacy_names()
    print("ok")

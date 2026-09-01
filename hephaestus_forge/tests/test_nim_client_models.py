# Copyright (c) 2024 HephaestusForge. All Rights Reserved.
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cloud.nim_client import (  # noqa: E402
    DEFAULT_CHAT_MODEL,
    DEFAULT_FAST_MODEL,
    DEFAULT_LEGACY_ULTRA_MODEL,
    DEFAULT_PLANNER_MODEL,
    MODEL_ALIASES,
    NIMClient,
    chat_template_kwargs_for_model,
)


def test_resolve_dead_ultra_alias():
    assert NIMClient.resolve_model("nvidia/nemotron-3-ultra") == DEFAULT_LEGACY_ULTRA_MODEL


def test_resolve_dead_8b_alias():
    assert NIMClient.resolve_model("nvidia/nemotron-3-8b") == DEFAULT_FAST_MODEL


def test_canonical_ids_passthrough():
    assert NIMClient.resolve_model(DEFAULT_PLANNER_MODEL) == DEFAULT_PLANNER_MODEL
    assert NIMClient.resolve_model(DEFAULT_LEGACY_ULTRA_MODEL) == DEFAULT_LEGACY_ULTRA_MODEL
    assert NIMClient.resolve_model(DEFAULT_FAST_MODEL) == DEFAULT_FAST_MODEL


def test_default_chat_model_is_planner():
    assert DEFAULT_CHAT_MODEL == DEFAULT_PLANNER_MODEL


def test_deepseek_aliases():
    assert NIMClient.resolve_model("deepseek-v4-pro") == DEFAULT_PLANNER_MODEL
    assert NIMClient.resolve_model("deepseek-ai/deepseek-v4-pro") == DEFAULT_PLANNER_MODEL


def test_chat_template_kwargs_by_family():
    assert chat_template_kwargs_for_model(DEFAULT_PLANNER_MODEL) == {"thinking": False}
    assert chat_template_kwargs_for_model(DEFAULT_LEGACY_ULTRA_MODEL)["enable_thinking"] is False
    assert chat_template_kwargs_for_model(DEFAULT_FAST_MODEL)["enable_thinking"] is False


def test_aliases_cover_legacy_names():
    assert "nvidia/nemotron-3-ultra" in MODEL_ALIASES
    assert "nvidia/nemotron-3-8b" in MODEL_ALIASES
    assert "deepseek-v4-pro" in MODEL_ALIASES


if __name__ == "__main__":
    test_resolve_dead_ultra_alias()
    test_resolve_dead_8b_alias()
    test_canonical_ids_passthrough()
    test_default_chat_model_is_planner()
    test_deepseek_aliases()
    test_chat_template_kwargs_by_family()
    test_aliases_cover_legacy_names()
    print("ok")

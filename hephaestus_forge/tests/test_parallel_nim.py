# Copyright (c) 2024 HephaestusForge. All Rights Reserved.
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cloud.parallel_nim import ParallelNemotronCoder, ParallelResult  # noqa: E402
from cloud.nim_client import DEFAULT_CHAT_MODEL, DEFAULT_FAST_MODEL  # noqa: E402


def test_parallel_result_ok_when_either_succeeds():
    r = ParallelResult(
        ultra_model=DEFAULT_CHAT_MODEL,
        lightning_model=DEFAULT_FAST_MODEL,
        ultra_text="",
        lightning_text="impl",
        ultra_error="boom",
    )
    assert r.ok is True


def test_parallel_result_not_ok_when_both_empty():
    r = ParallelResult(
        ultra_model=DEFAULT_CHAT_MODEL,
        lightning_model=DEFAULT_FAST_MODEL,
        ultra_text="",
        lightning_text="",
    )
    assert r.ok is False


def test_merge_includes_both_sections():
    md = ParallelNemotronCoder._merge("task", "plan here", "code here", "", "")
    assert "Ultra" in md and "Lightning" in md
    assert "plan here" in md and "code here" in md


def test_default_models_are_parallel_pair():
    coder = ParallelNemotronCoder(api_key="dummy")
    assert coder.ultra_model == DEFAULT_CHAT_MODEL
    assert coder.lightning_model == DEFAULT_FAST_MODEL
    assert "550b" in coder.ultra_model
    assert "lightning" in coder.lightning_model


if __name__ == "__main__":
    test_parallel_result_ok_when_either_succeeds()
    test_parallel_result_not_ok_when_both_empty()
    test_merge_includes_both_sections()
    test_default_models_are_parallel_pair()
    print("ok")

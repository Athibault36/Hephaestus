# Copyright (c) 2024 HephaestusForge. All Rights Reserved.
from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from project_registry import ProjectRegistry, RegisteredProject  # noqa: E402


def test_add_and_active():
    with tempfile.TemporaryDirectory() as td:
        tmp_path = Path(td)
        forge = tmp_path / ".hephaestus_forge"
        forge.mkdir()
        reg_file = tmp_path / "projects.json"

        with patch("project_registry._registry_path", return_value=reg_file):
            reg = ProjectRegistry.load()
            entry = reg.add(tmp_path, name="demo")
            assert entry.name == "demo"
            assert reg.active() == tmp_path.resolve()


def test_list_valid_skips_missing():
    with tempfile.TemporaryDirectory() as td:
        tmp_path = Path(td)
        reg_file = tmp_path / "projects.json"
        good = tmp_path / "good"
        good.mkdir()
        (good / ".hephaestus_forge").mkdir()
        bad = tmp_path / "bad"
        bad.mkdir()

        with patch("project_registry._registry_path", return_value=reg_file):
            reg = ProjectRegistry.load()
            reg.projects = [
                RegisteredProject(path=str(good), name="good"),
                RegisteredProject(path=str(bad), name="bad"),
            ]
            valid = reg.list_valid()
            assert len(valid) == 1
            assert valid[0].name == "good"


if __name__ == "__main__":
    test_add_and_active()
    test_list_valid_skips_missing()
    print("ok")

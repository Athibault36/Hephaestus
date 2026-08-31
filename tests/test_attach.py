"""forge attach wires HephaestusForge into an existing UE project."""

import json
from pathlib import Path

from hephaestus_forge.forge import _enable_plugin_in_uproject


def test_enable_plugin_adds_entry(tmp_path: Path):
    up = tmp_path / "test.uproject"
    up.write_text(json.dumps({"FileVersion": 3, "EngineAssociation": "5.8"}))
    changed = _enable_plugin_in_uproject(up, "HephaestusBridge")
    assert changed is True
    data = json.loads(up.read_text())
    assert {"Name": "HephaestusBridge", "Enabled": True} in data["Plugins"]


def test_enable_plugin_flips_disabled(tmp_path: Path):
    up = tmp_path / "test.uproject"
    up.write_text(json.dumps({"Plugins": [{"Name": "HephaestusBridge", "Enabled": False}]}))
    assert _enable_plugin_in_uproject(up, "HephaestusBridge") is True
    data = json.loads(up.read_text())
    assert data["Plugins"][0]["Enabled"] is True


def test_enable_plugin_idempotent(tmp_path: Path):
    up = tmp_path / "test.uproject"
    up.write_text(json.dumps({"Plugins": [{"Name": "HephaestusBridge", "Enabled": True}]}))
    assert _enable_plugin_in_uproject(up, "HephaestusBridge") is False

"""Plugin template sync (no Unreal required)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from plugin_sync import PLUGIN_TEMPLATE, sync_plugin  # noqa: E402
from version import BRIDGE_VERSION  # noqa: E402


def test_sync_plugin_copies_template(tmp_path):
    dest = sync_plugin(tmp_path)
    assert dest.is_dir()
    assert (dest / "HephaestusBridge.uplugin").is_file()
    handler = dest / "Source" / "HephaestusBridge" / "Private" / "Command" / "HephaestusCommandHandler.cpp"
    assert handler.is_file()
    text = handler.read_text(encoding="utf-8")
    assert "world.apply_move_input" in text
    assert "animation.play_montage" in text
    assert "animation.play_locomotion" in text
    assert (dest / "HEPHAESTUS_BRIDGE_VERSION").is_file()
    version_h = dest / "Source" / "HephaestusBridge" / "Public" / "HephaestusVersion.h"
    assert version_h.is_file()
    assert f'TEXT("{BRIDGE_VERSION}")' in version_h.read_text(encoding="utf-8")
    assert (dest / "HEPHAESTUS_BRIDGE_VERSION").read_text(encoding="utf-8").strip() == BRIDGE_VERSION
    uplugin = (dest / "HephaestusBridge.uplugin").read_text(encoding="utf-8")
    assert f'"VersionName": "{BRIDGE_VERSION}"' in uplugin


def test_plugin_template_has_sequence_verbs():
    handler = PLUGIN_TEMPLATE / "Source" / "HephaestusBridge" / "Private" / "Command" / "HephaestusCommandHandler.cpp"
    text = handler.read_text(encoding="utf-8")
    assert "sequence.play" in text
    assert "sequence.create_shot" in text


def test_plugin_template_has_world_gameplay_verbs():
    handler = PLUGIN_TEMPLATE / "Source" / "HephaestusBridge" / "Private" / "Command" / "HephaestusCommandHandler.cpp"
    text = handler.read_text(encoding="utf-8")
    assert "get_pawn_state" in text
    assert "PlayMontage" in text or "play_montage" in text

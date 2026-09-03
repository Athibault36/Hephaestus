"""Unit tests for FBX import command builders and validation (no Unreal required)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLUGIN_PY = ROOT / "templates" / "ue_plugin" / "HephaestusBridge" / "Content" / "Python"
sys.path.insert(0, str(PLUGIN_PY))
sys.path.insert(0, str(ROOT))

from hephaestus.commands import (  # noqa: E402
    build_import_fbx_command,
    build_import_fbx_command_v2,
)
from remote_command_schema import validate_import_fbx_command  # noqa: E402


def test_build_import_fbx_command():
    command = build_import_fbx_command(
        source_path="C:/tmp/MyMesh.fbx",
        destination_path="/Game/Imported",
        destination_name="MyMesh",
        destination_rename=False,
        destination_force_reimport=False,
        destination_package_error=False,
        auto_verify=True,
    )
    assert command["command"] == "asset.import_fbx"
    assert command["params"]["source_path"] == "C:/tmp/MyMesh.fbx"
    assert command["params"]["file_path"] == "C:/tmp/MyMesh.fbx"
    assert command["params"]["destination_path"] == "/Game/Imported"
    assert command["params"]["destination_name"] == "MyMesh"
    assert validate_import_fbx_command(command) == []
    restored = json.loads(json.dumps(command))
    assert restored["command"] == "asset.import_fbx"


def test_build_import_fbx_command_v2():
    command = build_import_fbx_command_v2(
        source_path="C:/tmp/MyMesh.fbx",
        destination_path="/Game/Imported",
        destination_name="MyMesh",
        destination_subobject_index=0,
        destination_subobject_name="MyMesh",
        destination_rename=False,
        destination_force_reimport=False,
        destination_package_error=False,
        auto_verify=True,
        verify_mesh_count=True,
        verify_anim_count=3,
        verify_texture_count=2,
    )
    assert command["command"] == "asset.import_fbx"
    assert command["params"]["verify"]["mesh_count"] is True
    assert command["params"]["verify"]["anim_count"] == 3
    assert command["params"]["verify"]["texture_count"] == 2
    assert validate_import_fbx_command(command) == []


if __name__ == "__main__":
    test_build_import_fbx_command()
    test_build_import_fbx_command_v2()
    print("All FBX import tests passed!")

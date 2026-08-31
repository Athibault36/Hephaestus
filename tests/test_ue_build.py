from pathlib import Path

from hephaestus_forge.ue_build import (
    build_script_path,
    build_ubt_command,
    editor_target_name,
    find_uproject,
    resolve_ue_root,
)


def test_find_uproject_in_subfolder(tmp_path: Path):
    proj = tmp_path / "Hephaestus"
    proj.mkdir()
    up = proj / "Hephaestus.uproject"
    up.write_text("{}")
    assert find_uproject(tmp_path) == up


def test_find_uproject_prefers_matching_stem(tmp_path: Path):
    (tmp_path / "Other.uproject").write_text("{}")
    matching = tmp_path / (tmp_path.name + ".uproject")
    matching.write_text("{}")
    assert find_uproject(tmp_path) == matching


def test_find_uproject_none(tmp_path: Path):
    assert find_uproject(tmp_path) is None


def test_editor_target_name():
    assert editor_target_name(Path("/x/Hephaestus.uproject")) == "HephaestusEditor"


def test_build_script_path_per_platform():
    ue = Path("/opt/UE_5.8")
    assert build_script_path(ue, "Win64").name == "Build.bat"
    assert build_script_path(ue, "Win64").parent.name == "BatchFiles"
    assert build_script_path(ue, "Linux") == ue / "Engine/Build/BatchFiles/Linux/Build.sh"
    assert build_script_path(ue, "Mac") == ue / "Engine/Build/BatchFiles/Mac/Build.sh"


def test_build_ubt_command_editor_target():
    ue = Path("/opt/UE_5.8")
    up = Path("/proj/Hephaestus/Hephaestus.uproject")
    cmd = build_ubt_command(ue, up, target_platform="Win64", configuration="Development")
    assert cmd[1] == "HephaestusEditor"
    assert cmd[2] == "Win64"
    assert cmd[3] == "Development"
    assert f"-project={up}" in cmd
    assert "-waitmutex" in cmd
    assert "-clean" not in cmd

    clean_cmd = build_ubt_command(ue, up, target_platform="Win64", clean=True)
    assert "-clean" in clean_cmd


def test_resolve_ue_root_from_env(tmp_path: Path):
    engine = tmp_path / "UE_5.8"
    engine.mkdir()
    assert resolve_ue_root(None, env={"UE_PATH": str(engine)}) == engine
    assert resolve_ue_root(None, env={}) is None

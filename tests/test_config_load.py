"""ForgeConfig.load must actually read YAML (the pydantic yaml_file key is inert)."""

import warnings
from pathlib import Path

from hephaestus_forge.forge import ForgeConfig

SAMPLE = Path(__file__).resolve().parents[1] / "hephaestus_forge" / "forge_config" / "config.yaml"


def test_load_populates_nested_and_extra_fields():
    cfg = ForgeConfig.load(SAMPLE)
    # Declared nested models are coerced from the YAML.
    assert cfg.system.ue_path == "C:/UnrealEngine/5.8"
    assert cfg.paths.mission_control_dir == "MissionControl"
    assert cfg.network.dashboard_port == 3000
    assert cfg.network.ue_bridge_port == 8099
    assert cfg.security.localhost_only is True
    # 'agent_runtime' is not a declared field but is preserved via extra="allow".
    assert cfg.agent_runtime["llama_server"]["port"] == 8080


def test_load_does_not_emit_yaml_file_warning():
    with warnings.catch_warnings():
        warnings.simplefilter("error")  # any UserWarning becomes an error
        ForgeConfig.load(SAMPLE)

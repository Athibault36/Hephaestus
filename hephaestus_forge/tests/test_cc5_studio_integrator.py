# Copyright (c) 2024 HephaestusForge. All Rights Reserved.
"""
Minimal reproducible integration test for cc5_studio_integrator.

Default: offline unit checks (no CC5 GUI required).
Live: set HEPHAESTUS_CC5_LIVE=1 and ensure CC5 + optional UE project root.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cc5_studio_integrator import (  # noqa: E402
    capability_report,
    configure_character,
    detach_cc5_control,
    export_asset,
    initialize_cc5_session,
    terminate_cc5_session,
)


def test_capability_matrix_honest():
    rep = capability_report()
    assert rep["integrator_version"]
    assert rep["capabilities"]["export_fbx"]["supported"] is True
    assert rep["capabilities"]["unity_backend"]["supported"] is False
    assert rep["capabilities"]["export_usdz_gltf"]["supported"] is False
    assert rep["capabilities"]["batch_50_parallel"]["supported"] is False


def test_configure_applies_three_morphs():
    out = configure_character(
        {
            "character_name": "MRT",
            "prompt": "muscular man",
            "morphs": {"muscle": 0.85, "jaw": 0.4, "nose": 0.25},
        }
    )
    assert out["ok"] is True
    morphs = out["appearance"]["morphs"]
    assert float(morphs["muscle"]) == 0.85
    assert float(morphs["jaw"]) == 0.4
    assert float(morphs["nose"]) == 0.25
    assert out["morph_count"] >= 3


def test_detach_emergency_stop():
    r = detach_cc5_control("unit_test")
    assert r["ok"] is True
    assert r["reason"] == "unit_test"


def test_unsupported_export_format():
    r = export_asset("usdz")
    assert r["ok"] is False
    assert "unsupported" in (r.get("error") or "").lower()


def test_live_mrt_optional():
    """Spawn → 3 morphs → export FBX → validation report (requires CC5)."""
    if os.environ.get("HEPHAESTUS_CC5_LIVE", "").strip() not in ("1", "true", "yes"):
        return
    project = os.environ.get("HEPHAESTUS_PROJECT") or r"C:\dev\FreshHephaestusGame"
    init = initialize_cc5_session("ue58", {"project_root": project, "dismiss_dialogs": True})
    assert init.get("ok"), init
    cfg = configure_character(
        {
            "character_name": "MRTLive",
            "prompt": "tall muscular man named MRTLive",
            "morphs": {"muscle": 0.9, "jaw": 0.35, "chin": 0.3},
        }
    )
    assert cfg["ok"]
    # Animation in CC5 is not streamed; export then (optional) UE animate separately
    exp = export_asset(
        "fbx",
        character_name="MRTLive",
        project_root=project,
        appearance=cfg["appearance"],
        import_to_ue=False,
        timeout_seconds=600,
    )
    report = exp.get("validation") or {}
    report_path = Path(report.get("report_path") or "")
    assert report_path.is_file(), report
    data = json.loads(report_path.read_text(encoding="utf-8"))
    assert data["checks"], data
    # Soft assert: if CC5 timed out, report fails honestly
    terminate_cc5_session()
    if not exp.get("ok"):
        raise AssertionError(f"live export failed: {exp.get('error')} report={data}")


if __name__ == "__main__":
    test_capability_matrix_honest()
    test_configure_applies_three_morphs()
    test_detach_emergency_stop()
    test_unsupported_export_format()
    test_live_mrt_optional()
    print("test_integration OK")

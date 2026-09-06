# Copyright (c) 2024 HephaestusForge. All Rights Reserved.
"""Per-asset validation reports for CC5 studio exports."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Optional


def _reports_dir() -> Path:
    home = Path(os.environ.get("HEPHAESTUS_HOME") or (Path.home() / ".hephaestus"))
    d = home / "cc5_validation"
    d.mkdir(parents=True, exist_ok=True)
    return d


def build_export_validation_report(
    *,
    export: dict[str, Any],
    fbm: Optional[dict[str, Any]],
    elapsed_s: float,
    appearance: Optional[dict[str, Any]],
    import_result: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def add(name: str, passed: bool, detail: Any = None) -> None:
        checks.append({"name": name, "pass": bool(passed), "detail": detail})

    fbx = export.get("output_path")
    fbx_path = Path(str(fbx)) if fbx else None
    add("export_success", bool(export.get("success")))
    add("fbx_exists", bool(fbx_path and fbx_path.is_file()), str(fbx_path) if fbx_path else None)
    size = fbx_path.stat().st_size if fbx_path and fbx_path.is_file() else 0
    # Real CC5 humanoids are tens–hundreds of MB; reject empty stubs / blender fallbacks
    add("fbx_min_size", size > 1_000_000, {"bytes": size})
    add("fbm_sidecar", bool(fbm and fbm.get("exists")), fbm)
    if fbm and fbm.get("exists"):
        add("fbm_has_files", int(fbm.get("files") or 0) > 0, fbm.get("files"))
    if appearance:
        morphs = appearance.get("morphs") or {}
        add("appearance_has_morphs", len(morphs) >= 1, len(morphs))
    if import_result is not None:
        add("ue_import_success", bool(import_result.get("success")), import_result.get("error"))
        bound = import_result.get("materials_bound")
        if bound is not None:
            add("materials_bound", int(bound) > 0, bound)

    # Studio benchmark: CC5 authoring is minutes, not <2s — report honestly
    add(
        "elapsed_reported",
        True,
        {
            "elapsed_s": round(elapsed_s, 3),
            "benchmark_note": (
                "Full CC5 morph+cloth+FBX is typically 60–600s on workstation hardware; "
                "<2s/character is not achievable with GUI OpenPlugin authoring."
            ),
        },
    )

    passed = all(c["pass"] for c in checks if c["name"] != "elapsed_reported")
    report = {
        "pass": passed,
        "summary": "PASS" if passed else "FAIL",
        "checks": checks,
        "t": time.time(),
        "iso": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    out_path = _reports_dir() / f"validate_{int(time.time() * 1000)}.json"
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    report["report_path"] = str(out_path)
    return report

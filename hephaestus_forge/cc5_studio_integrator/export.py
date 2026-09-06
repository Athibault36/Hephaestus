# Copyright (c) 2024 HephaestusForge. All Rights Reserved.
"""Programmatic CC5 export into Hephaestus dcc_exports (+ optional UE import)."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Optional

from .audit import audit_log
from .session import get_session
from .validation import build_export_validation_report


def export_asset(
    format: str = "fbx",
    *,
    character_name: Optional[str] = None,
    project_root: Optional[str | Path] = None,
    appearance: Optional[dict[str, Any]] = None,
    prompt: str = "",
    import_to_ue: bool = False,
    timeout_seconds: int = 600,
) -> dict[str, Any]:
    """
    Export character to studio format.

    Supported format: ``fbx`` (Unreal-ready with .fbm textures).
    USDZ/glTF are not supported on the Hephaestus path.
    """
    fmt = (format or "fbx").strip().lower()
    if fmt not in ("fbx", "ue", "unreal"):
        err = f"unsupported format={format!r}; use fbx"
        audit_log("export_asset", ok=False, error=err)
        return {"ok": False, "error": err}

    sess = get_session()
    cfg = sess.get("config") if isinstance(sess.get("config"), dict) else {}
    plan = appearance or cfg.get("appearance")
    name = character_name or (plan or {}).get("character_name") or "Character"
    root = project_root or sess.get("project_root") or cfg.get("project_root")
    root_path = Path(root) if root else None

    try:
        from cc5_bridge import export_character_fbx
    except ImportError:
        from hephaestus_forge.cc5_bridge import export_character_fbx  # type: ignore

    t0 = time.time()
    export = export_character_fbx(
        character_name=str(name),
        project_root=root_path,
        timeout_seconds=int(timeout_seconds),
        prompt=prompt or str((plan or {}).get("prompt") or ""),
        appearance=plan,
    )
    elapsed = time.time() - t0
    ok = bool(export.get("success") and export.get("output_path"))
    fbx = export.get("output_path")
    fbm = None
    if fbx:
        fbm_path = Path(str(fbx)).with_suffix(".fbm")
        fbm = {
            "exists": fbm_path.is_dir(),
            "path": str(fbm_path) if fbm_path.is_dir() else None,
            "files": len(list(fbm_path.iterdir())) if fbm_path.is_dir() else 0,
        }

    import_result = None
    if ok and import_to_ue and root_path:
        try:
            from dcc_import import dcc_import_to_pie
        except ImportError:
            from hephaestus_forge.dcc_import import dcc_import_to_pie  # type: ignore
        import_result = dcc_import_to_pie(
            fbx=str(fbx),
            project_root=root_path,
            name=str(name),
            import_as_skeletal=True,
            force_skeletal_spawn=True,
        )

    report = build_export_validation_report(
        export=export,
        fbm=fbm,
        elapsed_s=elapsed,
        appearance=plan,
        import_result=import_result,
    )

    out = {
        "ok": ok and report.get("pass", False),
        "format": "fbx",
        "output_path": fbx,
        "fbm": fbm,
        "export": export,
        "import": import_result,
        "validation": report,
        "elapsed_s": elapsed,
    }
    audit_log(
        "export_asset",
        ok=bool(out["ok"]),
        detail={"fbx": fbx, "elapsed_s": elapsed, "validation": report.get("summary")},
        error="" if out["ok"] else (export.get("error") or "export_or_validation_failed"),
    )
    return out

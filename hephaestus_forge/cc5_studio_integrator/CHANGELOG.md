# Changelog — CC5 Studio Integrator

## 1.0.0 — 2026-09-06

- Initial Hephaestus-facing integrator package (`initialize_cc5_session`, `configure_character`, `generate_animation`, `export_asset`, `terminate_cc5_session`, `detach_cc5_control`).
- Audit JSONL under `~/.hephaestus/cc5_audit/`; validation reports under `~/.hephaestus/cc5_validation/`.
- Capability matrix documents unsupported mega-brief items (Unity, USDZ, parallel CC5 GUI, sub-2s authoring).
- Compatible with Character Creator 5 via HephaestusExport OpenPlugin + HephaestusBridge 1.0.9 (UE 5.8).

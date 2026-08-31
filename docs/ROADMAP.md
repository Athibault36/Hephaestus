# HephaestusForge — Production Roadmap

This roadmap sequences the work required to take HephaestusForge from its current
state (a tested Python runtime + CLI + dashboard, with review-only UE C++) to a
production-ready autonomous UE5.8 agent system.

It is ordered by **dependency and exit criteria**, not calendar dates: the pace is
gated by hardware availability (Windows + UE5.8 + GPU) and by how many iterations
the first plugin compile needs, so milestone sequencing + "definition of done" is
the reliable way to track it.

Legend: **[G]** gated on hardware/environment · **[now]** doable on Linux without
the engine/GPU · risk = engineering uncertainty.

---

## Definition of "production done"

- [ ] UE plugin compiles cleanly and loads in a packaged build, not just the editor.
- [ ] `deploy → agent` completes a real goal end-to-end (observe → reason → act) against a live editor.
- [ ] LLM served with acceptable latency (config target: total loop p95 < 300 ms excluding model think time) and a real, tool-calling-capable model.
- [ ] All advertised commands (`world/asset/blueprint/rendering/pcg/animation/audio/vision`) are implemented, not stubs.
- [ ] The HTTP bridge is authenticated and bound to localhost by default; no secrets in source.
- [ ] Structured logs, metrics, and traces emit; dashboard reflects live state.
- [ ] CI is green (tests, build, lint, type-check); releases are versioned and tagged.
- [ ] Onboarding docs let a new user go from clone → running agent.

---

## Phase 0 — Current state (complete)

- Python agent runtime: `UEClient`, tool registry (`world.spawn_actor`, `world.destroy_actor`, `world.query_spatial`, `vision.capture_frame`), `LLMClient` (native + text/ReAct tool-calling), `AgentRuntime` observe→think→act loop. **56 tests.**
- CLI: `init`, `attach`, `compile` (editor target + plugin auto-placement + `--dry-run`), `health`, `agent` (`--stream`), plus existing commands.
- Mission Control dashboard builds cleanly; live Socket.IO bridge streams chain-of-thought / actors / latency metrics.
- Packaging (`pyproject.toml` + console script), reproducible dev installs, CI (pytest + build) green on PRs.
- Config loader fixed; frame egress (`/frame`); Windows compile docs.
- Review-only C++ (not compiled here): `HephaestusHttpServer` (`/health`, `/commands`, `/command`, `/batch`, `/frame/:id`), `SpawnActor` transform fix, `Build.cs`/`.uplugin` wiring.

---

## Gate G — Hardware & environment

Windows 11 + Unreal Engine 5.8 + Visual Studio 2022 (Desktop + Game C++ workloads) +
an NVIDIA GPU (target: L40S). Enable the engine plugins the module depends on
(PixelStreaming, WebRTC, OpenCV, and the LLM/gRPC third-party libs). **Everything in
Phases 1–2 that touches the engine or GPU is blocked on this.**

---

## Phase 1 — Engine bring-up (critical path) [G]

| M | Milestone | Scope | Exit criteria | Risk |
| --- | --- | --- | --- | --- |
| 1 | Compile the plugin | Build `HephaestusBridge`; verify `HephaestusHttpServer`, `/frame`, spawn fix, `HTTPServer` wiring; reconcile heavy module deps | `<Project>Editor` builds; plugin loads; `GET /health` responds | **High** — first compile of a large plugin with many engine deps; expect iteration |
| 2 | Live loop | `forge deploy` starts editor + services; `forge agent` spawns an actor & captures a frame for real | An end-to-end goal completes against the running editor | Medium (needs M1 + M3) |
| 3 | LLM serving | Validate llama.cpp on L40S (flash-attn flag, tokens/sec) **or** NIM; replace the placeholder `nvidia/Nemotron-3-Ultra` id; confirm tool-calling (else text fallback) | Model responds within latency budget and drives the loop | Medium |

---

## Phase 2 — Capability completeness

| M | Milestone | Scope | Exit criteria | Gate |
| --- | --- | --- | --- | --- |
| 4 | Vision observe loop | Real `UTexture2D` readback → PNG at `/frame`; feed a vision model | Agent reasons over an actual captured frame | [G] after M2 |
| 5 | Command handlers | Implement stubbed `asset/blueprint/rendering/pcg/animation/audio` + `world.batch_edit/query_spatial` in C++ + Python tools | Each command performs a real engine action, tested | [G] after M1; incremental |
| 6 | Dashboard completion | Viewport (WebRTC or `/frame` polling), Voice console (STT/TTS), UE-sourced metrics | Panels show live data, no placeholders | Viewport polling **[now]**; rest [G] |

---

## Phase 3 — Reliability & correctness

- Integration tests against a live (or headless `-nullrhi`) editor covering the command surface.
- Process lifecycle: robust startup/shutdown of llama/tts/vision/dcc/bridge in `deploy`; readiness checks; restart-safety.
- Bridge resilience: reconnection, timeouts, backpressure (client retries exist; extend to the server/loop).
- Config-driven everything: ports/hosts from `config.yaml` (bridge port, UE URL) rather than hard-coded defaults.
- Error taxonomy: distinguish transport vs. command vs. tool errors end-to-end (partially done in the runtime).

Exit: a soak run of repeated agent goals completes without leaks, hangs, or orphaned processes.

## Phase 4 — Security & safety

- Authenticate the HTTP bridge (shared-token header), bind to `127.0.0.1` by default, gate remote exposure explicitly (`security.localhost_only` already in config).
- Validate/limit command input server-side (size, allowed classes/paths) to prevent unsafe spawns/loads.
- Secrets only via environment/secret store (`NVIDIA_API_KEY`, `MESHY_API_KEY`, Brev creds) — never in source; redact in logs.
- Enforce cloud budget guardrails (existing `BudgetManager`) on any GPU/cloud path.
- Security review of the command handler and bridge before any non-localhost use.

Exit: no unauthenticated mutation path; no secret in repo/logs; a security-review pass is clean.

## Phase 5 — Observability

- Structured JSONL logging (config: `observability.log_format=jsonl`) across runtime + plugin.
- Prometheus metrics endpoint (config: port 9090) for loop/tool/LLM latency and error rates.
- Tracing to the configured OTLP endpoint; correlate agent steps with `command_id`.
- Dashboard: real FPS/GPU/latency from UE (extends the current latency-only metrics).

Exit: latency percentiles (p50/95/99) are measurable and meet the config targets.

## Phase 6 — Packaging, docs & release

- UE plugin packaging: a distributable, versioned `.uplugin` (Marketplace-shaped) with an install path that isn't the manual `Plugins/` copy.
- Python: versioning/changelog; publishable wheel; pinned lockfile for reproducibility.
- Docs: a top-level README, a user guide (clone → attach → compile → agent), and a command/API reference (the Windows compile doc exists).
- CI extensions: add `ruff`/`mypy` (Python) — `tsc` strict already runs; build artifacts; release tagging.
- Merge sequencing: land the dev-environment PR into `main`, then rebase the feature PR onto `main`.

Exit: a tagged release; a new user reaches a running agent from the docs alone.

---

## Parallelizable now (no hardware) [now]

- Viewport panel fallback: poll `/frame` and render as `<img>` (a Linux-testable slice of M6).
- Python-side tools + tests for the M5 command families (wiring verifiable now; effective once C++ handlers land).
- Config-driven ports/hosts (Phase 3) and bridge token auth scaffolding (Phase 4) — both testable without the engine.
- README / user-guide draft and CI lint/type-check jobs (Phase 6).

## Risk register (top items)

1. **M1 plugin compile** — many heavy engine-module dependencies may be absent/disabled; highest-uncertainty step. Mitigation: compile incrementally, gate optional subsystems behind `WITH_*` defines.
2. **Model reality** — the configured model id is a placeholder; tool-calling support is unproven. Mitigation: text/ReAct fallback already in the loop; validate a concrete served model in M3.
3. **UE API drift** — the review-only C++ uses UE5 HTTP-server/ImageWrapper APIs that can shift between engine versions. Mitigation: verify signatures at M1.
4. **Security of an open local bridge** — mutation endpoints are currently unauthenticated. Mitigation: Phase 4 before any non-localhost exposure.

---

## Critical path

`G → M1 → M2` (with `M3` in parallel) yields the first real autonomous loop; Phases 2–6
then harden and broaden it to production. The Track-marked **[now]** items proceed on
Linux while the hardware gate is pending.

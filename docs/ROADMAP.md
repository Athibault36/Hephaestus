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
- [ ] Voice is real-time (always-on, no push-to-talk) and speaker-verified — Hephaestus acts only on the enrolled operator's voice.
- [ ] Structured logs, metrics, and traces emit; dashboard reflects live state.
- [ ] CI is green (tests, build, lint, type-check); releases are versioned and tagged.
- [ ] Onboarding docs let a new user go from clone → running agent.

---

## Phase 0 — Current state (complete)

- Python agent runtime: `UEClient`, tool registry (27 commands across world/vision/asset/blueprint/rendering/pcg/animation/audio), `LLMClient` (native + text/ReAct tool-calling), `AgentRuntime` observe→think→act loop. **123+ tests.**
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

## Phase 2b — Real-time, speaker-verified voice

Requirement: no push-to-talk. Hephaestus listens continuously and responds ONLY
to the enrolled operator's voice, ignoring everyone else.

| M | Milestone | Scope | Exit criteria | Gate |
| --- | --- | --- | --- | --- |
| V1 | Verification + gate core | `runtime/voice`: `SpeakerVerifier` (enroll + cosine threshold) and `RealtimeVoicePipeline` (always-on VAD → verify → STT gate; non-operator speech ignored, never transcribed; barge-in hooks) | Impostor rejected, operator accepted, mixed-speaker stream gated — **done, unit-tested** | [now] |
| V2 | Dashboard voice UX | Voice Console: always-listening state, live waveform, "Recognized — you" badge, mute toggle (no push-to-talk); bridge `voiceActive`/`speaker` events | Panel reflects live listening + recognition — **done** | [now] |
| V3 | Real backends | Wire silero-vad (VAD), ECAPA-TDNN or NVIDIA TitaNet (speaker embeddings), faster-whisper/Parakeet (streaming STT); browser mic → server audio (WebRTC/WS) | Live mic drives the loop; only the operator is obeyed | [G] |
| V4 | Enrollment + barge-in | Operator enrollment flow (record samples → profile), and TTS ducking/interruption when the operator speaks | Enroll once, then hands-free; agent stops talking when interrupted | [G] |

## Phase 3 — Reliability & correctness

- Integration tests against FakeUE covering the command surface (**done** — contract + soak tests).
- Process lifecycle: `ProcessSupervisor` in `deploy`, readiness checks, graceful shutdown (**done** for Python services).
- Bridge resilience: client retries for transport/503; auth + validation on mutations (**done** Python + C++ scaffold).
- Config-driven everything: ports/hosts/observability from `config.yaml` (**done**).
- Error taxonomy: transport vs. command vs. tool vs. validation end-to-end (**done**).

Exit: a soak run of repeated agent goals completes without leaks, hangs, or orphaned processes — **`forge agent --repeat N`** + `tests/test_soak.py` on Linux; live editor soak after M2.

## Phase 4 — Security & safety

- Authenticate the HTTP bridge (shared-token header), bind to `127.0.0.1` by default (**done** Python + C++ auth; `HEPHAESTUS_LOCALHOST_ONLY` env).
- Validate/limit command input server-side (**done** Python validation + C++ `ValidateCommand` for spawn; 413 payload limit).
- Secrets only via environment/secret store — never in source (**ongoing** — config placeholders only).
- Enforce cloud budget guardrails on GPU/cloud path (**existing** `BudgetManager` for NIM).
- Security review before non-localhost exposure (**pending** human review).

Exit: no unauthenticated mutation path; no secret in repo/logs; a security-review pass is clean.

## Phase 5 — Observability

- Structured JSONL logging (`observability.log_format=jsonl`) across runtime (**done** — auto path in `forge agent`).
- Prometheus metrics endpoint (port 9090) for loop/tool/LLM latency (**done** — `MetricsRegistry` + deploy/agent bootstrap).
- Tracing to OTLP endpoint (**stub done** — `TraceRecorder` spans; full export when `opentelemetry-sdk` installed).
- Dashboard: real FPS/GPU from UE (**pending** — agent-measured latency only until M2).

Exit: latency percentiles (p50/95/99) are measurable and meet the config targets — metrics histograms live; UE GPU fields pending.

## Phase 6 — Packaging, docs & release

- UE plugin packaging: distributable `.uplugin` (**pending** M1).
- Python: versioning/changelog; publishable wheel (**partial** — `pyproject.toml` v0.1.0).
- Docs: README, user guide, command/API reference (**done** for Linux path; M1 checklist for Windows).
- CI extensions: `ruff`/`mypy` + `tsc` build (**done** in `.github/workflows/ci.yml`).
- Merge sequencing: dev-environment PR → main, rebase feature PR (**PR #2** open).

Exit: a tagged release; a new user reaches a running agent from the docs alone.

---

## Parallelizable now (no hardware) [now]

- ~~Viewport panel fallback: poll `/frame` and render as `<img>`~~ (**done** — ViewportStream + agent frame relay).
- ~~Python-side tools + tests for the M5 command families~~ (**done** — 27 tools + contract tests).
- ~~Config-driven ports/hosts and bridge token auth~~ (**done**).
- ~~README / user-guide and CI lint/type-check jobs~~ (**done**).
- Remaining: live C++ command handlers (M5), real voice backends (V3), plugin compile (M1).

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

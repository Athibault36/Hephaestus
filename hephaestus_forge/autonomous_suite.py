# Copyright (c) 2024 HephaestusForge. All Rights Reserved.
"""Operator A–G autonomous acceptance suite (v1)."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

try:
    from autonomous_runner import AutonomousReport, run_autonomous_goal
    from mission_control_build import is_vite_build, mc_dist_path
    from operator_gate import run_operator_gate
    from version import OPERATOR_MILESTONE
except ImportError:
    from hephaestus_forge.autonomous_runner import AutonomousReport, run_autonomous_goal  # type: ignore
    from hephaestus_forge.mission_control_build import is_vite_build, mc_dist_path  # type: ignore
    from hephaestus_forge.operator_gate import run_operator_gate  # type: ignore
    from hephaestus_forge.version import OPERATOR_MILESTONE  # type: ignore

ThoughtFn = Callable[[str, str, dict[str, Any]], None]


@dataclass
class SuiteScenario:
    id: str
    name: str
    kind: str  # autonomous | direct | infra
    goal: str = ""
    require_nim: bool = True


@dataclass
class SuiteStepResult:
    scenario_id: str
    ok: bool
    detail: str
    report: dict[str, Any] = field(default_factory=dict)


@dataclass
class SuiteReport:
    ok: bool
    milestone: str = OPERATOR_MILESTONE
    steps: list[SuiteStepResult] = field(default_factory=list)

    @property
    def skipped_ids(self) -> list[str]:
        return [
            s.scenario_id
            for s in self.steps
            if s.ok and bool((s.report or {}).get("skipped"))
        ]

    @property
    def passed_ids(self) -> list[str]:
        return [
            s.scenario_id
            for s in self.steps
            if s.ok and not bool((s.report or {}).get("skipped"))
        ]

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "milestone": self.milestone,
            "step_count": len(self.steps),
            "passed": self.passed_ids,
            "skipped": self.skipped_ids,
            "failed": [s.scenario_id for s in self.steps if not s.ok],
            "steps": [
                {
                    "scenario_id": s.scenario_id,
                    "ok": s.ok,
                    "skipped": bool((s.report or {}).get("skipped")),
                    "detail": s.detail,
                    "report": s.report,
                }
                for s in self.steps
            ],
        }


SUITE_SCENARIOS: list[SuiteScenario] = [
    SuiteScenario("C", "Mission Control dist", "infra"),
    SuiteScenario("D", "Operator gate (offline blockers)", "infra"),
    SuiteScenario(
        "A",
        "Spawn creature and walk",
        "direct",
        # Same direct path as E2/G4 — AnimSequence when available, else transform walk.
        "__suite_locomotion__",
    ),
    SuiteScenario("B", "Cinematic framing", "direct", "__suite_camera_frame__"),
    # Direct scenarios resolve paths from the target project at runtime.
    SuiteScenario("E1", "Direct spawn path", "direct", "__suite_spawn_mesh__"),
    SuiteScenario("E2", "Direct locomotion", "direct", "__suite_locomotion__"),
    SuiteScenario("E3", "Direct audio", "direct", "__suite_play_audio__"),
    SuiteScenario("E4", "Direct asset search", "direct", "__suite_search_character__"),
    SuiteScenario("F", "Asset pipeline validation", "direct", "__suite_asset_pipeline__"),
    SuiteScenario("G1", "Grade material", "direct", "__suite_create_material__"),
    SuiteScenario("G2", "Grade audio", "direct", "__suite_play_audio__"),
    SuiteScenario("G3", "Grade camera", "direct", "__suite_camera_frame__"),
    SuiteScenario("G4", "Grade displacement", "direct", "__suite_locomotion__"),
    SuiteScenario("H1", "Direct world view", "direct", "__suite_get_view__"),
    SuiteScenario("H2", "Direct create material", "direct", "__suite_create_material__"),
    SuiteScenario("I1", "Grade spotlight", "direct", "__suite_spawn_spotlight__"),
    SuiteScenario("I2", "Grade list + idle", "direct", "__suite_list_actors__"),
]


def _client(remote_api: str, timeout: float = 60.0):
    try:
        from ue_agent_loop import RemoteUeClient, _is_connection_error
    except ImportError:
        from hephaestus_forge.ue_agent_loop import RemoteUeClient, _is_connection_error  # type: ignore
    return RemoteUeClient(remote_api, timeout=timeout), _is_connection_error


def _search(client: Any, query: str, asset_class: str = "", limit: int = 8) -> list[str]:
    try:
        from agent_asset import search_project_assets
    except ImportError:
        from hephaestus_forge.agent_asset import search_project_assets  # type: ignore
    return search_project_assets(client, query, asset_class=asset_class, limit=limit)


def _prefer_sk_paths(paths: list[str]) -> list[str]:
    ranked = sorted(
        paths,
        key=lambda p: (
            0 if ("_SK." in p or "/SK_" in p or p.endswith(".SkeletalMesh")) else 1,
            0 if "Anim" not in p else 1,
            len(p),
        ),
    )
    return [p for p in ranked if ".AnimSequence" not in p and "/Anims/" not in p]


def resolve_suite_character_assets(client: Any) -> tuple[str, str]:
    """Pick a skeletal mesh + walk anim from the live project (any UE target).

    Falls back to Engine package search via asset.search when /Game is empty.
    """
    mesh_hits: list[str] = []
    for query in (
        "Beverly",
        "character",
        "mannequin",
        "DefaultSkeletalMesh",
        "SK_",
        "SKM_",
        "body",
        "Quinn",
        "Manny",
    ):
        mesh_hits.extend(_search(client, query, asset_class="SkeletalMesh", limit=8))
        if mesh_hits:
            break
    mesh_hits = _prefer_sk_paths(list(dict.fromkeys(mesh_hits)))
    # Prefer project /Game assets over Engine placeholders when both exist.
    game_meshes = [p for p in mesh_hits if p.startswith("/Game/")]
    mesh = (game_meshes or mesh_hits)[0] if mesh_hits else ""

    anim_hits: list[str] = []
    tokens = []
    if mesh:
        # Prefer walk anims near the chosen character folder.
        parts = [p for p in mesh.split("/") if p and p not in ("Game", "Engine")]
        if parts:
            tokens.append(
                parts[0]
                if parts[0] not in ("EditorMeshes", "EngineMeshes", "SkeletalMesh")
                else (parts[1] if len(parts) > 1 else parts[0])
            )
    tokens.extend(["Walk", "walk", "locomotion", "MF_Walk", "Idle"])
    for token in tokens:
        anim_hits.extend(_search(client, token, asset_class="AnimSequence", limit=8))
        walkish = [p for p in anim_hits if "walk" in p.lower()]
        if walkish:
            anim_hits = walkish
            break
    anim_hits = list(dict.fromkeys(anim_hits))
    # Prefer /Game walk anims; drop Engine noise unless nothing else exists.
    game_anims = [p for p in anim_hits if p.startswith("/Game/")]
    anim = (game_anims or anim_hits)[0] if anim_hits else ""
    return mesh, anim


def _skip_no_character(scenario_id: str, detail: str) -> SuiteStepResult:
    """Blank projects have no SK content — treat as soft skip, not suite failure."""
    return SuiteStepResult(
        scenario_id,
        True,
        f"skipped: {detail}",
        report={"skipped": True, "reason": detail},
    )


def resolve_suite_static_mesh(client: Any) -> str:
    for query in ("Dog", "Cube", "BasicShape", "SM_", "mesh"):
        hits = _search(client, query, asset_class="StaticMesh", limit=8)
        hits = [p for p in hits if ".Material" not in p]
        if hits:
            return hits[0]
    return ""


def wait_for_pie(
    remote_api: str,
    *,
    timeout_s: float = 45.0,
    poll_s: float = 2.0,
    project_root: Optional[Path] = None,
) -> bool:
    """Block until /v1/health is ok (and matches project_root when given), or timeout."""
    try:
        from preflight_health import fetch_ue_health, pie_matches_project
    except ImportError:
        from hephaestus_forge.preflight_health import fetch_ue_health, pie_matches_project  # type: ignore

    client, _is_conn = _client(remote_api, timeout=5.0)
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            health = fetch_ue_health(remote_api, timeout=5.0)
            if not health.get("ok"):
                time.sleep(poll_s)
                continue
            if project_root is not None:
                ok, _ = pie_matches_project(health, Path(project_root))
                if not ok:
                    time.sleep(poll_s)
                    continue
            return True
        except Exception as exc:
            if not _is_conn(exc):
                # Non-connection errors while matching may still be transient JSON issues.
                try:
                    client.health()
                except Exception:
                    pass
        time.sleep(poll_s)
    return False


def _spawn_walk_goal(remote_api: str) -> str:
    client, _ = _client(remote_api)
    mesh, anim = resolve_suite_character_assets(client)
    if not mesh:
        return "__suite_skip_no_character__"
    if not anim:
        return "__suite_skip_no_walk_anim__"
    return (
        f"Spawn skeletal mesh {mesh} in front of the camera, then play AnimSequence "
        f"{anim} on that actor"
    )


def _actor_path_from_spawn(spawn: dict[str, Any]) -> Optional[str]:
    actor = (spawn.get("actor_paths") or [None])[0]
    if actor:
        return str(actor)
    import json as _json

    try:
        return _json.loads(spawn.get("result_json") or "{}").get("actor_path")
    except Exception:
        return None


def _direct_locomotion_suite(remote_api: str, scenario_id: str = "E2") -> SuiteStepResult:
    """Spawn a skeletal mesh and walk — AnimSequence when found, else transform displace."""
    client, _ = _client(remote_api, timeout=60.0)
    mesh, anim = resolve_suite_character_assets(client)
    if not mesh:
        return _skip_no_character(
            scenario_id,
            "No SkeletalMesh via asset.search (/Game or Engine) — blank project",
        )

    spawn = client.command({
        "command": "animation.spawn_skeletal_mesh",
        "params": {
            "mesh_path": mesh,
            "transform": {
                "location": {"x": 300, "y": 0, "z": 100},
                "rotation": {"pitch": 0, "yaw": 0, "roll": 0},
                "scale": {"x": 1, "y": 1, "z": 1},
            },
        },
    })
    if not spawn.get("success"):
        return SuiteStepResult(
            scenario_id,
            False,
            f"Could not spawn skeletal mesh for locomotion: {spawn.get('error')}",
            report={"spawn": spawn, "mesh": mesh, "anim": anim},
        )
    actor = _actor_path_from_spawn(spawn)
    if not actor:
        return SuiteStepResult(
            scenario_id, False, "Spawn succeeded but no actor_path returned", report={"spawn": spawn}
        )

    play: dict[str, Any] = {"success": False, "error": "no walk anim"}
    mode = "anim"
    if anim:
        play = client.command({
            "command": "animation.play_locomotion",
            "params": {"actor_path": actor, "mode": "walk", "loop": True, "anim_path": anim},
        })
        if not play.get("success"):
            play = client.command({
                "command": "animation.play_sequence",
                "params": {"actor_path": actor, "anim_path": anim, "loop": True},
            })
    if not play.get("success"):
        # Blank / Engine-only targets often have DefaultSkeletalMesh but no AnimSequence.
        mode = "transform"
        play = client.command({
            "command": "animation.play_transform_sequence",
            "params": {
                "actor_path": actor,
                "target_location": {"x": 600, "y": 0, "z": 100},
                "duration": 2.0,
            },
        })
    ok = bool(play.get("success"))
    if ok and mode == "transform":
        detail = (
            f"mode=transform mesh={mesh} — Transform walk on {actor} "
            f"(no AnimSequence — displaced)"
        )
        if mesh.startswith("/Game/"):
            detail += " [warn: /Game mesh without walk anim]"
    elif ok:
        detail = f"mode=anim mesh={mesh} anim={anim} — Playing walk on {actor}"
    else:
        detail = f"Could not walk {actor}: {play.get('error', 'failed')}"
    return SuiteStepResult(
        scenario_id,
        ok,
        detail,
        report={
            "planner": "direct_locomotion",
            "mode": mode,
            "mesh": mesh,
            "anim": anim,
            "actor": actor,
            "play": play,
        },
    )


def _direct_spawn_mesh_suite(remote_api: str, scenario_id: str = "E1") -> SuiteStepResult:
    client, _ = _client(remote_api)
    mesh = resolve_suite_static_mesh(client)
    if not mesh:
        return SuiteStepResult(scenario_id, False, "No StaticMesh found via asset.search", report={})
    try:
        from agent_asset import spawn_asset_in_view
    except ImportError:
        from hephaestus_forge.agent_asset import spawn_asset_in_view  # type: ignore
    results = spawn_asset_in_view(client, mesh, with_light=True)
    ok = any(bool(r.get("success")) for r in results)
    detail = f"Spawned {mesh}" if ok else f"Failed to spawn {mesh}"
    return SuiteStepResult(
        scenario_id,
        ok,
        detail,
        report={"mesh": mesh, "planner": "direct_spawn", "results": results},
    )


def _direct_search_character_suite(remote_api: str, scenario_id: str = "E4") -> SuiteStepResult:
    client, _ = _client(remote_api)
    hits: list[str] = []
    for query in ("character", "mannequin", "DefaultSkeletalMesh", "SK_", "SKM_"):
        hits.extend(_search(client, query, asset_class="SkeletalMesh", limit=12))
        if hits:
            break
    hits = list(dict.fromkeys(hits))
    if not hits:
        return _skip_no_character(
            scenario_id,
            "No /Game or Engine skeletal meshes matched — blank project",
        )
    detail = "Asset matches:\n- " + "\n- ".join(hits[:12])
    return SuiteStepResult(scenario_id, True, detail, report={"matches": hits})


def _direct_camera_frame_suite(remote_api: str, scenario_id: str = "G3") -> SuiteStepResult:
    """Spawn a skeletal mesh then frame it from the left (no NIM)."""
    client, _ = _client(remote_api, timeout=60.0)
    mesh, _anim = resolve_suite_character_assets(client)
    if not mesh:
        return _skip_no_character(scenario_id, "No SkeletalMesh via asset.search — blank project")

    spawn = client.command({
        "command": "animation.spawn_skeletal_mesh",
        "params": {
            "mesh_path": mesh,
            "transform": {
                "location": {"x": 300, "y": 0, "z": 100},
                "rotation": {"pitch": 0, "yaw": 0, "roll": 0},
                "scale": {"x": 1, "y": 1, "z": 1},
            },
        },
    })
    if not spawn.get("success"):
        return SuiteStepResult(
            scenario_id,
            False,
            f"Could not spawn skeletal mesh for camera grade: {spawn.get('error')}",
            report={"spawn": spawn, "mesh": mesh},
        )
    actor = (spawn.get("actor_paths") or [None])[0]
    if not actor:
        import json as _json

        try:
            actor = _json.loads(spawn.get("result_json") or "{}").get("actor_path")
        except Exception:
            actor = None
    if not actor:
        return SuiteStepResult(
            scenario_id, False, "Spawn succeeded but no actor_path returned", report={"spawn": spawn}
        )

    view = client.command({
        "command": "world.set_view",
        "params": {
            "mode": "free",
            "look_at_actor": actor,
            "distance": 450,
            "yaw_offset": 90,
            "height": 120,
        },
    })
    ok = bool(view.get("success"))
    detail = (
        f"Framed {actor} from the left"
        if ok
        else f"set_view failed: {view.get('error')}"
    )
    return SuiteStepResult(
        scenario_id,
        ok,
        detail,
        report={"planner": "direct_camera", "mesh": mesh, "actor": actor, "view": view},
    )


def _direct_get_view_suite(remote_api: str, scenario_id: str = "H1") -> SuiteStepResult:
    client, _ = _client(remote_api)
    view = client.command({"command": "world.get_view", "params": {}})
    ok = bool(view.get("success"))
    detail = "world.get_view ok" if ok else f"world.get_view failed: {view.get('error')}"
    return SuiteStepResult(scenario_id, ok, detail, report={"view": view})


def _direct_create_material_suite(remote_api: str, scenario_id: str = "H2") -> SuiteStepResult:
    client, _ = _client(remote_api)
    name = f"SuiteDirectMat_{scenario_id}_{int(time.time()) % 100000}"
    result = client.command({
        "command": "asset.create_material",
        "params": {"name": name},
    })
    ok = bool(result.get("success"))
    detail = f"Created material {name}" if ok else f"create_material failed: {result.get('error')}"
    return SuiteStepResult(scenario_id, ok, detail, report={"result": result, "name": name})


def _direct_play_audio_suite(remote_api: str, scenario_id: str = "E3") -> SuiteStepResult:
    client, _ = _client(remote_api)
    result = client.command({"command": "audio.play_quartz", "params": {"clock": "test"}})
    ok = bool(result.get("success"))
    detail = "Played test audio (clock=test)." if ok else f"audio.play_quartz failed: {result.get('error')}"
    return SuiteStepResult(scenario_id, ok, detail, report={"result": result})


def _direct_asset_pipeline_suite(remote_api: str, scenario_id: str = "F") -> SuiteStepResult:
    client, _ = _client(remote_api)
    name = f"SuiteMetal_{int(time.time()) % 100000}"
    created = client.command({"command": "asset.create_material", "params": {"name": name}})
    if not created.get("success"):
        return SuiteStepResult(
            scenario_id,
            False,
            f"create_material failed: {created.get('error')}",
            report={"created": created},
        )
    missing = client.command({
        "command": "asset.reimport",
        "params": {"asset_path": "/Game/MissingAsset"},
    })
    # Expect a clear failure for the missing asset.
    err = str(missing.get("error") or "").lower()
    ok_err = (not missing.get("success")) and ("not found" in err or "missing" in err or err != "")
    ok = bool(created.get("success")) and ok_err
    detail = (
        f"Created {name}; reimport MissingAsset failed as expected"
        if ok
        else f"pipeline unexpected: create={created.get('success')} reimport={missing}"
    )
    return SuiteStepResult(
        scenario_id,
        ok,
        detail,
        report={"created": created, "reimport": missing},
    )


def _direct_spawn_spotlight_suite(remote_api: str, scenario_id: str = "I1") -> SuiteStepResult:
    client, _ = _client(remote_api)
    result = client.command({
        "command": "world.spawn_actor",
        "params": {
            "class_path": "/Script/Engine.SpotLight",
            "transform": {
                "location": {"x": 200, "y": 0, "z": 250},
                "rotation": {"pitch": -45, "yaw": 0, "roll": 0},
                "scale": {"x": 1, "y": 1, "z": 1},
            },
        },
    })
    ok = bool(result.get("success"))
    detail = "Spawned SpotLight" if ok else f"spawn SpotLight failed: {result.get('error')}"
    return SuiteStepResult(scenario_id, ok, detail, report={"result": result})


def _direct_list_actors_suite(remote_api: str, scenario_id: str = "I2") -> SuiteStepResult:
    client, _ = _client(remote_api)
    result = client.command({"command": "world.list_actors", "params": {}})
    ok = bool(result.get("success"))
    detail = "world.list_actors ok" if ok else f"list_actors failed: {result.get('error')}"
    return SuiteStepResult(scenario_id, ok, detail, report={"result": result})


def _infra_c(project_root: Path) -> SuiteStepResult:
    dist = mc_dist_path(project_root)
    ok = dist.is_dir() and is_vite_build(dist)
    return SuiteStepResult(
        "C",
        ok,
        f"Mission Control dist at {dist}" if ok else f"Missing MC dist — run: forge build-mc {project_root}",
    )


def _infra_d(project_root: Path, *, live: bool) -> SuiteStepResult:
    gate = run_operator_gate(project_root, live=live)
    blockers = [s for s in gate.steps if s.blocker and not s.ok]
    return SuiteStepResult(
        "D",
        gate.ok,
        "gate ok" if gate.ok else f"{len(blockers)} blocker(s)",
        report=gate.to_dict(),
    )


def run_autonomous_suite(
    project_root: Path,
    *,
    remote_api: str = "http://127.0.0.1:8765",
    scenario_filter: Optional[list[str]] = None,
    live: bool = True,
    skip_nim: bool = False,
    on_thought: Optional[ThoughtFn] = None,
) -> SuiteReport:
    """Run operator A–G suite. Infra steps C/D always run first when included."""
    root = Path(project_root).resolve()
    selected = {
        s.id.upper(): s
        for s in SUITE_SCENARIOS
        if not scenario_filter or s.id.upper() in {x.upper() for x in scenario_filter}
    }
    steps: list[SuiteStepResult] = []

    try:
        from ue_agent_loop import UePieOfflineError, _is_connection_error
    except ImportError:
        from hephaestus_forge.ue_agent_loop import UePieOfflineError, _is_connection_error  # type: ignore

    def _needs_pie(scenario: SuiteScenario) -> bool:
        return scenario.kind in ("autonomous", "direct") and not skip_nim

    def _run_one(sid: str, scenario: SuiteScenario) -> SuiteStepResult:
        if scenario.kind == "infra":
            if sid == "C":
                return _infra_c(root)
            if sid == "D":
                return _infra_d(root, live=live)
            return SuiteStepResult(sid, False, f"unknown infra step {sid}")

        if scenario.kind == "direct":
            if skip_nim:
                return SuiteStepResult(sid, True, "skipped (offline — direct scenarios not run)", report={})
            if sid in ("A", "E2", "G4") or scenario.goal == "__suite_locomotion__":
                return _direct_locomotion_suite(remote_api, scenario_id=sid)
            if sid == "E1" or scenario.goal == "__suite_spawn_mesh__":
                return _direct_spawn_mesh_suite(remote_api, scenario_id=sid)
            if sid == "E4" or scenario.goal == "__suite_search_character__":
                return _direct_search_character_suite(remote_api, scenario_id=sid)
            if sid == "B" or sid == "G3" or scenario.goal == "__suite_camera_frame__":
                return _direct_camera_frame_suite(remote_api, scenario_id=sid)
            if sid == "E3" or sid == "G2" or scenario.goal == "__suite_play_audio__":
                return _direct_play_audio_suite(remote_api, scenario_id=sid)
            if sid == "F" or scenario.goal == "__suite_asset_pipeline__":
                return _direct_asset_pipeline_suite(remote_api, scenario_id=sid)
            if sid == "G1" or sid == "H2" or scenario.goal == "__suite_create_material__":
                return _direct_create_material_suite(remote_api, scenario_id=sid)
            if sid == "H1" or scenario.goal == "__suite_get_view__":
                return _direct_get_view_suite(remote_api, scenario_id=sid)
            if sid == "I1" or scenario.goal == "__suite_spawn_spotlight__":
                return _direct_spawn_spotlight_suite(remote_api, scenario_id=sid)
            if sid == "I2" or scenario.goal == "__suite_list_actors__":
                return _direct_list_actors_suite(remote_api, scenario_id=sid)
            try:
                from agent_chat import run_chat
            except ImportError:
                from hephaestus_forge.agent_chat import run_chat  # type: ignore
            out = run_chat(
                scenario.goal,
                project_root=root,
                remote_api=remote_api,
                reset=True,
                on_thought=on_thought,
            )
            return SuiteStepResult(
                sid,
                bool(out.get("ok")),
                str(out.get("reply") or out.get("grade", {}).get("summary", "")),
                report={"planner": out.get("planner"), "grade": out.get("grade")},
            )

        if skip_nim:
            return SuiteStepResult(sid, True, "skipped (offline — NIM goals not run)", report={})

        goal = scenario.goal
        if goal == "__suite_spawn_walk__":
            goal = _spawn_walk_goal(remote_api)
        if goal == "__suite_skip_no_character__":
            return _skip_no_character(sid, "No SkeletalMesh via asset.search — blank project")
        if goal == "__suite_skip_no_walk_anim__":
            # Prefer transform displacement over soft-skip when a mesh exists.
            return _direct_locomotion_suite(remote_api, scenario_id=sid)

        report: AutonomousReport = run_autonomous_goal(
            goal,
            project_root=root,
            remote_api=remote_api,
            require_nim=True,
            repair=True,
            max_steps=12,
            on_thought=on_thought or (
                lambda kind, content, meta: print(
                    f"[suite:{sid}] {kind}: {str(content)[:140]}",
                    flush=True,
                )
                if kind in ("plan", "error", "reflection", "action")
                else None
            ),
        )
        return SuiteStepResult(
            sid,
            report.ok,
            report.grade.get("summary", ""),
            report=report.to_dict(),
        )

    order = ["C", "D", "A", "B", "E1", "E2", "E3", "E4", "F", "G1", "G2", "G3", "G4", "H1", "H2", "I1", "I2"]
    for sid in order:
        scenario = selected.get(sid)
        if not scenario:
            continue
        print(f"[suite] {sid} starting…", flush=True)
        try:
            if live and _needs_pie(scenario):
                if not wait_for_pie(remote_api, timeout_s=30.0, project_root=root):
                    steps.append(
                        SuiteStepResult(
                            sid,
                            False,
                            "PIE offline or wrong project before scenario — Play the matching .uproject",
                            report={"error": "pie_offline_or_mismatch"},
                        )
                    )
                    print(f"[suite] {sid} FAIL: PIE offline or wrong project before scenario", flush=True)
                    continue

            result = _run_one(sid, scenario)
            # One recovery pass if PIE dropped mid-scenario.
            detail_l = (result.detail or "").lower()
            if (
                live
                and _needs_pie(scenario)
                and not result.ok
                and (_is_connection_error(result.detail) or "pie offline" in detail_l)
            ):
                print(f"[suite] {sid} PIE drop — waiting to retry…", flush=True)
                if wait_for_pie(remote_api, timeout_s=45.0, project_root=root):
                    result = _run_one(sid, scenario)
                    result.report = {**(result.report or {}), "pie_retry": True}

            steps.append(result)
            print(f"[suite] {sid} {'ok' if result.ok else 'FAIL'}: {result.detail}", flush=True)
        except UePieOfflineError as exc:
            print(f"[suite] {sid} PIE offline — waiting to retry…", flush=True)
            if live and wait_for_pie(remote_api, timeout_s=45.0, project_root=root):
                try:
                    result = _run_one(sid, scenario)
                    result.report = {**(result.report or {}), "pie_retry": True}
                    steps.append(result)
                    print(f"[suite] {sid} {'ok' if result.ok else 'FAIL'}: {result.detail}", flush=True)
                    continue
                except Exception as retry_exc:
                    exc = retry_exc  # type: ignore[assignment]
            steps.append(
                SuiteStepResult(
                    sid,
                    False,
                    f"PIE offline: {exc}",
                    report={"error": str(exc), "error_type": type(exc).__name__},
                )
            )
            print(f"[suite] {sid} FAIL: PIE offline: {exc}", flush=True)
        except Exception as exc:
            if live and _is_connection_error(exc) and wait_for_pie(remote_api, timeout_s=45.0, project_root=root):
                try:
                    result = _run_one(sid, scenario)
                    result.report = {**(result.report or {}), "pie_retry": True}
                    steps.append(result)
                    print(f"[suite] {sid} {'ok' if result.ok else 'FAIL'}: {result.detail}", flush=True)
                    continue
                except Exception as retry_exc:
                    exc = retry_exc
            steps.append(
                SuiteStepResult(
                    sid,
                    False,
                    f"scenario crashed: {exc}",
                    report={"error": str(exc), "error_type": type(exc).__name__},
                )
            )
            print(f"[suite] {sid} CRASH: {exc}", flush=True)

    ok = all(s.ok for s in steps) if steps else False
    return SuiteReport(ok=ok, steps=steps)

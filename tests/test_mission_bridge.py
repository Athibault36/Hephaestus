from hephaestus_forge.runtime.mission_bridge import MissionBridge
from hephaestus_forge.runtime.orchestrator import TrajectoryEvent


class FakeSio:
    def __init__(self):
        self.emitted = []

    def emit(self, event, data):
        self.emitted.append((event, data))


def test_thought_and_state_mapping():
    sio = FakeSio()
    bridge = MissionBridge(server=sio)
    bridge.on_agent_event(TrajectoryEvent("thought", "planning the build"))

    events = dict((e, d) for e, d in sio.emitted)
    assert "thought" in events and "agentState" in events
    assert events["thought"]["type"] == "plan"  # 'thought' -> dashboard 'plan'
    assert events["thought"]["content"] == "planning the build"
    assert events["agentState"] == "thinking"


def test_action_and_error_states():
    sio = FakeSio()
    bridge = MissionBridge(server=sio)
    bridge.on_agent_event(TrajectoryEvent("action", "world.spawn_actor(...)", {"tool": "world.spawn_actor"}))
    bridge.on_agent_event(TrajectoryEvent("error", "boom", {"error": "bad"}))
    states = [d for e, d in sio.emitted if e == "agentState"]
    assert "acting" in states and "error" in states


def test_metrics_emitted_with_real_tool_latency():
    sio = FakeSio()
    bridge = MissionBridge(server=sio)
    bridge.on_agent_event(TrajectoryEvent("tool_result", "ok", {"execution_time_ms": 12.5}))
    bridge.on_agent_event(TrajectoryEvent("tool_result", "ok", {"execution_time_ms": 7.5}))
    metrics = [d for e, d in sio.emitted if e == "metrics"]
    assert len(metrics) == 2
    last = metrics[-1]
    assert last["latency"]["tool"] == 7.5      # most recent tool time
    assert last["latency"]["total"] == 20.0    # accumulated
    assert last["drawCalls"] == 2              # tool-call count
    # Unmeasured fields are honestly zero, not fabricated.
    assert last["fps"] == 0 and last["gpuTime"] == 0.0


def test_emit_frame_sends_png_data_url():
    sio = FakeSio()
    bridge = MissionBridge(server=sio)
    png = b"\x89PNG\r\n\x1a\n fake-bytes"
    bridge.emit_frame(png, width=1920, height=1080)
    frames = [d for e, d in sio.emitted if e == "frame"]
    assert len(frames) == 1
    assert frames[0]["dataUrl"].startswith("data:image/png;base64,")
    assert frames[0]["width"] == 1920 and frames[0]["height"] == 1080


def test_emit_frame_ignores_empty():
    sio = FakeSio()
    bridge = MissionBridge(server=sio)
    bridge.emit_frame(b"")
    assert not [e for e, _ in sio.emitted if e == "frame"]


def test_emit_voice_active_and_speaker():
    sio = FakeSio()
    bridge = MissionBridge(server=sio)
    bridge.emit_voice_active(True)
    bridge.emit_speaker(True)
    bridge.emit_speaker(False)
    bridge.emit_speaker(None)
    assert ("voiceActive", True) in sio.emitted
    speaker_payloads = [d for e, d in sio.emitted if e == "speaker"]
    assert speaker_payloads[0] == {"recognized": True}
    assert speaker_payloads[1] == {"recognized": False}
    assert speaker_payloads[2] is None


def test_actors_accumulate_and_emit_full_list():
    sio = FakeSio()
    bridge = MissionBridge(server=sio)
    bridge.on_agent_event(TrajectoryEvent("tool_result", "ok", {"actors": ["/Game/L.L:PersistentLevel.Cube_1"]}))
    bridge.on_agent_event(TrajectoryEvent("tool_result", "ok", {"actors": ["/Game/L.L:PersistentLevel.Cube_2"]}))
    actor_emits = [d for e, d in sio.emitted if e == "actors"]
    assert actor_emits  # emitted at least once
    last = actor_emits[-1]
    assert len(last) == 2
    assert last[0]["name"] == "Cube_1" and last[1]["name"] == "Cube_2"
    assert last[0]["location"] == [0, 0, 0]

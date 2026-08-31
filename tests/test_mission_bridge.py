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

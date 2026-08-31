from hephaestus_forge.runtime.llm import extract_tool_calls_from_text


def test_extract_simple_tool_directive():
    calls = extract_tool_calls_from_text('{"tool": "world.spawn_actor", "args": {"class_path": "X"}}')
    assert len(calls) == 1
    assert calls[0].name == "world.spawn_actor"
    assert calls[0].arguments == {"class_path": "X"}


def test_extract_react_style():
    text = 'Thought: I should look.\n{"action": "vision.capture_frame", "action_input": {}}'
    calls = extract_tool_calls_from_text(text)
    assert len(calls) == 1 and calls[0].name == "vision.capture_frame"


def test_extract_array_of_calls():
    text = '[{"tool": "a", "args": {}}, {"name": "b", "arguments": {"x": 1}}]'
    calls = extract_tool_calls_from_text(text)
    assert [c.name for c in calls] == ["a", "b"]
    assert calls[1].arguments == {"x": 1}


def test_extract_json_embedded_in_prose():
    text = 'Sure, I will run {"tool": "world.spawn_actor", "args": {"class_path": "Y"}} for you.'
    calls = extract_tool_calls_from_text(text)
    assert len(calls) == 1 and calls[0].arguments["class_path"] == "Y"


def test_plain_text_yields_no_calls():
    assert extract_tool_calls_from_text("All done, the scene looks great.") == []


def test_final_directive_is_not_a_tool_call():
    assert extract_tool_calls_from_text('{"final": "goal complete"}') == []

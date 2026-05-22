from opencode_backend.protocols import (
    a2a_task_to_ag_ui_events,
    build_a2a_task,
    parse_opencode_json_output,
)
from opencode_backend.schemas import ProvisionResponse, Scope, WrittenFile


def test_parse_opencode_json_output_extracts_assistant_text() -> None:
    stdout = (
        '{"type":"message","role":"assistant","content":"created calculator.html"}\n'
        '{"type":"tool","name":"write","path":"calculator.html"}\n'
    )

    text, events = parse_opencode_json_output(stdout)

    assert text == "created calculator.html"
    assert len(events) == 2


def test_parse_opencode_json_output_extracts_opencode_part_text() -> None:
    stdout = (
        '{"type":"text","part":{"type":"text","text":"pong"}}\n'
        '{"type":"step_finish","part":{"type":"step-finish"}}\n'
    )

    text, events = parse_opencode_json_output(stdout)

    assert text == "pong"
    assert len(events) == 2


def test_build_a2a_task_wraps_opencode_result() -> None:
    response = ProvisionResponse(
        sandbox_id="sandbox-1",
        scope=Scope.project,
        config_root="/home/user/workspace",
        files_written=[WrittenFile(path="/home/user/workspace/opencode.json", bytes=10)],
        launch_command=["opencode", "run"],
        stdout='{"type":"message","role":"assistant","content":"done"}\n',
    )

    task, events = build_a2a_task(response=response, query="build calculator", task_id="task-1")

    assert task["id"] == "task-1"
    assert task["status"]["state"] == "completed"
    assert task["history"][0]["role"] == "user"
    assert task["history"][0]["parts"][0]["kind"] == "text"
    assert task["artifacts"][0]["parts"][0]["text"] == "done"
    assert events[-1]["statusUpdate"]["status"]["state"] == "completed"


def test_a2a_task_to_ag_ui_events_emits_text_message() -> None:
    response = ProvisionResponse(
        sandbox_id="sandbox-1",
        scope=Scope.project,
        config_root="/home/user/workspace",
        files_written=[],
        launch_command=["opencode", "run"],
        stdout='{"type":"message","role":"assistant","content":"done"}\n',
    )
    task, _ = build_a2a_task(response=response, query="build calculator", task_id="task-1")

    events = a2a_task_to_ag_ui_events(task)

    assert events[0]["type"] == "RUN_STARTED"
    assert any(event["type"] == "TEXT_MESSAGE_CONTENT" and event["delta"] == "done" for event in events)
    assert events[-1]["type"] == "RUN_FINISHED"

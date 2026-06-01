from __future__ import annotations

import json
from pathlib import Path

from engine.config import Settings
from engine.models import CreateRuntimeSessionRequest, CreateSessionRequest, GenerateRequest, RuntimeQueryRequest, SessionStatus
from engine.sandbox import CommandResult
from engine.service import AgentEngineService


class FakeSandbox:
    def __init__(self, sandbox_id: str):
        self.sandbox_id = sandbox_id
        self.files: dict[str, str] = {}
        self.commands: list[tuple[str, str | None]] = []
        self.closed = False

    def write_text(self, path: str, content: str) -> None:
        self.files[path] = content

    def run(self, command: str, cwd: str | None = None, timeout_ms: int | None = None, env: dict[str, str] | None = None) -> CommandResult:
        self.commands.append((command, cwd))
        if command.startswith("mkdir"):
            return CommandResult(exit_code=0)
        if "tar -C" in command and "base64 -w0" in command:
            return CommandResult(exit_code=0, stdout="ARCHIVE")
        if "base64 -d" in command:
            return CommandResult(exit_code=0)
        if "print(next(" in command:
            return CommandResult(exit_code=0, stdout="runtime-agent\n")
        if command.startswith("opencode run --agent runtime-agent"):
            return CommandResult(exit_code=0, stdout="runtime query complete")
        if command.startswith("test -f swarm.yaml"):
            return CommandResult(exit_code=0)
        return CommandResult(
            exit_code=0,
            stdout="Generated package: /home/user/template/.engine-sessions/session/generated/test-team\nvalidation passed",
        )

    def close(self) -> None:
        self.closed = True


class FakeFactory:
    def __init__(self):
        self.created: list[FakeSandbox] = []

    def create(self, env: dict[str, str]) -> FakeSandbox:
        sandbox = FakeSandbox(f"sbx-{len(self.created) + 1}")
        self.created.append(sandbox)
        return sandbox

    def connect(self, sandbox_id: str, env: dict[str, str]) -> FakeSandbox:
        for sandbox in self.created:
            if sandbox.sandbox_id == sandbox_id:
                return sandbox
        raise KeyError(sandbox_id)


def settings() -> Settings:
    return Settings(e2b_api_key="test-e2b", deepseek_api_key="test-deepseek")


def test_create_session_copies_template_plugins_and_status() -> None:
    factory = FakeFactory()
    service = AgentEngineService(settings(), factory)

    response = service.create_session(CreateSessionRequest(user_id="user-1"))

    sandbox = factory.created[0]
    assert response.status == SessionStatus.READY
    assert response.sandbox_id == "sbx-1"
    assert "/home/user/template/opencode.json" in sandbox.files
    assert "/home/user/template/.opencode/plugins/proxy-hooks.ts" in sandbox.files
    assert response.state_path in sandbox.files
    status = json.loads(sandbox.files[response.state_path])
    assert status["user_id"] == "user-1"
    assert status["sandbox_id"] == "sbx-1"


def test_generate_reuses_session_sandbox_and_writes_query_result() -> None:
    factory = FakeFactory()
    service = AgentEngineService(settings(), factory)
    created = service.create_session(CreateSessionRequest(user_id="user-1"))

    response = service.generate(created.session_id, GenerateRequest(user_id="user-1", query="make a qa team", output_slug="qa-team"))

    sandbox = factory.created[0]
    assert response.status == SessionStatus.VALIDATED
    assert response.generated_package_path == f"/home/user/template/.engine-sessions/{created.session_id}/generated/qa-team"
    assert sandbox.files[f"/home/user/template/.engine-sessions/{created.session_id}/state/last-query.txt"] == "make a qa team"
    assert any(command.startswith("opencode run") for command, _ in sandbox.commands)


def test_generate_allows_custom_relative_output_root() -> None:
    factory = FakeFactory()
    service = AgentEngineService(settings(), factory)
    created = service.create_session(CreateSessionRequest(user_id="user-1"))

    response = service.generate(
        created.session_id,
        GenerateRequest(user_id="user-1", query="make a qa team", output_root="exports", output_slug="qa-team"),
    )

    assert response.generated_package_path == "/home/user/template/exports/qa-team"


def test_runtime_session_imports_generated_package_and_runs_query() -> None:
    factory = FakeFactory()
    service = AgentEngineService(settings(), factory)
    created = service.create_session(CreateSessionRequest(user_id="user-1"))
    generated = service.generate(
        created.session_id,
        GenerateRequest(user_id="user-1", query="make a qa team", output_root="exports", output_slug="qa-team"),
    )

    runtime = service.create_runtime_session(
        CreateRuntimeSessionRequest(user_id="user-1", source_session_id=created.session_id)
    )

    assert runtime.status == SessionStatus.READY
    assert runtime.source_package_path == generated.generated_package_path
    assert runtime.runtime_package_path.endswith(f"/.runtime-sessions/{runtime.runtime_session_id}/package")
    assert runtime.data["primary_agent"] == "runtime-agent"
    assert len(factory.created) == 2
    source_sandbox = factory.created[0]
    runtime_sandbox = factory.created[1]
    assert any("tar -C /home/user/template/exports/qa-team" in command for command, _ in source_sandbox.commands)
    assert runtime_sandbox.files[runtime.state_path].count('"status": "ready"') == 1
    assert runtime_sandbox.files[f"{runtime.runtime_package_path}/.opencode/plugins/proxy-hooks.ts"]

    result = service.runtime_query(
        runtime.runtime_session_id,
        RuntimeQueryRequest(user_id="user-1", query="answer with the imported team"),
    )

    assert result.status == SessionStatus.VALIDATED
    assert result.data["agent"] == "runtime-agent"
    assert result.data["last_stdout"] == "runtime query complete"
    assert any(command.startswith("opencode run --agent runtime-agent") for command, _ in runtime_sandbox.commands)


def test_templates_can_be_listed_and_used_for_runtime_session() -> None:
    factory = FakeFactory()
    service = AgentEngineService(settings(), factory)
    created = service.create_session(CreateSessionRequest(user_id="user-1"))
    generated = service.generate(
        created.session_id,
        GenerateRequest(user_id="user-1", query="make a qa team", output_root="exports", output_slug="qa-team"),
    )

    template_id = generated.data["template_id"]
    templates = service.list_templates("user-1")

    assert len(templates) == 1
    assert templates[0].template_id == template_id
    assert templates[0].package_path == "/home/user/template/exports/qa-team"
    assert templates[0].output_slug == "qa-team"
    assert f"/home/user/template/.engine-sessions/{created.session_id}/state/template-{template_id}.json" in factory.created[0].files

    runtime = service.create_runtime_session(CreateRuntimeSessionRequest(user_id="user-1", template_id=template_id))

    assert runtime.status == SessionStatus.READY
    assert runtime.source_session_id == created.session_id
    assert runtime.source_package_path == templates[0].package_path


def test_runtime_session_requires_generated_package() -> None:
    service = AgentEngineService(settings(), FakeFactory())
    created = service.create_session(CreateSessionRequest(user_id="user-1"))

    try:
        service.create_runtime_session(CreateRuntimeSessionRequest(user_id="user-1", source_session_id=created.session_id))
    except ValueError as exc:
        assert "generated_package_path" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_generate_rejects_external_output_root() -> None:
    service = AgentEngineService(settings(), FakeFactory())
    created = service.create_session(CreateSessionRequest(user_id="user-1"))

    try:
        service.generate(
            created.session_id,
            GenerateRequest(user_id="user-1", query="make a qa team", output_root="/tmp/exports", output_slug="qa-team"),
        )
    except ValueError as exc:
        assert "inside /home/user/template" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_session_paths_are_isolated_for_multiple_users() -> None:
    factory = FakeFactory()
    service = AgentEngineService(settings(), factory)
    one = service.create_session(CreateSessionRequest(user_id="user-1"))
    two = service.create_session(CreateSessionRequest(user_id="user-2"))

    assert one.session_id != two.session_id
    assert one.sandbox_id != two.sandbox_id
    assert f"/home/user/template/.engine-sessions/{one.session_id}" in one.state_path
    assert f"/home/user/template/.engine-sessions/{two.session_id}" in two.state_path


def test_wrong_user_cannot_read_session() -> None:
    service = AgentEngineService(settings(), FakeFactory())
    created = service.create_session(CreateSessionRequest(user_id="user-1"))

    try:
        service.status(created.session_id, "user-2")
    except PermissionError as exc:
        assert "does not own" in str(exc)
    else:
        raise AssertionError("expected PermissionError")


def test_plugin_config_is_merged() -> None:
    factory = FakeFactory()
    service = AgentEngineService(settings(), factory)
    response = service.create_session(CreateSessionRequest(user_id="user-1"))
    sandbox = factory.created[0]
    config = json.loads(sandbox.files["/home/user/template/opencode.json"])

    assert "./.opencode/plugins/session-export.ts" in config["plugin"]
    assert "./.opencode/plugins/session-import.ts" in config["plugin"]
    assert "./.opencode/plugins/proxy-hooks.ts" in config["plugin"]

from __future__ import annotations

from fastapi.testclient import TestClient

from engine.app import create_app
from engine.config import Settings
from engine.sandbox import CommandResult
from engine.service import AgentEngineService


class FakeSandbox:
    def __init__(self, sandbox_id: str):
        self.sandbox_id = sandbox_id
        self.files: dict[str, str] = {}
        self.commands: list[str] = []

    def write_text(self, path: str, content: str) -> None:
        self.files[path] = content

    def run(self, command: str, cwd: str | None = None, timeout_ms: int | None = None, env: dict[str, str] | None = None) -> CommandResult:
        self.commands.append(command)
        if command.startswith("mkdir"):
            return CommandResult(exit_code=0)
        if "tar -C" in command and "base64 -w0" in command:
            return CommandResult(exit_code=0, stdout="ARCHIVE")
        if "base64 -d" in command:
            return CommandResult(exit_code=0)
        if "print(next(" in command:
            return CommandResult(exit_code=0, stdout="api-runtime-agent\n")
        if command.startswith("test -f swarm.yaml"):
            return CommandResult(exit_code=0)
        if command.startswith("opencode run --agent api-runtime-agent"):
            return CommandResult(exit_code=0, stdout="api runtime complete")
        return CommandResult(exit_code=0, stdout="Generated package: /home/user/template/.engine-sessions/x/generated/api-team")

    def close(self) -> None:
        return None


class FakeFactory:
    def __init__(self):
        self.sandbox = FakeSandbox("sbx-api")

    def create(self, env: dict[str, str]) -> FakeSandbox:
        return self.sandbox

    def connect(self, sandbox_id: str, env: dict[str, str]) -> FakeSandbox:
        return self.sandbox


def client() -> TestClient:
    settings = Settings(e2b_api_key="test-e2b", deepseek_api_key="test-deepseek")
    service = AgentEngineService(settings, FakeFactory())
    return TestClient(create_app(service))


def test_health_endpoint() -> None:
    response = client().get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_generate_status_flow() -> None:
    api = client()

    created = api.post("/v1/sessions", json={"user_id": "user-1"})
    assert created.status_code == 200
    session_id = created.json()["session_id"]

    generated = api.post(
        f"/v1/sessions/{session_id}/generate",
        json={"user_id": "user-1", "query": "create api team", "output_slug": "api-team"},
    )
    assert generated.status_code == 200
    assert generated.json()["status"] == "validated"
    assert generated.json()["generated_package_path"].endswith("/generated/api-team")

    status = api.get(f"/v1/sessions/{session_id}/status", params={"user_id": "user-1"})
    assert status.status_code == 200
    assert status.json()["status"] == "validated"


def test_wrong_user_gets_403() -> None:
    api = client()
    created = api.post("/v1/sessions", json={"user_id": "user-1"})
    session_id = created.json()["session_id"]

    response = api.get(f"/v1/sessions/{session_id}/status", params={"user_id": "user-2"})

    assert response.status_code == 403


def test_external_output_root_gets_400() -> None:
    api = client()
    created = api.post("/v1/sessions", json={"user_id": "user-1"})
    session_id = created.json()["session_id"]

    response = api.post(
        f"/v1/sessions/{session_id}/generate",
        json={"user_id": "user-1", "query": "create api team", "output_root": "/tmp/out"},
    )

    assert response.status_code == 400


def test_runtime_session_api_flow() -> None:
    api = client()

    created = api.post("/v1/sessions", json={"user_id": "user-1"})
    session_id = created.json()["session_id"]
    generated = api.post(
        f"/v1/sessions/{session_id}/generate",
        json={"user_id": "user-1", "query": "create api team", "output_root": "exports", "output_slug": "api-team"},
    )
    assert generated.status_code == 200

    runtime = api.post("/v1/runtime-sessions", json={"user_id": "user-1", "source_session_id": session_id})
    assert runtime.status_code == 200
    assert runtime.json()["status"] == "ready"
    runtime_session_id = runtime.json()["runtime_session_id"]

    result = api.post(
        f"/v1/runtime-sessions/{runtime_session_id}/query",
        json={"user_id": "user-1", "query": "run the generated team"},
    )
    assert result.status_code == 200
    assert result.json()["status"] == "validated"
    assert result.json()["data"]["primary_agent"] == "api-runtime-agent"

    status = api.get(f"/v1/runtime-sessions/{runtime_session_id}/status", params={"user_id": "user-1"})
    assert status.status_code == 200
    assert status.json()["runtime_session_id"] == runtime_session_id


def test_template_list_and_runtime_from_template_api_flow() -> None:
    api = client()

    created = api.post("/v1/sessions", json={"user_id": "user-1"})
    session_id = created.json()["session_id"]
    generated = api.post(
        f"/v1/sessions/{session_id}/generate",
        json={"user_id": "user-1", "query": "create api team", "output_root": "exports", "output_slug": "api-team"},
    )
    template_id = generated.json()["data"]["template_id"]

    templates = api.get("/v1/templates", params={"user_id": "user-1"})
    assert templates.status_code == 200
    assert templates.json()[0]["template_id"] == template_id
    assert templates.json()[0]["package_path"] == "/home/user/template/exports/api-team"

    detail = api.get(f"/v1/templates/{template_id}", params={"user_id": "user-1"})
    assert detail.status_code == 200
    assert detail.json()["output_slug"] == "api-team"

    runtime = api.post("/v1/runtime-sessions", json={"user_id": "user-1", "template_id": template_id})
    assert runtime.status_code == 200
    assert runtime.json()["source_package_path"] == "/home/user/template/exports/api-team"

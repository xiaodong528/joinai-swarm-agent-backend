from fastapi.testclient import TestClient

from opencode_backend.app import create_app, get_provisioner
from opencode_backend.sandbox import LocalSandboxSession
from opencode_backend.service import OpenCodeProvisioner


def test_api_provision(monkeypatch) -> None:
    app = create_app()

    def override() -> OpenCodeProvisioner:
        session = LocalSandboxSession()
        return OpenCodeProvisioner(session)

    app.dependency_overrides.clear()
    app.dependency_overrides[get_provisioner] = override

    client = TestClient(app)
    response = client.post(
        "/v1/opencode/provision",
        json={
            "scope": "project",
            "workspace_path": "/tmp/workspace",
            "config": {},
            "skills": [],
            "agents": [],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["sandbox_id"]
    assert body["config_root"] == "/tmp/workspace"


def test_api_a2a_run(monkeypatch) -> None:
    app = create_app()

    def override() -> OpenCodeProvisioner:
        session = LocalSandboxSession()
        return OpenCodeProvisioner(session)

    app.dependency_overrides.clear()
    app.dependency_overrides[get_provisioner] = override

    client = TestClient(app)
    response = client.post(
        "/v1/opencode/a2a/run",
        json={
            "scope": "project",
            "workspace_path": "/tmp/workspace",
            "provider": {
                "base_url": "https://api.deepseek.com",
                "api_key": "sk-test",
                "model_name": "deepseek-v4-pro",
            },
            "query": "build calculator",
            "task_id": "task-1",
            "context_id": "ctx-1",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["task"]["id"] == "task-1"
    assert body["task"]["status"]["state"] == "completed"
    assert body["events"][-1]["statusUpdate"]["status"]["state"] == "completed"


def test_api_rpc_message_send_returns_a2a_task(monkeypatch) -> None:
    app = create_app()

    def override() -> OpenCodeProvisioner:
        session = LocalSandboxSession()
        return OpenCodeProvisioner(session)

    app.dependency_overrides.clear()
    app.dependency_overrides[get_provisioner] = override

    client = TestClient(app)
    response = client.post(
        "/rpc",
        json={
            "jsonrpc": "2.0",
            "id": "req-1",
            "method": "message/send",
            "params": {
                "message": {
                    "messageId": "msg-1",
                    "role": "user",
                    "taskId": "task-1",
                    "contextId": "ctx-1",
                    "parts": [{"text": "build calculator"}],
                },
                "opencode": {
                    "scope": "project",
                    "workspace_path": "/tmp/workspace",
                    "provider": {
                        "base_url": "https://api.deepseek.com",
                        "api_key": "sk-test",
                        "model_name": "deepseek-v4-pro",
                    },
                },
            },
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == "req-1"
    assert body["error"] is None
    assert body["result"]["id"] == "task-1"
    assert body["result"]["history"][0]["messageId"] == "msg-1"


def test_api_ag_ui_run_wraps_a2a_task(monkeypatch) -> None:
    app = create_app()

    def override() -> OpenCodeProvisioner:
        session = LocalSandboxSession()
        return OpenCodeProvisioner(session)

    app.dependency_overrides.clear()
    app.dependency_overrides[get_provisioner] = override

    client = TestClient(app)
    response = client.post(
        "/v1/opencode/ag-ui/run",
        json={
            "scope": "project",
            "workspace_path": "/tmp/workspace",
            "provider": {
                "base_url": "https://api.deepseek.com",
                "api_key": "sk-test",
                "model_name": "deepseek-v4-pro",
            },
            "query": "build calculator",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["a2a_task"]["status"]["state"] == "completed"
    assert body["events"][0]["type"] == "RUN_STARTED"
    assert body["events"][-1]["type"] == "RUN_FINISHED"


def test_api_provision_can_enable_a2a_runtime(monkeypatch) -> None:
    app = create_app()

    def override() -> OpenCodeProvisioner:
        session = LocalSandboxSession()
        return OpenCodeProvisioner(session)

    app.dependency_overrides.clear()
    app.dependency_overrides[get_provisioner] = override

    client = TestClient(app)
    response = client.post(
        "/v1/opencode/provision",
        json={
            "scope": "project",
            "workspace_path": "/tmp/workspace",
            "a2a": {
                "enabled": True,
                "opencode_base_url": "https://api.deepseek.com",
            },
            "provider": {
                "base_url": "https://api.deepseek.com",
                "api_key": "sk-test",
                "model_name": "deepseek-v4-pro",
            },
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["a2a_command"][0] == "opencode-a2a"
    assert body["a2a_pid"] is not None

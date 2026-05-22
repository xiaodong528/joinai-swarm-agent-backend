from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient

from opencode_backend.app import create_app, get_chat_service
from opencode_backend.chat import ChatSessionService, SandboxManager
from opencode_backend.crypto import SecretBox
from opencode_backend.sandbox import LocalSandboxSession
from opencode_backend.schemas import ChatSessionCreateRequest
from opencode_backend.store import ChatStore


def make_client(tmp_path: Path, *, run_inline: bool = True) -> tuple[TestClient, ChatSessionService]:
    service = make_service(tmp_path, run_inline=run_inline)
    app = create_app()
    app.dependency_overrides[get_chat_service] = lambda: service
    return TestClient(app), service


def make_service(
    tmp_path: Path,
    *,
    db_name: str = "chat.db",
    run_inline: bool = True,
) -> ChatSessionService:
    store = ChatStore(str(tmp_path / db_name))
    sandbox_manager = SandboxManager(
        store,
        session_factory=lambda: LocalSandboxSession(root=str(tmp_path / "sandboxes")),
        ttl_seconds=3600,
    )
    return ChatSessionService(
        store=store,
        sandbox_manager=sandbox_manager,
        secret_box=SecretBox("test-secret"),
        run_inline=run_inline,
    )


def auth(user: str = "user-a") -> dict[str, str]:
    return {"Authorization": f"Bearer {user}"}


def session_payload() -> dict:
    return {
        "title": "Calculator",
        "scope": "project",
        "workspace_path": "/workspace",
        "provider": {
            "base_url": "https://api.deepseek.com",
            "api_key": "sk-secret",
            "model_name": "deepseek-v4-pro",
        },
    }


def test_chat_session_create_list_and_restore_are_user_scoped(tmp_path: Path) -> None:
    client, _ = make_client(tmp_path)

    created = client.post("/v1/chat/sessions", json=session_payload(), headers=auth()).json()
    assert created["title"] == "Calculator"
    assert created["provider"]["model_name"] == "deepseek-v4-pro"
    assert "api_key" not in created["provider"]

    listed = client.get("/v1/chat/sessions", headers=auth()).json()
    assert [item["id"] for item in listed] == [created["id"]]

    other_user = client.get(f"/v1/chat/sessions/{created['id']}", headers=auth("user-b"))
    assert other_user.status_code == 404


def test_chat_run_persists_messages_and_reuses_sandbox(tmp_path: Path) -> None:
    client, _ = make_client(tmp_path)
    session = client.post("/v1/chat/sessions", json=session_payload(), headers=auth()).json()

    first = client.post(
        f"/v1/chat/sessions/{session['id']}/runs",
        json={"message": "build calculator"},
        headers=auth(),
    ).json()
    assert first["status"] == "completed", first
    assert first["a2a_task"]["status"]["state"] == "completed"

    restored = client.get(f"/v1/chat/sessions/{session['id']}", headers=auth()).json()
    assert [message["role"] for message in restored["messages"]] == ["user", "assistant"]
    first_sandbox = restored["sandbox"]["sandbox_id"]

    second = client.post(
        f"/v1/chat/sessions/{session['id']}/runs",
        json={"message": "add tests"},
        headers=auth(),
    ).json()
    assert second["status"] == "completed"

    restored_again = client.get(f"/v1/chat/sessions/{session['id']}", headers=auth()).json()
    assert restored_again["sandbox"]["sandbox_id"] == first_sandbox
    assert len(restored_again["messages"]) == 4


def test_chat_provider_key_is_encrypted_at_rest(tmp_path: Path) -> None:
    client, service = make_client(tmp_path)
    session = client.post("/v1/chat/sessions", json=session_payload(), headers=auth()).json()

    row = service.store.get_session("user-a", session["id"])
    assert row.provider_json is not None
    assert row.provider_json["api_key"] != "sk-secret"
    assert "sk-secret" not in str(row.provider_json)


def test_chat_rejects_second_active_run(tmp_path: Path) -> None:
    client, service = make_client(tmp_path, run_inline=False)
    session = client.post("/v1/chat/sessions", json=session_payload(), headers=auth()).json()

    service.store.add_message(session["id"], "user", "still running")
    service.store.create_run(session["id"], service.store.list_messages(session["id"])[0].id)

    response = client.post(
        f"/v1/chat/sessions/{session['id']}/runs",
        json={"message": "new message"},
        headers=auth(),
    )

    assert response.status_code == 409


def test_three_parallel_chat_sessions_with_distinct_context_and_restore(tmp_path: Path) -> None:
    db_name = "multi-chat.db"
    service = make_service(tmp_path, db_name=db_name)
    owner_id = "parallel-user"
    scenarios = [
        {
            "title": "math-session",
            "workspace_path": "/workspace/math",
            "skills": [
                {
                    "name": "math-solver",
                    "description": "Solve arithmetic problems",
                    "content": "Show concise numeric reasoning.",
                }
            ],
            "mcp": {"math-tools": {"type": "stdio", "command": "math-mcp"}},
            "a2a": {"enabled": True, "port": 8101, "database_url": "sqlite+aiosqlite:///./math.db"},
            "query": "数学题：计算 19 * 23 并只给出答案。",
        },
        {
            "title": "code-session",
            "workspace_path": "/workspace/code",
            "skills": [
                {
                    "name": "code-writer",
                    "description": "Write small Python snippets",
                    "content": "Prefer simple, tested Python.",
                }
            ],
            "mcp": {"repo-tools": {"type": "stdio", "command": "repo-mcp"}},
            "a2a": {"enabled": True, "port": 8102, "database_url": "sqlite+aiosqlite:///./code.db"},
            "query": "代码任务：写一个 Python add(a, b) 函数。",
        },
        {
            "title": "docs-session",
            "workspace_path": "/workspace/docs",
            "skills": [
                {
                    "name": "doc-summarizer",
                    "description": "Summarize documents",
                    "content": "Extract the main points in bullets.",
                }
            ],
            "mcp": {"docs-tools": {"type": "stdio", "command": "docs-mcp"}},
            "a2a": {"enabled": True, "port": 8103, "database_url": "sqlite+aiosqlite:///./docs.db"},
            "query": "文档总结：总结这段话：后端需要支持多会话恢复。",
        },
    ]

    sessions = []
    for scenario in scenarios:
        sessions.append(
            service.create_session(
                owner_id,
                ChatSessionCreateRequest.model_validate(
                    {
                    "title": scenario["title"],
                    "scope": "project",
                    "workspace_path": scenario["workspace_path"],
                    "provider": {
                        "base_url": "https://api.deepseek.com",
                        "api_key": f"sk-{scenario['title']}",
                        "model_name": "deepseek-v4-pro",
                    },
                    "skills": scenario["skills"],
                    "mcp": scenario["mcp"],
                    "a2a": scenario["a2a"],
                    }
                ),
            )
        )

    def run_one(index: int):
        return service.start_run(owner_id, sessions[index].id, scenarios[index]["query"])

    with ThreadPoolExecutor(max_workers=3) as executor:
        runs = list(executor.map(run_one, range(3)))

    assert [run.status for run in runs] == ["completed", "completed", "completed"]

    sandbox_ids = set()
    for session, scenario in zip(sessions, scenarios):
        detail = service.get_session_detail(owner_id, session.id)
        row = service.store.get_session(owner_id, session.id)
        assert row.skills_json[0]["name"] == scenario["skills"][0]["name"]
        assert row.skills_json[0]["content"] == scenario["skills"][0]["content"]
        assert row.mcp_json == scenario["mcp"]
        assert row.a2a_json["enabled"] is True
        assert row.a2a_json["port"] == scenario["a2a"]["port"]
        assert [message.role for message in detail.messages] == ["user", "assistant"]
        assert detail.messages[0].content == scenario["query"]
        assert detail.sandbox is not None
        sandbox_ids.add(detail.sandbox.sandbox_id)

    assert len(sandbox_ids) == 3

    resumed_service = make_service(tmp_path, db_name=db_name)
    resumed_sessions = resumed_service.list_sessions(owner_id)
    assert {session.title for session in resumed_sessions} == {
        "math-session",
        "code-session",
        "docs-session",
    }

    resumed_math = next(session for session in resumed_sessions if session.title == "math-session")
    restored = resumed_service.get_session_detail(owner_id, resumed_math.id)
    assert len(restored.messages) == 2
    followup = resumed_service.start_run(owner_id, resumed_math.id, "用户回来后继续：再计算 7 + 8。")
    assert followup.status == "completed"

    restored_again = resumed_service.get_session_detail(owner_id, resumed_math.id)
    assert [message.role for message in restored_again.messages] == [
        "user",
        "assistant",
        "user",
        "assistant",
    ]
    assert restored_again.messages[2].content == "用户回来后继续：再计算 7 + 8。"


def test_restored_service_does_not_reuse_stale_opencode_session_id(tmp_path: Path) -> None:
    db_name = "stale-session.db"
    service = make_service(tmp_path, db_name=db_name)
    session = service.create_session(
        "user-a",
        ChatSessionCreateRequest.model_validate(session_payload()),
    )
    service.store.update_opencode_session_id(session.id, "ses_from_previous_process")

    resumed_service = make_service(tmp_path, db_name=db_name)
    run = resumed_service.start_run("user-a", session.id, "continue after leaving")

    assert run.status == "completed"
    execution_artifact = next(
        artifact for artifact in run.a2a_task["artifacts"] if artifact["name"] == "opencode-execution"
    )
    launch_command = execution_artifact["parts"][0]["data"]["launchCommand"]
    assert "--session" not in launch_command

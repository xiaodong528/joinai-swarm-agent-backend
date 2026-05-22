from opencode_backend.sandbox import LocalSandboxSession
from opencode_backend.schemas import AgentInput, ProvisionRequest, ProviderInput, Scope, SkillInput
from opencode_backend.service import OpenCodeProvisioner


def test_provision_local_writes_expected_files_and_launches() -> None:
    session = LocalSandboxSession()
    provisioner = OpenCodeProvisioner(session)
    request = ProvisionRequest(
        scope=Scope.project,
        workspace_path="/workspace",
        config={"model": "anthropic/claude-sonnet-4-20250514"},
        mcp={"context7": {"type": "remote", "url": "https://mcp.context7.com/mcp"}},
        skills=[SkillInput(name="docs-writer", description="Write docs", content="Docs.")],
        agents=[AgentInput(name="review", description="Reviews code", content="Focus on issues.")],
    )

    response = provisioner.provision(request)

    assert response.sandbox_id
    assert response.public_url == "http://localhost:4096"
    assert any(item.path.endswith("opencode.json") for item in response.files_written)
    assert any(item.path.endswith("SKILL.md") for item in response.files_written)
    assert any(item.path.endswith("review.md") for item in response.files_written)


def test_provision_local_query_uses_run_path() -> None:
    session = LocalSandboxSession()
    provisioner = OpenCodeProvisioner(session)
    request = ProvisionRequest(
        scope=Scope.project,
        workspace_path="/workspace",
        provider=ProviderInput(
            base_url="https://api.deepseek.com",
            api_key="sk-test",
            model_name="deepseek-v4-pro",
        ),
        query="帮我写一个加法计算器",
    )

    response = provisioner.provision(request)

    assert response.sandbox_id
    assert response.stdout
    assert response.public_url is None
    assert response.launch_command[:2] == ["opencode", "run"]


def test_run_a2a_returns_task_and_events() -> None:
    session = LocalSandboxSession()
    provisioner = OpenCodeProvisioner(session)
    request = ProvisionRequest(
        scope=Scope.project,
        workspace_path="/workspace",
        provider=ProviderInput(
            base_url="https://api.deepseek.com",
            api_key="sk-test",
            model_name="deepseek-v4-pro",
        ),
        query="build calculator",
    )

    response = provisioner.run_a2a(request, task_id="task-1", context_id="ctx-1")

    assert response.task["id"] == "task-1"
    assert response.task["contextId"] == "ctx-1"
    assert response.task["status"]["state"] == "completed"
    assert response.events
    assert response.provision.launch_command[:2] == ["opencode", "run"]


def test_provision_local_starts_a2a_runtime() -> None:
    session = LocalSandboxSession()
    provisioner = OpenCodeProvisioner(session)
    request = ProvisionRequest(
        scope=Scope.project,
        workspace_path="/workspace",
        a2a={"enabled": True, "opencode_base_url": "https://api.deepseek.com"},
        provider=ProviderInput(
            base_url="https://api.deepseek.com",
            api_key="sk-test",
            model_name="deepseek-v4-pro",
        ),
    )

    response = provisioner.provision(request)

    assert response.a2a_command[0] == "opencode-a2a"
    assert response.a2a_pid is not None
    assert response.a2a_stdout.strip() == "a2a server started"

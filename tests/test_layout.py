from opencode_backend.layout import build_file_artifacts, render_agent, render_skill, validate_name
from opencode_backend.schemas import AgentInput, ProvisionRequest, ProviderInput, Scope, SkillInput


def test_validate_name_accepts_lowercase_hyphenated_name() -> None:
    validate_name("docs-writer")


def test_render_skill_includes_frontmatter_and_body() -> None:
    skill = SkillInput(
        name="docs-writer",
        description="Write docs",
        content="You are a docs bot.",
        frontmatter={"compatibility": "opencode"},
    )
    rendered = render_skill(skill)
    assert "name: docs-writer" in rendered
    assert "description: Write docs" in rendered
    assert "compatibility: opencode" in rendered
    assert "You are a docs bot." in rendered


def test_render_agent_uses_filename_name_and_description() -> None:
    agent = AgentInput(
        name="review",
        description="Reviews code",
        content="Focus on issues.",
        frontmatter={"mode": "subagent"},
    )
    rendered = render_agent(agent)
    assert "description: Reviews code" in rendered
    assert "mode: subagent" in rendered


def test_build_file_artifacts_project_scope() -> None:
    request = ProvisionRequest(
        scope=Scope.project,
        workspace_path="/workspace/app",
        config={"model": "anthropic/claude-sonnet-4-20250514"},
        mcp={"context7": {"type": "remote", "url": "https://mcp.context7.com/mcp"}},
        skills=[SkillInput(name="docs-writer", description="Write docs", content="Docs.")],
    )
    artifacts = build_file_artifacts(request, "/home/user")
    paths = [item.path for item in artifacts]
    assert "/workspace/app/opencode.json" in paths
    assert "/workspace/app/.opencode/skills/docs-writer/SKILL.md" in paths


def test_build_file_artifacts_includes_provider_and_model() -> None:
    request = ProvisionRequest(
        scope=Scope.project,
        workspace_path="/workspace/app",
        provider=ProviderInput(
            base_url="https://api.deepseek.com",
            api_key="sk-test",
            model_name="deepseek-v4-pro",
        ),
    )
    artifacts = build_file_artifacts(request, "/home/user")
    opencode_json = next(item.content for item in artifacts if item.path.endswith("opencode.json"))
    assert '"deepseek-v4-pro"' in opencode_json
    assert '"baseURL": "https://api.deepseek.com"' in opencode_json
    assert '"apiKey": "sk-test"' in opencode_json
    assert '"model": "deepseek/deepseek-v4-pro"' in opencode_json

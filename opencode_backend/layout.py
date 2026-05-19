from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any
import re

import yaml

from .schemas import AgentInput, ProvisionRequest, Scope, SkillInput

NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SCHEMA_URL = "https://opencode.ai/config.json"


@dataclass(frozen=True)
class FileArtifact:
    path: str
    content: str


def validate_name(name: str) -> None:
    if len(name) < 1 or len(name) > 64:
        raise ValueError(f"invalid OpenCode name: {name!r}")
    if not NAME_RE.fullmatch(name):
        raise ValueError(
            f"invalid OpenCode name: {name!r}; use lowercase letters, numbers, and single hyphens"
        )


def deep_merge(base: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key, value in extra.items():
        if (
            key in result
            and isinstance(result[key], dict)
            and isinstance(value, dict)
        ):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def render_markdown_document(frontmatter: dict[str, Any], content: str) -> str:
    normalized = yaml.safe_dump(
        frontmatter,
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
    ).strip()
    body = content.strip()
    if body:
        return f"---\n{normalized}\n---\n\n{body}\n"
    return f"---\n{normalized}\n---\n"


def project_root(workspace_path: str) -> PurePosixPath:
    return PurePosixPath(workspace_path)


def project_config_path(workspace_path: str) -> PurePosixPath:
    return project_root(workspace_path) / "opencode.json"


def project_opencode_dir(workspace_path: str) -> PurePosixPath:
    return project_root(workspace_path) / ".opencode"


def global_config_root(home_dir: str) -> PurePosixPath:
    return PurePosixPath(home_dir) / ".config" / "opencode"


def config_file_path(scope: Scope, workspace_path: str | None, home_dir: str) -> str:
    if scope == Scope.project:
        return str(project_config_path(workspace_path or ""))
    return str(global_config_root(home_dir) / "opencode.json")


def skill_file_path(scope: Scope, workspace_path: str | None, home_dir: str, name: str) -> str:
    if scope == Scope.project:
        return str(project_opencode_dir(workspace_path or "") / "skills" / name / "SKILL.md")
    return str(global_config_root(home_dir) / "skills" / name / "SKILL.md")


def agent_file_path(scope: Scope, workspace_path: str | None, home_dir: str, name: str) -> str:
    if scope == Scope.project:
        return str(project_opencode_dir(workspace_path or "") / "agents" / f"{name}.md")
    return str(global_config_root(home_dir) / "agents" / f"{name}.md")


def build_opencode_json(request: ProvisionRequest) -> dict[str, Any]:
    merged = deep_merge({"$schema": SCHEMA_URL}, request.config)
    if request.mcp:
        merged["mcp"] = deep_merge(dict(merged.get("mcp", {})), request.mcp)
    if request.agent_config:
        merged["agent"] = deep_merge(dict(merged.get("agent", {})), request.agent_config)
    if request.provider:
        provider = request.provider
        provider_block = {
            provider.id: {
                "name": provider.name,
                "npm": provider.npm,
                "options": {
                    "baseURL": provider.base_url,
                },
                "models": {
                    provider.model_name: {
                        "name": provider.model_name,
                    }
                },
            }
        }
        if provider.api_key:
            provider_block[provider.id]["options"]["apiKey"] = provider.api_key
        merged["provider"] = deep_merge(dict(merged.get("provider", {})), provider_block)
        merged["model"] = f"{provider.id}/{provider.model_name}"
    if request.launch.enabled:
        merged["server"] = deep_merge(
            dict(merged.get("server", {})),
            {
                "port": request.launch.port,
                "hostname": request.launch.hostname,
            },
        )
    if request.a2a.enabled:
        merged["a2a"] = deep_merge(
            dict(merged.get("a2a", {})),
            {
                "enabled": True,
                "port": request.a2a.port,
                "hostname": request.a2a.hostname,
                "publicURL": request.a2a.public_url,
                "databaseURL": request.a2a.database_url,
                "staticAuthCredentials": request.a2a.static_auth_credentials,
            },
        )
    return merged


def render_skill(skill: SkillInput) -> str:
    validate_name(skill.name)
    frontmatter = dict(skill.frontmatter)
    frontmatter.update({"name": skill.name, "description": skill.description})
    return render_markdown_document(frontmatter, skill.content)


def render_agent(agent: AgentInput) -> str:
    validate_name(agent.name)
    frontmatter = dict(agent.frontmatter)
    frontmatter.update({"description": agent.description})
    return render_markdown_document(frontmatter, agent.content)


def build_file_artifacts(request: ProvisionRequest, home_dir: str) -> list[FileArtifact]:
    artifacts: list[FileArtifact] = []
    if request.scope == Scope.project:
        assert request.workspace_path is not None
        artifacts.append(
            FileArtifact(
                path=str(project_config_path(request.workspace_path)),
                content=_json_dump(build_opencode_json(request)),
            )
        )
    else:
        artifacts.append(
            FileArtifact(
                path=str(global_config_root(home_dir) / "opencode.json"),
                content=_json_dump(build_opencode_json(request)),
            )
        )

    for skill in request.skills:
        artifacts.append(
            FileArtifact(
                path=skill_file_path(request.scope, request.workspace_path, home_dir, skill.name),
                content=render_skill(skill),
            )
        )

    for agent in request.agents:
        artifacts.append(
            FileArtifact(
                path=agent_file_path(request.scope, request.workspace_path, home_dir, agent.name),
                content=render_agent(agent),
            )
        )
    return artifacts


def _json_dump(data: dict[str, Any]) -> str:
    import json

    return json.dumps(data, indent=2, ensure_ascii=False, sort_keys=False) + "\n"

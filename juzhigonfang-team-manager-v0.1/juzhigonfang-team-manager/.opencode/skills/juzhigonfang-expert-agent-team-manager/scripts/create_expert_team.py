#!/usr/bin/env python3
"""Generate a Juzhigonfang expert team package from a YAML manifest."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import tarfile
from pathlib import Path
from string import Template
from typing import Any

try:
    import yaml
except ImportError as exc:  # pragma: no cover - depends on host environment
    raise SystemExit(
        "PyYAML is required. Install it in this environment or run with a Python "
        "runtime that provides `import yaml`."
    ) from exc


NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$|^(primary|secondary|accent|success|warning|error|info)$")
DEFAULT_COLOR = "primary"
ACTION_VALUES = {"allow", "ask", "deny"}
TEAM_DIR = "." + "opencode"
AGENTS_SUBDIR = "agents"
SKILLS_SUBDIR = "skills"
RUNTIME_CONFIG = "opencode.json"
RUNTIME_SCHEMA = "https://opencode.ai/config.json"


def fail(message: str) -> None:
    raise SystemExit(f"error: {message}")


def validate_slug(value: Any, field: str) -> str:
    if not isinstance(value, str) or not NAME_RE.fullmatch(value):
        fail(f"{field} must match ^[a-z0-9]+(-[a-z0-9]+)*$")
    if len(value) > 64:
        fail(f"{field} must be 64 characters or fewer")
    return value


def text_list(values: Any, field: str, *, default: list[str] | None = None) -> list[str]:
    if values is None:
        return list(default or [])
    if not isinstance(values, list) or not all(isinstance(item, str) for item in values):
        fail(f"{field} must be a list of strings")
    return values


def validate_permission_value(value: Any, field: str) -> Any:
    if isinstance(value, str):
        if value not in ACTION_VALUES:
            fail(f"{field} must be allow, ask, or deny")
        return value
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, nested in value.items():
            if not isinstance(key, str):
                fail(f"{field} keys must be strings")
            result[key] = validate_permission_value(nested, f"{field}.{key}")
        return result
    fail(f"{field} must be allow/ask/deny or a mapping")


def normalize_permission(raw: Any, field: str) -> dict[str, Any]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        fail(f"{field} must be a mapping")
    return {key: validate_permission_value(value, f"{field}.{key}") for key, value in raw.items()}


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        fail("manifest root must be a YAML mapping")
    return data


def dump_yaml(data: dict[str, Any]) -> str:
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=True).strip()


def load_template(name: str) -> Template:
    template_dir = Path(__file__).resolve().parents[1] / "templates"
    return Template((template_dir / name).read_text(encoding="utf-8"))


def normalize_mcp(raw: Any) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    servers = raw or []
    if not isinstance(servers, list):
        fail("mcp_servers must be a list")
    for index, item in enumerate(servers):
        if not isinstance(item, dict):
            fail(f"mcp_servers[{index}] must be a mapping")
        name = validate_slug(item.get("name"), f"mcp_servers[{index}].name")
        server_type = item.get("type", "local")
        if server_type not in {"local", "remote"}:
            fail(f"mcp_servers[{index}].type must be local or remote")
        # This scaffold treats MCP entries as placeholders. Users must deliberately
        # enable them after filling real commands, URLs, and credentials.
        entry: dict[str, Any] = {"type": server_type, "enabled": False}
        if server_type == "local":
            command = item.get("command", [])
            if not isinstance(command, list) or not all(isinstance(part, str) for part in command):
                fail(f"mcp_servers[{index}].command must be a list of strings")
            entry["command"] = command
        else:
            url = item.get("url", "https://example.com/mcp")
            if not isinstance(url, str):
                fail(f"mcp_servers[{index}].url must be a string")
            entry["url"] = url
        if "environment" in item:
            if not isinstance(item["environment"], dict):
                fail(f"mcp_servers[{index}].environment must be a mapping")
            entry["environment"] = item["environment"]
        if "headers" in item:
            if not isinstance(item["headers"], dict):
                fail(f"mcp_servers[{index}].headers must be a mapping")
            entry["headers"] = item["headers"]
        result[name] = entry
    return result


def normalize_role(raw: Any, field: str, *, expected_mode: str | None = None) -> dict[str, Any]:
    if not isinstance(raw, dict):
        fail(f"{field} must be a mapping")
    role_id = validate_slug(raw.get("id"), f"{field}.id")
    mode = raw.get("mode", expected_mode or "subagent")
    if mode not in {"primary", "subagent", "all"}:
        fail(f"{field}.mode must be primary, subagent, or all")
    if expected_mode and mode != expected_mode:
        fail(f"{field}.mode must be {expected_mode}")
    color = raw.get("color", DEFAULT_COLOR)
    if not isinstance(color, str) or not COLOR_RE.fullmatch(color):
        fail(f"{field}.color must be a hex color or supported theme color")
    role = {
        "id": role_id,
        "mode": mode,
        "title": raw.get("title", role_id.replace("-", " ").title()),
        "description": raw.get("description", f"{role_id} expert agent"),
        "color": color,
        "responsibilities": text_list(raw.get("responsibilities"), f"{field}.responsibilities"),
        "workflow": text_list(raw.get("workflow"), f"{field}.workflow"),
        "quality_gates": text_list(raw.get("quality_gates"), f"{field}.quality_gates"),
        "skills": text_list(raw.get("skills"), f"{field}.skills"),
        "mcp": text_list(raw.get("mcp"), f"{field}.mcp"),
        "permission": normalize_permission(raw.get("permission"), f"{field}.permission"),
        "tools": raw.get("tools", {}),
    }
    if not isinstance(role["title"], str) or not isinstance(role["description"], str):
        fail(f"{field}.title and {field}.description must be strings")
    if not isinstance(role["tools"], dict):
        fail(f"{field}.tools must be a mapping")
    for skill_name in role["skills"]:
        validate_slug(skill_name, f"{field}.skills[]")
    for mcp_name in role["mcp"]:
        validate_slug(mcp_name, f"{field}.mcp[]")
    return role


def normalize_manifest(raw: dict[str, Any]) -> dict[str, Any]:
    slug = validate_slug(raw.get("slug"), "slug")
    name = raw.get("name", slug.replace("-", " ").title())
    if not isinstance(name, str):
        fail("name must be a string")
    primary = normalize_role(raw.get("primary_agent"), "primary_agent", expected_mode="primary")
    subagents_raw = raw.get("subagents")
    if not isinstance(subagents_raw, list) or not subagents_raw:
        fail("subagents must contain at least one role")
    subagents = [
        normalize_role(item, f"subagents[{index}]", expected_mode="subagent")
        for index, item in enumerate(subagents_raw)
    ]
    ids = [primary["id"], *[item["id"] for item in subagents]]
    if len(ids) != len(set(ids)):
        fail("agent ids must be unique")

    common_skills = text_list(raw.get("common_skills"), "common_skills", default=[f"{slug}-common"])
    role_skills: list[str] = []
    for role in [primary, *subagents]:
        role_skill = f"{slug}-{role['id']}"
        role_skills.append(role_skill)
        role["generated_skill"] = role_skill
        for custom_skill in role["skills"]:
            if custom_skill not in role_skills:
                role_skills.append(custom_skill)
    for skill_name in [*common_skills, *role_skills]:
        validate_slug(skill_name, "skill name")

    mcp = normalize_mcp(raw.get("mcp_servers"))
    for role in [primary, *subagents]:
        for name_ in role["mcp"]:
            if name_ not in mcp:
                fail(f"agent {role['id']} references unknown mcp server {name_}")
        role["allowed_skills"] = [*common_skills, role["generated_skill"], *role["skills"]]
        role["permission"] = build_role_permission(
            role,
            mcp_names=list(mcp.keys()),
            subagent_ids=[item["id"] for item in subagents],
            is_primary=role["id"] == primary["id"],
        )

    return {
        "slug": slug,
        "name": name,
        "summary": raw.get("summary", ""),
        "objective": raw.get("objective", "Deliver the requested expert workflow with evidence."),
        "language": raw.get("language", "zh"),
        "primary_agent": primary,
        "subagents": subagents,
        "common_skills": common_skills,
        "role_skills": role_skills,
        "mcp": mcp,
        "source_manifest": raw,
    }


def bullet_list(items: list[str], fallback: str) -> str:
    values = items or [fallback]
    return "\n".join(f"- {item}" for item in values)


def merge_permission(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            nested = dict(result[key])
            nested.update(value)
            result[key] = nested
        else:
            result[key] = value
    return result


def tools_to_permission(raw: dict[str, Any], field: str) -> dict[str, Any]:
    permission: dict[str, Any] = {}
    for key, value in raw.items():
        if not isinstance(key, str):
            fail(f"{field} keys must be strings")
        if isinstance(value, bool):
            permission_key = "edit" if key in {"write", "patch"} else key
            permission[permission_key] = "allow" if value else "deny"
        else:
            fail(f"{field}.{key} must be a boolean for compatibility conversion")
    return permission


def build_role_permission(
    role: dict[str, Any],
    *,
    mcp_names: list[str],
    subagent_ids: list[str],
    is_primary: bool,
) -> dict[str, Any]:
    permission: dict[str, Any] = {
        "read": "allow",
        "edit": "allow",
        "bash": {"*": "allow", "git status*": "allow", "git diff*": "allow"},
        "webfetch": "allow",
        "skill": {"*": "deny", **{skill: "allow" for skill in role["allowed_skills"]}},
        "task": {"*": "deny"},
    }
    if is_primary:
        permission["task"].update({agent_id: "allow" for agent_id in subagent_ids})
    for name in mcp_names:
        permission[f"{name}_*"] = "allow" if name in role["mcp"] else "deny"
    permission = merge_permission(permission, tools_to_permission(role["tools"], f"{role['id']}.tools"))
    return merge_permission(permission, role["permission"])


def role_skill_lines(role: dict[str, Any]) -> str:
    return "\n".join(f"- `/{skill}` and load/use skill `{skill}`" for skill in role["allowed_skills"])


def render_agent(role: dict[str, Any], manifest: dict[str, Any], *, is_primary: bool) -> str:
    common_skill = manifest["common_skills"][0]
    role_skill = role["generated_skill"]
    frontmatter = {
        "description": role["description"],
        "mode": role["mode"],
        "color": role["color"],
        "permission": role["permission"],
    }

    if is_primary:
        subagent_calls = "\n".join(
            f"- Call @{sub['id']} for {sub['description']}" for sub in manifest["subagents"]
        )
        workflow = bullet_list(
            role["workflow"],
            "Clarify scope, assign subagents, integrate outputs, and verify acceptance criteria.",
        )
        body = load_template("primary-agent.md.tmpl").safe_substitute(
            title=role["title"],
            swarm_name=manifest["name"],
            objective=manifest["objective"],
            common_skill=common_skill,
            role_skill=role_skill,
            allowed_skills=role_skill_lines(role),
            subagent_calls=subagent_calls,
            workflow=workflow,
            quality_gates=bullet_list(
                role["quality_gates"],
                "Before completion, verify artifacts, cite evidence, and record unresolved risk.",
            ),
        )
    else:
        body = load_template("subagent.md.tmpl").safe_substitute(
            title=role["title"],
            swarm_name=manifest["name"],
            objective=manifest["objective"],
            common_skill=common_skill,
            role_skill=role_skill,
            allowed_skills=role_skill_lines(role),
            responsibilities=bullet_list(role["responsibilities"], role["description"]),
            quality_gates=bullet_list(
                role["quality_gates"],
                "Return findings, files touched, verification status, and open risks.",
            ),
        )
    return f"---\n{dump_yaml(frontmatter)}\n---\n\n{body.strip()}\n"


def render_skill(skill_name: str, description: str, content: str) -> str:
    frontmatter = {"name": skill_name, "description": description}
    return f"---\n{dump_yaml(frontmatter)}\n---\n\n{content.strip()}\n"


def render_runtime_config(manifest: dict[str, Any]) -> dict[str, Any]:
    primary = manifest["primary_agent"]
    subagents = manifest["subagents"]
    config: dict[str, Any] = {
        "$schema": RUNTIME_SCHEMA,
        "agent": {},
    }
    if manifest["mcp"]:
        config["mcp"] = manifest["mcp"]
    config["agent"][primary["id"]] = {
        "mode": "primary",
        "description": primary["description"],
        "permission": primary["permission"],
    }
    for sub in subagents:
        config["agent"][sub["id"]] = {
            "mode": "subagent",
            "description": sub["description"],
            "permission": sub["permission"],
        }
    return config


def write_project(manifest: dict[str, Any], output_root: Path, *, package: bool, force: bool) -> Path:
    project_dir = output_root / manifest["slug"]
    if project_dir.exists():
        if not force:
            fail(f"{project_dir} already exists; pass --force to replace it")
        shutil.rmtree(project_dir)
    agents_dir = project_dir / TEAM_DIR / AGENTS_SUBDIR
    skills_dir = project_dir / TEAM_DIR / SKILLS_SUBDIR
    dist_dir = project_dir / "dist"
    agents_dir.mkdir(parents=True)
    skills_dir.mkdir(parents=True)
    dist_dir.mkdir(parents=True)

    (project_dir / "swarm.yaml").write_text(
        dump_yaml(manifest["source_manifest"]) + "\n", encoding="utf-8"
    )
    (project_dir / RUNTIME_CONFIG).write_text(
        json.dumps(render_runtime_config(manifest), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    primary = manifest["primary_agent"]
    (agents_dir / f"{primary['id']}.md").write_text(
        render_agent(primary, manifest, is_primary=True), encoding="utf-8"
    )
    for sub in manifest["subagents"]:
        (agents_dir / f"{sub['id']}.md").write_text(
            render_agent(sub, manifest, is_primary=False), encoding="utf-8"
        )

    common_content = load_template("common-skill.md.tmpl").safe_substitute(
        swarm_name=manifest["name"], objective=manifest["objective"]
    )
    for skill_name in manifest["common_skills"]:
        skill_path = skills_dir / skill_name
        skill_path.mkdir()
        (skill_path / "SKILL.md").write_text(
            render_skill(skill_name, f"Common operating guidance for {manifest['name']}.", common_content),
            encoding="utf-8",
        )
    written_custom_skills = set(manifest["common_skills"])
    for role in [primary, *manifest["subagents"]]:
        skill_name = role["generated_skill"]
        skill_path = skills_dir / skill_name
        skill_path.mkdir(exist_ok=True)
        written_custom_skills.add(skill_name)
        content = load_template("role-skill.md.tmpl").safe_substitute(
            title=role["title"],
            swarm_name=manifest["name"],
            responsibilities=bullet_list(role["responsibilities"], role["description"]),
            quality_gates=bullet_list(role["quality_gates"], "Verify work against role acceptance criteria."),
        )
        (skill_path / "SKILL.md").write_text(
            render_skill(skill_name, f"Role playbook for {role['title']} in {manifest['name']}.", content),
            encoding="utf-8",
        )
        for custom_skill in role["skills"]:
            if custom_skill in written_custom_skills:
                continue
            custom_path = skills_dir / custom_skill
            custom_path.mkdir(exist_ok=True)
            written_custom_skills.add(custom_skill)
            custom_content = load_template("role-skill.md.tmpl").safe_substitute(
                title=f"{role['title']} Supplemental Skill",
                swarm_name=manifest["name"],
                responsibilities=bullet_list(
                    role["responsibilities"],
                    f"Support {role['title']} with focused supplemental guidance.",
                ),
                quality_gates=bullet_list(
                    role["quality_gates"],
                    "Verify the supplemental work before handoff.",
                ),
            )
            (custom_path / "SKILL.md").write_text(
                render_skill(custom_skill, f"Supplemental skill for {role['title']} in {manifest['name']}.", custom_content),
                encoding="utf-8",
            )

    readme = load_template("README.md.tmpl").safe_substitute(
        swarm_name=manifest["name"],
        slug=manifest["slug"],
        primary=primary["id"],
        subagents=", ".join(sub["id"] for sub in manifest["subagents"]),
        objective=manifest["objective"],
        mcp_note=(
            "MCP entries are generated as disabled placeholders. Fill in real commands, URLs, "
            "and environment variables before enabling them."
            if manifest["mcp"]
            else "No MCP entries were configured in `swarm.yaml`, so this package does not include MCP placeholders."
        ),
    )
    (project_dir / "README.md").write_text(readme, encoding="utf-8")

    if package:
        archive = dist_dir / f"{manifest['slug']}.tar.gz"
        with tarfile.open(archive, "w:gz") as tar:
            for child in sorted(project_dir.iterdir()):
                if child.name == "dist":
                    continue
                tar.add(child, arcname=f"{manifest['slug']}/{child.name}")
    return project_dir


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path, help="Path to swarm.yaml")
    parser.add_argument("--output-dir", required=True, type=Path, help="Directory to receive generated package")
    parser.add_argument("--package", action="store_true", help="Create dist/<slug>.tar.gz")
    parser.add_argument("--force", action="store_true", help="Replace existing output project directory")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    raw = load_yaml(args.manifest)
    manifest = normalize_manifest(raw)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    project_dir = write_project(manifest, args.output_dir, package=args.package, force=args.force)
    print(project_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())

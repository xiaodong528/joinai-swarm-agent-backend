#!/usr/bin/env python3
"""Validate a generated Juzhigonfang expert team package."""

from __future__ import annotations

import json
import re
import sys
import tarfile
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError as exc:  # pragma: no cover - host dependent
    raise SystemExit("PyYAML is required to validate swarm.yaml and agent frontmatter.") from exc


NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
TEAM_DIR = "." + "opencode"
AGENTS_SUBDIR = "agents"
SKILLS_SUBDIR = "skills"
RUNTIME_CONFIG = "opencode.json"
SECRET_PATTERNS = [
    re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bghp_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b"),
    re.compile(
        r"(?i)\b(api[_-]?key|secret|token|password)\b\s*[:=]\s*[\"']?"
        r"(?!\{env:|\[TODO|<|your-|YOUR_|example|xxx)[A-Za-z0-9_./+=:-]{12,}"
    ),
]


class Result:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def error(self, message: str) -> None:
        self.errors.append(message)

    def warn(self, message: str) -> None:
        self.warnings.append(message)

    @property
    def ok(self) -> bool:
        return not self.errors

    def print_summary(self) -> None:
        if self.errors:
            print(f"ERRORS ({len(self.errors)}):")
            for message in self.errors:
                print(f"- {message}")
        if self.warnings:
            print(f"WARNINGS ({len(self.warnings)}):")
            for message in self.warnings:
                print(f"- {message}")
        if self.ok:
            print("Expert team package is valid.")


def read_yaml(path: Path, result: Result) -> dict[str, Any] | None:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as exc:
        result.error(f"{path.name}: cannot parse YAML: {exc}")
        return None
    if not isinstance(data, dict):
        result.error(f"{path.name}: root must be a mapping")
        return None
    return data


def read_json(path: Path, result: Result) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        result.error(f"{path.name}: cannot parse JSON: {exc}")
        return None
    if not isinstance(data, dict):
        result.error(f"{path.name}: root must be an object")
        return None
    return data


def validate_name(value: Any, field: str, result: Result) -> str | None:
    if not isinstance(value, str) or not NAME_RE.fullmatch(value):
        result.error(f"{field}: must match ^[a-z0-9]+(-[a-z0-9]+)*$")
        return None
    if len(value) > 64:
        result.error(f"{field}: must be 64 characters or fewer")
        return None
    return value


def parse_frontmatter(path: Path, result: Result) -> dict[str, Any] | None:
    try:
        content = path.read_text(encoding="utf-8")
    except Exception as exc:
        result.error(f"{path}: cannot read file: {exc}")
        return None
    match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
    if not match:
        result.error(f"{path}: missing YAML frontmatter")
        return None
    try:
        data = yaml.safe_load(match.group(1))
    except Exception as exc:
        result.error(f"{path}: cannot parse frontmatter: {exc}")
        return None
    if not isinstance(data, dict):
        result.error(f"{path}: frontmatter must be a mapping")
        return None
    return data


def list_role_ids(manifest: dict[str, Any], result: Result) -> tuple[str | None, list[str]]:
    primary = manifest.get("primary_agent")
    if not isinstance(primary, dict):
        result.error("swarm.yaml: primary_agent must be a mapping")
        primary_id = None
    else:
        primary_id = validate_name(primary.get("id"), "primary_agent.id", result)
        if primary.get("mode", "primary") != "primary":
            result.error("swarm.yaml: primary_agent.mode must be primary")

    subagents_raw = manifest.get("subagents")
    subagent_ids: list[str] = []
    if not isinstance(subagents_raw, list) or not subagents_raw:
        result.error("swarm.yaml: subagents must contain at least one role")
        return primary_id, subagent_ids

    for index, item in enumerate(subagents_raw):
        if not isinstance(item, dict):
            result.error(f"swarm.yaml: subagents[{index}] must be a mapping")
            continue
        agent_id = validate_name(item.get("id"), f"subagents[{index}].id", result)
        if item.get("mode", "subagent") != "subagent":
            result.error(f"swarm.yaml: subagents[{index}].mode must be subagent")
        if agent_id:
            subagent_ids.append(agent_id)

    ids = [item for item in [primary_id, *subagent_ids] if item]
    if len(ids) != len(set(ids)):
        result.error("swarm.yaml: agent ids must be unique")
    return primary_id, subagent_ids


def expected_skill_names(manifest: dict[str, Any], primary_id: str | None, subagent_ids: list[str]) -> list[str]:
    slug = manifest.get("slug")
    if not isinstance(slug, str):
        return []
    common = manifest.get("common_skills")
    skills: list[str] = []
    if isinstance(common, list) and all(isinstance(item, str) for item in common):
        skills.extend(common)
    else:
        skills.append(f"{slug}-common")

    roles: list[dict[str, Any]] = []
    if isinstance(manifest.get("primary_agent"), dict):
        roles.append(manifest["primary_agent"])
    if isinstance(manifest.get("subagents"), list):
        roles.extend(item for item in manifest["subagents"] if isinstance(item, dict))

    for role in roles:
        role_id = role.get("id")
        if isinstance(role_id, str):
            skills.append(f"{slug}-{role_id}")
        extra = role.get("skills", [])
        if isinstance(extra, list):
            skills.extend(item for item in extra if isinstance(item, str))

    return sorted(set(skills))


def check_files(package_dir: Path, manifest: dict[str, Any], result: Result) -> None:
    primary_id, subagent_ids = list_role_ids(manifest, result)
    agents_dir = package_dir / TEAM_DIR / AGENTS_SUBDIR
    skills_dir = package_dir / TEAM_DIR / SKILLS_SUBDIR

    if primary_id and not (agents_dir / f"{primary_id}.md").exists():
        result.error(f"missing primary agent file: {TEAM_DIR}/{AGENTS_SUBDIR}/{primary_id}.md")
    for agent_id in subagent_ids:
        if not (agents_dir / f"{agent_id}.md").exists():
            result.error(f"missing subagent file: {TEAM_DIR}/{AGENTS_SUBDIR}/{agent_id}.md")

    for skill_name in expected_skill_names(manifest, primary_id, subagent_ids):
        validate_name(skill_name, f"skill {skill_name}", result)
        if not (skills_dir / skill_name / "SKILL.md").exists():
            result.error(f"missing skill file: {TEAM_DIR}/{SKILLS_SUBDIR}/{skill_name}/SKILL.md")


def check_runtime_config(package_dir: Path, config: dict[str, Any], manifest: dict[str, Any], result: Result) -> None:
    agents = config.get("agent")
    if not isinstance(agents, dict):
        result.error(f"{RUNTIME_CONFIG}: agent must be an object")
        return

    primary_count = sum(1 for data in agents.values() if isinstance(data, dict) and data.get("mode") == "primary")
    subagent_count = sum(1 for data in agents.values() if isinstance(data, dict) and data.get("mode") == "subagent")
    if primary_count != 1:
        result.error(f"{RUNTIME_CONFIG}: expected exactly 1 primary agent, got {primary_count}")
    if subagent_count < 1:
        result.error(f"{RUNTIME_CONFIG}: expected at least 1 subagent")

    manifest_mcp_raw = manifest.get("mcp_servers", [])
    manifest_has_mcp = isinstance(manifest_mcp_raw, list) and bool(manifest_mcp_raw)
    if not manifest_has_mcp and "mcp" in config:
        result.error(f"{RUNTIME_CONFIG}: mcp must be omitted when swarm.yaml has no mcp_servers")
    if manifest_has_mcp and "mcp" not in config:
        result.error(f"{RUNTIME_CONFIG}: mcp is required when swarm.yaml defines mcp_servers")

    mcp = config.get("mcp", {})
    if not isinstance(mcp, dict):
        result.error(f"{RUNTIME_CONFIG}: mcp must be an object")
    else:
        for name, entry in mcp.items():
            if not isinstance(entry, dict):
                result.error(f"{RUNTIME_CONFIG}: mcp.{name} must be an object")
                continue
            if entry.get("enabled") is not False:
                result.error(f"{RUNTIME_CONFIG}: mcp.{name}.enabled must be false")

    agents_dir = package_dir / TEAM_DIR / AGENTS_SUBDIR
    role_ids = [manifest.get("primary_agent", {}).get("id")]
    role_ids.extend(
        item.get("id")
        for item in manifest.get("subagents", [])
        if isinstance(item, dict)
    )
    for agent_id in [item for item in role_ids if isinstance(item, str)]:
        md_path = agents_dir / f"{agent_id}.md"
        if not md_path.exists():
            continue
        fm = parse_frontmatter(md_path, result)
        config_agent = agents.get(agent_id)
        if not isinstance(config_agent, dict):
            result.error(f"{RUNTIME_CONFIG}: missing agent entry for {agent_id}")
            continue
        if fm and fm.get("permission") != config_agent.get("permission"):
            result.error(f"permission mismatch for agent {agent_id}: Markdown frontmatter != {RUNTIME_CONFIG}")


def scan_secrets(package_dir: Path, result: Result) -> None:
    scanned_suffixes = {".md", ".json", ".yaml", ".yml", ".toml", ".txt"}
    for path in sorted(package_dir.rglob("*")):
        if not path.is_file() or path.suffix not in scanned_suffixes:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for pattern in SECRET_PATTERNS:
            if pattern.search(text):
                result.warn(f"possible secret-like value in {path.relative_to(package_dir)}")
                break


def check_archive(package_dir: Path, manifest: dict[str, Any], result: Result) -> None:
    slug = manifest.get("slug")
    if not isinstance(slug, str):
        return
    archive = package_dir / "dist" / f"{slug}.tar.gz"
    if not archive.exists():
        result.warn(f"archive not found: dist/{slug}.tar.gz")
        return
    try:
        with tarfile.open(archive, "r:gz") as handle:
            names = handle.getnames()
    except Exception as exc:
        result.error(f"archive cannot be read: {exc}")
        return
    for required in [f"{slug}/swarm.yaml", f"{slug}/{RUNTIME_CONFIG}", f"{slug}/README.md"]:
        if required not in names:
            result.error(f"archive missing {required}")


def validate_package(package_dir: Path) -> Result:
    result = Result()
    if not package_dir.exists() or not package_dir.is_dir():
        result.error(f"package directory does not exist: {package_dir}")
        return result

    manifest_path = package_dir / "swarm.yaml"
    config_path = package_dir / RUNTIME_CONFIG
    if not manifest_path.exists():
        result.error("missing swarm.yaml")
        return result
    if not config_path.exists():
        result.error(f"missing {RUNTIME_CONFIG}")
        return result

    manifest = read_yaml(manifest_path, result)
    config = read_json(config_path, result)
    if not manifest or not config:
        return result

    validate_name(manifest.get("slug"), "slug", result)
    check_files(package_dir, manifest, result)
    check_runtime_config(package_dir, config, manifest, result)
    check_archive(package_dir, manifest, result)
    scan_secrets(package_dir, result)
    return result


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: validate_expert_team.py <path/to/generated-package-dir>")
        return 2
    package_dir = Path(sys.argv[1]).expanduser().resolve()
    result = validate_package(package_dir)
    result.print_summary()
    return 0 if result.ok else 1


if __name__ == "__main__":
    sys.exit(main())

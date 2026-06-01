# Juzhigonfang Team Manager OpenCode 主智能体包

Generated Juzhigonfang expert team package.

## Objective

让 expert-team-manager 作为 primary agent 加载并使用 juzhigonfang-expert-agent-team-manager skill，编排 manifest 设计、skill 配置、包生成和验证审查四个子专家，交付可复用、可验证、无 MCP 默认启用、无敏感信息的聚智工坊专家团包。

## Structure

- `opencode.json`: project runtime configuration.
- `.opencode/agents/`: primary and subagent Markdown definitions.
- `.opencode/skills/`: common and role-specific playbooks.
- `swarm.yaml`: source manifest used to generate this package.
- `dist/juzhigonfang-team-manager.tar.gz`: packaged copy when generated with `--package`.

## Agents

- Primary: `expert-team-manager`
- Subagents: manifest-architect, skill-configurator, package-builder, validation-reviewer

## Usage

Run the team from this project directory. Switch to the primary agent, then ask it to execute the workflow. The primary prompt contains explicit `@subagent` routing and skill loading guidance.

No MCP entries were configured in `swarm.yaml`, so this package does not include MCP placeholders.

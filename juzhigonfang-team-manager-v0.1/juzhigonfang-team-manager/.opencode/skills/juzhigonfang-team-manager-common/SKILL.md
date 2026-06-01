---
name: juzhigonfang-team-manager-common
description: Common operating guidance for Juzhigonfang Team Manager OpenCode 主智能体包.
---

# Common Swarm Playbook

Use this playbook for every agent in `Juzhigonfang Team Manager OpenCode 主智能体包`.

Objective: 让 expert-team-manager 作为 primary agent 加载并使用 juzhigonfang-expert-agent-team-manager skill，编排 manifest 设计、skill 配置、包生成和验证审查四个子专家，交付可复用、可验证、无 MCP 默认启用、无敏感信息的聚智工坊专家团包。

## Work Rhythm

1. Clarify the requested outcome and success criteria.
2. Identify which role owns each workstream.
3. Delegate specialist work to the owning role instead of bypassing role boundaries.
4. Mark workstreams as serial or parallel-safe based on dependencies, shared-write risk, and acceptance boundaries.
5. Keep outputs evidence-backed and easy for the primary agent to accept, reject, or re-dispatch.
6. Prefer the smallest useful artifact over broad speculation.
7. Verify before reporting completion.

## Handoff Format

Use this shape when handing work back to another agent:

```markdown
## Result
[What changed or what was found.]

## Evidence
[Commands, files, checks, or source references.]

## Acceptance Status
[Each acceptance criterion marked pass, fail, or blocked.]

## Dependencies
[Upstream inputs used, downstream work unblocked, and whether this branch was serial or parallel-safe.]

## Failed or Blocked Criteria
[Exact reason and required next action, or none.]

## Risks
[Known gaps or none.]
```

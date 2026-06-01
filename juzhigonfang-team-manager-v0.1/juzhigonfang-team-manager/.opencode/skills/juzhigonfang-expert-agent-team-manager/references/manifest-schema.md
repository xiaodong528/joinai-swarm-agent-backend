# Manifest Schema

`swarm.yaml` 是专家团项目包的 source of truth。优先编辑 manifest，再重新生成 `.opencode` 目录。

## Required Fields

```yaml
slug: software-dev-team
name: Software Development Expert Swarm
objective: Deliver software from product intent to verified release.
primary_agent:
  id: delivery-director
  title: Delivery Director
  description: Orchestrates delivery workflow, delegates specialist steps, and accepts or rejects subagent outputs.
  mode: primary
subagents:
  - id: product-manager
    title: Product Manager
    description: Clarifies user needs and acceptance criteria.
```

Rules:

- `slug`, agent ids, skill names, and MCP names must match `^[a-z0-9]+(-[a-z0-9]+)*$`.
- Exactly one primary agent is expected.
- At least one subagent is required.
- Agent ids must be unique.
- Generated role skill names are `<slug>-<agent-id>`.
- Default common skill is `<slug>-common`.

## Display and Structure Field Mapping

These fields are the Juzhigonfang equivalent of an expert team's public shape. Keep them consistent in creation, conversion, and modification workflows:

| User-visible concept | `swarm.yaml` field | Rule |
|---|---|---|
| Package identity | `slug` | Stable kebab-case directory/package id. Rename only when the user explicitly asks and all references are updated. |
| Team name | `name` | Human-readable team name used in generated README and prompts. |
| Short positioning | `summary` | One-line package summary; use it to explain the team in listings or handoffs. |
| Mission | `objective` | The concrete outcome the primary agent optimizes for. |
| Lead/orchestrator | `primary_agent` | Exactly one `mode: primary` agent; owns routing, acceptance, re-dispatch, and final integration. |
| Team members | `subagents` | One or more `mode: subagent` roles; each should have a single responsibility boundary. |
| Shared playbook | `common_skills` | Local generated skill names for team-wide operating rules and handoff format. |
| External tools | `mcp_servers` | Optional placeholder MCP definitions; omit this field when the team does not need MCP. Generated `enabled` state must remain `false` until explicitly configured. |
| Per-role capability | `skills`, `permission` | Local supplemental skills and Juzhigonfang permissions; keep `.md` frontmatter and `opencode.json` aligned. |

Do not add WorkBuddy-only fields such as `categoryId`, `displayName`, `profession`, `avatar`, `quickPrompts`, or `marketplace.json` registration metadata to this manifest. If those are needed, create a separate compatibility mode instead of mixing formats.

## Source Material Conversion

When the user provides existing documents, prompts, process notes, or a repository instead of `swarm.yaml`, extract durable structure into the manifest before generation:

| Source material | Convert to | Notes |
|---|---|---|
| Role descriptions, personas, job titles | `primary_agent` / `subagents` titles, descriptions, responsibilities | Choose `primary_agent` for orchestration ownership; choose `subagents` for specialist work. |
| SOP, phase flow, routing rules | `primary_agent.workflow` | Mark dependency order, parallel-safe branches, and re-dispatch rules explicitly. |
| Acceptance criteria, quality standards | `quality_gates` | Put shared release/acceptance rules on primary; role-specific checks on subagents. |
| Output formats and report templates | Role skills or supplemental local skills | Keep long templates out of agent frontmatter. |
| Domain reference, API docs, policies | Generated supplemental skills or `references/` resources | Preserve precise terminology and cite source paths in handoffs. |
| Scripts, CLIs, services | `permission.bash`, explicitly configured MCP placeholders, or bundled scripts | Never store real secrets; use `{env:...}` placeholders. |
| Multi-role collaboration notes | `subagents[]` plus `permission.task` allowlist | Primary routes to subagents; subagents should not call peers unless deliberately allowed. |

Conversion workflow:

1. Read the source material and separate facts from inferred structure.
2. Propose `slug`, `name`, `summary`, `objective`, primary role, and subagent list.
3. Ask only for missing or high-impact choices that cannot be inferred.
4. Show a complete `swarm.yaml` draft before writing or generating.
5. After confirmation, generate, validate, and package through the normal workflow.

## Modification Workflow

For an existing package, `swarm.yaml` is the durable source of truth:

- Locate the package directory and read `swarm.yaml` first.
- Treat `.opencode/agents`, `.opencode/skills`, `opencode.json`, `README.md`, and `dist/` as generated artifacts.
- Make the smallest manifest change that satisfies the user's request.
- Preserve valid user-provided ids and permissions unless the request requires changing them.
- If `slug`, agent ids, skill names, or MCP names change, update every reference in `common_skills`, agent `skills`, `permission.skill`, `permission.task`, and `mcp`.
- Re-run generation with `--force` only after the user explicitly permits replacing the existing output directory.
- Run `scripts/validate_expert_team.py` after regeneration.

## Optional Fields

```yaml
summary: Short package summary.
language: zh
common_skills:
  - software-dev-team-common
mcp_servers:
  - name: context-docs
    type: remote
    url: https://example.com/mcp
    enabled: false
primary_agent:
  color: "#2563eb"
  skills:
    - software-dev-team-delivery-review
  workflow:
    - Clarify scope and acceptance criteria for routing.
    - Run @product-manager and @architect in parallel when discovery can be accepted independently.
    - Ask @engineer to implement the accepted scope.
  quality_gates:
    - No release without test evidence.
    - Parallel branches must have separate outputs and acceptance criteria.
    - Re-dispatch failed subagent work with concrete acceptance feedback.
  mcp:
    - context-docs
  permission:
    read: allow
    edit: allow
    bash:
      "*": allow
      "git status*": allow
      "git diff*": allow
    webfetch: allow
    task:
      "*": deny
      engineer: allow
subagents:
  - id: engineer
    title: Engineer
    description: Implements scoped changes.
    color: success
    responsibilities:
      - Make minimal code changes.
    quality_gates:
      - Run relevant tests.
    skills:
      - software-dev-team-code-change
      - software-dev-team-test-runner
    mcp:
      - context-docs
    permission:
      read: allow
      edit: allow
      bash:
        "*": allow
        "git status*": allow
        "git diff*": allow
        "pnpm test*": allow
      webfetch: allow
```

## Per-Agent Skills and Permissions

Every `primary_agent` and `subagents[]` entry may declare dedicated skills and permissions:

- `skills`: extra skill names that belong to that agent. The generator always adds the common skill plus the generated role skill `<slug>-<agent-id>`; values in `skills` are additional dedicated skills.
- `mcp`: MCP server names this agent is allowed to use. MCP servers are generated only when `mcp_servers` is present, and generated entries stay `enabled: false`; the agent permission table controls whether the MCP tool glob is `allow` or `deny`.
- `permission`: Juzhigonfang permission rules for that agent. Prefer this field over legacy boolean `tools`.

`skills` entries are local generated supplemental skills. They are not proof that an external skill discovered by a finder is installed, copied, or packaged. Convert external candidates into local skill names only after the user confirms that choice.

Default generated permissions:

- `read: allow`
- `edit: allow`
- `bash`: `*` is allowed, with specific command examples also allowed
- `webfetch: allow`
- `skill`: `*` denied, then common/role/dedicated skills allowed
- `task`: primary can call declared subagents; subagents cannot call other subagents unless explicitly allowed
- `<mcp-name>_*`: generated only for configured MCP servers; `allow` for MCPs listed in agent `mcp`, otherwise `deny`

Legacy `tools` mappings are only read for compatibility. New manifests should use `permission`.

## Delegation and Acceptance Model

Generated swarms use a delegation-first primary model:

- The primary agent owns orchestration, acceptance, rejection, re-dispatch, and final integration.
- The primary agent normally does not execute specialist workflow steps directly when a declared subagent owns the responsibility.
- Each workflow step should map to a concrete `@subagent` route or to an explicit primary-only coordination action.
- Each delegated task should include the task, expected output, acceptance criteria, and evidence required.
- Dependent work should run serially; independent work may run in parallel when each branch has separate inputs, separate expected outputs, no shared-write conflict, and independently checkable acceptance criteria.
- Parallel batches should be accepted branch by branch. If one branch fails, re-dispatch only that branch and do not advance dependent work until every required branch has passed or been explicitly waived.
- If a subagent result fails the criteria, the primary agent should re-dispatch the same subagent with the failed criteria, concrete feedback, and required rework.
- Subagent handoffs should report completed work, evidence, acceptance criteria status, dependencies, failed or blocked criteria, and unresolved risks.

## MCP Policy

When `mcp_servers` is omitted, the generated `opencode.json` should not include MCP placeholders. When `mcp_servers` is provided, MCP definitions are placeholders by default:

- `enabled` defaults to `false`.
- Local MCP entries require `command: [...]`.
- Remote MCP entries use `url`.
- Environment variables and headers should use placeholders such as `{env:MY_API_KEY}`.
- The generated `opencode.json` omits `mcp` when no MCP servers are configured; configured MCP role tool globs stay disabled or role-scoped until the user deliberately enables them.

## Skill Discovery Before Manifest

When the manifest is missing, incomplete, or weak on agent-specific skills, run skill discovery before finalizing `swarm.yaml`:

- Use `find-skills` for local Skills CLI / skills.sh ecosystem discovery.
- Use `internet-skill-finder` for verified GitHub repository discovery.
- Search from the objective, audience, expected artifacts, primary-agent orchestration needs, and each subagent responsibility.
- Present candidate skills with source, intended role, and whether they should become a local generated skill, remain an external installation suggestion, or be skipped.
- Ask the user to confirm choices with the available ask-user-question tool, such as `request_user_input`; fall back to one concise normal question only when no such tool is available.
- Do not auto-install external skills, silently copy external skill contents, or write finder results into `common_skills` / agent `skills` without explicit user confirmation.
- If the search tool, network, or CLI is unavailable, state that limitation and continue with user-confirmed local skill names instead of claiming an external skill is available.

## No Manifest Interview Order

If the user has not uploaded or pointed to a `swarm.yaml`, collect only enough information to build a good first manifest. Ask one focused question per round, preferably with the environment's ask-user-question tool when available.

Use this order and map answers into fields:

1. Mission and audience -> `objective`, `summary`
2. Package identity -> `slug`, `name`, `language`
3. Role structure -> `primary_agent.id`, `primary_agent.title`, `primary_agent.description`, `subagents[].id`, `subagents[].title`, `subagents[].description`, and `subagents[].responsibilities`
4. Skill discovery -> run `find-skills` and `internet-skill-finder` for shared capabilities and each agent role
5. Candidate confirmation -> ask which candidates become local `common_skills` or agent `skills`, which remain external install suggestions, and which are skipped
6. Workflow -> `primary_agent.workflow`, including which steps route to which `@subagent`, which steps are serial, and which independent steps can run as a parallel batch
7. Quality gates and permissions -> `primary_agent.quality_gates`, `subagents[].quality_gates`, agent `mcp`, agent `permission`, and the rule for re-dispatching failed work
8. Output policy -> output directory, `--package`, and whether an existing directory can use `--force`

After these rounds, show the complete `swarm.yaml` draft and wait for user confirmation before generation. If the user asks to change the draft, update the YAML and show it again.

## Uploaded Manifest Review

If a `swarm.yaml` already exists, do not run the full interview. Validate it and ask only about gaps:

- Missing `slug`, `name`, `objective`, `primary_agent`, or `subagents`
- Invalid lowercase-hyphen names
- Duplicate agent ids
- Missing primary workflow or quality gates when the user expects a managed delivery process
- Primary workflow that asks the primary agent to directly execute specialist work despite a declared subagent owning that role
- Parallel workflow that lacks independent outputs, independent acceptance criteria, or shared-write boundaries
- Agent-specific `skills`, `mcp`, or `permission` fields that conflict with the intended role boundary
- Agent `skills` that are missing, generic, duplicated, or not aligned with the role. For these gaps, search with `find-skills` and `internet-skill-finder`, present only the relevant candidates, and confirm whether to convert them into local supplemental skills.
- MCP entries that look enabled or credential-bearing; if the team does not need MCP, remove `mcp_servers` and agent `mcp` references instead of generating default placeholders

For each gap, propose the smallest concrete correction and ask for confirmation. Preserve valid user-provided fields.

## Software Team Preset

Use `examples/software-dev-team.swarm.yaml` as the reference for:

- Delivery Director as primary agent.
- Product Manager, Architect, Engineer, and QA Engineer as subagents.
- Delegation-first workflow with step-level acceptance, parallel-safe discovery branches, and re-dispatch on failed criteria.
- Context/docs MCP placeholders that remain disabled.

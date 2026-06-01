---
name: juzhigonfang-expert-agent-team-manager
description: >-
  Use this skill whenever the user wants to create, convert, modify, validate,
  package, or operate a Juzhigonfang expert agent team from `swarm.yaml`.
  Use it for expert team lifecycle management, primary/subagent team design,
  bundled skill creation, optional MCP placeholder configuration, per-agent permissions,
  finder-backed skill discovery, source-material conversion, package review,
  regeneration, validation, or prompts like "创建专家团", "修改专家团",
  "资料转成专家团", "检查专家团包", or "打包专家团项目".
metadata:
  display_name: juzhigonfang-expert-agent-team-manager
---

# juzhigonfang-expert-agent-team-manager

用这个技能管理聚智工坊专家团项目包的生命周期。它面向“一个主智能体 + 多个子智能体 + 通用/角色专属 skill + 可选 MCP 配置 + 每个智能体的工具权限”的可复用交付，而不是一次性手写几个 Markdown 文件。

默认用中文交流和写交付说明，除非用户要求英文。生成的智能体和 skill 可以按 manifest 语言选择中文或英文。

## First Decision

先判断用户要做哪件事：

- 新建专家团：如果没有 manifest，进入 `Interactive Manifest Confirmation`，确认目标、角色、技能、权限、输出目录后生成。
- 资料转化专家团：读取用户提供的文档、流程、提示词、仓库说明或现有项目，按 `Source Material Conversion` 提取角色、人设、SOP、输出规范和资源，再展示 `swarm.yaml` 草案让用户确认。
- 修改已有专家团：定位目标包，优先读取并编辑 `swarm.yaml`，只改用户要求的字段；确认修改范围后重新生成派生的智能体定义、技能目录、运行时配置、`README.md` 和归档。
- 校验/打包专家团：对已有包运行静态校验和打包检查，不为了掩盖问题重写包；失败时报告具体字段、文件和修复建议。
- 只要示例：优先展示下方 `Complete swarm.yaml Template`；如果用户要软件开发团队 preset，再展示或复制 `examples/software-dev-team.swarm.yaml` 的结构。
- 需要接入其它执行底座：本技能只生成聚智工坊专家团包；跨底座适配需要另开集成设计，不在默认流程里混入。

## Lifecycle Workflow

整体流程遵循“先定位、再确认、后校验”的项目包管理思想：

1. 收集或定位输入：确认用户是要新建、资料转化、修改、校验还是打包。
2. 确定 source of truth：新建/转化先形成 `swarm.yaml` 草案；修改已有包先读取目标目录里的 `swarm.yaml`。
3. 校验关键字段：`slug`、agent id、skill name、MCP name 必须 lowercase-hyphen；角色数量和职责决定 primary/subagent 结构，不凭空改。
4. 确认修改范围：只问会改变 manifest 或产物边界的问题；不要一次性抛长表单。
5. 生成或重生成：用 `scripts/create_expert_team.py` 从确认后的 `swarm.yaml` 生成派生文件。
6. 验证和打包：运行 `scripts/validate_expert_team.py`、JSON/tar 检查和必要的结构读回。

## Source Material Conversion

当用户提供资料而不是 manifest 时，先提取再确认，不要直接生成：

- 角色描述、专家人设 -> `primary_agent` / `subagents` 的 `title`、`description`、`responsibilities`。
- 工作流程、操作步骤、SOP -> `primary_agent.workflow`，并标明哪些步骤串行、哪些步骤可并行。
- 输出格式、质量要求、验收标准 -> 各角色 `quality_gates` 和 role skill 内容。
- API 文档、领域资料、长参考文本 -> 建议转为生成包内的 supplemental skill 或 `references/` 资源，不塞进智能体正文。
- 可执行脚本或工具调用 -> 建议转为 `scripts/`、显式配置的 MCP 占位或 agent `permission.bash`，真实密钥和私有 endpoint 必须留空或用 `{env:...}`。
- 多角色分工 -> 一个 `mode: primary` 主智能体加多个 `mode: subagent` 子智能体；主智能体负责编排、验收、失败重派和最终集成。

## Modify Existing Team

修改已有专家团时：

- 先定位目录并读取 `swarm.yaml`、运行时配置、智能体定义目录和技能目录，确认它是本技能生成或兼容的包。
- 优先修改 `swarm.yaml`；智能体定义目录、技能目录、运行时配置、`README.md`、`dist/` 视为可重建派生物。
- 不要改 `slug`、agent id 或 skill name，除非用户明确要求重命名；重命名必须同步所有引用。
- 如果目标目录存在，只有在用户明确允许覆盖时才使用 `--force`。
- 修改后重新生成并运行完整验证；不要只手改派生 Markdown 后宣称完成。

## Format Boundary

本技能不生成第三方市场插件字段，例如 `.codebuddy-plugin/plugin.json`、`marketplace.json`、`categoryId`、`displayName`、`profession` 或头像资源；这些字段只作为参考思路。除非用户另开兼容模式，否则不要把其它插件格式混入聚智工坊专家团包。

## Source Discipline

运行时细节要从本地生成器、验证器和 manifest schema 刷新，不靠记忆猜。当前生成器采用这些稳定约定：

- 智能体 Markdown 写入团队定义目录。
- Skill 写入技能目录的 `<skill-name>/SKILL.md`。
- 项目配置写入 `opencode.json`。
- 只有 manifest 明确配置 `mcp_servers` 时才生成 MCP 条目；生成出的 MCP 条目默认 `enabled: false`，只作为占位，用户填好命令、URL、环境变量后再启用。
- 工具、skill、task、MCP tool glob 使用 `permission` 控制；旧版 `tools` 布尔配置只做兼容输入，不作为新模板推荐。

## Manifest Workflow

1. 读取 `references/manifest-schema.md` 和用户需求。
2. 若用户没有 manifest，先执行 `Interactive Manifest Confirmation`。在角色结构初步明确后，用 `find-skills` 和 `internet-skill-finder` 搜索主智能体、子智能体、common skill、角色 skill 的候选能力，再通过 ask-user-question 工具逐轮确认。
3. 再创建 `swarm.yaml` 草案，至少包含：
   - `slug`
   - `name`
   - `objective`
   - `primary_agent`
   - `subagents`
4. 若用户已提供 manifest，只校验并补问缺失或冲突字段，不要重新访谈所有问题；如果 agent `skills` 明显缺失或与职责冲突，只针对该缺口做 finder 搜索和确认。
5. 确认命名都是 lowercase-hyphen：`slug`、agent id、skill name、MCP name。
6. 确认每个 agent 的专属 `skills`、可选 `mcp`、`permission` 是否符合角色边界，并确认 workflow 的每个专业步骤都能映射到一个或多个 `@subagent` 调用；有依赖的步骤串行，互不依赖且可独立验收的步骤可以并行。
7. 展示最终 `swarm.yaml` 草案，让用户确认后再运行生成脚本。
8. 用脚本生成：

```bash
python .opencode/skills/juzhigonfang-expert-agent-team-manager/scripts/create_expert_team.py \
  --manifest <swarm.yaml> \
  --output-dir <output-dir> \
  --package
```

9. 如果目标目录已存在且确认要覆盖，加 `--force`。
10. 生成后验证运行时配置、agent frontmatter、skill frontmatter、归档内容、权限一致性、已配置 MCP 的 disabled 状态，以及 primary/subagent prompt 是否体现编排优先、串行/并行路由、逐步验收、失败重派。

## Complete swarm.yaml Template

当用户要“完整模板”或没有现成 manifest 时，可以先展示并改写这个模板。同一份可复制文件保存在 `templates/swarm.yaml`。它覆盖常用 required 和推荐 optional 字段，但默认不包含 MCP；只有用户明确需要外部工具接入时才添加 `mcp_servers` 和 agent `mcp`。新 manifest 统一使用 `permission`；`tools` 只是 legacy compatibility input，不放进新模板主路径。

```yaml
slug: expert-swarm-template
name: Expert Swarm Template
summary: Copyable expert team manifest with primary orchestration, subagents, local skills, and per-agent permissions.
objective: Deliver an expert workflow through delegated specialist work, evidence-backed acceptance, and final integration.
language: zh
common_skills:
  - expert-swarm-template-common

primary_agent:
  id: delivery-director
  title: Delivery Director
  description: Orchestrates the workflow, delegates specialist steps, accepts or rejects handoffs, and owns final quality.
  mode: primary
  color: "#2563eb"
  skills:
    - expert-swarm-template-delivery-review
  workflow:
    - Clarify the user goal, constraints, scope boundaries, and acceptance criteria.
    - Route each specialist step to one or more declared @subagent owners instead of doing the specialist work directly.
    - Dispatch @product-strategist and @domain-researcher in parallel only when their outputs are independently checkable and have no shared-write conflict.
    - Accept or re-dispatch each discovery branch with concrete failed criteria before implementation begins.
    - Ask @implementation-lead to produce the scoped implementation or delivery artifact after required discovery handoffs pass.
    - Ask @qa-reviewer to verify acceptance criteria, evidence, edge cases, and release readiness.
    - Integrate only accepted subagent outputs into the final response and record unresolved risks.
  quality_gates:
    - Every delegated task includes task, expected output, acceptance criteria, and required evidence.
    - Dependent steps wait for upstream acceptance unless the risk is explicitly waived.
    - Parallel branches must have separate outputs, separate acceptance criteria, and no shared mutable write target.
    - Failed checks are re-dispatched to the same responsible subagent with concrete feedback.
    - Final delivery cites evidence from accepted subagent handoffs.
  permission:
    read: allow
    edit: allow
    bash:
      "*": allow
      "git status*": allow
      "git diff*": allow
    webfetch: allow
    skill:
      "*": deny
      expert-swarm-template-common: allow
      expert-swarm-template-delivery-director: allow
      expert-swarm-template-delivery-review: allow
    task:
      "*": deny
      product-strategist: allow
      domain-researcher: allow
      implementation-lead: allow
      qa-reviewer: allow

subagents:
  - id: product-strategist
    title: Product Strategist
    description: Turns user intent into scope, user value, acceptance criteria, and out-of-scope boundaries.
    mode: subagent
    color: accent
    skills:
      - expert-swarm-template-product-brief
    responsibilities:
      - Convert ambiguous requests into concrete user stories, scope boundaries, and acceptance criteria.
      - Identify product risks, sequencing constraints, and questions that block downstream work.
    quality_gates:
      - Acceptance criteria are testable and tied to user value.
      - Handoff reports each criterion as pass, fail, or blocked.
      - Handoff names downstream dependencies for domain research, implementation, or QA.
    permission:
      read: allow
      edit: allow
      bash:
        "*": allow
        "git status*": allow
        "git diff*": allow
      webfetch: allow
      skill:
        "*": deny
        expert-swarm-template-common: allow
        expert-swarm-template-product-strategist: allow
        expert-swarm-template-product-brief: allow

  - id: domain-researcher
    title: Domain Researcher
    description: Inspects available context, documents, architecture, data, or market facts to ground the solution.
    mode: subagent
    color: warning
    skills:
      - expert-swarm-template-context-review
    responsibilities:
      - Gather relevant evidence from approved local files, docs, optional MCP entries, or web sources when allowed.
      - Separate verified facts from assumptions and call out missing context.
    quality_gates:
      - Findings cite concrete files, commands, URLs, or source names.
      - Handoff states whether the branch was independent or depended on product-strategist output.
      - Unverified assumptions are labeled before downstream work starts.
    permission:
      read: allow
      edit: allow
      bash:
        "*": allow
        "git status*": allow
        "git diff*": allow
      webfetch: allow
      skill:
        "*": deny
        expert-swarm-template-common: allow
        expert-swarm-template-domain-researcher: allow
        expert-swarm-template-context-review: allow

  - id: implementation-lead
    title: Implementation Lead
    description: Produces the scoped artifact or code change with minimal impact and reports exact verification.
    mode: subagent
    color: success
    skills:
      - expert-swarm-template-code-change
      - expert-swarm-template-test-runner
    responsibilities:
      - Reuse existing project patterns and make the smallest change that satisfies accepted criteria.
      - Avoid unrelated refactors, speculative flexibility, and formatting churn.
      - Return files changed, commands run, observed results, failed criteria, and residual risk.
    quality_gates:
      - Work starts only after required discovery branches are accepted or explicitly waived.
      - Relevant tests or checks are run, or the blocker is explained with evidence.
      - Handoff is ready for QA review without hidden follow-up assumptions.
    permission:
      read: allow
      edit: allow
      bash:
        "*": allow
        "git status*": allow
        "git diff*": allow
        "pnpm test*": allow
        "python -m pytest*": allow
      webfetch: allow
      skill:
        "*": deny
        expert-swarm-template-common: allow
        expert-swarm-template-implementation-lead: allow
        expert-swarm-template-code-change: allow
        expert-swarm-template-test-runner: allow

  - id: qa-reviewer
    title: QA Reviewer
    description: Verifies accepted criteria, checks edge cases, and decides whether delivery evidence is complete.
    mode: subagent
    color: info
    skills:
      - expert-swarm-template-test-plan
    responsibilities:
      - Turn acceptance criteria into verification scenarios.
      - Check regressions, edge cases, release risk, and evidence completeness.
      - Mark each criterion pass, fail, or blocked with concrete observations.
    quality_gates:
      - Verification includes commands, source evidence, or observed behavior.
      - Handoff identifies any failed or blocked criterion before final integration.
      - Residual risks and recommended re-dispatch targets are explicit.
    permission:
      read: allow
      edit: allow
      bash:
        "*": allow
        "git status*": allow
        "git diff*": allow
        "pnpm test*": allow
        "python -m pytest*": allow
      webfetch: allow
      skill:
        "*": deny
        expert-swarm-template-common: allow
        expert-swarm-template-qa-reviewer: allow
        expert-swarm-template-test-plan: allow
```

如果改 `slug`、agent id、自定义 skill 名称或 MCP 名称，同步改所有引用到这些名称的 `common_skills`、agent `skills`、`permission.skill`、`permission.task` 和 `mcp` 条目。没有配置 `mcp_servers` 时不要生成 MCP 占位；如果配置了 MCP，则生成条目保持 `enabled: false`，等用户填好真实 command、URL、headers、environment 后再另行启用。

## Interactive Manifest Confirmation

当用户没有上传或指定 `swarm.yaml` 时，不要直接生成项目包。先通过多轮对话把 manifest 收敛到可执行状态。

优先使用当前运行环境可用的 ask-user-question 工具。在 Codex Plan Mode 中，这通常是 `request_user_input`。如果当前环境没有这类工具，就用普通对话短问短答退化执行。每轮只问一个会改变 manifest 的问题，避免一次性抛出长表单。

在生成 `swarm.yaml` 之前尽可能频繁地使用 ask-user-question 工具确认会影响 manifest 的内容和细节，尤其是角色边界、候选技能、权限、workflow 顺序、并行批次和输出目录。不要把 finder 搜索结果静默写入 manifest。

## Skill Discovery Before Manifest

当用户没有完整 manifest，或 manifest 中 agent `skills` 缺失、过泛、与职责不匹配时，先做技能发现，再确认 YAML：

- 用 `find-skills` 查本地 Skills CLI / skills.sh 生态中可能适合的技能。
- 用 `internet-skill-finder` 查 verified GitHub repositories 中可能适合的 Agent Skills。
- 搜索词来自专家团目标、primary agent 职责、每个 subagent 职责、预期产物和关键工具链；每个角色至少考虑一次是否需要专属 skill。
- 展示候选时说明来源、适用角色、为什么匹配、以及它是“可安装外部 skill”“可转写成本地 supplemental skill”还是“仅作设计参考”。
- 搜索结果必须交给用户确认。不要自动安装外部 skill，不要静默复制外部 skill，不要因为搜索命中就把名字写入 `common_skills` 或 agent `skills`。
- Finder 结果只有在用户明确确认后才进入 manifest：可以转成生成器会创建的本地 supplemental skill 名称，也可以作为后续安装建议保留在说明中。
- 如果 finder 工具、网络或 CLI 不可用，说明限制，基于已知本地技能和用户回答继续确认；不要把不可验证候选当成已安装能力。

推荐问题顺序：

1. 目标和边界：专家团要解决什么任务，产出给谁看，哪些内容不在本轮范围。
2. 包名和语言：确认 `slug`、`name`、`objective`、`language`。
3. 主智能体：确认 primary agent 的 `id`、`title`、`description`、编排/验收所有权；primary 一般不直接执行专业工作流步骤。
4. 子智能体清单：确认每个 subagent 的职责边界；没有明确角色时，先建议 3-5 个角色。
5. 技能发现：基于目标和角色使用 `find-skills`、`internet-skill-finder` 搜索候选技能，询问用户哪些候选要转成本地 common/role/supplemental skill，哪些只作为外部安装建议，哪些跳过。
6. 工作流和质量门控：确认 primary 的阶段流转、`@subagent` 调用顺序或并行批次、每步验收条件，以及验收失败后带反馈重新派发同一子智能体的规则。
7. Skills 和 MCP：确认最终 `common_skills`、角色 skill、agent `skills`；只有用户明确需要 MCP 时才确认 MCP 占位，且 MCP 默认保持 `enabled: false`。
8. Agent 权限：确认每个智能体需要的 `permission`，尤其是 `edit`、`bash`、`webfetch`、`skill`、`task` 和 MCP tool glob。
9. 输出与覆盖：确认输出目录、是否 `--package`、已有目录是否允许 `--force`。

在生成前必须展示最终 `swarm.yaml` 草案，并明确等待用户确认。用户确认后再写 manifest、运行脚本和验证。若用户修改草案，先更新草案并再次确认，不要跳过 review gate。

已上传 manifest 时只做差异式追问：

- 缺少 required fields 时，只问缺失字段。
- 存在非法命名时，给出建议修正值并确认。
- primary/subagent 数量或职责冲突时，只问冲突点。
- agent `skills` 缺失、过泛、重复或与职责不匹配时，针对该角色运行 finder 搜索并询问是否转成本地 supplemental skill；不要重启完整访谈。
- MCP 写成启用时，说明本技能会把保留的 MCP 输出为 disabled 占位，并确认是否保留该 MCP 条目；如果 manifest 没有 MCP 需求，不要补默认 MCP 占位。

本技能可以借鉴“先理解、再提出选择、最后确认设计”的对话思想，但不要调用、依赖或要求加载外部 `brainstorming` 技能；两个技能保持独立。

本技能也可以借鉴 `goal-driven-development` 的 criteria-first acceptance、依赖步骤串行、独立步骤并行、restart/reassign 思想：先写清可验收标准，再派发执行，最后按证据验收；若未通过验收，primary 应带着失败原因和补救要求重新派发给相同职责的子智能体。不要调用、依赖或要求加载 `goal-driven-development`；这里只吸收其编排思想，不把它的 master/primary/grandchild 拓扑硬塞进专家团包。

## Generated Package

默认生成：

```text
<slug>/
  swarm.yaml
  opencode.json
  README.md
  .opencode/
    agents/
      <primary>.md
      <subagent>.md
    skills/
      <slug>-common/SKILL.md
      <slug>-<role>/SKILL.md
  dist/
    <slug>.tar.gz
```

## Design Rules

- 保持一个 `mode: primary` 主智能体，负责工作流编排、质量门控、对子智能体的 `@agent-id` 调用、逐步验收和最终集成。
- Primary 默认不直接执行专业工作流步骤；它应把每个可委派步骤发送给合适的 `@subagent`，再根据验收标准接受、拒绝或要求返工。
- 每次委派都要包含任务、预期产物、验收标准和需要返回的证据；若验收失败，primary 应把未通过项和补救要求发回同一个子智能体重新完成。
- 允许多智能体并行：当多个工作流步骤互不依赖、没有共享写入冲突、且输出可以分别验收时，primary 可以先并行派发多个 `@subagent`，再逐个验收结果。
- 依赖步骤必须串行：后续步骤需要前置产物、共享同一可变文件/资源、或验收标准互相耦合时，primary 应等前置结果验收通过后再派发下一步。
- 并行批次中某个分支未通过验收时，只重派失败分支；不要让已通过分支重复返工，也不要在必需分支未通过前推进依赖步骤。
- 每个子智能体使用 `mode: subagent`，职责单一，输出能被主智能体验收并直接合并。
- 子智能体输出应包含完成内容、证据、验收标准逐项状态、未通过项和剩余风险；不要只返回泛泛建议。
- 主智能体 `permission.task` 默认先 deny，再 allow manifest 中声明的子智能体。
- Agent prompt 同时写人类可读 `/skill-name` 标记和 `load/use skill <name>` 说明，贴合 skill discovery 机制。
- 每个智能体可用 `skills` 声明专属 skill；生成器会创建 skill 目录，并写入 `permission.skill` allowlist。
- `skills` 字段表示生成器会创建并允许的本地 supplemental skill，不代表外部 finder 命中的 skill 已安装或已复制进包；外部候选必须经用户确认后才转成本地 skill 名称。
- 每个智能体可用 `permission` 声明权限；生成器会把规范化后的同一份权限写入 `.md` frontmatter 和运行时配置。
- 通用 skill 放团队共识、交接格式和验证节奏；角色 skill 放该角色的方法、边界和质量门控。
- MCP 只在 manifest 显式配置 `mcp_servers` 时生成占位，不把远程 OAuth/API key 或本地命令默认打开；agent `mcp` 只控制该 agent 的 MCP tool glob 权限。

## Verification Checklist

生成后至少执行：

```bash
python /Users/xiaodong/.agents/skills/skill-creator/scripts/quick_validate.py \
  .opencode/skills/juzhigonfang-expert-agent-team-manager

python .opencode/skills/juzhigonfang-expert-agent-team-manager/scripts/validate_expert_team.py \
  <generated>/<slug>

python3 -m json.tool <generated>/<slug>/opencode.json
tar -tzf <generated>/<slug>/dist/<slug>.tar.gz
```

再做针对性检查：

- `opencode.json` 是否合法。
- 智能体定义目录是否有 1 个 primary 和至少 1 个 subagent。
- 技能目录是否包含 common skill 和每个角色的 role skill。
- 专属 skill 是否被创建，并出现在对应 agent 的 `permission.skill` allowlist 中。
- 同一 agent 在 `.md` frontmatter 和运行时配置中的 `permission` 是否一致。
- 若配置了 MCP，`enabled` 是否默认 `false`；若没有配置 MCP，运行时配置不应包含默认 MCP 占位。
- primary agent 是否包含 `@subagent` 路由、skill loading 指令、delegation-first 编排规则、串行/并行路由判断、步骤级验收和失败重派规则。
- subagent 和 role skill 是否要求返回证据、验收标准逐项状态、未通过项和风险。
- 没有真实 token、API key、私有 endpoint、未填 secret。
- 修改已有包时，确认 `swarm.yaml` 是变更来源，派生文件来自重生成，不是孤立手改。

## Safety Boundaries

- 不要生成真实密钥、真实 token、私有 URL 或凭据文件。
- 不要默认启用远程 MCP。
- 不要把其它执行底座配置混进默认专家团包，除非用户明确扩大范围。
- 不要修改用户现有全局运行配置；本技能只生成项目包。
- 如果用户要覆盖已有输出目录，先确认或使用明确的 `--force` 请求。

## Quick Test Prompts

- "创建一个软件开发专家团，主智能体是交付总监，子智能体有产品经理、架构师、工程师、QA，生成项目包。"
- "我想做一个投研专家团，主智能体统筹，子智能体有数据分析师、行业研究员、风险审查员，MCP 先禁用占位。"
- "根据这个 swarm.yaml 重新打包 agents 和 skills，检查运行时配置是否合法。"
- "把这份产品流程文档转成一个聚智工坊专家团，先提取角色和 SOP，再给我确认 swarm.yaml。"
- "修改已有专家团，只新增一个 risk-reviewer 子智能体，重新生成并验证。"
- "检查这个专家团包为什么不能用，不要重写文件，先给出失败原因。"

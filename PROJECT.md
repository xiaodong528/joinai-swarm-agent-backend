# Swarm Engine 项目说明

## 亚信/E2B OpenCode 对接方案摘要

当前项目已经实现 FastAPI + E2B Sandbox + OpenCode CLI 的专家生成和运行闭环。近期对接仍保持 E2B sandbox 和当前 `opencode run` 执行方式不变；`0.0.0.0:4096` 仅表示后续需要让外部能够访问 E2B sandbox 内的 OpenCode 服务/端口，不代表要把主执行链路改成 OpenCode Server API。

详细对接技术方案见 [README.md](README.md)。README 按两个视角组织：

- **上游调用方（亚信）**：说明当前调用 Swarm Engine 创建/生成/选择模板/运行 query 的流程，以及后续 S3、模型 JSON、代理协议的预留点。
- **E2B OpenCode Sandbox 内部**：说明当前专家文件加载、`opencode run` 执行、会话同步插件、状态 hook、制品路径，以及 `0.0.0.0:4096` 端口访问预留。

当前主要差距：

- 尚未启动/暴露 E2B sandbox 内的 OpenCode 访问端口 `0.0.0.0:4096`。
- Sandbox 适配层当前保持 E2B；CM Sandbox SDK 只作为未来替换点。
- 尚未实现专家依赖、模型 JSON、会话数据、制品产物到 S3 的同步。
- 尚未对齐模型 JSON/litellm schema、S3 目录、代理协议正式 payload。
- hook 当前主要做事件透传和本地 JSONL，尚未按代理协议拆出会话结束、运行失败、打断、超时等标准状态写入接口。

当前占位约定：

```text
s3://fake-joinai-swarm/{tenant_id}/{sandbox_id}/experts/{expert_id}/
s3://fake-joinai-swarm/{tenant_id}/{sandbox_id}/models/model.json
s3://fake-joinai-swarm/{tenant_id}/{sandbox_id}/sessions/{session_id}/
s3://fake-joinai-swarm/{tenant_id}/{sandbox_id}/artifacts/{session_id}/
```

## 目标

本项目实现一个多用户 E2B OpenCode Agent 模板生成引擎。

引擎接收用户 `query`，在 E2B 官方 `opencode` sandbox 中加载本地 OpenCode 模板和插件，让 OpenCode 基于模板生成新的专家团/agent 包。生成结果是标准 OpenCode 项目结构，供外部服务读取并同步到 S3。

原始模板和 skills 文件只读使用，不直接修改。

## 目录结构

```text
.
├── engine/                         # FastAPI 引擎实现
│   ├── app.py                      # HTTP API
│   ├── service.py                  # session 编排和生成流程
│   ├── sandbox.py                  # E2B 适配层
│   ├── assets.py                   # 模板和插件复制逻辑
│   ├── hooks.py                    # 生成 proxy-hooks.ts
│   ├── paths.py                    # 沙箱路径约定
│   ├── models.py                   # API 数据模型
│   ├── config.py                   # 环境变量配置
│   └── README.md                   # 引擎运行说明
├── scripts/
│   └── e2b_smoke.py                # 真实 E2B/OpenCode smoke 测试
├── tests/                          # 本地 fake sandbox 和 API 测试
├── juzhigonfang-team-manager-v0.1/ # 原始 OpenCode 模板，只读复制到沙箱
├── plugins/                        # 原始 session import/export 插件，只读复制到沙箱
├── pyproject.toml
└── PROJECT.md
```

## 核心设计

- 一个常驻 FastAPI 引擎服务支持多个用户。
- 隔离单位是 `user_id + session_id`。
- 一个 session 绑定一个 E2B sandbox。
- 同一个 session 的多次生成可以复用同一个 sandbox。
- 不同 session 使用不同 sandbox，避免文件和上下文污染。
- 引擎不直接和 S3 交互。
- 所有产出物、会话导出和状态文件写在 sandbox 本地路径，外部服务负责读取并同步 S3。

## 完整架构

本项目现在包含两条独立但可串联的引擎链路：

### 项目架构图

```mermaid
flowchart TD
    FE[前端/外部服务] -->|POST /v1/sessions| API[FastAPI Swarm Engine]
    FE -->|POST /v1/sessions/{id}/generate| API
    FE -->|GET /v1/templates| API
    FE -->|POST /v1/runtime-sessions| API
    FE -->|POST /v1/runtime-sessions/{id}/query| API

    API --> GEN[创建引擎 AgentEngineService]
    API --> REG[模板 Registry]
    API --> RUN[运行引擎 Runtime Session]

    GEN -->|create| GSBOX[E2B OpenCode 生成 Sandbox]
    GSBOX --> TMPL[/home/user/template<br/>专家团管理模板/]
    TMPL --> PLUGINS[session-export.ts<br/>session-import.ts<br/>proxy-hooks.ts]
    GEN -->|opencode run --agent expert-team-manager| TMPL
    TMPL --> PKG[生成 OpenCode 专家团包<br/>generated_package_path]
    GEN -->|validate_expert_team.py| PKG
    GEN -->|登记 template_id| REG
    REG --> META[template-&lt;template_id&gt;.json<br/>模板元数据]

    RUN -->|create| RSBOX[E2B OpenCode 运行 Sandbox]
    RUN -->|按 template_id 找源包| REG
    PKG -->|tar + base64| RSBOX
    RSBOX --> RPKG[/home/user/template/.runtime-sessions/&lt;runtime_session_id&gt;/package/]
    RUN -->|注入插件并合并 opencode.json| RPKG
    RUN -->|识别 mode: primary agent| RPKG
    RUN -->|opencode run --agent &lt;primary&gt;| RPKG

    RPKG --> RSTATE[runtime state.json<br/>events.jsonl<br/>last-result.txt]
    TMPL --> GSTATE[generation state.json<br/>events.jsonl<br/>last-result.txt]
    PLUGINS --> WEBHOOK[外部 webhook/status webhook]
    RPKG --> WEBHOOK
```

1. 创建引擎（generation engine）
   - 创建一个 E2B `opencode` sandbox。
   - 把本地 OpenCode 专家团管理模板复制到 `/home/user/template`。
   - 注入 `session-export.ts`、`session-import.ts`、`proxy-hooks.ts`。
   - 使用 `expert-team-manager` 处理用户生成需求，产出一个新的 OpenCode 专家团项目包。
   - 校验产物结构和 `validate_expert_team.py`。
   - 登记一个可被前端选择的模板记录，返回 `generated_package_path` 和 `data.template_id`。

2. 运行引擎（runtime engine）
   - 基于前端选择的 `template_id`，或创建引擎产出的 `generated_package_path`，创建一个新的 E2B `opencode` sandbox。
   - 从源 sandbox 将生成的 OpenCode 包打成 tar/base64，并导入到新 runtime sandbox 的：

     ```text
     /home/user/template/.runtime-sessions/<runtime_session_id>/package
     ```

   - 在导入后的包内重新注入同一组 OpenCode 插件，并把插件入口合并到包内 `opencode.json`。
   - 自动识别包内 `mode: primary` 的 agent，作为后续 query 的默认执行 agent。
   - 后续 query 在导入包目录中执行，让生成出来的专家团真正响应新的任务。

生成链路和运行链路的 sandbox 相互隔离：

```text
用户 query
  │
  ▼
创建引擎 session sandbox
  │  opencode run --agent expert-team-manager
  ▼
生成 OpenCode 专家团包 generated_package_path
  │
  ├─ 登记 template_id，供前端列表选择
  │
  ▼
前端选择 template_id
  │
  ▼
运行引擎 runtime sandbox
  │  导入生成包 + 注入 hooks/plugins
  ▼
runtime query
  │  opencode run --agent <generated-primary-agent>
  ▼
生成出来的专家团执行任务
```

## API

### 创建会话

```http
POST /v1/sessions
```

请求：

```json
{
  "user_id": "user-1",
  "webhook_url": "https://example.com/session-events",
  "session_status_url": "https://example.com/session-status",
  "keep_sandbox": true
}
```

返回包含：

- `session_id`
- `sandbox_id`
- `session_export_path`
- `state_path`

### 生成 OpenCode 专家团包

```http
POST /v1/sessions/{session_id}/generate
```

请求：

```json
{
  "user_id": "user-1",
  "query": "创建一个软件交付专家团队",
  "output_root": "exports/custom-output",
  "output_slug": "software-delivery-team"
}
```

字段说明：

- `query`: 用户生成需求。
- `output_root`: 可选，产出根目录。
- `output_slug`: 可选，产出包目录名。
- `sandbox_id`: 可选，用于外部服务显式校验 session 与 sandbox 绑定关系。
- `timeout_ms`: 可选，单次生成命令超时。

生成成功后，响应的 `data.template_id` 会标识本次生成出来的模板。前端应优先使用 `template_id` 创建运行会话，而不是自己拼 sandbox 路径。

每次生成成功也会在源 sandbox 写入模板元数据：

```text
/home/user/template/.engine-sessions/<session_id>/state/template-<template_id>.json
```

### 查询已生成模板列表

```http
GET /v1/templates?user_id=user-1
```

返回：

```json
[
  {
    "user_id": "user-1",
    "template_id": "...",
    "source_session_id": "...",
    "source_sandbox_id": "...",
    "package_path": "/home/user/template/exports/custom-output/software-delivery-team",
    "output_root": "/home/user/template/exports/custom-output",
    "output_slug": "software-delivery-team",
    "status": "validated",
    "created_at": "...",
    "data": {}
  }
]
```

### 查询单个模板详情

```http
GET /v1/templates/{template_id}?user_id=user-1
```

### 查询状态

```http
GET /v1/sessions/{session_id}/status?user_id=user-1
```

### 关闭会话

```http
POST /v1/sessions/{session_id}/close
```

请求：

```json
{
  "user_id": "user-1",
  "sandbox_id": "..."
}
```

### 创建运行会话

```http
POST /v1/runtime-sessions
```

请求：

```json
{
  "user_id": "user-1",
  "template_id": "<template-id>",
  "source_session_id": "<creation-session-id>",
  "source_sandbox_id": "<optional-source-sandbox-id>",
  "generated_package_path": "/home/user/template/exports/custom-output/software-delivery-team",
  "webhook_url": "https://example.com/runtime-events",
  "session_status_url": "https://example.com/runtime-status",
  "keep_sandbox": true
}
```

字段说明：

- `template_id`: 推荐，前端从 `GET /v1/templates` 选择的模板 id。
- `source_session_id`: 可选，兼容旧链路；没有 `template_id` 时必填。
- `source_sandbox_id`: 可选，用于显式校验源 session 与源 sandbox 绑定关系。
- `generated_package_path`: 可选；不传时优先使用模板记录的 `package_path`，否则使用源 session 已记录的 `generated_package_path`。
- `webhook_url`: 可选，runtime sandbox 内 OpenCode 事件 webhook。
- `session_status_url`: 可选，runtime sandbox 内 `session.*` 事件状态 webhook。
- `keep_sandbox`: 可选，关闭 runtime 会话后是否保留 sandbox。

返回包含：

- `runtime_session_id`
- `sandbox_id`
- `source_session_id`
- `source_sandbox_id`
- `source_package_path`
- `runtime_package_path`
- `session_export_path`
- `state_path`
- `data.primary_agent`

前端推荐流程：

```text
1. POST /v1/sessions
2. POST /v1/sessions/{session_id}/generate
3. 读取响应 data.template_id
4. GET /v1/templates?user_id=...
5. 用户选择模板
6. POST /v1/runtime-sessions，传 template_id
7. POST /v1/runtime-sessions/{runtime_session_id}/query
```

### 执行运行会话 Query

```http
POST /v1/runtime-sessions/{runtime_session_id}/query
```

请求：

```json
{
  "user_id": "user-1",
  "query": "用刚生成的专家团分析这个需求",
  "sandbox_id": "<optional-runtime-sandbox-id>",
  "agent": "<optional-agent-id>",
  "timeout_ms": 600000
}
```

字段说明：

- `query`: 要交给生成出来的 OpenCode 专家团执行的新任务。
- `sandbox_id`: 可选，用于显式校验 runtime session 与 sandbox 绑定关系。
- `agent`: 可选；不传时使用运行引擎从 `opencode.json` 识别出的 primary agent。
- `timeout_ms`: 可选，单次执行超时。

执行命令：

```bash
opencode run --agent <agent> <query>
```

命令工作目录是：

```text
/home/user/template/.runtime-sessions/<runtime_session_id>/package
```

### 查询运行会话状态

```http
GET /v1/runtime-sessions/{runtime_session_id}/status?user_id=user-1
```

### 关闭运行会话

```http
POST /v1/runtime-sessions/{runtime_session_id}/close
```

请求：

```json
{
  "user_id": "user-1",
  "sandbox_id": "..."
}
```

## 沙箱路径约定

模板复制到：

```text
/home/user/template
```

默认 session 数据：

```text
/home/user/template/.engine-sessions/<session_id>/
├── swarm.yaml
├── generated/
├── session-export/
└── state/
    ├── status.json
    ├── events.jsonl
    ├── webhook-dead-letter.jsonl
    ├── last-query.txt
    ├── last-prompt.txt
    └── last-result.txt
```

默认 runtime session 数据：

```text
/home/user/template/.runtime-sessions/<runtime_session_id>/
├── package/
│   ├── swarm.yaml
│   ├── opencode.json
│   ├── README.md
│   └── .opencode/
├── session-export/
└── state/
    ├── status.json
    ├── events.jsonl
    ├── webhook-dead-letter.jsonl
    ├── last-query.txt
    ├── last-result.txt
    └── source-package.tar.gz.b64
```

自定义产出目录：

```text
/home/user/template/<output_root>/<output_slug>
```

重要限制：

- `output_root` 可以是相对路径，例如 `exports/custom-output`。
- 相对路径会解析到 `/home/user/template/<output_root>`。
- 绝对路径必须位于 `/home/user/template` 内。
- 不允许写 `/home/user/sessions`、`/tmp` 等项目外路径，否则 OpenCode 会触发 `external_directory auto-rejecting`。

## 产出物结构

生成结果是标准 OpenCode 项目包：

```text
<slug>/
├── swarm.yaml
├── opencode.json
├── README.md
├── dist/
│   └── <slug>.tar.gz
└── .opencode/
    ├── agents/
    │   ├── <primary-agent>.md
    │   └── <subagent>.md
    └── skills/
        └── <skill-name>/
            └── SKILL.md
```

## Hook 和会话导出

引擎会把以下插件复制到 sandbox 模板内：

```text
/home/user/template/.opencode/plugins/session-export.ts
/home/user/template/.opencode/plugins/session-import.ts
/home/user/template/.opencode/plugins/proxy-hooks.ts
```

`proxy-hooks.ts` 负责：

- 监听 OpenCode session/message 事件。
- 写入 `state/events.jsonl`。
- 如果配置了 webhook，则 POST 到外部代理服务。
- webhook 失败时写入 `state/webhook-dead-letter.jsonl`。

运行引擎导入生成包后，也会把同一组插件写入 runtime package 的 `.opencode/plugins/`，并把插件路径合并到 runtime package 的 `opencode.json`。因此 runtime query 也会产生：

- `state/events.jsonl`
- `state/webhook-dead-letter.jsonl`
- `session-export/<opencode-session-id>.json`

事件结构首版为：

```json
{
  "version": 1,
  "user_id": "...",
  "session_id": "...",
  "sandbox_id": "...",
  "event_type": "...",
  "status": "...",
  "timestamp": "...",
  "data": {}
}
```

## 配置

运行时环境变量：

```text
E2B_API_KEY              # 宿主侧创建/连接 E2B sandbox
DEEPSEEK_API_KEY         # 注入 sandbox，供 OpenCode provider 使用
OPENCODE_MODEL           # 默认 deepseek/deepseek-v4-pro
E2B_OPENCODE_TEMPLATE    # 默认 opencode
E2B_TIMEOUT_SECONDS      # 默认 1800
ENGINE_DEFAULT_TIMEOUT_MS # 默认 600000
```

密钥约束：

- 不把 key 写入源码。
- 不把 key 写入生成文件。
- 不把 `E2B_API_KEY` 注入 sandbox。
- `DEEPSEEK_API_KEY` 只作为 sandbox 运行时环境变量使用。

## 真实测试记录

已跑通过真实 E2B/OpenCode smoke。

测试 query：

```text
创建最小专家团：一个主智能体和一个QA子智能体
```

自定义输出：

```text
output_root = exports/custom-output
output_slug = custom-qa-team
```

结果：

```text
status = validated
sandbox_id = i3owvzs8djsj79ulou0ac
session_id = fde41df3eae0470389ab43d71b6fac35
generated_package_path = /home/user/template/exports/custom-output/custom-qa-team
validation_stdout = Expert team package is valid.
```

## 真实 Runtime Smoke 记录

已跑通过真实“创建引擎 + 运行引擎”端到端 smoke。

生成请求：

```text
query = Create a minimal expert team with one primary agent and one QA subagent. Use slug runtime-smoke-team.
output_root = exports/runtime-smoke
output_slug = runtime-smoke-team
```

创建引擎结果：

```text
status = validated
sandbox_id = ig5e4cs2dn962qv8lwaj0
session_id = 9a275edd2d164fb4abf544d9070aa626
generated_package_path = /home/user/template/exports/runtime-smoke/runtime-smoke-team
validation_stdout = Expert team package is valid.
```

运行引擎结果：

```text
status = ready
sandbox_id = isc6vwax3xelcad1v2hji
runtime_session_id = 871d35cdd5664506915c1d670d7edc7c
runtime_package_path = /home/user/template/.runtime-sessions/871d35cdd5664506915c1d670d7edc7c/package
primary_agent = smoke-orchestrator
```

Runtime query：

```text
query = Reply in one short sentence that the generated team is loaded.
status = validated
stdout = The generated team is loaded and ready to orchestrate.
last_result_path = /home/user/template/.runtime-sessions/871d35cdd5664506915c1d670d7edc7c/state/last-result.txt
```

## 真实 Template Picker Runtime Smoke 记录

已跑通过“生成模板 -> 前端列表选择 template_id -> 运行引擎按 template_id 创建 runtime -> query”的真实 smoke。

```text
created_status = ready
generated_status = validated
template_count = 1
template_id = c101aa0f28c04e57bbdfe44b92c1ebf2
generated_package_path = /home/user/template/exports/template-picker-smoke/template-picker-smoke-team
runtime_status = ready
runtime_query_status = validated
primary_agent = template-picker
runtime_stdout = Template picker runtime works.
runtime_session_id = bd15073498cf4b0880a8ec2a3744eb4f
runtime_sandbox_id = iu2p0q16d17jufu5s2nro
```

## 本地测试

```bash
python -m pytest -q
```

当前结果：

```text
11 passed
```

## 真实 E2B Smoke

先设置环境变量，再运行：

```bash
python scripts/e2b_smoke.py \
  --query "创建最小专家团：一个主智能体和一个QA子智能体" \
  --output-root "exports/custom-output" \
  --output-slug "custom-qa-team" \
  --keep-sandbox
```

如果只想验证 sandbox 创建和模板初始化，不跑生成：

```bash
python scripts/e2b_smoke.py --keep-sandbox
```

## 修改注意事项

- 不要直接修改 `juzhigonfang-team-manager-v0.1/.../.opencode/skills` 原始文件。
- 不要直接修改 `plugins/plugins/session-export.ts` 和 `session-import.ts` 原始文件，除非用户明确要求修改插件源。
- 如需调整运行时行为，优先改 `engine/`，让引擎在 sandbox 内复制和生成派生产物。
- 产出目录必须保持在 `/home/user/template` 内，避免 OpenCode 外部目录权限拒绝。
- 生成状态不能只看 `opencode run` 退出码，必须继续检查产出结构并运行 `validate_expert_team.py`。
- E2B sandbox 默认生命周期可能不够，当前通过 `E2B_TIMEOUT_SECONDS=1800` 延长。

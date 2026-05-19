# OpenCode E2B 后端

这个服务接收前端传入的 OpenCode 配置 JSON，把配置拆成 OpenCode 认识的文件，写入 E2B 官方 `opencode` 模板沙箱，然后按需执行 `opencode run` 或启动 `opencode serve`。

## 已支持的配置

接口：`POST /v1/opencode/provision`

支持前端传入：

- `provider`: 模型供应商配置，写入 `opencode.json.provider`，并设置默认 `model`
- `mcp`: MCP server 配置，合并进 `opencode.json.mcp`
- `agent_config`: JSON agent 配置，合并进 `opencode.json.agent`
- `skills`: 生成 `skills/<name>/SKILL.md`
- `agents`: 生成 `agents/<name>.md`
- `config`: 其它 OpenCode 原生配置，直接合并进 `opencode.json`
- `query`: 如果传入，后端直接执行 `opencode run`
- `launch`: 如果没有 `query` 且 `launch.enabled=true`，后端启动 `opencode serve`

## 文件落点

项目级 `scope=project`：

- `<workspace_path>/opencode.json`
- `<workspace_path>/.opencode/skills/<name>/SKILL.md`
- `<workspace_path>/.opencode/agents/<name>.md`

全局级 `scope=global`：

- `~/.config/opencode/opencode.json`
- `~/.config/opencode/skills/<name>/SKILL.md`
- `~/.config/opencode/agents/<name>.md`

E2B 官方 `opencode` 模板里建议使用 `/home/user/workspace` 作为项目工作目录。

## 完整请求示例

```json
{
  "scope": "project",
  "workspace_path": "/home/user/workspace",
  "provider": {
    "id": "deepseek",
    "name": "DeepSeek",
    "npm": "@ai-sdk/openai-compatible",
    "base_url": "https://api.deepseek.com",
    "api_key": "sk-...",
    "model_name": "deepseek-v4-pro"
  },
  "mcp": {
    "context7": {
      "type": "remote",
      "url": "https://mcp.context7.com/mcp"
    }
  },
  "agent_config": {
    "reviewer": {
      "description": "Review code changes",
      "model": "deepseek/deepseek-v4-pro",
      "prompt": "Focus on correctness, edge cases, and missing tests."
    }
  },
  "skills": [
    {
      "name": "frontend-builder",
      "description": "Build small frontend apps",
      "frontmatter": {
        "category": "frontend"
      },
      "content": "When building UI, create complete runnable files and keep the layout simple."
    }
  ],
  "agents": [
    {
      "name": "calculator-agent",
      "description": "Creates calculator examples",
      "frontmatter": {
        "model": "deepseek/deepseek-v4-pro"
      },
      "content": "You create concise calculator implementations with clear input validation."
    }
  ],
  "config": {
    "permission": {
      "write": "allow"
    }
  },
  "query": "帮我写一个加法计算器",
  "launch": {
    "enabled": true,
    "command": ["opencode", "serve"],
    "port": 4096,
    "hostname": "0.0.0.0",
    "timeout": 600
  }
}
```

上面的请求会写出：

- `/home/user/workspace/opencode.json`
- `/home/user/workspace/.opencode/skills/frontend-builder/SKILL.md`
- `/home/user/workspace/.opencode/agents/calculator-agent.md`

如果传入 `query`，服务会执行：

```bash
opencode run --format json --model deepseek/deepseek-v4-pro "帮我写一个加法计算器"
```

如果不传 `query`，并且 `launch.enabled=true`，服务会启动：

```bash
opencode serve --hostname 0.0.0.0 --port 4096
```

## DeepSeek 两种接口

OpenAI-compatible：

```json
{
  "id": "deepseek",
  "name": "DeepSeek",
  "npm": "@ai-sdk/openai-compatible",
  "base_url": "https://api.deepseek.com",
  "api_key": "sk-...",
  "model_name": "deepseek-v4-pro"
}
```

Anthropic-compatible：

```json
{
  "id": "deepseek-anthropic",
  "name": "DeepSeek Anthropic",
  "npm": "@ai-sdk/anthropic",
  "base_url": "https://api.deepseek.com/anthropic",
  "api_key": "sk-...",
  "model_name": "deepseek-v4-pro"
}
```

两种方式已经用 E2B 官方 `opencode` 模板真实跑通过。

## 环境变量

- `OPENCODE_BACKEND=e2b|local`
- `E2B_API_KEY=e2b_...`

不要把真实 API key 写入仓库文件。生产调用时由部署环境注入。

## Conda 环境

```powershell
conda create -y -p .\.conda python=3.12
.\.conda\python.exe -m pip install --ignore-installed -r requirements-dev.txt
```

## 本地运行

```powershell
$env:OPENCODE_BACKEND='local'
.\.conda\python.exe -m uvicorn opencode_backend.main:app --reload
```

## 测试

```powershell
$env:PYTHONNOUSERSITE='1'
.\.conda\python.exe -m pytest -q
```

真实 E2B 冒烟测试：

```powershell
$env:PYTHONNOUSERSITE='1'
$env:PYTHONPATH='.'
$env:E2B_API_KEY='e2b_...'
$env:OPENCODE_PROVIDER_KEY='sk-...'
.\.conda\python.exe scripts\backend_e2b_query_smoke.py
```


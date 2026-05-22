# Persistent Chat Sessions

This backend now supports two execution modes:

- One-shot OpenCode provisioning through the existing `/v1/opencode/*` and `/rpc` APIs.
- Persistent chat sessions through `/v1/chat/*`, with stored history, per-user isolation, encrypted provider secrets, sandbox reuse, and recovery after the user leaves.

The existing one-shot APIs are unchanged.

## Runtime Model

Persistent chat sessions are stored in SQLite. Each session stores:

- owner id from the `Authorization: Bearer ...` token
- title, scope, workspace path
- provider config with `api_key` encrypted at rest
- OpenCode config, MCP config, skills, agents, launch config, and A2A config
- user and assistant messages
- run records and A2A/AG-UI output
- active sandbox binding metadata

When a session has an active in-process sandbox, later turns reuse that sandbox and pass the stored OpenCode `sessionID` to `opencode run --session`.

If the backend process was restarted or the user returns after the in-process sandbox is gone, the backend creates a new sandbox and rebuilds context from the stored message history. It does not pass a stale OpenCode `sessionID` to a new sandbox.

## Environment Variables

Required:

```powershell
$env:CHAT_SECRET_KEY='replace-with-a-long-random-secret'
```

Recommended:

```powershell
$env:CHAT_DATABASE_URL='sqlite:///./opencode_backend.db'
$env:CHAT_SANDBOX_TTL_SECONDS='3600'
$env:CHAT_RUN_WORKERS='4'
```

For real E2B execution:

```powershell
$env:OPENCODE_BACKEND='e2b'
$env:E2B_API_KEY='e2b_...'
```

For local tests:

```powershell
$env:OPENCODE_BACKEND='local'
```

## Authentication

Every `/v1/chat/*` request requires:

```http
Authorization: Bearer <token>
```

If the token is a JWT-like string, the backend uses the payload `sub` as the owner id. Otherwise, it uses the bearer token string as the owner id. This is a lightweight boundary for the current backend; production deployments should replace it with a real auth dependency.

## API

Create a session:

```http
POST /v1/chat/sessions
Authorization: Bearer user-a
Content-Type: application/json
```

```json
{
  "title": "Math helper",
  "scope": "project",
  "workspace_path": "/home/user/workspace/math",
  "provider": {
    "id": "deepseek",
    "name": "DeepSeek",
    "npm": "@ai-sdk/openai-compatible",
    "base_url": "https://api.deepseek.com",
    "api_key": "sk-...",
    "model_name": "deepseek-v4-pro"
  },
  "skills": [
    {
      "name": "math-solver",
      "description": "Solve arithmetic problems",
      "content": "Return concise numeric answers."
    }
  ],
  "mcp": {
    "math-tools": {
      "type": "remote",
      "url": "https://example.invalid/math-mcp"
    }
  },
  "a2a": {
    "enabled": false,
    "port": 8201,
    "database_url": "sqlite+aiosqlite:///./math-a2a.db"
  }
}
```

Run a turn:

```http
POST /v1/chat/sessions/{session_id}/runs
Authorization: Bearer user-a
Content-Type: application/json
```

```json
{
  "message": "Compute 19 * 23. Return only the answer."
}
```

Check a run:

```http
GET /v1/chat/sessions/{session_id}/runs/{run_id}
Authorization: Bearer user-a
```

Restore a session:

```http
GET /v1/chat/sessions/{session_id}
Authorization: Bearer user-a
```

List sessions:

```http
GET /v1/chat/sessions
Authorization: Bearer user-a
```

Delete a session:

```http
DELETE /v1/chat/sessions/{session_id}
Authorization: Bearer user-a
```

## Concurrency

Different sessions can run in parallel. The backend creates separate sandbox bindings for each session.

The same session is protected by an active-run guard. If a session already has a `queued` or `running` run, starting another run returns `409`.

## Real Smoke Result

A real E2B + DeepSeek smoke was run with three concurrent sessions:

- math query: returned `437`
- code query: returned a Python `add(a, b)` function
- document summary query: returned a one-sentence summary

The three sessions used three different E2B sandbox ids. A later restore test created a new sandbox and continued from stored history, returning `19` for `9 + 10`.

## Tests

Run all tests:

```powershell
$env:PYTHONNOUSERSITE='1'
.\.conda\python.exe -m pytest -q
```

Focused persistent-session tests:

```powershell
$env:PYTHONNOUSERSITE='1'
.\.conda\python.exe -m pytest tests\test_chat_api.py -q
```

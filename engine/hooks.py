from __future__ import annotations

import json


def proxy_hooks_plugin() -> str:
    """Return the OpenCode plugin used to mirror events into local files and optional webhooks."""
    return r'''import { type Plugin } from "@opencode-ai/plugin"
import fs from "node:fs/promises"
import path from "node:path"

type Obj = Record<string, unknown>

const sessionID = process.env.ENGINE_SESSION_ID || "unknown"
const userID = process.env.ENGINE_USER_ID || "unknown"
const sandboxID = process.env.ENGINE_SANDBOX_ID || "unknown"
const eventsFile = process.env.ENGINE_EVENTS_FILE || `/home/user/template/.engine-sessions/${sessionID}/state/events.jsonl`
const deadLetterFile =
  process.env.ENGINE_DEAD_LETTER_FILE || `/home/user/template/.engine-sessions/${sessionID}/state/webhook-dead-letter.jsonl`
const webhook = process.env.ENGINE_WEBHOOK_URL
const statusWebhook = process.env.ENGINE_STATUS_WEBHOOK_URL

async function append(file: string, payload: Obj) {
  await fs.mkdir(path.dirname(file), { recursive: true })
  await fs.appendFile(file, `${JSON.stringify(payload)}\n`, "utf8")
}

async function post(url: string | undefined, payload: Obj) {
  if (!url) return
  try {
    const res = await fetch(url, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload),
    })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
  } catch (err) {
    await append(deadLetterFile, {
      ...payload,
      deliveryError: err instanceof Error ? err.message : String(err),
    })
  }
}

function payload(eventType: string, status: string, data: Obj) {
  return {
    version: 1,
    user_id: userID,
    session_id: sessionID,
    sandbox_id: sandboxID,
    event_type: eventType,
    status,
    timestamp: new Date().toISOString(),
    data,
  }
}

export const ProxyHooks: Plugin = async ({ client }) => {
  await client.app
    .log({
      body: {
        service: "proxy-hooks",
        level: "info",
        message: "proxy hooks plugin initialized",
        extra: { sessionID, eventsFile },
      },
    })
    .catch(() => undefined)

  return {
    event: async ({ event }) => {
      const evt = event as Obj
      const type = typeof evt.type === "string" ? evt.type : "unknown"
      const item = payload(type, "running", evt)
      await append(eventsFile, item)
      const target = type.startsWith("session.") ? statusWebhook || webhook : webhook
      await post(target, item)
    },
  }
}
'''


def plugin_config_entries() -> list[str]:
    return [
        "./.opencode/plugins/session-export.ts",
        "./.opencode/plugins/session-import.ts",
        "./.opencode/plugins/proxy-hooks.ts",
    ]


def merge_plugin_config(raw: str, model: str) -> str:
    data = json.loads(raw)
    plugins = list(data.get("plugin") or [])
    for item in plugin_config_entries():
        if item not in plugins:
            plugins.append(item)
    data["plugin"] = plugins
    data.setdefault("model", model)
    providers = dict(data.get("provider") or {})
    deepseek = dict(providers.get("deepseek") or {})
    deepseek.setdefault("env", ["DEEPSEEK_API_KEY"])
    providers["deepseek"] = deepseek
    data["provider"] = providers
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"

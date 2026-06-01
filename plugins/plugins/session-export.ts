import { tool, type Plugin } from "@opencode-ai/plugin"
import fs from "node:fs/promises"
import path from "node:path"

type Obj = Record<string, unknown>
type Msg = {
  info: Obj
  parts: Obj[]
}

type Snap = {
  version: 1
  exportedAt: number
  project: unknown
  directory: string
  worktree: string
  session: unknown
  messages: Msg[]
  diff: unknown[]
  todos: unknown[]
  deleted?: boolean
}

const wait = Number(process.env.OPENCODE_SESSION_EXPORT_DEBOUNCE_MS ?? 300)

function safe(value: string) {
  return value.replace(/[^a-zA-Z0-9._-]/g, "_")
}

function id(value: unknown) {
  if (!value || typeof value !== "object") return
  const item = value as { id?: unknown }
  return typeof item.id === "string" ? item.id : undefined
}

function session(event: Obj) {
  const props = event.properties
  if (!props || typeof props !== "object") return
  const data = props as { sessionID?: unknown; info?: unknown; part?: unknown }
  if (typeof data.sessionID === "string") return data.sessionID
  if (data.info && typeof data.info === "object") {
    const info = data.info as { id?: unknown; sessionID?: unknown }
    const type = typeof event.type === "string" ? event.type : ""
    if (typeof info.sessionID === "string") return info.sessionID
    if (typeof info.id === "string" && type.startsWith("session.")) return info.id
  }
  if (data.part && typeof data.part === "object") {
    const part = data.part as { sessionID?: unknown }
    if (typeof part.sessionID === "string") return part.sessionID
  }
}

function sort(list: Obj[]) {
  return list.sort((a, b) => String(a.id ?? "").localeCompare(String(b.id ?? "")))
}

function upsert(list: Obj[], item: Obj) {
  const found = list.findIndex((x) => x.id === item.id)
  if (found >= 0) {
    list[found] = item
    return
  }
  list.push(item)
  sort(list)
}

function remove(list: Obj[], value: string) {
  const index = list.findIndex((x) => x.id === value)
  if (index >= 0) list.splice(index, 1)
}

function response<T>(value: { data?: T }) {
  return value.data
}

export const SessionExport: Plugin = async ({ client, project, directory, worktree }) => {
  const root = process.env.OPENCODE_SESSION_EXPORT_DIR || path.join(worktree || directory, ".opencode", "session-export")
  const snaps = new Map<string, Snap>()
  const timers = new Map<string, ReturnType<typeof setTimeout>>()
  const loading = new Set<string>()

  await fs.mkdir(root, { recursive: true })

  async function log(level: "info" | "warn" | "error", message: string, extra?: Obj) {
    await client.app
      .log({
        body: {
          service: "session-export",
          level,
          message,
          extra,
        },
      })
      .catch(() => undefined)
  }

  async function write(sessionID: string) {
    const snap = snaps.get(sessionID)
    if (!snap) return
    const file = path.join(root, `${safe(sessionID)}.json`)
    const tmp = `${file}.${process.pid}.tmp`
    snap.exportedAt = Date.now()
    await Bun.write(tmp, JSON.stringify(snap, null, 2))
    await fs.rename(tmp, file)
  }

  function queue(sessionID: string) {
    const timer = timers.get(sessionID)
    if (timer) clearTimeout(timer)
    timers.set(
      sessionID,
      setTimeout(() => {
        timers.delete(sessionID)
        write(sessionID).catch((err) => {
          log("error", "failed to write session export", {
            sessionID,
            error: err instanceof Error ? err.message : String(err),
          })
        })
      }, wait),
    )
  }

  async function sync(sessionID: string) {
    if (loading.has(sessionID)) return
    loading.add(sessionID)
    try {
      const [info, messages, diff, todos] = await Promise.all([
        client.session.get({ path: { id: sessionID }, query: { directory } }).then(response),
        client.session.messages({ path: { id: sessionID }, query: { directory } }).then((x) => response(x) ?? []),
        client.session.diff({ path: { id: sessionID }, query: { directory } }).then((x) => response(x) ?? []),
        client.session.todo({ path: { id: sessionID }, query: { directory } }).then((x) => response(x) ?? []),
      ])
      if (!info) return
      snaps.set(sessionID, {
        version: 1,
        exportedAt: Date.now(),
        project,
        directory,
        worktree,
        session: info,
        messages: messages as Msg[],
        diff: diff as unknown[],
        todos: todos as unknown[],
      })
      queue(sessionID)
    } catch (err) {
      await log("warn", "failed to sync session export", {
        sessionID,
        error: err instanceof Error ? err.message : String(err),
      })
    } finally {
      loading.delete(sessionID)
    }
  }

  function ensure(sessionID: string) {
    const snap = snaps.get(sessionID)
    if (snap) return snap
    sync(sessionID)
  }

  function message(snap: Snap, messageID: string) {
    return snap.messages.find((item) => item.info.id === messageID)
  }

  await log("info", "session export plugin initialized", { root })

  return {
    event: async ({ event }) => {
      const evt = event as Obj
      const sessionID = session(evt)
      if (!sessionID) return

      const props = evt.properties && typeof evt.properties === "object" ? (evt.properties as Obj) : {}
      const snap = snaps.get(sessionID)

      switch (evt.type) {
        case "session.created":
        case "session.updated": {
          if (snap) {
            snap.session = props.info
            snap.deleted = undefined
            queue(sessionID)
            return
          }
          ensure(sessionID)
          return
        }
        case "session.deleted": {
          const next =
            snap ??
            ({
              version: 1,
              exportedAt: Date.now(),
              project,
              directory,
              worktree,
              session: props.info,
              messages: [],
              diff: [],
              todos: [],
            } satisfies Snap)
          next.session = props.info
          next.deleted = true
          snaps.set(sessionID, next)
          queue(sessionID)
          return
        }
        case "message.updated": {
          if (!snap) {
            ensure(sessionID)
            return
          }
          const info = props.info
          if (!info || typeof info !== "object") return
          const item = message(snap, id(info) ?? "")
          if (item) item.info = info as Obj
          else snap.messages.push({ info: info as Obj, parts: [] })
          snap.messages.sort((a, b) => String(a.info.id ?? "").localeCompare(String(b.info.id ?? "")))
          queue(sessionID)
          return
        }
        case "message.removed": {
          if (!snap) return
          if (typeof props.messageID === "string") {
            const index = snap.messages.findIndex((item) => item.info.id === props.messageID)
            if (index >= 0) snap.messages.splice(index, 1)
            queue(sessionID)
          }
          return
        }
        case "message.part.updated": {
          if (!snap) {
            ensure(sessionID)
            return
          }
          const part = props.part
          if (!part || typeof part !== "object") return
          const data = part as Obj
          const messageID = typeof data.messageID === "string" ? data.messageID : ""
          const item = message(snap, messageID)
          if (!item) {
            ensure(sessionID)
            return
          }
          upsert(item.parts, data)
          queue(sessionID)
          return
        }
        case "message.part.delta": {
          if (!snap) return
          if (typeof props.messageID !== "string") return
          if (typeof props.partID !== "string") return
          if (typeof props.field !== "string") return
          if (typeof props.delta !== "string") return
          const item = message(snap, props.messageID)
          const part = item?.parts.find((x) => x.id === props.partID)
          if (!part) return
          const value = part[props.field]
          part[props.field] = (typeof value === "string" ? value : "") + props.delta
          queue(sessionID)
          return
        }
        case "message.part.removed": {
          if (!snap) return
          if (typeof props.messageID !== "string") return
          if (typeof props.partID !== "string") return
          const item = message(snap, props.messageID)
          if (!item) return
          remove(item.parts, props.partID)
          queue(sessionID)
          return
        }
        case "session.diff": {
          if (!snap) {
            ensure(sessionID)
            return
          }
          snap.diff = Array.isArray(props.diff) ? props.diff : []
          queue(sessionID)
          return
        }
        case "todo.updated": {
          if (!snap) {
            ensure(sessionID)
            return
          }
          snap.todos = Array.isArray(props.todos) ? props.todos : []
          queue(sessionID)
          return
        }
      }
    },
  }
}

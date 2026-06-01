import { tool, type Plugin } from "@opencode-ai/plugin"
import fs from "node:fs/promises"
import os from "node:os"
import path from "node:path"

type Obj = Record<string, unknown>

const guard = "OPENCODE_SESSION_IMPORT_CHILD"

function file(input: string, dir: string) {
  if (path.isAbsolute(input)) return input
  return path.resolve(dir, input)
}

function text(input: unknown) {
  if (input instanceof Uint8Array) return new TextDecoder().decode(input)
  if (typeof input === "string") return input
  return String(input ?? "")
}

function split(input: string) {
  return input.match(/(?:[^\s"]+|"[^"]*")+/g)?.map((item) => item.replace(/^"|"$/g, "")) ?? []
}

function importable(input: Obj) {
  if (input.info && Array.isArray(input.messages)) return input
  if (input.session && Array.isArray(input.messages)) {
    return {
      info: input.session,
      messages: input.messages,
    }
  }
}

async function run(cmd: string[], dir: string) {
  const proc = Bun.spawn(cmd, {
    cwd: dir,
    env: {
      ...process.env,
      [guard]: "1",
    },
    stdout: "pipe",
    stderr: "pipe",
  })
  const [out, err, code] = await Promise.all([new Response(proc.stdout).text(), new Response(proc.stderr).text(), proc.exited])
  return { out, err, code }
}

function cmds(tmp: string) {
  const list: string[][] = []
  const env = process.env.OPENCODE_SESSION_IMPORT_CMD
  if (env) list.push(split(env))
  if (process.argv[1]) list.push([process.execPath, process.argv[1]])
  list.push(["opencode"])
  return list.map((cmd) => [...cmd, "import", tmp])
}

async function files(input: string, dir: string) {
  const src = file(input, dir)
  const stat = await fs.stat(src)
  if (stat.isFile()) return [src]
  const all = await fs.readdir(src)
  return all.filter((item) => item.endsWith(".json")).map((item) => path.join(src, item))
}

export const SessionImport: Plugin = async ({ client, directory }) => {
  async function log(level: "info" | "warn" | "error", message: string, extra?: Obj) {
    await client.app
      .log({
        body: {
          service: "session-import",
          level,
          message,
          extra,
        },
      })
      .catch(() => undefined)
  }

  await log("info", "session import plugin initialized")

  async function load(src: string, dir: string) {
    const raw = await fs.readFile(src, "utf8")
    const data = JSON.parse(raw) as Obj
    const body = importable(data)
    if (!body) {
      throw new Error("Unsupported session JSON. Expected { info, messages } or { session, messages }.")
    }

    const tmpdir = await fs.mkdtemp(path.join(os.tmpdir(), "opencode-session-import-"))
    const tmp = path.join(tmpdir, "session.json")
    try {
      await Bun.write(tmp, JSON.stringify(body, null, 2))

      const tried: string[] = []
      let last = ""
      for (const cmd of cmds(tmp)) {
        tried.push(cmd.join(" "))
        const result = await run(cmd, dir).catch((err) => ({
          out: "",
          err: err instanceof Error ? err.message : String(err),
          code: 1,
        }))
        last = text(result.err || result.out).trim()
        if (result.code !== 0) continue
        await log("info", "session imported", { file: src, output: result.out.trim() })
        return text(result.out || result.err).trim() || "Session imported."
      }

      throw new Error(`Import failed. Tried: ${tried.join("; ")}${last ? ` Last error: ${last}` : ""}`)
    } finally {
      await fs.rm(tmpdir, { recursive: true, force: true }).catch(() => undefined)
    }
  }

  async function loadAll(input: string, dir: string) {
    const list = await files(input, dir)
    if (list.length === 0) return `No JSON files found in ${input}.`
    const done: string[] = []
    const fail: string[] = []
    for (const src of list) {
      try {
        await load(src, dir)
        done.push(src)
      } catch (err) {
        fail.push(`${src}: ${err instanceof Error ? err.message : String(err)}`)
      }
    }
    if (fail.length > 0) {
      throw new Error(`Imported ${done.length}/${list.length} file(s). Failed:\n${fail.join("\n")}`)
    }
    return `Imported ${done.length} session file(s) from ${input}.`
  }

  const root = process.env.OPENCODE_SESSION_EXPORT_DIR
  if (root && process.env[guard] !== "1") {
    loadAll(root, directory).catch((err) => {
      log("warn", "automatic session import failed", {
        root,
        error: err instanceof Error ? err.message : String(err),
      })
    })
  }

  return {
    tool: {
      session_import: tool({
        description:
          "Import opencode session JSON. If no path is provided, imports JSON files from OPENCODE_SESSION_EXPORT_DIR.",
        args: {
          path: tool.schema.string().optional().describe("Path to a JSON file or directory. Defaults to OPENCODE_SESSION_EXPORT_DIR."),
        },
        async execute(args, ctx) {
          const src = args.path || process.env.OPENCODE_SESSION_EXPORT_DIR
          if (!src) throw new Error("No path provided and OPENCODE_SESSION_EXPORT_DIR is not set.")
          return loadAll(src, ctx.directory || directory)
        },
      }),
    },
  }
}

from __future__ import annotations

import json
import os
import shlex
import sys

from e2b import Sandbox

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def run_case(sandbox: Sandbox, label: str, cfg: dict, model: str, query: str) -> None:
    sandbox.files.write("/home/user/opencode.json", json.dumps(cfg, indent=2, ensure_ascii=False))
    sandbox.commands.run("mkdir -p /home/user/workspace && cp /home/user/opencode.json /home/user/workspace/opencode.json", timeout=30)
    cmd = f"opencode run --print-logs --log-level DEBUG --format json --model {model} {shlex.quote(query)}"
    print(f"=== {label} command ===")
    print(cmd)
    result = sandbox.commands.run(f"{cmd} || true", cwd="/home/user/workspace", timeout=240, request_timeout=300)
    print(f"=== {label} stdout ===")
    print((result.stdout or "").strip())
    print(f"=== {label} stderr ===")
    print((result.stderr or "").strip())


def main() -> None:
    key = os.getenv("OPENCODE_PROVIDER_KEY")
    if not key:
        raise SystemExit("OPENCODE_PROVIDER_KEY is required")

    query = os.getenv("OPENCODE_QUERY", "帮我写一个加法计算器")
    sandbox = Sandbox.create("opencode", timeout=180)
    try:
        print(f"sandbox_id={sandbox.sandbox_id}")
        version = sandbox.commands.run("opencode --version", timeout=30)
        print(f"opencode_version={version.stdout.strip()}")

        openai_model = "deepseek/deepseek-v4-pro"
        openai_cfg = {
            "$schema": "https://opencode.ai/config.json",
            "provider": {
                "deepseek": {
                    "name": "DeepSeek",
                    "npm": "@ai-sdk/openai-compatible",
                    "options": {"baseURL": "https://api.deepseek.com", "apiKey": key},
                    "models": {"deepseek-v4-pro": {"name": "deepseek-v4-pro"}},
                }
            },
            "model": openai_model,
        }
        run_case(sandbox, "openai-compatible", openai_cfg, openai_model, query)

        anthropic_model = "deepseek-anthropic/deepseek-v4-pro"
        anthropic_cfg = {
            "$schema": "https://opencode.ai/config.json",
            "provider": {
                "deepseek-anthropic": {
                    "name": "DeepSeek Anthropic",
                    "npm": "@ai-sdk/anthropic",
                    "options": {"baseURL": "https://api.deepseek.com/anthropic", "apiKey": key},
                    "models": {"deepseek-v4-pro": {"name": "deepseek-v4-pro"}},
                }
            },
            "model": anthropic_model,
        }
        run_case(sandbox, "anthropic-compatible", anthropic_cfg, anthropic_model, query)
    finally:
        sandbox.kill()
        print("sandbox_killed=true")


if __name__ == "__main__":
    main()

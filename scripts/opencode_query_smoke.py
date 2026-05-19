from __future__ import annotations

import json
import os

from e2b import Sandbox


QUERY = os.getenv("OPENCODE_QUERY", "帮我写一个加法计算器")
MODEL = os.getenv("OPENCODE_MODEL", "deepseek/deepseek-v4-pro")
BASE_URL = os.getenv("OPENCODE_BASE_URL", "https://api.deepseek.com")
API_KEY = os.getenv("OPENCODE_PROVIDER_KEY")


def main() -> None:
    if not API_KEY:
        raise SystemExit("OPENCODE_PROVIDER_KEY is required")

    sandbox = Sandbox.create(timeout=180)
    try:
        print(f"sandbox_id={sandbox.sandbox_id}")
        check = sandbox.commands.run("command -v opencode || true; command -v curl || true; command -v node || true; command -v npm || true", timeout=30)
        print("precheck_stdout_start")
        print(check.stdout.strip())
        print("precheck_stdout_end")

        if "opencode" not in check.stdout:
            install = sandbox.commands.run("curl -fsSL https://opencode.ai/install | bash", timeout=180)
            print("install_stdout_start")
            print((install.stdout or "").strip())
            print("install_stdout_end")
            print("install_stderr_start")
            print((install.stderr or "").strip())
            print("install_stderr_end")

        cfg = {
            "$schema": "https://opencode.ai/config.json",
            "provider": {
                "deepseek": {
                    "name": "DeepSeek",
                    "npm": "@ai-sdk/openai-compatible",
                    "options": {
                        "baseURL": BASE_URL,
                        "apiKey": API_KEY,
                    },
                    "models": {
                        "deepseek-v4-pro": {"name": "deepseek-v4-pro"},
                    },
                }
            },
            "model": MODEL,
            "server": {"port": 4096, "hostname": "0.0.0.0"},
        }
        sandbox.files.write("/home/user/opencode.json", json.dumps(cfg, indent=2, ensure_ascii=False))
        sandbox.commands.run("mkdir -p /home/user/.config/opencode && cp /home/user/opencode.json /home/user/.config/opencode/opencode.json", timeout=30)

        result = sandbox.commands.run(
            f'printf "%s" {json.dumps(QUERY)} | opencode run --model {MODEL}',
            cwd="/home/user",
            timeout=300,
        )
        print("query_stdout_start")
        print((result.stdout or "").strip())
        print("query_stdout_end")
        print("query_stderr_start")
        print((result.stderr or "").strip())
        print("query_stderr_end")
    finally:
        sandbox.kill()
        print("sandbox_killed=true")


if __name__ == "__main__":
    main()


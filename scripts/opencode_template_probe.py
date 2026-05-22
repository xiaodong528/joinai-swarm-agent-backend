from __future__ import annotations

import sys

from e2b import Sandbox

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def run(label: str, sandbox: Sandbox, command: str) -> None:
    result = sandbox.commands.run(f"{command} || true", timeout=60, request_timeout=120)
    print(f"--- {label} stdout ---")
    print((result.stdout or "").strip())
    print(f"--- {label} stderr ---")
    print((result.stderr or "").strip())


def main() -> None:
    sandbox = Sandbox.create("opencode", timeout=180)
    try:
        print(f"sandbox_id={sandbox.sandbox_id}")
        run("which", sandbox, "command -v opencode && opencode --version")
        run("help", sandbox, "opencode --help")
        run("run-help", sandbox, "opencode run --help")
        run("config-list", sandbox, "find /home/user -maxdepth 4 -type f | sort")
    finally:
        sandbox.kill()
        print("sandbox_killed=true")


if __name__ == "__main__":
    main()

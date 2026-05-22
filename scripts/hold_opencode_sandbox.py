from __future__ import annotations

import json
import os
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from e2b import Sandbox


STATUS_PATH = Path("tmp/opencode_sandbox_hold.json")
LOG_PATH = Path("tmp/opencode_sandbox_hold.log")


def write_status(payload: dict[str, object]) -> None:
    STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATUS_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def log(message: str) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    with LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(f"{timestamp} {message}\n")
    print(message, flush=True)


def main() -> None:
    timeout = int(os.getenv("E2B_SANDBOX_TIMEOUT", "3600"))
    provider_key = os.getenv("OPENCODE_PROVIDER_KEY")

    log(f"creating opencode sandbox with timeout={timeout}s")
    sandbox = Sandbox.create("opencode", timeout=timeout)

    stopping = False

    def stop(_signum: int, _frame: object) -> None:
        nonlocal stopping
        stopping = True
        log("hold process received stop signal; sandbox is intentionally not killed")

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)

    sandbox_id = getattr(sandbox, "sandbox_id", "unknown")
    home = sandbox.commands.run('printf "%s" "$HOME"', timeout=10).stdout.strip() or "/home/user"
    workspace = "/home/user/workspace"
    sandbox.commands.run(f"mkdir -p {workspace}", timeout=30)

    checks = sandbox.commands.run(
        "command -v opencode && opencode --version || true",
        timeout=60,
        request_timeout=120,
    )

    status = {
        "sandbox_id": sandbox_id,
        "home": home,
        "workspace": workspace,
        "timeout_seconds": timeout,
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "opencode_check_stdout": checks.stdout.strip(),
        "opencode_check_stderr": checks.stderr.strip(),
        "provider_key_present": bool(provider_key),
    }
    write_status(status)
    log(f"sandbox_id={sandbox_id}")
    log(f"status_file={STATUS_PATH}")

    while not stopping:
        time.sleep(30)
        try:
            sandbox.commands.run("true", timeout=10)
            status["last_heartbeat_at"] = (
                datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            )
            write_status(status)
            log("heartbeat ok")
        except Exception as exc:
            status["last_error"] = str(exc)
            write_status(status)
            log(f"heartbeat failed: {exc}")
            break

    return None


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    main()

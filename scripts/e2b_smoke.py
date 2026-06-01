from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.config import Settings
from engine.models import CreateSessionRequest, GenerateRequest
from engine.service import AgentEngineService


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a real E2B/OpenCode smoke test using environment variables.")
    parser.add_argument("--user-id", default="smoke-user")
    parser.add_argument("--query", help="If provided, run a generation request after creating the session.")
    parser.add_argument("--output-root", help="Optional output root inside /home/user/template.")
    parser.add_argument("--output-slug", default="smoke-agent-team")
    parser.add_argument("--keep-sandbox", action="store_true")
    return parser.parse_args()


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")

    args = parse_args()
    missing = [name for name in ("E2B_API_KEY", "DEEPSEEK_API_KEY") if not os.getenv(name)]
    if missing:
        print(f"Missing environment variable(s): {', '.join(missing)}", file=sys.stderr)
        return 2

    service = AgentEngineService(Settings())
    payload = {}
    try:
        created = service.create_session(CreateSessionRequest(user_id=args.user_id, keep_sandbox=args.keep_sandbox))
        payload["created"] = created.model_dump(mode="json")

        if args.query:
            generated = service.generate(
                created.session_id,
                GenerateRequest(
                    user_id=args.user_id,
                    query=args.query,
                    output_root=args.output_root,
                    output_slug=args.output_slug,
                ),
            )
            payload["generated"] = generated.model_dump(mode="json")
    except Exception as exc:
        payload["exception"] = {"type": type(exc).__name__, "message": str(exc)}

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 1 if "exception" in payload else 0


if __name__ == "__main__":
    raise SystemExit(main())

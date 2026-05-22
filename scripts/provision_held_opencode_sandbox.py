from __future__ import annotations

import json
import os
from pathlib import Path

from e2b import Sandbox

from opencode_backend.layout import build_file_artifacts
from opencode_backend.schemas import ProviderInput, ProvisionRequest, Scope


STATUS_PATH = Path("tmp/opencode_sandbox_hold.json")


def main() -> None:
    provider_key = os.getenv("OPENCODE_PROVIDER_KEY")
    if not provider_key:
        raise SystemExit("OPENCODE_PROVIDER_KEY is required")

    status = json.loads(STATUS_PATH.read_text(encoding="utf-8"))
    sandbox_id = status["sandbox_id"]
    sandbox = Sandbox.connect(sandbox_id, timeout=int(status.get("timeout_seconds", 3600)))

    request = ProvisionRequest(
        scope=Scope.project,
        workspace_path=status.get("workspace") or "/home/user/workspace",
        provider=ProviderInput(
            id="deepseek",
            name="DeepSeek",
            npm="@ai-sdk/openai-compatible",
            base_url="https://api.deepseek.com",
            api_key=provider_key,
            model_name="deepseek-v4-pro",
        ),
        config={"permission": {"write": "allow"}},
        launch={"enabled": False},
    )

    artifacts = build_file_artifacts(request, status.get("home") or "/home/user")
    for artifact in artifacts:
        sandbox.files.write(artifact.path, artifact.content)

    check = sandbox.commands.run(
        "cd /home/user/workspace && ls -la && printf '\\n--- opencode.json ---\\n' && "
        "python - <<'PY'\n"
        "import json\n"
        "data=json.load(open('opencode.json'))\n"
        "data['provider']['deepseek']['options']['apiKey']='***'\n"
        "print(json.dumps(data, ensure_ascii=False, indent=2))\n"
        "PY",
        timeout=30,
        request_timeout=60,
    )
    print(f"sandbox_id={sandbox_id}")
    print(check.stdout)
    if check.stderr:
        print(check.stderr)


if __name__ == "__main__":
    main()

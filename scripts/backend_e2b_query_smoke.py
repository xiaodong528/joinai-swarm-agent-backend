from __future__ import annotations

import os

from opencode_backend.sandbox import E2BSandboxSession
from opencode_backend.schemas import ProvisionRequest, ProviderInput, Scope
from opencode_backend.service import OpenCodeProvisioner


def main() -> None:
    provider_key = os.getenv("OPENCODE_PROVIDER_KEY")
    if not provider_key:
        raise SystemExit("OPENCODE_PROVIDER_KEY is required")

    session = E2BSandboxSession()
    provisioner = OpenCodeProvisioner(session)
    request = ProvisionRequest(
        scope=Scope.project,
        workspace_path="/home/user/workspace",
        provider=ProviderInput(
            id="deepseek",
            name="DeepSeek",
            npm="@ai-sdk/openai-compatible",
            base_url="https://api.deepseek.com",
            api_key=provider_key,
            model_name="deepseek-v4-pro",
        ),
        query="帮我写一个加法计算器",
    )
    response = provisioner.provision(request)
    print(f"sandbox_id={response.sandbox_id}")
    print(f"public_url={response.public_url}")
    print(f"launch_pid={response.launch_pid}")
    print("stdout_start")
    print(response.stdout.strip())
    print("stdout_end")
    print("stderr_start")
    print(response.stderr.strip())
    print("stderr_end")
    print("files_written")
    for item in response.files_written:
        print(f"{item.path} {item.bytes}")


if __name__ == "__main__":
    main()

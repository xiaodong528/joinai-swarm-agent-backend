from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import json
import shlex

from .layout import build_file_artifacts
from .sandbox import SandboxSession
from .protocols import build_a2a_task
from .schemas import A2ARunResponse, ProvisionRequest, ProvisionResponse, WrittenFile


@dataclass
class ProvisionResult:
    response: ProvisionResponse


class OpenCodeProvisioner:
    def __init__(self, session: SandboxSession) -> None:
        self.session = session

    def run_a2a(
        self,
        request: ProvisionRequest,
        *,
        task_id: str | None = None,
        context_id: str | None = None,
        user_message: dict[str, Any] | None = None,
    ) -> A2ARunResponse:
        if not request.query:
            raise ValueError("A2A run requires query")
        response = self.provision(request)
        task, events = build_a2a_task(
            response=response,
            query=request.query,
            task_id=task_id,
            context_id=context_id,
            user_message=user_message,
        )
        return A2ARunResponse(task=task, events=events, provision=response)

    def provision(self, request: ProvisionRequest) -> ProvisionResponse:
        home_dir = self.session.home_dir
        artifacts = build_file_artifacts(request, home_dir)
        self.session.write_files(artifacts)

        cwd = request.workspace_path if request.scope.value == "project" else home_dir
        stdout = ""
        stderr = ""
        pid = None
        public_url = None
        a2a_stdout = ""
        a2a_stderr = ""
        a2a_pid = None
        a2a_public_url = None
        a2a_command = []
        executed_command = [
            *request.launch.command,
            "--hostname",
            request.launch.hostname,
            "--port",
            str(request.launch.port),
        ]

        if request.launch.enabled and not request.query:
            command = " ".join(request.launch.command)
            result = self.session.run(
                f"{command} --hostname {request.launch.hostname} --port {request.launch.port}",
                cwd=request.launch.cwd or cwd,
                envs=request.launch.envs,
                background=True,
                timeout=request.launch.timeout,
                request_timeout=request.launch.timeout,
            )
            stdout = result.stdout
            stderr = result.stderr
            pid = result.pid
            public_url = self.session.get_public_url(request.launch.port)

        if request.query:
            if not request.provider:
                raise ValueError("query requires provider configuration")
            query_cmd = (
                f"opencode run --format json --model {request.provider.id}/{request.provider.model_name} "
                f"{shlex.quote(request.query)}"
            )
            executed_command = [
                "opencode",
                "run",
                "--format",
                "json",
                "--model",
                f"{request.provider.id}/{request.provider.model_name}",
                request.query,
            ]
            query_result = self.session.run(
                query_cmd,
                cwd=request.launch.cwd or cwd,
                envs=request.launch.envs,
                background=False,
                timeout=request.launch.timeout,
                request_timeout=request.launch.timeout,
            )
            stdout = query_result.stdout
            stderr = query_result.stderr
            if query_result.exit_code not in (None, 0):
                raise RuntimeError(
                    f"opencode run failed with exit code {query_result.exit_code}: "
                    f"{query_result.stderr or query_result.error or query_result.stdout}"
                )

        if request.a2a.enabled:
            a2a_command = [
                *request.a2a.command,
                "--hostname",
                request.a2a.hostname,
                "--port",
                str(request.a2a.port),
            ]
            if request.a2a.install:
                self.session.run(
                    "python -m pip install opencode-a2a",
                    cwd=request.launch.cwd or cwd,
                    envs=request.a2a.envs,
                    background=False,
                    timeout=request.a2a.timeout,
                    request_timeout=request.a2a.timeout,
                )
            a2a_envs = dict(request.a2a.envs)
            if request.a2a.opencode_base_url:
                a2a_envs["OPENCODE_BASE_URL"] = request.a2a.opencode_base_url
            if request.a2a.bearer_token:
                a2a_envs["A2A_BEARER_TOKEN"] = request.a2a.bearer_token
            a2a_envs["A2A_HOSTNAME"] = request.a2a.hostname
            a2a_envs["A2A_PORT"] = str(request.a2a.port)
            a2a_envs["A2A_DATABASE_URL"] = request.a2a.database_url
            if request.a2a.public_url:
                a2a_envs["A2A_PUBLIC_URL"] = request.a2a.public_url
            if request.a2a.static_auth_credentials:
                import json as _json

                a2a_envs["A2A_STATIC_AUTH_CREDENTIALS"] = _json.dumps(
                    request.a2a.static_auth_credentials,
                    ensure_ascii=False,
                )
            a2a_result = self.session.run(
                " ".join(a2a_command),
                cwd=request.launch.cwd or cwd,
                envs=a2a_envs,
                background=True,
                timeout=request.a2a.timeout,
                request_timeout=request.a2a.timeout,
            )
            a2a_stdout = a2a_result.stdout
            a2a_stderr = a2a_result.stderr
            a2a_pid = a2a_result.pid
            a2a_public_url = (
                request.a2a.public_url
                or self.session.get_public_url(request.a2a.port)
                or public_url
            )

        files_written = [
            WrittenFile(path=item.path, bytes=len(item.content.encode("utf-8")))
            for item in artifacts
        ]
        config_root = (
            request.workspace_path
            if request.scope.value == "project"
            else home_dir + "/.config/opencode"
        )
        return ProvisionResponse(
            sandbox_id=self.session.sandbox_id,
            scope=request.scope,
            config_root=config_root,
            files_written=files_written,
            launch_command=executed_command,
            launch_pid=pid,
            public_url=public_url,
            stdout=stdout,
            stderr=stderr,
            a2a_command=a2a_command,
            a2a_pid=a2a_pid,
            a2a_public_url=a2a_public_url,
            a2a_stdout=a2a_stdout,
            a2a_stderr=a2a_stderr,
        )

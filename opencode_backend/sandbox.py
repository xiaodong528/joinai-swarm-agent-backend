from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Protocol
import os
import subprocess
import uuid

from .layout import FileArtifact


@dataclass
class CommandResult:
    stdout: str = ""
    stderr: str = ""
    pid: int | None = None
    exit_code: int | None = None
    error: str = ""


class SandboxSession(Protocol):
    sandbox_id: str
    home_dir: str

    def write_files(self, files: list[FileArtifact]) -> None: ...

    def run(
        self,
        command: str,
        *,
        cwd: str | None = None,
        envs: dict[str, str] | None = None,
        background: bool = False,
        timeout: float | None = None,
        request_timeout: float | None = None,
    ) -> CommandResult: ...

    def get_public_url(self, port: int) -> str | None: ...


class E2BSandboxSession:
    def __init__(self) -> None:
        try:
            from e2b import Sandbox
        except ImportError as exc:
            raise RuntimeError(
                "E2B SDK is not installed. Install the `e2b` package or set OPENCODE_BACKEND=local for tests."
            ) from exc

        self._sandbox = Sandbox.create("opencode")
        self.sandbox_id = getattr(self._sandbox, "sandbox_id", "unknown")
        home_result = self._sandbox.commands.run('printf "%s" "$HOME"', timeout=10)
        self.home_dir = (home_result.stdout or "").strip() or "/home/user"

    def write_files(self, files: list[FileArtifact]) -> None:
        for item in files:
            self._sandbox.files.write(item.path, item.content)

    def run(
        self,
        command: str,
        *,
        cwd: str | None = None,
        envs: dict[str, str] | None = None,
        background: bool = False,
        timeout: float | None = None,
        request_timeout: float | None = None,
    ) -> CommandResult:
        try:
            result = self._sandbox.commands.run(
                command,
                cwd=cwd,
                envs=envs,
                background=background,
                timeout=timeout if timeout is not None else (0 if background else 60),
                request_timeout=request_timeout,
            )
        except Exception as exc:
            return CommandResult(
                stdout=getattr(exc, "stdout", "") or "",
                stderr=getattr(exc, "stderr", "") or "",
                exit_code=getattr(exc, "exit_code", None),
                error=str(getattr(exc, "error", "") or exc),
            )
        if background:
            stdout = ""
            stderr = ""
        else:
            stdout = getattr(result, "stdout", "") or ""
            stderr = getattr(result, "stderr", "") or ""
        pid = getattr(result, "pid", None)
        return CommandResult(
            stdout=stdout,
            stderr=stderr,
            pid=pid,
            exit_code=getattr(result, "exit_code", None),
            error=getattr(result, "error", "") or "",
        )

    def get_public_url(self, port: int) -> str | None:
        for attr in ("get_host", "get_hostname", "getHost", "getHostname"):
            fn = getattr(self._sandbox, attr, None)
            if fn is not None:
                host = fn(port)
                if host:
                    return f"https://{host}"
        return None


class LocalSandboxSession:
    def __init__(self, root: str | None = None) -> None:
        self._tmp = TemporaryDirectory(dir=root)
        self._root = Path(self._tmp.name)
        self.sandbox_id = uuid.uuid4().hex[:12]
        self.home_dir = str(self._root / "home")
        Path(self.home_dir).mkdir(parents=True, exist_ok=True)
        self._commands: list[str] = []

    def _resolve_path(self, raw_path: str) -> Path:
        normalized = raw_path.lstrip("/")
        return self._root / normalized

    def write_files(self, files: list[FileArtifact]) -> None:
        for item in files:
            path = self._resolve_path(item.path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(item.content, encoding="utf-8")

    def run(
        self,
        command: str,
        *,
        cwd: str | None = None,
        envs: dict[str, str] | None = None,
        background: bool = False,
        timeout: float | None = None,
        request_timeout: float | None = None,
    ) -> CommandResult:
        self._commands.append(command)
        if command.strip().startswith("command -v opencode"):
            return CommandResult(stdout="/usr/bin/opencode\n")
        if command.startswith("opencode web"):
            return CommandResult(stdout="started\n", pid=1000 + len(self._commands))
        if command.startswith("opencode run"):
            return CommandResult(
                stdout='{"type":"message","role":"assistant","content":"mocked opencode output"}\n'
            )
        if command.startswith("opencode-a2a"):
            return CommandResult(stdout="a2a server started\n", pid=2000 + len(self._commands))
        if command.startswith("mkdir -p"):
            return CommandResult(stdout="")
        return CommandResult(stdout="", stderr="")

    def get_public_url(self, port: int) -> str | None:
        return f"http://localhost:{port}"


def create_session(backend: str | None = None) -> SandboxSession:
    backend_name = (backend or os.getenv("OPENCODE_BACKEND", "e2b")).lower()
    if backend_name == "local":
        return LocalSandboxSession(root=os.getenv("OPENCODE_LOCAL_ROOT"))
    if backend_name == "e2b":
        return E2BSandboxSession()
    raise ValueError(f"Unsupported backend: {backend_name}")

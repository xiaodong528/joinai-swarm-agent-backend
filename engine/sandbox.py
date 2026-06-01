from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from engine.config import Settings


@dataclass
class CommandResult:
    exit_code: int
    stdout: str = ""
    stderr: str = ""

    @property
    def ok(self) -> bool:
        return self.exit_code == 0


class SandboxHandle(Protocol):
    sandbox_id: str

    def write_text(self, path: str, content: str) -> None: ...

    def run(self, command: str, cwd: str | None = None, timeout_ms: int | None = None, env: dict[str, str] | None = None) -> CommandResult: ...

    def close(self) -> None: ...


class SandboxFactory(Protocol):
    def create(self, env: dict[str, str]) -> SandboxHandle: ...

    def connect(self, sandbox_id: str, env: dict[str, str]) -> SandboxHandle: ...


class E2BSandboxHandle:
    def __init__(self, sandbox: object, sandbox_id: str):
        self._sandbox = sandbox
        self.sandbox_id = sandbox_id

    def write_text(self, path: str, content: str) -> None:
        self._sandbox.files.write(path, content)

    def run(self, command: str, cwd: str | None = None, timeout_ms: int | None = None, env: dict[str, str] | None = None) -> CommandResult:
        kwargs = {}
        if cwd:
            kwargs["cwd"] = cwd
        if timeout_ms:
            kwargs["timeout"] = timeout_ms / 1000
        if env:
            kwargs["envs"] = env
        try:
            result = self._sandbox.commands.run(command, **kwargs)
            exit_code = int(getattr(result, "exit_code", getattr(result, "return_code", 0)))
            stdout = str(getattr(result, "stdout", ""))
            stderr = str(getattr(result, "stderr", ""))
            return CommandResult(exit_code=exit_code, stdout=stdout, stderr=stderr)
        except Exception as exc:
            return CommandResult(exit_code=1, stderr=f"{type(exc).__name__}: {exc}")

    def close(self) -> None:
        close = getattr(self._sandbox, "kill", None) or getattr(self._sandbox, "close", None)
        if close:
            close()


class E2BSandboxFactory:
    def __init__(self, settings: Settings):
        self.settings = settings

    def _sandbox_cls(self):
        try:
            from e2b import Sandbox
        except ImportError as exc:
            raise RuntimeError("The e2b package is required for real sandbox execution.") from exc
        return Sandbox

    def create(self, env: dict[str, str]) -> SandboxHandle:
        self.settings.validate_runtime()
        Sandbox = self._sandbox_cls()
        sandbox = Sandbox.create(template=self.settings.e2b_template, envs=env, timeout=self.settings.e2b_timeout_seconds)
        sandbox_id = str(getattr(sandbox, "sandbox_id", getattr(sandbox, "id", "")))
        if not sandbox_id:
            raise RuntimeError("E2B sandbox was created but no sandbox id was returned.")
        return E2BSandboxHandle(sandbox, sandbox_id)

    def connect(self, sandbox_id: str, env: dict[str, str]) -> SandboxHandle:
        Sandbox = self._sandbox_cls()
        connect = getattr(Sandbox, "connect", None)
        if not connect:
            raise RuntimeError("Installed e2b SDK does not support connecting to an existing sandbox.")
        sandbox = connect(sandbox_id, envs=env)
        set_timeout = getattr(sandbox, "set_timeout", None)
        if set_timeout:
            set_timeout(self.settings.e2b_timeout_seconds)
        return E2BSandboxHandle(sandbox, sandbox_id)

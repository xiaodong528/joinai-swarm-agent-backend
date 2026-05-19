from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class Scope(str, Enum):
    project = "project"
    global_ = "global"


class SkillInput(BaseModel):
    name: str
    description: str
    content: str = ""
    frontmatter: dict[str, Any] = Field(default_factory=dict)


class AgentInput(BaseModel):
    name: str
    description: str
    content: str = ""
    frontmatter: dict[str, Any] = Field(default_factory=dict)


class ProviderInput(BaseModel):
    id: str = "deepseek"
    name: str = "DeepSeek"
    npm: str = "@ai-sdk/openai-compatible"
    base_url: str
    api_key: str | None = None
    model_name: str


class LaunchInput(BaseModel):
    enabled: bool = True
    command: list[str] = Field(default_factory=lambda: ["opencode", "serve"])
    port: int = 4096
    hostname: str = "0.0.0.0"
    cwd: str | None = None
    envs: dict[str, str] = Field(default_factory=dict)
    timeout: float = 600.0


class A2ARuntimeInput(BaseModel):
    enabled: bool = False
    command: list[str] = Field(default_factory=lambda: ["opencode-a2a"])
    port: int = 8000
    hostname: str = "0.0.0.0"
    database_url: str = "sqlite+aiosqlite:///./opencode-a2a.db"
    public_url: str | None = None
    opencode_base_url: str | None = None
    bearer_token: str | None = None
    install: bool = False
    static_auth_credentials: list[dict[str, Any]] = Field(default_factory=list)
    envs: dict[str, str] = Field(default_factory=dict)
    timeout: float = 600.0


class ProvisionRequest(BaseModel):
    scope: Scope = Scope.project
    workspace_path: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)
    mcp: dict[str, Any] = Field(default_factory=dict)
    agent_config: dict[str, Any] = Field(default_factory=dict)
    provider: ProviderInput | None = None
    query: str | None = None
    skills: list[SkillInput] = Field(default_factory=list)
    agents: list[AgentInput] = Field(default_factory=list)
    launch: LaunchInput = Field(default_factory=LaunchInput)
    a2a: A2ARuntimeInput = Field(default_factory=A2ARuntimeInput)

    @field_validator("workspace_path")
    @classmethod
    def validate_workspace_path(cls, value: str | None) -> str | None:
        if value is None:
            return value
        if not value.startswith("/"):
            raise ValueError("workspace_path must be an absolute Linux path")
        return value

    @model_validator(mode="after")
    def validate_scope(self) -> "ProvisionRequest":
        if self.scope == Scope.project and not self.workspace_path:
            raise ValueError("workspace_path is required when scope=project")
        return self


class WrittenFile(BaseModel):
    path: str
    bytes: int


class ProvisionResponse(BaseModel):
    sandbox_id: str
    scope: Scope
    config_root: str
    files_written: list[WrittenFile]
    launch_command: list[str]
    launch_pid: int | None = None
    public_url: str | None = None
    stdout: str = ""
    stderr: str = ""
    a2a_command: list[str] = Field(default_factory=list)
    a2a_pid: int | None = None
    a2a_public_url: str | None = None
    a2a_stdout: str = ""
    a2a_stderr: str = ""


class A2AMessageSendParams(BaseModel):
    message: dict[str, Any]
    configuration: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    opencode: ProvisionRequest | None = None


class A2AJsonRpcRequest(BaseModel):
    jsonrpc: Literal["2.0"] = "2.0"
    id: str | int | None = None
    method: str
    params: dict[str, Any] = Field(default_factory=dict)


class A2AJsonRpcResponse(BaseModel):
    jsonrpc: Literal["2.0"] = "2.0"
    id: str | int | None = None
    result: Any | None = None
    error: dict[str, Any] | None = None


class A2ARunRequest(ProvisionRequest):
    task_id: str | None = None
    context_id: str | None = None


class A2ARunResponse(BaseModel):
    task: dict[str, Any]
    events: list[dict[str, Any]]
    provision: ProvisionResponse


class AGUIRunResponse(BaseModel):
    events: list[dict[str, Any]]
    a2a_task: dict[str, Any]

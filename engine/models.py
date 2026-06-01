from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, HttpUrl


class SessionStatus(StrEnum):
    CREATED = "created"
    INITIALIZING = "initializing"
    READY = "ready"
    RUNNING = "running"
    GENERATED = "generated"
    VALIDATED = "validated"
    FAILED = "failed"
    INTERRUPTED = "interrupted"
    TIMEOUT = "timeout"
    CLOSED = "closed"


class CreateSessionRequest(BaseModel):
    user_id: str = Field(min_length=1)
    webhook_url: HttpUrl | None = None
    session_status_url: HttpUrl | None = None
    keep_sandbox: bool = False


class GenerateRequest(BaseModel):
    user_id: str = Field(min_length=1)
    query: str = Field(min_length=1)
    sandbox_id: str | None = None
    output_root: str | None = None
    output_slug: str | None = None
    timeout_ms: int | None = Field(default=None, gt=0)


class CreateRuntimeSessionRequest(BaseModel):
    user_id: str = Field(min_length=1)
    template_id: str | None = None
    source_session_id: str | None = None
    source_sandbox_id: str | None = None
    generated_package_path: str | None = None
    webhook_url: HttpUrl | None = None
    session_status_url: HttpUrl | None = None
    keep_sandbox: bool = False


class RuntimeQueryRequest(BaseModel):
    user_id: str = Field(min_length=1)
    query: str = Field(min_length=1)
    sandbox_id: str | None = None
    agent: str | None = None
    timeout_ms: int | None = Field(default=None, gt=0)


class CloseSessionRequest(BaseModel):
    user_id: str = Field(min_length=1)
    sandbox_id: str | None = None


class EngineResponse(BaseModel):
    user_id: str
    session_id: str
    sandbox_id: str
    status: SessionStatus
    generated_package_path: str | None = None
    session_export_path: str
    state_path: str
    errors: list[str] = Field(default_factory=list)
    data: dict[str, Any] = Field(default_factory=dict)


class RuntimeSessionResponse(BaseModel):
    user_id: str
    runtime_session_id: str
    sandbox_id: str
    status: SessionStatus
    source_session_id: str
    source_sandbox_id: str
    source_package_path: str
    runtime_package_path: str
    session_export_path: str
    state_path: str
    errors: list[str] = Field(default_factory=list)
    data: dict[str, Any] = Field(default_factory=dict)


class TemplateResponse(BaseModel):
    user_id: str
    template_id: str
    source_session_id: str
    source_sandbox_id: str
    package_path: str
    output_root: str
    output_slug: str
    status: SessionStatus
    created_at: str
    data: dict[str, Any] = Field(default_factory=dict)


class HealthResponse(BaseModel):
    status: str = "ok"

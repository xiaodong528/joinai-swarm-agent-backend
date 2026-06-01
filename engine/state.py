from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from engine.models import SessionStatus
from engine.paths import RuntimePaths, SessionPaths


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class SessionRecord:
    user_id: str
    session_id: str
    sandbox_id: str
    paths: SessionPaths
    status: SessionStatus = SessionStatus.CREATED
    webhook_url: str | None = None
    session_status_url: str | None = None
    keep_sandbox: bool = False
    generated_package_path: str | None = None
    errors: list[str] = field(default_factory=list)
    data: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)

    def to_payload(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "session_id": self.session_id,
            "sandbox_id": self.sandbox_id,
            "status": self.status,
            "generated_package_path": self.generated_package_path,
            "session_export_path": self.paths.session_export_root,
            "state_path": self.paths.status_file,
            "errors": self.errors,
            "data": self.data,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class RuntimeSessionRecord:
    user_id: str
    runtime_session_id: str
    sandbox_id: str
    paths: RuntimePaths
    source_session_id: str
    source_sandbox_id: str
    source_package_path: str
    status: SessionStatus = SessionStatus.CREATED
    webhook_url: str | None = None
    session_status_url: str | None = None
    keep_sandbox: bool = False
    errors: list[str] = field(default_factory=list)
    data: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)

    def to_payload(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "runtime_session_id": self.runtime_session_id,
            "sandbox_id": self.sandbox_id,
            "status": self.status,
            "source_session_id": self.source_session_id,
            "source_sandbox_id": self.source_sandbox_id,
            "source_package_path": self.source_package_path,
            "runtime_package_path": self.paths.package_root,
            "session_export_path": self.paths.session_export_root,
            "state_path": self.paths.status_file,
            "errors": self.errors,
            "data": self.data,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class GeneratedTemplateRecord:
    user_id: str
    template_id: str
    source_session_id: str
    source_sandbox_id: str
    package_path: str
    output_root: str
    output_slug: str
    status: SessionStatus = SessionStatus.VALIDATED
    data: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now)

    def to_payload(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "template_id": self.template_id,
            "source_session_id": self.source_session_id,
            "source_sandbox_id": self.source_sandbox_id,
            "package_path": self.package_path,
            "output_root": self.output_root,
            "output_slug": self.output_slug,
            "status": self.status,
            "created_at": self.created_at,
            "data": self.data,
        }

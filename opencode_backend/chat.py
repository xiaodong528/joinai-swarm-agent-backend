from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import Any, Callable
import base64
import json
import os

from .crypto import SecretBox
from .protocols import a2a_task_to_ag_ui_events
from .sandbox import SandboxSession, create_session
from .schemas import (
    AgentInput,
    A2ARuntimeInput,
    ChatMessageResponse,
    ChatRunResponse,
    ChatSandboxBindingResponse,
    ChatSessionCreateRequest,
    ChatSessionDetailResponse,
    ChatSessionResponse,
    ProviderInput,
    ProvisionRequest,
    SkillInput,
)
from .service import OpenCodeProvisioner
from .store import (
    ChatMessageRow,
    ChatRunRow,
    ChatSessionRow,
    ChatStore,
    SandboxBindingRow,
    utc_now,
)


SessionFactory = Callable[[], SandboxSession]


class ChatConflictError(RuntimeError):
    pass


class SandboxManager:
    def __init__(
        self,
        store: ChatStore,
        session_factory: SessionFactory = create_session,
        ttl_seconds: int | None = None,
    ) -> None:
        self.store = store
        self.session_factory = session_factory
        self.ttl_seconds = ttl_seconds or int(os.getenv("CHAT_SANDBOX_TTL_SECONDS", "3600"))
        self._sessions: dict[str, SandboxSession] = {}
        self._lock = Lock()

    def get_or_create(self, session_id: str) -> SandboxSession:
        now = datetime.now(timezone.utc)
        with self._lock:
            cached = self._sessions.get(session_id)
            binding = self.store.get_binding(session_id)
            if cached is not None and binding is not None and self._binding_is_active(binding, now):
                self._touch(session_id, cached)
                return cached
            if cached is not None:
                self._kill(cached)
                self._sessions.pop(session_id, None)
            session = self.session_factory()
            self._sessions[session_id] = session
            self._touch(session_id, session)
            return session

    def has_cached_active(self, session_id: str) -> bool:
        now = datetime.now(timezone.utc)
        with self._lock:
            binding = self.store.get_binding(session_id)
            return (
                session_id in self._sessions
                and binding is not None
                and self._binding_is_active(binding, now)
            )

    def release(self, session_id: str) -> None:
        with self._lock:
            session = self._sessions.pop(session_id, None)
            if session is not None:
                self._kill(session)
            self.store.release_binding(session_id)

    def _touch(self, session_id: str, session: SandboxSession) -> None:
        now = datetime.now(timezone.utc)
        expires = now + timedelta(seconds=self.ttl_seconds)
        self.store.upsert_binding(
            SandboxBindingRow(
                session_id=session_id,
                sandbox_id=session.sandbox_id,
                home_dir=session.home_dir,
                status="active",
                last_used_at=now.isoformat().replace("+00:00", "Z"),
                expires_at=expires.isoformat().replace("+00:00", "Z"),
            )
        )

    def _binding_is_active(self, binding: SandboxBindingRow, now: datetime) -> bool:
        if binding.status != "active":
            return False
        expires = datetime.fromisoformat(binding.expires_at.replace("Z", "+00:00"))
        return expires > now

    def _kill(self, session: SandboxSession) -> None:
        try:
            session.kill()
        except Exception:
            pass


class ChatSessionService:
    def __init__(
        self,
        store: ChatStore | None = None,
        sandbox_manager: SandboxManager | None = None,
        secret_box: SecretBox | None = None,
        *,
        run_inline: bool = False,
    ) -> None:
        self.store = store or ChatStore()
        self.secret_box = secret_box or SecretBox()
        self.sandbox_manager = sandbox_manager or SandboxManager(self.store)
        self.run_inline = run_inline
        self._executor = ThreadPoolExecutor(max_workers=int(os.getenv("CHAT_RUN_WORKERS", "4")))
        self._session_locks: dict[str, Lock] = {}
        self._start_lock = Lock()

    def create_session(self, owner_id: str, request: ChatSessionCreateRequest) -> ChatSessionResponse:
        payload = request.model_dump(mode="json")
        payload["provider"] = self._encrypt_provider(payload.get("provider"))
        row = self.store.create_session(owner_id, payload)
        return self._session_response(row)

    def list_sessions(self, owner_id: str) -> list[ChatSessionResponse]:
        return [self._session_response(row) for row in self.store.list_sessions(owner_id)]

    def get_session_detail(self, owner_id: str, session_id: str) -> ChatSessionDetailResponse:
        row = self.store.get_session(owner_id, session_id)
        session = self._session_response(row).model_dump()
        session["messages"] = [self._message_response(item) for item in self.store.list_messages(session_id)]
        session["runs"] = [self._run_response(item) for item in self.store.list_runs(session_id)]
        return ChatSessionDetailResponse.model_validate(session)

    def delete_session(self, owner_id: str, session_id: str) -> None:
        self.store.get_session(owner_id, session_id)
        self.sandbox_manager.release(session_id)
        self.store.soft_delete_session(owner_id, session_id)

    def start_run(self, owner_id: str, session_id: str, message: str) -> ChatRunResponse:
        self.store.get_session(owner_id, session_id)
        if not message.strip():
            raise ValueError("message is required")
        with self._start_lock:
            if self.store.has_active_run(session_id):
                raise ChatConflictError("session already has an active run")
            user_message = self.store.add_message(session_id, "user", message.strip())
            run = self.store.create_run(session_id, user_message.id)
        if self.run_inline:
            self._execute_run(owner_id, session_id, run.id)
        else:
            self._executor.submit(self._execute_run, owner_id, session_id, run.id)
        return self._run_response(self.store.get_run(session_id, run.id))

    def get_run(self, owner_id: str, session_id: str, run_id: str) -> ChatRunResponse:
        self.store.get_session(owner_id, session_id)
        return self._run_response(self.store.get_run(session_id, run_id))

    def _execute_run(self, owner_id: str, session_id: str, run_id: str) -> None:
        lock = self._session_locks.setdefault(session_id, Lock())
        with lock:
            run = self.store.get_run(session_id, run_id)
            self.store.update_run(run_id, status="running")
            try:
                session_row = self.store.get_session(owner_id, session_id)
                messages = self.store.list_messages(session_id)
                opencode_session_id = (
                    session_row.opencode_session_id
                    if self.sandbox_manager.has_cached_active(session_id)
                    else None
                )
                request = self._build_provision_request(
                    session_row,
                    messages,
                    use_opencode_session=bool(opencode_session_id),
                )
                sandbox = self.sandbox_manager.get_or_create(session_id)
                result = OpenCodeProvisioner(sandbox).run_a2a(
                    request,
                    task_id=run_id,
                    context_id=session_id,
                    opencode_session_id=opencode_session_id,
                )
                task_state = (result.task.get("status") or {}).get("state")
                if task_state == "failed":
                    self.store.update_run(
                        run_id,
                        status="failed",
                        stdout=result.provision.stdout,
                        stderr=result.provision.stderr,
                        error=_status_text(result.task) or "OpenCode task failed.",
                        a2a_task_json=result.task,
                        ag_ui_events_json=a2a_task_to_ag_ui_events(result.task),
                    )
                    return
                assistant_text = _assistant_text(result.task) or result.provision.stdout.strip()
                assistant_message_id = None
                if assistant_text:
                    assistant_message_id = self.store.add_message(
                        session_id,
                        "assistant",
                        assistant_text,
                        result.task.get("status", {}).get("message"),
                    ).id
                self.store.update_opencode_session_id(
                    session_id,
                    _extract_opencode_session_id(result.task),
                )
                self.store.update_run(
                    run_id,
                    status="completed",
                    stdout=result.provision.stdout,
                    stderr=result.provision.stderr,
                    assistant_message_id=assistant_message_id,
                    a2a_task_json=result.task,
                    ag_ui_events_json=a2a_task_to_ag_ui_events(result.task),
                )
            except Exception as exc:
                self.store.update_run(run_id, status="failed", error=str(exc))

    def _build_provision_request(
        self,
        session_row: ChatSessionRow,
        messages: list[ChatMessageRow],
        *,
        use_opencode_session: bool,
    ) -> ProvisionRequest:
        provider = self._decrypt_provider(session_row.provider_json)
        if provider is None:
            raise ValueError("chat run requires provider configuration")
        query = _render_history_query(messages, use_full_history=not use_opencode_session)
        return ProvisionRequest(
            scope=session_row.scope,
            workspace_path=session_row.workspace_path,
            config=session_row.config_json,
            mcp=session_row.mcp_json,
            agent_config=session_row.agent_config_json,
            provider=ProviderInput.model_validate(provider),
            query=query,
            skills=[SkillInput.model_validate(item) for item in session_row.skills_json],
            agents=[AgentInput.model_validate(item) for item in session_row.agents_json],
            launch=session_row.launch_json,
            a2a=A2ARuntimeInput.model_validate(session_row.a2a_json),
        )

    def _encrypt_provider(self, provider: dict[str, Any] | None) -> dict[str, Any] | None:
        if provider is None:
            return None
        encrypted = dict(provider)
        if encrypted.get("api_key"):
            encrypted["api_key"] = self.secret_box.encrypt(str(encrypted["api_key"]))
            encrypted["api_key_encrypted"] = True
        return encrypted

    def _decrypt_provider(self, provider: dict[str, Any] | None) -> dict[str, Any] | None:
        if provider is None:
            return None
        decrypted = dict(provider)
        if decrypted.get("api_key_encrypted"):
            decrypted["api_key"] = self.secret_box.decrypt(decrypted.get("api_key"))
            decrypted.pop("api_key_encrypted", None)
        return decrypted

    def _session_response(self, row: ChatSessionRow) -> ChatSessionResponse:
        binding = self.store.get_binding(row.id)
        provider = dict(row.provider_json) if row.provider_json else None
        if provider is not None:
            provider.pop("api_key", None)
            provider.pop("api_key_encrypted", None)
        return ChatSessionResponse(
            id=row.id,
            title=row.title,
            status=row.status,
            scope=row.scope,
            workspace_path=row.workspace_path,
            provider=provider,
            opencode_session_id=row.opencode_session_id,
            sandbox=ChatSandboxBindingResponse(**binding.__dict__) if binding else None,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    def _message_response(self, row: ChatMessageRow) -> ChatMessageResponse:
        return ChatMessageResponse(
            id=row.id,
            role=row.role,
            content=row.content,
            a2a_message=row.a2a_message_json,
            created_at=row.created_at,
        )

    def _run_response(self, row: ChatRunRow) -> ChatRunResponse:
        return ChatRunResponse(
            id=row.id,
            session_id=row.session_id,
            status=row.status,
            user_message_id=row.user_message_id,
            assistant_message_id=row.assistant_message_id,
            stdout=row.stdout,
            stderr=row.stderr,
            error=row.error,
            a2a_task=row.a2a_task_json,
            ag_ui_events=row.ag_ui_events_json,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )


def owner_from_authorization(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise ValueError("Authorization Bearer token is required")
    token = authorization.split(" ", 1)[1].strip()
    parts = token.split(".")
    if len(parts) >= 2:
        try:
            payload = parts[1] + "=" * (-len(parts[1]) % 4)
            decoded = json.loads(base64.urlsafe_b64decode(payload.encode("ascii")))
            sub = decoded.get("sub")
            if isinstance(sub, str) and sub:
                return sub
        except Exception:
            pass
    if token:
        return token
    raise ValueError("Authorization Bearer token is required")


def _render_history_query(messages: list[ChatMessageRow], *, use_full_history: bool) -> str:
    if not messages:
        raise ValueError("chat run requires a user message")
    latest = messages[-1].content
    if not use_full_history:
        return latest
    lines = [
        "Continue this conversation. Use the prior messages as context and answer the latest user message.",
        "",
    ]
    for message in messages:
        role = "User" if message.role == "user" else "Assistant"
        lines.append(f"{role}: {message.content}")
    return "\n".join(lines).strip()


def _assistant_text(task: dict[str, Any]) -> str:
    chunks: list[str] = []
    for artifact in task.get("artifacts") or []:
        for part in artifact.get("parts") or []:
            text = part.get("text") if isinstance(part, dict) else None
            if text:
                chunks.append(text)
    return "\n".join(chunks).strip()


def _extract_opencode_session_id(task: dict[str, Any]) -> str | None:
    raw_events = (task.get("metadata") or {}).get("rawOpenCodeEvents") or []
    stack: list[Any] = list(raw_events)
    while stack:
        value = stack.pop()
        if isinstance(value, dict):
            for key in ("sessionID", "sessionId", "session_id"):
                candidate = value.get(key)
                if isinstance(candidate, str) and candidate:
                    return candidate
            stack.extend(value.values())
        elif isinstance(value, list):
            stack.extend(value)
    return None


def _status_text(task: dict[str, Any]) -> str:
    message = (task.get("status") or {}).get("message") or {}
    parts = message.get("parts") or []
    return "\n".join(
        part.get("text", "") for part in parts if isinstance(part, dict) and part.get("text")
    ).strip()

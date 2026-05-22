from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
import json
import uuid

from .schemas import ProvisionResponse


A2A_VERSION = "1.0"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def text_part(text: str, media_type: str = "text/plain") -> dict[str, Any]:
    return {"kind": "text", "text": text, "mediaType": media_type}


def data_part(data: Any) -> dict[str, Any]:
    return {"kind": "data", "data": data, "mediaType": "application/json"}


def a2a_message(
    *,
    role: str,
    parts: list[dict[str, Any]],
    message_id: str | None = None,
    task_id: str | None = None,
    context_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    message: dict[str, Any] = {
        "messageId": message_id or str(uuid.uuid4()),
        "role": role,
        "parts": parts,
    }
    if task_id:
        message["taskId"] = task_id
    if context_id:
        message["contextId"] = context_id
    if metadata:
        message["metadata"] = metadata
    return message


def extract_text_from_a2a_message(message: dict[str, Any]) -> str:
    chunks: list[str] = []
    for part in message.get("parts") or []:
        if not isinstance(part, dict):
            continue
        text = part.get("text")
        if isinstance(text, str):
            chunks.append(text)
        data = part.get("data")
        if isinstance(data, str):
            chunks.append(data)
    return "\n".join(chunk for chunk in chunks if chunk).strip()


def normalize_a2a_message(message: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(message)
    role = normalized.get("role")
    if role == "ROLE_USER":
        normalized["role"] = "user"
    elif role == "ROLE_AGENT":
        normalized["role"] = "agent"

    parts = []
    for part in normalized.get("parts") or []:
        if isinstance(part, dict) and "kind" not in part:
            if "text" in part:
                part = {"kind": "text", **part}
            elif "data" in part:
                part = {"kind": "data", **part}
        parts.append(part)
    normalized["parts"] = parts
    return normalized


def parse_opencode_json_output(stdout: str) -> tuple[str, list[dict[str, Any]]]:
    """Parse OpenCode --format json output without binding to one CLI schema."""
    raw_events: list[dict[str, Any]] = []
    text_chunks: list[str] = []
    plain_lines: list[str] = []

    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            plain_lines.append(line)
            continue
        if isinstance(payload, dict):
            raw_events.append(payload)
            text_chunks.extend(_extract_likely_text(payload))
        else:
            raw_events.append({"value": payload})
            if isinstance(payload, str):
                text_chunks.append(payload)

    text = "\n".join(_dedupe_preserve_order(text_chunks)).strip()
    if not text:
        text = "\n".join(plain_lines).strip()
    if not raw_events and plain_lines:
        raw_events.append({"type": "stdout", "text": "\n".join(plain_lines)})
    return text, raw_events


def _extract_likely_text(value: Any) -> list[str]:
    chunks: list[str] = []
    if isinstance(value, dict):
        role = str(value.get("role", "")).lower()
        event_type = str(value.get("type", "")).lower()
        if role in {"assistant", "agent", "role_agent"} or event_type in {
            "message",
            "assistant",
            "content",
            "text",
            "response",
        }:
            for key in ("text", "content", "delta", "message"):
                candidate = value.get(key)
                if isinstance(candidate, str):
                    chunks.append(candidate)
                elif isinstance(candidate, list):
                    for item in candidate:
                        chunks.extend(_extract_likely_text(item))
                elif isinstance(candidate, dict):
                    chunks.extend(_extract_likely_text(candidate))
        for key in ("part", "parts", "content", "message", "data"):
            nested = value.get(key)
            if isinstance(nested, list):
                for item in nested:
                    chunks.extend(_extract_likely_text(item))
            elif isinstance(nested, dict):
                chunks.extend(_extract_likely_text(nested))
    elif isinstance(value, list):
        for item in value:
            chunks.extend(_extract_likely_text(item))
    return [chunk for chunk in chunks if chunk.strip()]


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = value.strip()
        if normalized and normalized not in seen:
            result.append(normalized)
            seen.add(normalized)
    return result


def build_a2a_task(
    *,
    response: ProvisionResponse,
    query: str,
    task_id: str | None = None,
    context_id: str | None = None,
    user_message: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    task_id = task_id or str(uuid.uuid4())
    context_id = context_id or str(uuid.uuid4())
    now = utc_now()
    result_text, raw_events = parse_opencode_json_output(response.stdout)
    failed = bool(response.stderr and not response.stdout.strip())
    state = "failed" if failed else "completed"
    status_text = response.stderr.strip() if failed else "OpenCode task completed."

    user_msg = user_message or a2a_message(
        role="user",
        parts=[text_part(query)],
        task_id=task_id,
        context_id=context_id,
    )
    user_msg = normalize_a2a_message(user_msg)
    user_msg.setdefault("taskId", task_id)
    user_msg.setdefault("contextId", context_id)

    status_message = a2a_message(
        role="agent",
        parts=[text_part(status_text)],
        task_id=task_id,
        context_id=context_id,
    )

    artifacts = []
    if result_text:
        artifacts.append(
            {
                "artifactId": str(uuid.uuid4()),
                "name": "opencode-result",
                "description": "Final textual output returned by OpenCode.",
                "parts": [text_part(result_text)],
                "metadata": {"source": "opencode.stdout"},
            }
        )
    artifacts.append(
        {
            "artifactId": str(uuid.uuid4()),
            "name": "opencode-execution",
            "description": "OpenCode sandbox execution metadata.",
            "parts": [
                data_part(
                    {
                        "sandboxId": response.sandbox_id,
                        "configRoot": response.config_root,
                        "filesWritten": [item.model_dump() for item in response.files_written],
                        "launchCommand": response.launch_command,
                        "publicUrl": response.public_url,
                        "stderr": response.stderr,
                    }
                )
            ],
            "metadata": {"source": "backend"},
        }
    )

    task = {
        "id": task_id,
        "contextId": context_id,
        "status": {
            "state": state,
            "message": status_message,
            "timestamp": now,
        },
        "artifacts": artifacts,
        "history": [user_msg, status_message],
        "metadata": {
            "a2aVersion": A2A_VERSION,
            "backend": "opencode-e2b",
            "opencode": {
                "sandboxId": response.sandbox_id,
                "scope": response.scope.value,
                "configRoot": response.config_root,
                "rawEventCount": len(raw_events),
            },
            "rawOpenCodeEvents": raw_events,
        },
    }
    stream_events = build_a2a_stream_events(task)
    return task, stream_events


def build_a2a_stream_events(task: dict[str, Any]) -> list[dict[str, Any]]:
    task_id = task["id"]
    context_id = task.get("contextId", "")
    events: list[dict[str, Any]] = [
        {
            "task": {
                "id": task_id,
                "contextId": context_id,
                "status": {
                    "state": "working",
                    "timestamp": utc_now(),
                },
            }
        }
    ]
    for artifact in task.get("artifacts") or []:
        events.append(
            {
                "artifactUpdate": {
                    "taskId": task_id,
                    "contextId": context_id,
                    "artifact": artifact,
                    "append": False,
                    "lastChunk": True,
                }
            }
        )
    events.append(
        {
            "statusUpdate": {
                "taskId": task_id,
                "contextId": context_id,
                "status": task["status"],
            }
        }
    )
    return events


def a2a_task_to_ag_ui_events(task: dict[str, Any]) -> list[dict[str, Any]]:
    run_id = task["id"]
    context_id = task.get("contextId")
    timestamp = utc_now()
    events: list[dict[str, Any]] = [
        {
            "type": "RUN_STARTED",
            "runId": run_id,
            "threadId": context_id,
            "timestamp": timestamp,
            "rawEvent": {"source": "a2a", "taskId": run_id},
        }
    ]

    emitted_text = False
    for artifact in task.get("artifacts") or []:
        for part in artifact.get("parts") or []:
            text = part.get("text") if isinstance(part, dict) else None
            if not text:
                continue
            message_id = f"{artifact['artifactId']}-message"
            events.extend(
                [
                    {
                        "type": "TEXT_MESSAGE_START",
                        "messageId": message_id,
                        "role": "assistant",
                        "timestamp": utc_now(),
                        "rawEvent": {"source": "a2a", "artifactId": artifact["artifactId"]},
                    },
                    {
                        "type": "TEXT_MESSAGE_CONTENT",
                        "messageId": message_id,
                        "delta": text,
                        "timestamp": utc_now(),
                        "rawEvent": {"source": "a2a", "artifactId": artifact["artifactId"]},
                    },
                    {
                        "type": "TEXT_MESSAGE_END",
                        "messageId": message_id,
                        "timestamp": utc_now(),
                        "rawEvent": {"source": "a2a", "artifactId": artifact["artifactId"]},
                    },
                ]
            )
            emitted_text = True

    state = (task.get("status") or {}).get("state")
    if state in {"failed", "TASK_STATE_FAILED"}:
        events.append(
            {
                "type": "RUN_ERROR",
                "runId": run_id,
                "message": _status_text(task) or "OpenCode task failed.",
                "timestamp": utc_now(),
                "rawEvent": {"source": "a2a", "status": task.get("status")},
            }
        )
    else:
        if not emitted_text:
            events.append(
                {
                    "type": "RAW",
                    "source": "a2a",
                    "event": task,
                    "timestamp": utc_now(),
                }
            )
        events.append(
            {
                "type": "RUN_FINISHED",
                "runId": run_id,
                "timestamp": utc_now(),
                "rawEvent": {"source": "a2a", "status": task.get("status")},
            }
        )
    return events


def _status_text(task: dict[str, Any]) -> str:
    message = (task.get("status") or {}).get("message") or {}
    parts = message.get("parts") or []
    return "\n".join(
        part.get("text", "") for part in parts if isinstance(part, dict) and part.get("text")
    ).strip()


def build_agent_card(base_url: str = "") -> dict[str, Any]:
    rpc_url = f"{base_url.rstrip('/')}/rpc" if base_url else "/rpc"
    return {
        "name": "OpenCode E2B Agent",
        "description": "Runs OpenCode in an E2B sandbox after writing frontend-provided OpenCode configuration.",
        "version": "0.1.0",
        "supportedInterfaces": [
            {
                "url": rpc_url,
                "protocolBinding": "JSONRPC",
                "protocolVersion": A2A_VERSION,
            }
        ],
        "capabilities": {
            "streaming": True,
            "pushNotifications": False,
            "stateTransitionHistory": True,
        },
        "defaultInputModes": ["text/plain", "application/json"],
        "defaultOutputModes": ["text/plain", "application/json"],
        "skills": [
            {
                "id": "opencode-run",
                "name": "OpenCode Run",
                "description": "Execute a user query with OpenCode in an isolated E2B sandbox.",
                "tags": ["opencode", "e2b", "code-generation"],
                "examples": ["帮我写一个加法计算器"],
                "inputModes": ["text/plain", "application/json"],
                "outputModes": ["text/plain", "application/json"],
            }
        ],
    }

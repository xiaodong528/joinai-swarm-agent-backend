from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SessionPaths:
    session_id: str
    template_root: str = "/home/user/template"
    sessions_root: str = "/home/user/template/.engine-sessions"

    @property
    def session_root(self) -> str:
        return f"{self.sessions_root}/{self.session_id}"

    @property
    def generated_root(self) -> str:
        return f"{self.session_root}/generated"

    @property
    def session_export_root(self) -> str:
        return f"{self.session_root}/session-export"

    @property
    def state_root(self) -> str:
        return f"{self.session_root}/state"

    @property
    def status_file(self) -> str:
        return f"{self.state_root}/status.json"

    @property
    def events_file(self) -> str:
        return f"{self.state_root}/events.jsonl"

    @property
    def dead_letter_file(self) -> str:
        return f"{self.state_root}/webhook-dead-letter.jsonl"

    @property
    def query_file(self) -> str:
        return f"{self.state_root}/last-query.txt"

    @property
    def prompt_file(self) -> str:
        return f"{self.state_root}/last-prompt.txt"

    @property
    def result_file(self) -> str:
        return f"{self.state_root}/last-result.txt"


@dataclass(frozen=True)
class RuntimePaths:
    runtime_session_id: str
    template_root: str = "/home/user/template"
    runtime_root: str = "/home/user/template/.runtime-sessions"

    @property
    def session_root(self) -> str:
        return f"{self.runtime_root}/{self.runtime_session_id}"

    @property
    def package_root(self) -> str:
        return f"{self.session_root}/package"

    @property
    def session_export_root(self) -> str:
        return f"{self.session_root}/session-export"

    @property
    def state_root(self) -> str:
        return f"{self.session_root}/state"

    @property
    def status_file(self) -> str:
        return f"{self.state_root}/status.json"

    @property
    def events_file(self) -> str:
        return f"{self.state_root}/events.jsonl"

    @property
    def dead_letter_file(self) -> str:
        return f"{self.state_root}/webhook-dead-letter.jsonl"

    @property
    def query_file(self) -> str:
        return f"{self.state_root}/last-query.txt"

    @property
    def result_file(self) -> str:
        return f"{self.state_root}/last-result.txt"

    @property
    def archive_file(self) -> str:
        return f"{self.state_root}/source-package.tar.gz.b64"

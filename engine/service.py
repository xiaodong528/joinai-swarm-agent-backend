from __future__ import annotations

import json
import shlex
import uuid

from engine.assets import AssetManager
from engine.config import Settings
from engine.models import (
    CreateRuntimeSessionRequest,
    CreateSessionRequest,
    EngineResponse,
    GenerateRequest,
    RuntimeQueryRequest,
    RuntimeSessionResponse,
    SessionStatus,
    TemplateResponse,
)
from engine.paths import RuntimePaths, SessionPaths
from engine.sandbox import CommandResult, E2BSandboxFactory, SandboxFactory, SandboxHandle
from engine.state import GeneratedTemplateRecord, RuntimeSessionRecord, SessionRecord, utc_now


class AgentEngineService:
    def __init__(self, settings: Settings | None = None, sandbox_factory: SandboxFactory | None = None):
        self.settings = settings or Settings()
        self.assets = AssetManager(self.settings)
        self.sandbox_factory = sandbox_factory or E2BSandboxFactory(self.settings)
        self.records: dict[str, SessionRecord] = {}
        self.sandboxes: dict[str, SandboxHandle] = {}
        self.runtime_records: dict[str, RuntimeSessionRecord] = {}
        self.runtime_sandboxes: dict[str, SandboxHandle] = {}
        self.templates: dict[str, GeneratedTemplateRecord] = {}

    def create_session(self, request: CreateSessionRequest) -> EngineResponse:
        self.assets.validate()
        session_id = uuid.uuid4().hex
        paths = SessionPaths(session_id=session_id)
        env = self._base_env(request.user_id, session_id, None, paths, request.webhook_url, request.session_status_url)
        sandbox = self.sandbox_factory.create(env)
        env = self._base_env(request.user_id, session_id, sandbox.sandbox_id, paths, request.webhook_url, request.session_status_url)
        record = SessionRecord(
            user_id=request.user_id,
            session_id=session_id,
            sandbox_id=sandbox.sandbox_id,
            paths=paths,
            status=SessionStatus.INITIALIZING,
            webhook_url=str(request.webhook_url) if request.webhook_url else None,
            session_status_url=str(request.session_status_url) if request.session_status_url else None,
            keep_sandbox=request.keep_sandbox,
        )
        self.records[session_id] = record
        self.sandboxes[session_id] = sandbox
        try:
            self._initialize_sandbox(sandbox, record, env)
            self._write_status(sandbox, record, SessionStatus.READY)
        except Exception as exc:
            record.errors.append(str(exc))
            self._write_status(sandbox, record, SessionStatus.FAILED)
            raise
        return self._response(record)

    def generate(self, session_id: str, request: GenerateRequest) -> EngineResponse:
        record = self._record(session_id, request.user_id)
        sandbox = self._sandbox(record, request.sandbox_id)
        timeout_ms = request.timeout_ms or self.settings.default_timeout_ms
        self._write_status(sandbox, record, SessionStatus.RUNNING, {"query": request.query})
        sandbox.write_text(record.paths.query_file, request.query)
        prompt = self._build_prompt(record, request)
        sandbox.write_text(record.paths.prompt_file, prompt)
        env = self._base_env(record.user_id, record.session_id, record.sandbox_id, record.paths, record.webhook_url, record.session_status_url)
        command = f"opencode run --agent expert-team-manager {shlex.quote(prompt)}"
        result = sandbox.run(command, cwd=record.paths.template_root, timeout_ms=timeout_ms, env=env)
        sandbox.write_text(record.paths.result_file, self._result_text(result))
        if not result.ok:
            record.errors.append(self._error_from_result(result))
            self._write_status(sandbox, record, SessionStatus.FAILED)
            return self._response(record)

        slug = request.output_slug or self._extract_slug(result.stdout) or "generated-agent-team"
        output_root = self._resolve_output_root(record, request.output_root)
        package_path = f"{output_root}/{slug}"
        record.generated_package_path = package_path
        record.data["last_stdout"] = result.stdout[-4000:]
        self._write_status(sandbox, record, SessionStatus.GENERATED, {"generated_package_path": package_path})
        check = self._check_generated_package(sandbox, package_path, timeout_ms, env)
        if not check.ok:
            record.errors.append(self._error_from_result(check))
            self._write_status(sandbox, record, SessionStatus.FAILED)
            return self._response(record)
        validate = self._validate_generated_package(sandbox, package_path, timeout_ms, env)
        record.data["validation_stdout"] = validate.stdout[-4000:]
        if not validate.ok:
            record.errors.append(self._error_from_result(validate))
            self._write_status(sandbox, record, SessionStatus.FAILED)
            return self._response(record)
        template = self._register_template(record, output_root, slug, package_path)
        sandbox.write_text(
            f"{record.paths.state_root}/template-{template.template_id}.json",
            json.dumps(template.to_payload(), ensure_ascii=False, indent=2) + "\n",
        )
        self._write_status(sandbox, record, SessionStatus.VALIDATED, {"generated_package_path": package_path, "template_id": template.template_id})
        return self._response(record)

    def status(self, session_id: str, user_id: str | None = None) -> EngineResponse:
        record = self._record(session_id, user_id)
        return self._response(record)

    def create_runtime_session(self, request: CreateRuntimeSessionRequest) -> RuntimeSessionResponse:
        source_record, package_path = self._runtime_source(request)
        source_sandbox = self._sandbox(source_record, request.source_sandbox_id)
        if not package_path:
            raise ValueError("source session has no generated_package_path; generate a package first or provide generated_package_path")
        self._ensure_template_path(package_path, "generated_package_path")

        runtime_session_id = uuid.uuid4().hex
        paths = RuntimePaths(runtime_session_id=runtime_session_id)
        env = self._base_env(request.user_id, runtime_session_id, None, paths, request.webhook_url, request.session_status_url)
        sandbox = self.sandbox_factory.create(env)
        env = self._base_env(request.user_id, runtime_session_id, sandbox.sandbox_id, paths, request.webhook_url, request.session_status_url)
        record = RuntimeSessionRecord(
            user_id=request.user_id,
            runtime_session_id=runtime_session_id,
            sandbox_id=sandbox.sandbox_id,
            paths=paths,
            source_session_id=source_record.session_id,
            source_sandbox_id=source_record.sandbox_id,
            source_package_path=package_path,
            status=SessionStatus.INITIALIZING,
            webhook_url=str(request.webhook_url) if request.webhook_url else None,
            session_status_url=str(request.session_status_url) if request.session_status_url else None,
            keep_sandbox=request.keep_sandbox,
        )
        self.runtime_records[runtime_session_id] = record
        self.runtime_sandboxes[runtime_session_id] = sandbox
        try:
            self._initialize_runtime_sandbox(source_sandbox, sandbox, record, package_path, env)
            self._write_runtime_status(sandbox, record, SessionStatus.READY)
        except Exception as exc:
            record.errors.append(str(exc))
            self._write_runtime_status(sandbox, record, SessionStatus.FAILED)
            raise
        return self._runtime_response(record)

    def list_templates(self, user_id: str) -> list[TemplateResponse]:
        return [
            self._template_response(item)
            for item in sorted(self.templates.values(), key=lambda x: x.created_at)
            if item.user_id == user_id
        ]

    def get_template(self, template_id: str, user_id: str | None = None) -> TemplateResponse:
        return self._template_response(self._template_record(template_id, user_id))

    def runtime_query(self, runtime_session_id: str, request: RuntimeQueryRequest) -> RuntimeSessionResponse:
        record = self._runtime_record(runtime_session_id, request.user_id)
        sandbox = self._runtime_sandbox(record, request.sandbox_id)
        timeout_ms = request.timeout_ms or self.settings.default_timeout_ms
        agent = request.agent or str(record.data.get("primary_agent") or "")
        self._write_runtime_status(sandbox, record, SessionStatus.RUNNING, {"query": request.query, "agent": agent or None})
        sandbox.write_text(record.paths.query_file, request.query)

        command = f"opencode run {shlex.quote(request.query)}"
        if agent:
            command = f"opencode run --agent {shlex.quote(agent)} {shlex.quote(request.query)}"
        result = sandbox.run(command, cwd=record.paths.package_root, timeout_ms=timeout_ms, env=self._runtime_env(record))
        sandbox.write_text(record.paths.result_file, self._result_text(result))
        record.data["last_stdout"] = result.stdout[-4000:]
        record.data["last_stderr"] = result.stderr[-4000:]
        if not result.ok:
            record.errors.append(self._error_from_result(result))
            self._write_runtime_status(sandbox, record, SessionStatus.FAILED)
            return self._runtime_response(record)
        self._write_runtime_status(sandbox, record, SessionStatus.VALIDATED, {"last_result_path": record.paths.result_file})
        return self._runtime_response(record)

    def runtime_status(self, runtime_session_id: str, user_id: str | None = None) -> RuntimeSessionResponse:
        record = self._runtime_record(runtime_session_id, user_id)
        return self._runtime_response(record)

    def close_runtime_session(self, runtime_session_id: str, user_id: str, sandbox_id: str | None = None) -> RuntimeSessionResponse:
        record = self._runtime_record(runtime_session_id, user_id)
        sandbox = self._runtime_sandbox(record, sandbox_id)
        self._write_runtime_status(sandbox, record, SessionStatus.CLOSED)
        if not record.keep_sandbox:
            sandbox.close()
        return self._runtime_response(record)

    def close(self, session_id: str, user_id: str, sandbox_id: str | None = None) -> EngineResponse:
        record = self._record(session_id, user_id)
        sandbox = self._sandbox(record, sandbox_id)
        self._write_status(sandbox, record, SessionStatus.CLOSED)
        if not record.keep_sandbox:
            sandbox.close()
        return self._response(record)

    def _initialize_sandbox(self, sandbox: SandboxHandle, record: SessionRecord, env: dict[str, str]) -> None:
        dirs = [
            record.paths.template_root,
            f"{record.paths.template_root}/.opencode/plugins",
            record.paths.generated_root,
            record.paths.session_export_root,
            record.paths.state_root,
        ]
        sandbox.run("mkdir -p " + " ".join(shlex.quote(item) for item in dirs), timeout_ms=30000, env=env)
        for src, rel in self.assets.iter_template_files():
            sandbox.write_text(f"{record.paths.template_root}/{rel}", self.assets.read_template_file(src, rel))
        for name, content in self.assets.plugin_files().items():
            sandbox.write_text(f"{record.paths.template_root}/.opencode/plugins/{name}", content)
        sandbox.run('python -c "import yaml" || python -m pip install pyyaml', cwd=record.paths.template_root, timeout_ms=120000, env=env)
        self._write_status(sandbox, record, SessionStatus.INITIALIZING)

    def _write_status(
        self,
        sandbox: SandboxHandle,
        record: SessionRecord,
        status: SessionStatus,
        extra: dict[str, object] | None = None,
    ) -> None:
        record.status = status
        record.updated_at = utc_now()
        if extra:
            record.data.update(extra)
        sandbox.write_text(record.paths.status_file, json.dumps(record.to_payload(), ensure_ascii=False, indent=2) + "\n")

    def _write_runtime_status(
        self,
        sandbox: SandboxHandle,
        record: RuntimeSessionRecord,
        status: SessionStatus,
        extra: dict[str, object] | None = None,
    ) -> None:
        record.status = status
        record.updated_at = utc_now()
        if extra:
            record.data.update(extra)
        sandbox.write_text(record.paths.status_file, json.dumps(record.to_payload(), ensure_ascii=False, indent=2) + "\n")

    def _record(self, session_id: str, user_id: str | None) -> SessionRecord:
        record = self.records.get(session_id)
        if not record:
            raise KeyError(f"Unknown session_id: {session_id}")
        if user_id and record.user_id != user_id:
            raise PermissionError("user_id does not own this session_id")
        return record

    def _sandbox(self, record: SessionRecord, sandbox_id: str | None) -> SandboxHandle:
        if sandbox_id and sandbox_id != record.sandbox_id:
            raise PermissionError("sandbox_id does not match this session_id")
        sandbox = self.sandboxes.get(record.session_id)
        if sandbox:
            return sandbox
        env = self._base_env(record.user_id, record.session_id, record.sandbox_id, record.paths, record.webhook_url, record.session_status_url)
        sandbox = self.sandbox_factory.connect(record.sandbox_id, env)
        self.sandboxes[record.session_id] = sandbox
        return sandbox

    def _runtime_record(self, runtime_session_id: str, user_id: str | None) -> RuntimeSessionRecord:
        record = self.runtime_records.get(runtime_session_id)
        if not record:
            raise KeyError(f"Unknown runtime_session_id: {runtime_session_id}")
        if user_id and record.user_id != user_id:
            raise PermissionError("user_id does not own this runtime_session_id")
        return record

    def _template_record(self, template_id: str, user_id: str | None) -> GeneratedTemplateRecord:
        record = self.templates.get(template_id)
        if not record:
            raise KeyError(f"Unknown template_id: {template_id}")
        if user_id and record.user_id != user_id:
            raise PermissionError("user_id does not own this template_id")
        return record

    def _runtime_source(self, request: CreateRuntimeSessionRequest) -> tuple[SessionRecord, str | None]:
        if request.template_id:
            template = self._template_record(request.template_id, request.user_id)
            source_record = self._record(template.source_session_id, request.user_id)
            return source_record, request.generated_package_path or template.package_path
        if not request.source_session_id:
            raise ValueError("template_id or source_session_id is required")
        source_record = self._record(request.source_session_id, request.user_id)
        return source_record, request.generated_package_path or source_record.generated_package_path

    def _runtime_sandbox(self, record: RuntimeSessionRecord, sandbox_id: str | None) -> SandboxHandle:
        if sandbox_id and sandbox_id != record.sandbox_id:
            raise PermissionError("sandbox_id does not match this runtime_session_id")
        sandbox = self.runtime_sandboxes.get(record.runtime_session_id)
        if sandbox:
            return sandbox
        sandbox = self.sandbox_factory.connect(record.sandbox_id, self._runtime_env(record))
        self.runtime_sandboxes[record.runtime_session_id] = sandbox
        return sandbox

    def _runtime_env(self, record: RuntimeSessionRecord) -> dict[str, str]:
        return self._base_env(record.user_id, record.runtime_session_id, record.sandbox_id, record.paths, record.webhook_url, record.session_status_url)

    def _base_env(
        self,
        user_id: str,
        session_id: str,
        sandbox_id: str | None,
        paths: SessionPaths,
        webhook_url: str | object | None,
        status_url: str | object | None,
    ) -> dict[str, str]:
        env = {
            "DEEPSEEK_API_KEY": self.settings.deepseek_api_key or "",
            "OPENCODE_MODEL": self.settings.opencode_model,
            "OPENCODE_SESSION_EXPORT_DIR": paths.session_export_root,
            "ENGINE_USER_ID": user_id,
            "ENGINE_SESSION_ID": session_id,
            "ENGINE_SANDBOX_ID": sandbox_id or "",
            "ENGINE_EVENTS_FILE": paths.events_file,
            "ENGINE_DEAD_LETTER_FILE": paths.dead_letter_file,
        }
        if webhook_url:
            env["ENGINE_WEBHOOK_URL"] = str(webhook_url)
        if status_url:
            env["ENGINE_STATUS_WEBHOOK_URL"] = str(status_url)
        return env

    def _initialize_runtime_sandbox(
        self,
        source_sandbox: SandboxHandle,
        runtime_sandbox: SandboxHandle,
        record: RuntimeSessionRecord,
        package_path: str,
        env: dict[str, str],
    ) -> None:
        dirs = [
            record.paths.template_root,
            record.paths.session_root,
            record.paths.package_root,
            record.paths.session_export_root,
            record.paths.state_root,
        ]
        runtime_sandbox.run("mkdir -p " + " ".join(shlex.quote(item) for item in dirs), timeout_ms=30000, env=env)
        self._write_runtime_status(runtime_sandbox, record, SessionStatus.INITIALIZING)
        archive = self._archive_package(source_sandbox, package_path, env)
        runtime_sandbox.write_text(record.paths.archive_file, archive)
        self._extract_runtime_package(runtime_sandbox, record, env)
        self._install_runtime_plugins(runtime_sandbox, record, env)
        self._check_runtime_package(runtime_sandbox, record, env)
        primary = self._detect_primary_agent(runtime_sandbox, record, env)
        if primary:
            record.data["primary_agent"] = primary

    def _archive_package(self, source_sandbox: SandboxHandle, package_path: str, env: dict[str, str]) -> str:
        quoted = shlex.quote(package_path)
        command = f"test -d {quoted} && tar -C {quoted} -czf - . | base64 -w0"
        result = source_sandbox.run(command, timeout_ms=self.settings.default_timeout_ms, env=env)
        if not result.ok:
            raise RuntimeError(f"failed to archive generated package: {self._error_from_result(result)}")
        archive = result.stdout.strip()
        if not archive:
            raise RuntimeError("generated package archive was empty")
        return archive

    def _extract_runtime_package(self, sandbox: SandboxHandle, record: RuntimeSessionRecord, env: dict[str, str]) -> None:
        archive = shlex.quote(record.paths.archive_file)
        package = shlex.quote(record.paths.package_root)
        command = f"mkdir -p {package} && base64 -d {archive} | tar -C {package} -xzf -"
        result = sandbox.run(command, timeout_ms=self.settings.default_timeout_ms, env=env)
        if not result.ok:
            raise RuntimeError(f"failed to extract runtime package: {self._error_from_result(result)}")

    def _install_runtime_plugins(self, sandbox: SandboxHandle, record: RuntimeSessionRecord, env: dict[str, str]) -> None:
        plugins_dir = f"{record.paths.package_root}/.opencode/plugins"
        sandbox.run(f"mkdir -p {shlex.quote(plugins_dir)}", timeout_ms=30000, env=env)
        for name, content in self.assets.plugin_files().items():
            sandbox.write_text(f"{plugins_dir}/{name}", content)
        entries = json.dumps(["./.opencode/plugins/session-export.ts", "./.opencode/plugins/session-import.ts", "./.opencode/plugins/proxy-hooks.ts"])
        code = (
            "import json, pathlib; "
            "p=pathlib.Path('opencode.json'); "
            "d=json.loads(p.read_text(encoding='utf-8')); "
            f"add={entries}; "
            "plugins=list(d.get('plugin') or []); "
            "plugins.extend(x for x in add if x not in plugins); "
            "d['plugin']=plugins; "
            "p.write_text(json.dumps(d, ensure_ascii=False, indent=2)+'\\n', encoding='utf-8')"
        )
        result = sandbox.run(f"python -c {shlex.quote(code)}", cwd=record.paths.package_root, timeout_ms=30000, env=env)
        if not result.ok:
            raise RuntimeError(f"failed to merge runtime plugin config: {self._error_from_result(result)}")

    def _check_runtime_package(self, sandbox: SandboxHandle, record: RuntimeSessionRecord, env: dict[str, str]) -> None:
        command = (
            "test -f swarm.yaml && "
            "test -f opencode.json && "
            "test -d .opencode/agents && "
            "test -d .opencode/skills"
        )
        result = sandbox.run(command, cwd=record.paths.package_root, timeout_ms=30000, env=env)
        if not result.ok:
            raise RuntimeError(f"runtime package is missing required OpenCode files: {self._error_from_result(result)}")

    def _detect_primary_agent(self, sandbox: SandboxHandle, record: RuntimeSessionRecord, env: dict[str, str]) -> str | None:
        code = (
            "import json; "
            "d=json.load(open('opencode.json', encoding='utf-8')); "
            "agents=d.get('agent') or {}; "
            "print(next((k for k,v in agents.items() if isinstance(v, dict) and v.get('mode')=='primary'), ''))"
        )
        result = sandbox.run(f"python -c {shlex.quote(code)}", cwd=record.paths.package_root, timeout_ms=30000, env=env)
        if result.ok:
            return result.stdout.strip() or None
        return None

    def _build_prompt(self, record: SessionRecord, request: GenerateRequest) -> str:
        slug_line = f"\nPreferred output slug: {request.output_slug}" if request.output_slug else ""
        output_root = self._resolve_output_root(record, request.output_root)
        return f"""This is a non-interactive automated engine request. Do not ask follow-up questions and do not wait for user confirmation.
You are explicitly authorized to make reasonable assumptions, write files under the requested output directory, use --force for this session output, generate the package, and validate it.

Use the local Juzhigonfang expert team manager template to create an OpenCode agent team package.

User id: {record.user_id}
Session id: {record.session_id}
Output directory: {output_root}{slug_line}

User query:
{request.query}

Required actions:
1. Use the juzhigonfang-expert-agent-team-manager skill.
2. Derive a complete swarm.yaml from the query without asking for confirmation.
3. Save the manifest to {record.paths.session_root}/swarm.yaml.
4. Generate the package with:
   python .opencode/skills/juzhigonfang-expert-agent-team-manager/scripts/create_expert_team.py --manifest {record.paths.session_root}/swarm.yaml --output-dir {output_root} --package --force
5. Validate the generated package with:
   python .opencode/skills/juzhigonfang-expert-agent-team-manager/scripts/validate_expert_team.py {output_root}/{request.output_slug or '<derived-slug>'}
6. Return the generated package path, validation result, and any remaining risks.
"""

    @staticmethod
    def _extract_slug(output: str) -> str | None:
        for line in output.splitlines():
            marker = "/.engine-sessions/"
            if marker in line and "/generated/" in line:
                return line.rsplit("/generated/", 1)[-1].split("/", 1)[0].strip().strip(".")
        return None

    def _check_generated_package(
        self,
        sandbox: SandboxHandle,
        package_path: str,
        timeout_ms: int,
        env: dict[str, str],
    ) -> CommandResult:
        quoted = shlex.quote(package_path)
        command = (
            f"test -f {quoted}/swarm.yaml && "
            f"test -f {quoted}/opencode.json && "
            f"test -d {quoted}/.opencode/agents && "
            f"test -d {quoted}/.opencode/skills"
        )
        return sandbox.run(command, timeout_ms=timeout_ms, env=env)

    def _validate_generated_package(
        self,
        sandbox: SandboxHandle,
        package_path: str,
        timeout_ms: int,
        env: dict[str, str],
    ) -> CommandResult:
        script = (
            f"{self._quote_path(SessionPaths('unused').template_root)}/"
            ".opencode/skills/juzhigonfang-expert-agent-team-manager/scripts/validate_expert_team.py"
        )
        command = f"python {script} {shlex.quote(package_path)}"
        return sandbox.run(command, timeout_ms=timeout_ms, env=env)

    def _resolve_output_root(self, record: SessionRecord, output_root: str | None) -> str:
        if not output_root:
            return record.paths.generated_root
        cleaned = output_root.replace("\\", "/").rstrip("/")
        if not cleaned:
            return record.paths.generated_root
        if cleaned.startswith("/"):
            allowed = record.paths.template_root.rstrip("/") + "/"
            if cleaned != record.paths.template_root and not cleaned.startswith(allowed):
                raise ValueError(f"output_root must be inside {record.paths.template_root}")
            return cleaned
        return f"{record.paths.template_root}/{cleaned.lstrip('/')}"

    def _register_template(self, record: SessionRecord, output_root: str, output_slug: str, package_path: str) -> GeneratedTemplateRecord:
        template_id = uuid.uuid4().hex
        template = GeneratedTemplateRecord(
            user_id=record.user_id,
            template_id=template_id,
            source_session_id=record.session_id,
            source_sandbox_id=record.sandbox_id,
            package_path=package_path,
            output_root=output_root,
            output_slug=output_slug,
            data={
                "session_export_path": record.paths.session_export_root,
                "state_path": record.paths.status_file,
                "template_state_path": f"{record.paths.state_root}/template-{template_id}.json",
            },
        )
        self.templates[template_id] = template
        record.data["template_id"] = template_id
        return template

    @staticmethod
    def _ensure_template_path(value: str, field: str) -> None:
        cleaned = value.replace("\\", "/")
        allowed = SessionPaths("unused").template_root.rstrip("/") + "/"
        if cleaned == SessionPaths("unused").template_root or cleaned.startswith(allowed):
            return
        raise ValueError(f"{field} must be inside {SessionPaths('unused').template_root}")

    @staticmethod
    def _quote_path(value: str) -> str:
        return shlex.quote(value)

    @staticmethod
    def _result_text(result: CommandResult) -> str:
        return f"exit_code={result.exit_code}\n\nSTDOUT:\n{result.stdout}\n\nSTDERR:\n{result.stderr}\n"

    @staticmethod
    def _error_from_result(result: CommandResult) -> str:
        detail = result.stderr.strip() or result.stdout.strip() or f"Command failed with exit code {result.exit_code}"
        return detail[-2000:]

    @staticmethod
    def _response(record: SessionRecord) -> EngineResponse:
        return EngineResponse(
            user_id=record.user_id,
            session_id=record.session_id,
            sandbox_id=record.sandbox_id,
            status=record.status,
            generated_package_path=record.generated_package_path,
            session_export_path=record.paths.session_export_root,
            state_path=record.paths.status_file,
            errors=record.errors,
            data=record.data,
        )

    @staticmethod
    def _runtime_response(record: RuntimeSessionRecord) -> RuntimeSessionResponse:
        return RuntimeSessionResponse(
            user_id=record.user_id,
            runtime_session_id=record.runtime_session_id,
            sandbox_id=record.sandbox_id,
            status=record.status,
            source_session_id=record.source_session_id,
            source_sandbox_id=record.source_sandbox_id,
            source_package_path=record.source_package_path,
            runtime_package_path=record.paths.package_root,
            session_export_path=record.paths.session_export_root,
            state_path=record.paths.status_file,
            errors=record.errors,
            data=record.data,
        )

    @staticmethod
    def _template_response(record: GeneratedTemplateRecord) -> TemplateResponse:
        return TemplateResponse(
            user_id=record.user_id,
            template_id=record.template_id,
            source_session_id=record.source_session_id,
            source_sandbox_id=record.source_sandbox_id,
            package_path=record.package_path,
            output_root=record.output_root,
            output_slug=record.output_slug,
            status=record.status,
            created_at=record.created_at,
            data=record.data,
        )

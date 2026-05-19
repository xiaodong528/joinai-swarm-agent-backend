from __future__ import annotations

from fastapi import Depends, FastAPI, Request

from .protocols import (
    a2a_task_to_ag_ui_events,
    build_agent_card,
    extract_text_from_a2a_message,
)
from .sandbox import create_session
from .schemas import (
    A2AJsonRpcRequest,
    A2AJsonRpcResponse,
    A2AMessageSendParams,
    A2ARunRequest,
    A2ARunResponse,
    AGUIRunResponse,
    ProvisionRequest,
    ProvisionResponse,
)
from .service import OpenCodeProvisioner


def get_provisioner() -> OpenCodeProvisioner:
    return OpenCodeProvisioner(create_session())


def create_app() -> FastAPI:
    app = FastAPI(title="OpenCode E2B Backend", version="0.1.0")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/.well-known/agent-card.json")
    def agent_card(request: Request) -> dict:
        return build_agent_card(str(request.base_url).rstrip("/"))

    @app.post("/v1/opencode/provision", response_model=ProvisionResponse)
    def provision(
        request: ProvisionRequest,
        provisioner: OpenCodeProvisioner = Depends(get_provisioner),
    ) -> ProvisionResponse:
        return provisioner.provision(request)

    @app.post("/v1/opencode/a2a/run", response_model=A2ARunResponse)
    def run_a2a(
        request: A2ARunRequest,
        provisioner: OpenCodeProvisioner = Depends(get_provisioner),
    ) -> A2ARunResponse:
        return provisioner.run_a2a(
            request,
            task_id=request.task_id,
            context_id=request.context_id,
        )

    @app.post("/v1/opencode/ag-ui/run", response_model=AGUIRunResponse)
    def run_ag_ui(
        request: A2ARunRequest,
        provisioner: OpenCodeProvisioner = Depends(get_provisioner),
    ) -> AGUIRunResponse:
        a2a = provisioner.run_a2a(
            request,
            task_id=request.task_id,
            context_id=request.context_id,
        )
        return AGUIRunResponse(
            events=a2a_task_to_ag_ui_events(a2a.task),
            a2a_task=a2a.task,
        )

    @app.post("/rpc", response_model=A2AJsonRpcResponse)
    def rpc(
        request: A2AJsonRpcRequest,
        provisioner: OpenCodeProvisioner = Depends(get_provisioner),
    ) -> A2AJsonRpcResponse:
        try:
            if request.method == "agent/getCard":
                return A2AJsonRpcResponse(id=request.id, result=build_agent_card())
            if request.method in {"message/send", "tasks/send"}:
                params = A2AMessageSendParams.model_validate(request.params)
                opencode_request = params.opencode
                if opencode_request is None:
                    opencode_request = ProvisionRequest.model_validate(params.metadata.get("opencode", {}))
                query = extract_text_from_a2a_message(params.message)
                if not query:
                    raise ValueError("A2A message must include at least one text part")
                opencode_request.query = query
                result = provisioner.run_a2a(
                    opencode_request,
                    task_id=params.message.get("taskId"),
                    context_id=params.message.get("contextId"),
                    user_message=params.message,
                )
                return A2AJsonRpcResponse(id=request.id, result=result.task)
            if request.method in {"message/stream", "tasks/sendSubscribe"}:
                params = A2AMessageSendParams.model_validate(request.params)
                opencode_request = params.opencode
                if opencode_request is None:
                    opencode_request = ProvisionRequest.model_validate(params.metadata.get("opencode", {}))
                query = extract_text_from_a2a_message(params.message)
                if not query:
                    raise ValueError("A2A message must include at least one text part")
                opencode_request.query = query
                result = provisioner.run_a2a(
                    opencode_request,
                    task_id=params.message.get("taskId"),
                    context_id=params.message.get("contextId"),
                    user_message=params.message,
                )
                return A2AJsonRpcResponse(id=request.id, result=result.events)
            return A2AJsonRpcResponse(
                id=request.id,
                error={"code": -32601, "message": f"Method not found: {request.method}"},
            )
        except Exception as exc:
            return A2AJsonRpcResponse(
                id=request.id,
                error={"code": -32000, "message": str(exc)},
            )

    return app


app = create_app()

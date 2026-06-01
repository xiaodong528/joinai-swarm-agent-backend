from __future__ import annotations

from fastapi import FastAPI, HTTPException, Query

from engine.config import Settings
from engine.models import (
    CloseSessionRequest,
    CreateRuntimeSessionRequest,
    CreateSessionRequest,
    EngineResponse,
    GenerateRequest,
    HealthResponse,
    RuntimeQueryRequest,
    RuntimeSessionResponse,
    TemplateResponse,
)
from engine.service import AgentEngineService


def create_app(service: AgentEngineService | None = None) -> FastAPI:
    app = FastAPI(title="Swarm Engine", version="0.1.0")
    app.state.service = service or AgentEngineService(Settings())

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse()

    @app.post("/v1/sessions", response_model=EngineResponse)
    def create_session(request: CreateSessionRequest) -> EngineResponse:
        try:
            return app.state.service.create_session(request)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.post("/v1/sessions/{session_id}/generate", response_model=EngineResponse)
    def generate(session_id: str, request: GenerateRequest) -> EngineResponse:
        try:
            return app.state.service.generate(session_id, request)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.get("/v1/sessions/{session_id}/status", response_model=EngineResponse)
    def status(session_id: str, user_id: str | None = Query(default=None)) -> EngineResponse:
        try:
            return app.state.service.status(session_id, user_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc

    @app.post("/v1/sessions/{session_id}/close", response_model=EngineResponse)
    def close(session_id: str, request: CloseSessionRequest) -> EngineResponse:
        try:
            return app.state.service.close(session_id, request.user_id, request.sandbox_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.post("/v1/runtime-sessions", response_model=RuntimeSessionResponse)
    def create_runtime_session(request: CreateRuntimeSessionRequest) -> RuntimeSessionResponse:
        try:
            return app.state.service.create_runtime_session(request)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.get("/v1/templates", response_model=list[TemplateResponse])
    def list_templates(user_id: str = Query(...)) -> list[TemplateResponse]:
        return app.state.service.list_templates(user_id)

    @app.get("/v1/templates/{template_id}", response_model=TemplateResponse)
    def get_template(template_id: str, user_id: str | None = Query(default=None)) -> TemplateResponse:
        try:
            return app.state.service.get_template(template_id, user_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc

    @app.post("/v1/runtime-sessions/{runtime_session_id}/query", response_model=RuntimeSessionResponse)
    def runtime_query(runtime_session_id: str, request: RuntimeQueryRequest) -> RuntimeSessionResponse:
        try:
            return app.state.service.runtime_query(runtime_session_id, request)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.get("/v1/runtime-sessions/{runtime_session_id}/status", response_model=RuntimeSessionResponse)
    def runtime_status(runtime_session_id: str, user_id: str | None = Query(default=None)) -> RuntimeSessionResponse:
        try:
            return app.state.service.runtime_status(runtime_session_id, user_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc

    @app.post("/v1/runtime-sessions/{runtime_session_id}/close", response_model=RuntimeSessionResponse)
    def close_runtime_session(runtime_session_id: str, request: CloseSessionRequest) -> RuntimeSessionResponse:
        try:
            return app.state.service.close_runtime_session(runtime_session_id, request.user_id, request.sandbox_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    return app


app = create_app()

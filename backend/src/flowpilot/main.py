"""FlowPilot AI FastAPI application entrypoint."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from flowpilot.api import (
    routes_analytics,
    routes_auth,
    routes_benchmarks,
    routes_budgets,
    routes_documents,
    routes_workflows,
)
from flowpilot.api.deps import SessionDep
from flowpilot.config import get_settings
from flowpilot.db.seed import seed_defaults
from flowpilot.db.session import get_session_factory, init_db
from flowpilot.observability.logging import configure_logging
from flowpilot.observability.metrics import render_prometheus_metrics


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(debug=settings.debug)
    await init_db()
    factory = get_session_factory()
    async with factory() as session:
        await seed_defaults(session)
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(
        title="FlowPilot AI — Enterprise Tiered Multi-Agent Workflow Orchestrator",
        version="0.1.0",
        docs_url=None if settings.is_prod else "/docs",
        redoc_url=None if settings.is_prod else "/redoc",
        openapi_url=None if settings.is_prod else "/openapi.json",
        lifespan=lifespan,
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @application.middleware("http")
    async def request_context_middleware(request: Request, call_next: object) -> Response:
        req_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        response: Response = await call_next(request)  # type: ignore[operator]
        response.headers["X-Request-ID"] = req_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        return response

    for router in (
        routes_auth.router,
        routes_documents.router,
        routes_workflows.router,
        routes_budgets.router,
        routes_analytics.router,
        routes_benchmarks.router,
    ):
        application.include_router(router)

    @application.get("/health", tags=["system"])
    async def health(session: SessionDep) -> dict[str, str]:
        await session.execute(text("SELECT 1"))
        return {"status": "ok", "service": "flowpilot-ai", "provider": settings.llm_provider}

    @application.get("/metrics", tags=["system"])
    async def metrics() -> Response:
        return Response(content=render_prometheus_metrics(), media_type="text/plain; version=0.0.4")

    return application


app = create_app()

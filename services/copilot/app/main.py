from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import setup_logging
from app.core.request_id import REQUEST_ID_HEADER, RequestIdMiddleware
from app.db.session import close_database
from app.erp.client import close_erp_client
from app.graph.action_execution import action_execution_graph
from app.graph.business_workflow import business_workflow_graph
from app.knowledge.client import close_knowledge_client


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    setup_logging()
    settings.require_runtime_secrets()
    if settings.action_graph_enabled:
        await action_execution_graph.start()
        await business_workflow_graph.start()
    try:
        yield
    finally:
        if settings.action_graph_enabled:
            await business_workflow_graph.close()
            await action_execution_graph.close()
        await close_erp_client()
        await close_knowledge_client()
        await close_database()


def create_app() -> FastAPI:
    docs_enabled = settings.enable_api_docs
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="受 IAM 权限约束，具备真实模型状态、可恢复工作流与 V6 受控写入的 ERP Copilot V7。",
        lifespan=lifespan,
        docs_url="/docs" if docs_enabled else None,
        redoc_url="/redoc" if docs_enabled else None,
        openapi_url="/openapi.json" if docs_enabled else None,
    )
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_origin_regex=settings.cors_origin_regex,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=[REQUEST_ID_HEADER],
    )
    register_exception_handlers(app)
    app.include_router(api_router)
    return app


app = create_app()

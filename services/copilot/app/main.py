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
from app.knowledge.client import close_knowledge_client


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    setup_logging()
    settings.require_runtime_secrets()
    try:
        yield
    finally:
        await close_erp_client()
        await close_knowledge_client()
        await close_database()


def create_app() -> FastAPI:
    docs_enabled = settings.enable_api_docs
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="受 IAM 权限约束、可协同查询 ERP 与 Knowledge 并提供证据的 ERP Copilot V4。",
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

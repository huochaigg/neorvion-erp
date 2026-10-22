"""IAM 应用入口。"""

import logging
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.crypto import router as crypto_router
from app.api.v1.router import api_router
from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.jwt_keys import build_jwks
from app.core.logging import setup_logging
from app.core.redis import redis_client
from app.core.request_id import REQUEST_ID_HEADER, RequestIdMiddleware
from app.db.session import engine
from app.schemas.common import ApiResponse, ok

logger = logging.getLogger(__name__)


def _sweep_outbox_loop(stop: threading.Event) -> None:
    """后台补刷其他租户已经提交的授权 Outbox。请求路径仍负责本事务内的行。"""
    from app.services.snapshots import sweep_committed_outbox

    while not stop.wait(30):
        try:
            sweep_committed_outbox()
        except Exception:
            logger.exception("授权 Outbox 后台补刷失败")


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    setup_logging()
    stop = threading.Event()
    worker = threading.Thread(
        target=_sweep_outbox_loop,
        args=(stop,),
        name="iam-outbox",
        daemon=True,
    )
    worker.start()
    try:
        yield
    finally:
        stop.set()
        worker.join(timeout=2)
        redis_client.close()
        engine.dispose()


def create_app() -> FastAPI:
    docs_enabled = settings.enable_api_docs
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="Neorvion 统一 IAM：用户、租户、会话、RBAC、应用注册与 JWKS。",
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
    app.include_router(crypto_router)

    @app.get("/.well-known/jwks.json", summary="JWT 公钥集")
    def jwks() -> dict:
        return build_jwks()

    @app.get("/api/v1/jwks", response_model=ApiResponse[dict], summary="JWT 公钥集（鉴权网关备用）")
    def jwks_api() -> ApiResponse[dict]:
        return ok(build_jwks())

    app.include_router(api_router)
    return app


app = create_app()

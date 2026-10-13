"""请求级 request_id。V14 不做 OpenTelemetry，只做跨日志 / 操作日志关联。"""

from __future__ import annotations

import re
import uuid
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

REQUEST_ID_HEADER = "X-Request-ID"
_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{8,64}$")

current_request_id: ContextVar[str | None] = ContextVar("current_request_id", default=None)


def get_request_id() -> str | None:
    return current_request_id.get()


def set_request_id(value: str | None) -> None:
    current_request_id.set(value)


def new_request_id() -> str:
    return uuid.uuid4().hex


def resolve_request_id(raw: str | None) -> str:
    """客户端传入合法 X-Request-ID 则复用，否则服务端生成。"""
    if raw is None:
        return new_request_id()
    candidate = raw.strip()
    if _REQUEST_ID_PATTERN.fullmatch(candidate):
        return candidate
    return new_request_id()


class RequestIdMiddleware(BaseHTTPMiddleware):
    """每个 HTTP 请求写入 ContextVar，并在响应头回传 X-Request-ID。"""

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = resolve_request_id(request.headers.get(REQUEST_ID_HEADER))
        request.state.request_id = request_id
        token = current_request_id.set(request_id)
        try:
            response = await call_next(request)
            response.headers[REQUEST_ID_HEADER] = request_id
            return response
        finally:
            current_request_id.reset(token)

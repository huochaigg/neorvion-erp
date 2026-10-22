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


def resolve_request_id(raw: str | None) -> str:
    candidate = (raw or "").strip()
    if _REQUEST_ID_PATTERN.fullmatch(candidate):
        return candidate
    return uuid.uuid4().hex


class RequestIdMiddleware(BaseHTTPMiddleware):
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


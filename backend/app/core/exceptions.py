from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel


class AppError(Exception):
    """业务异常。API 层统一转换为标准 JSON。"""

    def __init__(self, message: str, *, code: int = 40001, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code


class ErrorBody(BaseModel):
    code: int
    message: str
    data: Any = None


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(_request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=ErrorBody(code=exc.code, message=exc.message).model_dump(),
        )

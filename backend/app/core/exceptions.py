from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
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

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        _request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        details = [{"loc": err.get("loc"), "msg": err.get("msg")} for err in exc.errors()]
        return JSONResponse(
            status_code=422,
            content=ErrorBody(code=40000, message="请求参数不合法", data=details).model_dump(),
        )

from pydantic import BaseModel, Field


class ApiResponse[T](BaseModel):
    """统一成功响应。"""

    code: int = Field(default=0, description="0 表示成功")
    message: str = "ok"
    data: T


def ok[T](data: T, message: str = "ok") -> ApiResponse[T]:
    return ApiResponse(code=0, message=message, data=data)

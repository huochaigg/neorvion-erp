from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, EmailStr, Field, field_validator

# 接口收到的是 SHA-256 摘要，不是用户输入的明文。强度规则在前端校验。
PasswordDigest = Annotated[
    str,
    Field(
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
        description="SHA-256(明文密码) 的 64 位小写十六进制",
    ),
]


class RegisterRequest(BaseModel):
    email: EmailStr
    password: PasswordDigest
    display_name: str = Field(min_length=1, max_length=64)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("display_name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        name = value.strip()
        if not name:
            raise ValueError("显示名称不能为空")
        return name


class LoginRequest(BaseModel):
    email: EmailStr
    password: PasswordDigest

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class UserOut(BaseModel):
    id: int
    email: str
    display_name: str
    status: str
    created_at: datetime
    last_login_at: datetime | None = None

    model_config = {"from_attributes": True}

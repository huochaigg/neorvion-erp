from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

EncryptedPassword = Annotated[
    str,
    Field(
        min_length=64,
        max_length=1024,
        description="RSA-OAEP 密文的 Base64，不是明文密码",
    ),
]


class PublicKeyOut(BaseModel):
    key_id: str
    public_key: str
    algorithm: str
    challenge_id: str
    expires_in: int


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    encrypted_password: EncryptedPassword
    key_id: str = Field(min_length=1, max_length=64)
    challenge_id: str = Field(min_length=8, max_length=64)
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

    @field_validator("key_id", "challenge_id")
    @classmethod
    def strip_ids(cls, value: str) -> str:
        return value.strip()


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    encrypted_password: EncryptedPassword
    key_id: str = Field(min_length=1, max_length=64)
    challenge_id: str = Field(min_length=8, max_length=64)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("key_id", "challenge_id")
    @classmethod
    def strip_ids(cls, value: str) -> str:
        return value.strip()


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

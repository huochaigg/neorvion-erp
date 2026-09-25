from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class TenantCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=64)
    code: str | None = Field(default=None, max_length=32)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        name = value.strip()
        if not name:
            raise ValueError("企业名称不能为空")
        return name

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: str | None) -> str | None:
        if value is None:
            return None
        code = value.strip().lower()
        return code or None


class TenantOut(BaseModel):
    id: int
    name: str
    code: str
    status: str
    created_by: int
    created_at: datetime
    updated_at: datetime
    my_role: str
    my_status: str
    is_owner: bool

    model_config = {"from_attributes": True}


class TenantContextOut(BaseModel):
    user_id: int
    tenant_id: int
    member_id: int
    is_owner: bool
    role: str


class MemberCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: int = Field(gt=0)


class MemberUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str = Field(min_length=1, max_length=16)

    @field_validator("status")
    @classmethod
    def normalize_status(cls, value: str) -> str:
        return value.strip().upper()


class MemberOut(BaseModel):
    id: int
    tenant_id: int
    user_id: int
    role: str
    status: str
    joined_at: datetime
    display_name: str
    email: str

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PermissionOut(BaseModel):
    id: int
    code: str
    name: str
    module: str
    description: str

    model_config = {"from_attributes": True}


class RoleOut(BaseModel):
    id: int
    tenant_id: int
    name: str
    code: str
    description: str
    is_system: bool
    created_at: datetime
    updated_at: datetime
    permissions: list[PermissionOut] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class RoleCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=64)
    code: str = Field(min_length=1, max_length=32)
    description: str | None = Field(default=None, max_length=255)
    permission_ids: list[int] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        name = value.strip()
        if not name:
            raise ValueError("角色名称不能为空")
        return name


class RoleUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=64)
    description: str | None = Field(default=None, max_length=255)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        name = value.strip()
        if not name:
            raise ValueError("角色名称不能为空")
        return name


class RolePermissionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    permission_ids: list[int]

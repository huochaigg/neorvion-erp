from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.schemas.rbac import PermissionOut


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
    permission_codes: list[str] = Field(default_factory=list)


class MyPermissionsOut(BaseModel):
    """当前租户成员的有效角色与权限快照。编码来自服务端聚合，不接受前端提交。"""

    roles: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)


class MemberRoleBrief(BaseModel):
    id: int
    code: str
    name: str
    is_system: bool


class MemberCreate(BaseModel):
    """按邮箱添加已注册用户；user_id 仅兼容旧调用。role_ids 为空时默认 VIEWER。"""

    model_config = ConfigDict(extra="forbid")

    email: EmailStr | None = None
    user_id: int | None = Field(default=None, gt=0)
    role_ids: list[int] = Field(default_factory=list)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr | None) -> str | None:
        if value is None:
            return None
        return str(value).strip().lower()

    @model_validator(mode="after")
    def require_identity(self) -> "MemberCreate":
        if self.email is None and self.user_id is None:
            raise ValueError("请提供邮箱")
        return self


class MemberUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str = Field(min_length=1, max_length=16)

    @field_validator("status")
    @classmethod
    def normalize_status(cls, value: str) -> str:
        return value.strip().upper()


class MemberRolesUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role_ids: list[int]


class MemberAccountCreate(BaseModel):
    """企业管理员代建全局 User，并加入当前租户。不接收管理员设定的长期密码。"""

    model_config = ConfigDict(extra="forbid")

    display_name: str = Field(min_length=1, max_length=64)
    email: EmailStr
    role_ids: list[int] = Field(default_factory=list)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> str:
        return str(value).strip().lower()

    @field_validator("display_name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        name = value.strip()
        if not name:
            raise ValueError("显示名称不能为空")
        return name


class MemberOut(BaseModel):
    id: int
    tenant_id: int
    user_id: int
    role: str
    status: str
    joined_at: datetime
    display_name: str
    email: str
    is_owner: bool
    roles: list[MemberRoleBrief] = Field(default_factory=list)


class MemberDetailOut(MemberOut):
    permission_codes: list[str] = Field(default_factory=list)
    permissions: list[PermissionOut] = Field(default_factory=list)


class MemberCreatedOut(MemberOut):
    """仅创建新账号接口返回 temporary_password；列表/详情不会带这个字段。"""

    temporary_password: str | None = None


class MemberListOut(BaseModel):
    items: list[MemberOut]
    total: int
    page: int
    page_size: int

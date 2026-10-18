"""ERP 会话快照 DTO。租户/成员 CRUD 的 Schema 在 IAM，这里只回传当前请求身份。"""

from pydantic import BaseModel, Field


class TenantContextOut(BaseModel):
    """当前 JWT + 快照校验后的租户上下文。"""

    user_id: int
    tenant_id: int
    member_id: int
    is_owner: bool
    role: str
    permission_codes: list[str] = Field(default_factory=list)


class MyPermissionsOut(BaseModel):
    """当前租户成员的有效角色与权限编码，供前端生成菜单。不是授权依据。"""

    roles: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)

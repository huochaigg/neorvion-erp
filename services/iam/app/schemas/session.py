from datetime import datetime

from pydantic import BaseModel, Field


class SessionOut(BaseModel):
    id: str = Field(description="会话公开标识，写入 JWT sid，不是数据库自增主键")
    user_agent: str
    ip_address: str
    created_at: datetime
    last_seen_at: datetime
    expires_at: datetime
    revoked_at: datetime | None = None
    revoke_reason: str | None = None
    current: bool = False


class AuthorityCheckIn(BaseModel):
    codes: list[str] = Field(default_factory=list, description="高风险接口要求的权限编码")
    audience: str = Field(default="", description="调用方正在保护的目标 Audience")
    resources: dict[str, list[str]] = Field(
        default_factory=dict, description="本次调用要求的资源范围"
    )
    high_risk: bool = True


class AuthorityCheckOut(BaseModel):
    user_id: int
    tenant_id: int
    member_id: int
    is_owner: bool
    role: str
    permission_codes: list[str]
    role_codes: list[str]
    token_jti: str
    token_version: int
    authz_version: int
    is_platform_admin: bool
    must_change_password: bool
    display_name: str
    email: str
    session_id: str
    high_risk_verified: bool = True
    authz_source: str = "iam-db"
    subject_type: str = "USER"
    service_id: str = ""
    service_scopes: list[str] = Field(default_factory=list)
    service_resources: dict[str, list[str]] = Field(default_factory=dict)

from datetime import datetime

from pydantic import BaseModel, Field


class ServiceIdentityCreate(BaseModel):
    name: str = Field(min_length=3, max_length=100)
    tenant_ids: list[int] = Field(min_length=1, description="允许访问的租户白名单")
    allowed_audiences: list[str] = Field(min_length=1, description="允许申请的业务服务 Audience")
    allowed_scopes: list[str] = Field(min_length=1, description="允许申请的只读权限编码")
    allowed_resources: dict[str, list[str]] = Field(
        default_factory=dict, description="按资源类型限制的标识白名单"
    )
    expires_at: datetime | None = Field(default=None, description="服务身份自身失效时间")


class ServiceTokenRequest(BaseModel):
    service_id: str = Field(min_length=8, max_length=64)
    client_secret: str = Field(min_length=32, max_length=256)
    audience: str = Field(min_length=3, max_length=64)
    tenant_id: int = Field(gt=0)
    scopes: list[str] = Field(min_length=1)
    resources: dict[str, list[str]] = Field(default_factory=dict)


class ServiceTokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    scope: str


class ServiceIdentityOut(BaseModel):
    id: int
    public_id: str
    name: str
    subject_type: str
    tenant_ids: list[int]
    allowed_audiences: list[str]
    allowed_scopes: list[str]
    allowed_resources: dict[str, list[str]]
    credential_version: int
    status: str
    expires_at: datetime | None
    last_used_at: datetime | None
    created_by: int
    created_at: datetime
    updated_at: datetime
    revoked_at: datetime | None

    model_config = {"from_attributes": True}


class ServiceIdentityCreated(BaseModel):
    identity: ServiceIdentityOut
    client_secret: str = Field(description="只返回一次的客户端密钥，IAM 不保存明文")

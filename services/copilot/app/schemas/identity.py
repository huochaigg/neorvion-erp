from pydantic import BaseModel, Field


class CurrentIdentityOut(BaseModel):
    user_id: int
    tenant_id: int
    member_id: int
    is_owner: bool
    roles: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)
    authz_version: int = Field(description="IAM 授权快照版本")


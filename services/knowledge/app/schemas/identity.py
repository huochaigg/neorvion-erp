from pydantic import BaseModel, Field


class IdentityIntrospectOut(BaseModel):
    user_id: int
    tenant_id: int
    member_id: int
    is_owner: bool
    role: str
    permission_codes: list[str] = Field(default_factory=list)
    token_jti: str
    token_exp: int


class MyPermissionsOut(BaseModel):
    roles: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)

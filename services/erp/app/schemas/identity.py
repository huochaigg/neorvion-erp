from pydantic import BaseModel, Field


class IdentityIntrospectOut(BaseModel):
    """内部身份快照。只给 Knowledge 等受控服务，不给浏览器。"""

    user_id: int
    tenant_id: int
    member_id: int
    is_owner: bool
    role: str
    permission_codes: list[str] = Field(default_factory=list)
    token_jti: str
    token_exp: int

"""HTTP 依赖。JWT 解析只写在这里，业务 Router 不要重复实现。"""

from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.core.context import set_tenant_context
from app.core.exceptions import AppError
from app.core.security import decode_token
from app.db.session import get_db
from app.models.user import User, UserStatus
from app.repositories.user import UserRepository

DbSession = Annotated[Session, Depends(get_db)]


def _extract_bearer_token(request: Request) -> str:
    header = request.headers.get("Authorization")
    if not header or not header.startswith("Bearer "):
        raise AppError("未登录", code=40100, status_code=401)
    token = header.removeprefix("Bearer ").strip()
    if not token:
        raise AppError("未登录", code=40100, status_code=401)
    return token


def get_current_user(request: Request, session: DbSession) -> User:
    """解析 Access Token 并加载当前用户。仅供受保护接口通过 CurrentUser 注入。

    公开接口见 app.core.auth_public.PUBLIC_ROUTES，尤其是 POST /api/v1/auth/refresh
    不得依赖本函数：Refresh 只校验 Cookie 中的 Refresh Token。
    """
    token = _extract_bearer_token(request)
    payload = decode_token(token, expected_type="access")
    user_id = int(payload["sub"])
    user = UserRepository(session).get_by_id(user_id)
    if user is None:
        raise AppError("未登录", code=40100, status_code=401)
    if user.status != UserStatus.ACTIVE.value:
        raise AppError("账号已被禁用", code=40300, status_code=403)
    set_tenant_context(tenant_id=None, user_id=user.id)
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]

from fastapi import APIRouter, Request, Response

from app.api.deps import CurrentUser, DbSession
from app.core.config import settings
from app.core.exceptions import AppError
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserOut
from app.schemas.common import ApiResponse, ok
from app.services.auth import AuthService

router = APIRouter(prefix="/auth")


def _set_refresh_cookie(response: Response, refresh_token: str, max_age: int) -> None:
    """Refresh Token 只放 HttpOnly Cookie，前端内存不保存，降低 XSS 窃取面。"""
    response.set_cookie(
        key=settings.refresh_cookie_name,
        value=refresh_token,
        max_age=max_age,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,  # type: ignore[arg-type]
        path=settings.refresh_cookie_path,
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key=settings.refresh_cookie_name,
        path=settings.refresh_cookie_path,
        secure=settings.cookie_secure,
        httponly=True,
        samesite=settings.cookie_samesite,  # type: ignore[arg-type]
    )


def _read_refresh_cookie(request: Request) -> str | None:
    return request.cookies.get(settings.refresh_cookie_name)


@router.post(
    "/register",
    response_model=ApiResponse[UserOut],
    summary="用户注册",
)
def register(payload: RegisterRequest, session: DbSession) -> ApiResponse[UserOut]:
    """注册全局用户。

    输入：email、encrypted_password、key_id、challenge_id、display_name。
    输出：用户公开资料，不含 password_hash。
    规则：email 唯一；RSA-OAEP 解密后用 Argon2id 入库。
    """
    user = AuthService(session).register(
        email=payload.email,
        encrypted_password=payload.encrypted_password,
        key_id=payload.key_id,
        challenge_id=payload.challenge_id,
        display_name=payload.display_name,
    )
    return ok(user, "注册成功")


@router.post(
    "/login",
    response_model=ApiResponse[TokenResponse],
    summary="用户登录",
)
def login(
    payload: LoginRequest,
    session: DbSession,
    response: Response,
) -> ApiResponse[TokenResponse]:
    """邮箱密码登录。

    输入：email、encrypted_password、key_id、challenge_id。
    输出：Access Token；Refresh Token 写入 HttpOnly Cookie。
    规则：失败信息不区分邮箱是否存在。
    """
    tokens, refresh_token, ttl = AuthService(session).login(
        email=payload.email,
        encrypted_password=payload.encrypted_password,
        key_id=payload.key_id,
        challenge_id=payload.challenge_id,
    )
    _set_refresh_cookie(response, refresh_token, ttl)
    return ok(tokens)


@router.post(
    "/refresh",
    response_model=ApiResponse[TokenResponse],
    summary="刷新访问令牌",
)
def refresh(request: Request, session: DbSession, response: Response) -> ApiResponse[TokenResponse]:
    """用 Refresh Cookie 换发新的 Access Token，并轮换 Refresh Token。

    本接口在认证白名单中，不读取、不校验 Authorization 里的 Access Token。
    Access Token 过期时仍可刷新。没有有效 Refresh Cookie 时返回 401。
    """
    refresh_token = _read_refresh_cookie(request)
    if not refresh_token:
        raise AppError("未登录", code=40100, status_code=401)
    tokens, new_refresh, ttl = AuthService(session).refresh(refresh_token)
    _set_refresh_cookie(response, new_refresh, ttl)
    return ok(tokens)


@router.post(
    "/logout",
    response_model=ApiResponse[None],
    summary="退出登录",
)
def logout(request: Request, session: DbSession, response: Response) -> ApiResponse[None]:
    """撤销当前 Refresh 会话并清除 Cookie。无 Cookie 时仍返回成功。"""
    AuthService(session).logout(_read_refresh_cookie(request))
    _clear_refresh_cookie(response)
    return ok(None, "已退出登录")


@router.get(
    "/me",
    response_model=ApiResponse[UserOut],
    summary="当前用户",
)
def me(user: CurrentUser, session: DbSession) -> ApiResponse[UserOut]:
    """返回当前 Access Token 对应的用户资料。需要登录。"""
    return ok(AuthService(session).get_profile(user))

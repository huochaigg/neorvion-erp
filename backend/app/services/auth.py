from datetime import datetime

from sqlalchemy.orm import Session

from app.core import token_store
from app.core.config import settings
from app.core.exceptions import AppError
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.user import User, UserStatus
from app.repositories.user import UserRepository
from app.schemas.auth import TokenResponse, UserOut


class AuthService:
    """注册、登录、刷新与注销。事务由本层 commit。"""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.users = UserRepository(session)

    def register(self, *, email: str, password: str, display_name: str) -> UserOut:
        """password 参数是前端 SHA-256 摘要，这里再做 Argon2id 后入库。"""
        if self.users.get_by_email(email) is not None:
            raise AppError("该邮箱已被注册", code=40011, status_code=409)

        user = User(
            email=email,
            password_hash=hash_password(password),
            display_name=display_name,
            status=UserStatus.ACTIVE.value,
        )
        self.users.add(user)
        self.session.commit()
        self.session.refresh(user)
        return UserOut.model_validate(user)

    def login(self, *, email: str, password: str) -> tuple[TokenResponse, str, int]:
        """校验传输摘要后签发双 Token。失败信息故意保持模糊，避免枚举邮箱。"""
        user = self.users.get_by_email(email)
        if user is None or not verify_password(password, user.password_hash):
            raise AppError("邮箱或密码错误", code=40010, status_code=401)
        if user.status != UserStatus.ACTIVE.value:
            raise AppError("账号已被禁用", code=40300, status_code=403)

        user.last_login_at = datetime.now()
        self.session.commit()
        return self._issue_tokens(user.id)

    def refresh(self, refresh_token: str) -> tuple[TokenResponse, str, int]:
        payload = decode_token(refresh_token, expected_type="refresh")
        jti = str(payload["jti"])
        user_id = int(payload["sub"])
        stored_user_id = token_store.get_refresh_user_id(jti)
        if stored_user_id is None or stored_user_id != user_id:
            raise AppError("登录已失效，请重新登录", code=40104, status_code=401)

        user = self._require_active_user(user_id)
        token_store.revoke_refresh_session(jti)
        return self._issue_tokens(user.id)

    def logout(self, refresh_token: str | None) -> None:
        if not refresh_token:
            return
        try:
            payload = decode_token(refresh_token, expected_type="refresh")
        except AppError:
            return
        token_store.revoke_refresh_session(str(payload["jti"]))

    def get_profile(self, user: User) -> UserOut:
        return UserOut.model_validate(user)

    def _require_active_user(self, user_id: int) -> User:
        user = self.users.get_by_id(user_id)
        if user is None:
            raise AppError("用户不存在", code=40105, status_code=401)
        if user.status != UserStatus.ACTIVE.value:
            raise AppError("账号已被禁用", code=40300, status_code=403)
        return user

    def _issue_tokens(self, user_id: int) -> tuple[TokenResponse, str, int]:
        access_token = create_access_token(user_id)
        refresh_token, jti, ttl_seconds = create_refresh_token(user_id)
        token_store.save_refresh_session(jti=jti, user_id=user_id, ttl_seconds=ttl_seconds)
        body = TokenResponse(
            access_token=access_token,
            expires_in=settings.jwt_access_expire_minutes * 60,
        )
        return body, refresh_token, ttl_seconds

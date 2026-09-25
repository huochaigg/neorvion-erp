from datetime import datetime

from sqlalchemy.orm import Session

from app.core import challenge_store, token_store
from app.core.config import settings
from app.core.exceptions import AppError
from app.core.rsa_crypto import RSA_ALGORITHM, RsaCryptoError, get_rsa_store
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.user import User, UserStatus
from app.repositories.user import UserRepository
from app.schemas.auth import PublicKeyOut, TokenResponse, UserOut


def _validate_plain_password(plain_password: str) -> None:
    if len(plain_password) < 8 or len(plain_password) > 72:
        raise AppError("密码长度须为 8-72 位", code=40023, status_code=400)
    if not any(char.isalpha() for char in plain_password) or not any(
        char.isdigit() for char in plain_password
    ):
        raise AppError("密码需同时包含字母和数字", code=40023, status_code=400)


class AuthService:
    """注册、登录、刷新与注销。事务由本层 commit。"""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.users = UserRepository(session)

    @staticmethod
    def issue_public_key() -> PublicKeyOut:
        """发放当前 RSA 公钥和一次性 challenge。私钥永不返回。"""
        store = get_rsa_store()
        challenge_id = challenge_store.issue_challenge(store.current_key_id)
        return PublicKeyOut(
            key_id=store.current_key_id,
            public_key=store.current_public_pem,
            algorithm=RSA_ALGORITHM,
            challenge_id=challenge_id,
            expires_in=settings.rsa_challenge_ttl_seconds,
        )

    def register(
        self,
        *,
        email: str,
        encrypted_password: str,
        key_id: str,
        challenge_id: str,
        display_name: str,
    ) -> UserOut:
        if self.users.get_by_email(email) is not None:
            raise AppError("该邮箱已被注册", code=40011, status_code=409)

        plain_password = self._unlock_password(
            encrypted_password=encrypted_password,
            key_id=key_id,
            challenge_id=challenge_id,
        )
        user = User(
            email=email,
            password_hash=hash_password(plain_password),
            display_name=display_name,
            status=UserStatus.ACTIVE.value,
        )
        self.users.add(user)
        self.session.commit()
        self.session.refresh(user)
        return UserOut.model_validate(user)

    def login(
        self,
        *,
        email: str,
        encrypted_password: str,
        key_id: str,
        challenge_id: str,
    ) -> tuple[TokenResponse, str, int]:
        """解密后校验 Argon2id。失败信息故意保持模糊，避免枚举邮箱。"""
        plain_password = self._unlock_password(
            encrypted_password=encrypted_password,
            key_id=key_id,
            challenge_id=challenge_id,
        )
        user = self.users.get_by_email(email)
        if user is None or not verify_password(plain_password, user.password_hash):
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

    def _unlock_password(
        self,
        *,
        encrypted_password: str,
        key_id: str,
        challenge_id: str,
    ) -> str:
        """原子消费 challenge，再用对应私钥做 RSA-OAEP 解密。"""
        bound_key_id = challenge_store.consume_challenge(challenge_id)
        if bound_key_id is None:
            raise AppError("认证凭证已失效，请重试", code=40020, status_code=400)
        if bound_key_id != key_id:
            raise AppError("认证凭证无效", code=40021, status_code=400)
        try:
            plain_password = get_rsa_store().decrypt(
                encrypted_password=encrypted_password,
                key_id=key_id,
            )
        except RsaCryptoError:
            raise AppError("认证凭证无效", code=40022, status_code=400) from None
        _validate_plain_password(plain_password)
        return plain_password

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

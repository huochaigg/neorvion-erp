"""注册、登录、刷新与注销。JWT 与 Redis 会话由本层发出。"""

from datetime import datetime, timedelta
from uuid import uuid4

from sqlalchemy.orm import Session

from app.core import challenge_store, token_store
from app.core.config import settings
from app.core.exceptions import AppError
from app.core.rsa_crypto import RsaCryptoError, get_rsa_store
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.core.token_hash import hash_token_id
from app.models.session import AuthSession
from app.models.user import User, UserStatus
from app.repositories.user import UserRepository
from app.schemas.auth import TokenResponse, UserOut
from app.services.session import SessionService
from app.services.snapshots import SnapshotService


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
        self.snapshots = SnapshotService(session)

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
            must_change_password=False,
            is_platform_admin=False,
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
        user_agent: str = "",
        ip_address: str = "",
    ) -> tuple[TokenResponse, str, int, str]:
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
        self.snapshots.refresh_user(user.id)
        return self._issue_tokens(
            user.id,
            user_agent=user_agent,
            ip_address=ip_address,
        )

    def refresh(
        self, refresh_token: str, *, csrf_token: str | None
    ) -> tuple[TokenResponse, str, int, str]:
        """Refresh 轮换以数据库会话为准。Redis GETDEL 只加速单飞，重放检测看 family。"""
        claims = decode_token(refresh_token, expected_type="refresh")
        incoming_hash = hash_token_id(claims.jti)
        sessions = SessionService(self.session)
        row = sessions.get_by_jti_hash(incoming_hash)
        if row is None:
            raced = sessions.get_by_previous_hash(incoming_hash)
            stolen = raced
            if stolen is None and claims.session_id:
                from sqlalchemy import select

                stolen = self.session.scalars(
                    select(AuthSession).where(AuthSession.public_id == claims.session_id)
                ).first()
            if stolen is not None and stolen.user_id == claims.user_id:
                sessions.revoke_family(stolen.family_id, reason="REPLAY")
                self.session.commit()
                self.snapshots.invalidate_sessions(stolen.user_id)
            raise AppError("登录已失效，请重新登录", code=40104, status_code=401)
        if row.revoked_at is not None or row.user_id != claims.user_id:
            raise AppError("登录已失效，请重新登录", code=40104, status_code=401)
        if not csrf_token or hash_token_id(csrf_token) != row.csrf_hash:
            redis_hit = token_store.consume_refresh_session(claims.jti)
            if redis_hit is None or redis_hit[1] != (csrf_token or ""):
                raise AppError("刷新请求未通过 CSRF 校验", code=40108, status_code=401)
        else:
            token_store.consume_refresh_session(claims.jti)
        user = self._require_active_user(claims.user_id)
        self.snapshots.refresh_user(user.id)
        return self._rotate_tokens(user.id, row)

    def logout(self, refresh_token: str | None) -> None:
        if not refresh_token:
            return
        try:
            claims = decode_token(refresh_token, expected_type="refresh")
        except AppError:
            return
        token_store.revoke_refresh_session(claims.jti)
        incoming_hash = hash_token_id(claims.jti)
        row = SessionService(self.session).get_by_jti_hash(incoming_hash)
        if row is None and claims.session_id:
            from sqlalchemy import select

            row = self.session.scalars(
                select(AuthSession).where(AuthSession.public_id == claims.session_id)
            ).first()
        if row is not None and row.revoked_at is None:
            row.revoked_at = datetime.now()
            row.revoke_reason = "LOGOUT"
            self.session.commit()

    def change_password(
        self,
        *,
        user: User,
        encrypted_old_password: str,
        old_key_id: str,
        old_challenge_id: str,
        encrypted_new_password: str,
        new_key_id: str,
        new_challenge_id: str,
    ) -> UserOut:
        old_password = self._unlock_password(
            encrypted_password=encrypted_old_password,
            key_id=old_key_id,
            challenge_id=old_challenge_id,
        )
        if not verify_password(old_password, user.password_hash):
            raise AppError("原密码错误", code=40010, status_code=400)
        new_password = self._unlock_password(
            encrypted_password=encrypted_new_password,
            key_id=new_key_id,
            challenge_id=new_challenge_id,
        )
        if new_password == old_password:
            raise AppError("新密码不能与原密码相同", code=40023, status_code=400)
        user.password_hash = hash_password(new_password)
        user.must_change_password = False
        try:
            self.session.commit()
            self.session.refresh(user)
        except Exception:
            self.session.rollback()
            raise
        self.snapshots.invalidate_sessions(user.id)
        SessionService(self.session).revoke_all(user.id, reason="PASSWORD")
        self.snapshots.refresh_user(user.id)
        return UserOut.model_validate(user)

    def get_profile(self, user: User) -> UserOut:
        return UserOut.model_validate(user)

    def _unlock_password(
        self,
        *,
        encrypted_password: str,
        key_id: str,
        challenge_id: str,
    ) -> str:
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

    def _issue_tokens(
        self,
        user_id: int,
        *,
        user_agent: str = "",
        ip_address: str = "",
        session_row: AuthSession | None = None,
    ) -> tuple[TokenResponse, str, int, str]:
        token_version = self.snapshots.token_version(user_id)
        public_id = session_row.public_id if session_row is not None else uuid4().hex
        family_id = session_row.family_id if session_row is not None else uuid4().hex
        access_token = create_access_token(
            user_id, token_version=token_version, session_id=public_id
        )
        refresh_token, jti, ttl_seconds = create_refresh_token(
            user_id, token_version=token_version, session_id=public_id
        )
        csrf_token = token_store.new_csrf_token()
        now = datetime.now()
        expires_at = now + timedelta(seconds=ttl_seconds)
        jti_hash = hash_token_id(jti)
        csrf_hash = hash_token_id(csrf_token)
        if session_row is None:
            self.session.add(
                AuthSession(
                    public_id=public_id,
                    user_id=user_id,
                    family_id=family_id,
                    refresh_jti_hash=jti_hash,
                    previous_jti_hash=None,
                    csrf_hash=csrf_hash,
                    user_agent=(user_agent or "")[:255],
                    ip_address=(ip_address or "")[:64],
                    created_at=now,
                    last_seen_at=now,
                    expires_at=expires_at,
                )
            )
        else:
            session_row.previous_jti_hash = session_row.refresh_jti_hash
            session_row.refresh_jti_hash = jti_hash
            session_row.csrf_hash = csrf_hash
            session_row.last_seen_at = now
            session_row.expires_at = expires_at
        self.session.commit()
        token_store.save_refresh_session(
            jti=jti,
            user_id=user_id,
            ttl_seconds=ttl_seconds,
            csrf_token=csrf_token,
        )
        body = TokenResponse(
            access_token=access_token,
            expires_in=settings.access_token_ttl_seconds(),
        )
        return body, refresh_token, ttl_seconds, csrf_token

    def _rotate_tokens(
        self, user_id: int, session_row: AuthSession
    ) -> tuple[TokenResponse, str, int, str]:
        return self._issue_tokens(user_id, session_row=session_row)

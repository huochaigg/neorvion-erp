"""登录会话查询与撤销。Refresh Token 只比对哈希。"""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.core.token_hash import hash_token_id
from app.models.session import AuthSession
from app.schemas.session import SessionOut
from app.services.snapshots import SnapshotService


class SessionService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_mine(self, user_id: int, *, current_public_id: str = "") -> list[SessionOut]:
        rows = list(
            self.session.scalars(
                select(AuthSession)
                .where(AuthSession.user_id == user_id)
                .order_by(AuthSession.last_seen_at.desc())
            ).all()
        )
        return [self._out(row, current_public_id=current_public_id) for row in rows]

    def revoke_one(self, user_id: int, public_id: str) -> None:
        row = self._get_owned(user_id, public_id)
        if row.revoked_at is not None:
            return
        row.revoked_at = datetime.now()
        row.revoke_reason = "USER"
        self.session.commit()

    def revoke_all(self, user_id: int, *, reason: str = "LOGOUT_ALL") -> int:
        rows = list(
            self.session.scalars(
                select(AuthSession).where(
                    AuthSession.user_id == user_id,
                    AuthSession.revoked_at.is_(None),
                )
            ).all()
        )
        now = datetime.now()
        for row in rows:
            row.revoked_at = now
            row.revoke_reason = reason
        self.session.commit()
        SnapshotService(self.session).invalidate_sessions(user_id)
        return len(rows)

    def require_active(self, *, user_id: int, public_id: str) -> AuthSession:
        """高风险与 IAM 本服务校验：会话必须存在且未撤销。"""
        if not public_id:
            raise AppError("登录已失效，请重新登录", code=40104, status_code=401)
        row = self.session.scalars(
            select(AuthSession).where(AuthSession.public_id == public_id)
        ).first()
        if row is None or row.user_id != user_id:
            raise AppError("登录已失效，请重新登录", code=40104, status_code=401)
        if row.revoked_at is not None:
            raise AppError("登录已失效，请重新登录", code=40104, status_code=401)
        if row.expires_at <= datetime.now():
            raise AppError("登录已失效，请重新登录", code=40104, status_code=401)
        return row

    def get_by_jti_hash(self, jti_hash: str) -> AuthSession | None:
        return self.session.scalars(
            select(AuthSession).where(AuthSession.refresh_jti_hash == jti_hash).with_for_update()
        ).first()

    def get_by_previous_hash(self, jti_hash: str) -> AuthSession | None:
        return self.session.scalars(
            select(AuthSession).where(AuthSession.previous_jti_hash == jti_hash).with_for_update()
        ).first()

    def revoke_family(self, family_id: str, *, reason: str = "REPLAY") -> None:
        now = datetime.now()
        rows = list(
            self.session.scalars(
                select(AuthSession).where(
                    AuthSession.family_id == family_id,
                    AuthSession.revoked_at.is_(None),
                )
            ).all()
        )
        for row in rows:
            row.revoked_at = now
            row.revoke_reason = reason

    def _get_owned(self, user_id: int, public_id: str) -> AuthSession:
        row = self.session.scalars(
            select(AuthSession).where(
                AuthSession.public_id == public_id,
                AuthSession.user_id == user_id,
            )
        ).first()
        if row is None:
            raise AppError("会话不存在", code=40440, status_code=404)
        return row

    @staticmethod
    def _out(row: AuthSession, *, current_public_id: str) -> SessionOut:
        return SessionOut(
            id=row.public_id,
            user_agent=row.user_agent,
            ip_address=row.ip_address,
            created_at=row.created_at,
            last_seen_at=row.last_seen_at,
            expires_at=row.expires_at,
            revoked_at=row.revoked_at,
            revoke_reason=row.revoke_reason or None,
            current=bool(current_public_id) and row.public_id == current_public_id,
        )


def hash_refresh_jti(jti: str) -> str:
    return hash_token_id(jti)

"""把当前请求 JWT 中的展示名投影到本地快照表。

不是 IAM 双写：不写密码、成员、角色。只保证本请求内 JOIN 操作人姓名可见。
"""

from __future__ import annotations

from datetime import UTC, datetime

from neorvion_security.tenant import TenantContext
from sqlalchemy.orm import Session

from app.models.identity import IdentityNameSnapshot


def project_display_user(session: Session, context: TenantContext) -> None:
    """按 IAM user_id upsert 展示名。同一请求 flush 后即可被 OUTER JOIN 看到。"""
    name = (context.display_name or "").strip() or f"用户{context.user_id}"
    row = session.get(IdentityNameSnapshot, context.user_id)
    now = datetime.now(UTC).replace(tzinfo=None)
    if row is None:
        session.add(
            IdentityNameSnapshot(
                user_id=context.user_id,
                display_name=name[:64],
                updated_at=now,
            )
        )
        session.flush()
        return
    if row.display_name != name[:64]:
        row.display_name = name[:64]
        row.updated_at = now
        session.flush()

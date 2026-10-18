"""把 IAM 快照中的展示名投影到本地 users 表。

身份所有权在 IAM。本模块只写展示字段，供库存流水、拣货记录等 JOIN 操作人姓名。
password_hash 使用不可校验占位符，ERP 不得再用本表做登录。
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.user import User
from neorvion_security.tenant import TenantContext

_UNUSABLE_PASSWORD_HASH = "!"


def project_display_user(session: Session, context: TenantContext) -> None:
    """按 IAM user_id 写入或更新本地展示名。同一请求内 flush 后即可被 JOIN 看到。"""
    email = (context.email or "").strip().lower() or f"iam-user-{context.user_id}@neorvion.invalid"
    name = (context.display_name or "").strip() or f"用户{context.user_id}"
    user = session.get(User, context.user_id)
    if user is None:
        session.add(
            User(
                id=context.user_id,
                email=email[:255],
                password_hash=_UNUSABLE_PASSWORD_HASH,
                display_name=name[:64],
                status="ACTIVE",
            )
        )
        session.flush()
        return
    if user.display_name != name[:64]:
        user.display_name = name[:64]
    if user.email != email[:255]:
        user.email = email[:255]
    session.flush()

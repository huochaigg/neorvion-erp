"""按 IAM user_id 读取本地展示名快照。批量查询，避免逐单跨服务 HTTP。"""

from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.identity import IdentityNameSnapshot


def identity_display_name(session: Session, user_id: int | None) -> str | None:
    """单条单据详情用。没有快照时返回 None，调用方显示空或「未知」。"""
    if user_id is None:
        return None
    return session.scalar(
        select(IdentityNameSnapshot.display_name).where(IdentityNameSnapshot.user_id == user_id)
    )


def identity_display_names(session: Session, user_ids: Iterable[int | None]) -> dict[int, str]:
    """一次查出多个操作人姓名，给拣货记录等列表用。"""
    ids = sorted({int(uid) for uid in user_ids if uid is not None})
    if not ids:
        return {}
    rows = session.execute(
        select(IdentityNameSnapshot.user_id, IdentityNameSnapshot.display_name).where(
            IdentityNameSnapshot.user_id.in_(ids)
        )
    ).all()
    return {int(uid): name for uid, name in rows}

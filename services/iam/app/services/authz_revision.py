"""在同一数据库事务内递增授权版本并写入 outbox。"""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.authz import AuthzOutbox, AuthzRevision
from app.models.tenant import TenantMember


def bump_member_revision(session: Session, *, user_id: int, tenant_id: int) -> int:
    """递增 (user, tenant) 授权版本，并登记 Redis 刷新 outbox。不 commit。"""
    row = session.scalars(
        select(AuthzRevision)
        .where(AuthzRevision.user_id == user_id, AuthzRevision.tenant_id == tenant_id)
        .with_for_update()
    ).first()
    if row is None:
        row = AuthzRevision(user_id=user_id, tenant_id=tenant_id, version=1)
        session.add(row)
        session.flush()
    else:
        row.version += 1
        row.updated_at = datetime.now()
        session.flush()
    session.add(AuthzOutbox(user_id=user_id, tenant_id=tenant_id, version=row.version))
    return int(row.version)


def bump_role_members(session: Session, *, tenant_id: int, role_id: int) -> list[tuple[int, int]]:
    """角色权限变更时，给所有持有该角色的成员递增版本。"""
    from app.repositories.rbac import RoleRepository
    from app.repositories.tenant import TenantMemberRepository

    members = TenantMemberRepository(session)
    affected: list[tuple[int, int]] = []
    for member_id in RoleRepository(session).list_member_ids_for_role(
        tenant_id=tenant_id,
        role_id=role_id,
    ):
        member = members.get_in_tenant(tenant_id=tenant_id, member_id=member_id)
        if member is None:
            continue
        bump_member_revision(session, user_id=member.user_id, tenant_id=tenant_id)
        affected.append((member.user_id, tenant_id))
    return affected


def current_revision(session: Session, *, user_id: int, tenant_id: int) -> int:
    row = session.scalars(
        select(AuthzRevision).where(
            AuthzRevision.user_id == user_id,
            AuthzRevision.tenant_id == tenant_id,
        )
    ).first()
    return int(row.version) if row is not None else 0


def list_tenant_members_for_user(session: Session, user_id: int) -> list[TenantMember]:
    return list(session.scalars(select(TenantMember).where(TenantMember.user_id == user_id)).all())

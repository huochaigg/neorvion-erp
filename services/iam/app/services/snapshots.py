"""把 IAM 数据库中的成员授权写成 Redis 快照，供 ERP / Knowledge 本地校验。"""

import logging
from datetime import datetime

from neorvion_security.snapshot import AuthzSnapshot, SnapshotStore
from neorvion_security.tenant import TenantContext
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.redis import redis_client
from app.models.authz import AuthzOutbox
from app.models.tenant import MemberRole, MemberStatus, TenantStatus
from app.models.user import UserStatus
from app.repositories.tenant import TenantMemberRepository
from app.repositories.user import UserRepository
from app.services.authorization import AuthorizationService
from app.services.authz_revision import current_revision

logger = logging.getLogger(__name__)


class SnapshotService:
    """登录、刷新、角色变更后刷新授权快照。业务服务不回源 IAM 数据库。"""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.store = SnapshotStore(redis_client, ttl_seconds=settings.snapshot_ttl_seconds)
        self.members = TenantMemberRepository(session)
        self.users = UserRepository(session)
        self.authz = AuthorizationService(session)

    def token_version(self, user_id: int) -> int:
        return self.store.current_token_version(user_id)

    def invalidate_sessions(self, user_id: int) -> int:
        """停用账号或强制下线：递增 token_version，未过期 Access Token 立即失效。"""
        return self.store.bump_token_version(user_id)

    def refresh_user(self, user_id: int) -> None:
        """刷新该用户加入的每个企业快照。

        全局身份会话不能读取 tenant_members。登录后的跨企业投影改用普通会话，
        并且只在身份事务提交之后调用，这样能看到刚写入的用户行。
        """
        from neorvion_db import GlobalIdentitySession

        from app.db.session import SessionLocal

        if isinstance(self.session, GlobalIdentitySession):
            plain = SessionLocal()
            try:
                SnapshotService(plain).refresh_user(user_id)
            finally:
                plain.close()
            return
        user = self.users.get_by_id(user_id)
        if user is None:
            return
        token_version = self.token_version(user_id)
        for member in self.members.list_for_user(user_id):
            self._write_member(user_id=user_id, member=member, token_version=token_version)

    def refresh_member(self, *, user_id: int, tenant_id: int) -> None:
        member = self.members.get_by_tenant_user(tenant_id, user_id)
        if member is None:
            self.store.bump_authz_version(user_id, tenant_id)
            return
        self._write_member(
            user_id=user_id, member=member, token_version=self.token_version(user_id)
        )

    def refresh_role_members(self, *, tenant_id: int, role_id: int) -> None:
        """角色权限变更后刷新所有持有该角色的成员快照，使旧 JWT 立刻按新权限判定。"""
        from app.repositories.rbac import RoleRepository

        for member_id in RoleRepository(self.session).list_member_ids_for_role(
            tenant_id=tenant_id,
            role_id=role_id,
        ):
            member = self.members.get_in_tenant(tenant_id=tenant_id, member_id=member_id)
            if member is None:
                continue
            self.refresh_member(user_id=member.user_id, tenant_id=tenant_id)

    def _write_member(self, *, user_id: int, member, token_version: int) -> None:
        tenant = member.tenant
        if tenant is None:
            return
        context = TenantContext(
            user_id=user_id,
            tenant_id=tenant.id,
            member_id=member.id,
            is_owner=member.role == MemberRole.OWNER.value,
            role=member.role,
        )
        codes = tuple(sorted(self.authz.permission_codes(context)))
        grants = self.authz.roles.list_grants_for_member(tenant_id=tenant.id, member_id=member.id)
        role_codes = tuple(sorted({grant.role.code for grant in grants if grant.role is not None}))
        version = current_revision(self.session, user_id=user_id, tenant_id=tenant.id)
        if version <= 0:
            version = self.store.bump_authz_version(user_id, tenant.id)
        user = self.users.get_by_id(user_id)
        member_status = member.status if member.status else MemberStatus.ACTIVE.value
        if user is not None and user.status != UserStatus.ACTIVE.value:
            member_status = "DISABLED"
        snapshot = AuthzSnapshot(
            user_id=user_id,
            tenant_id=tenant.id,
            member_id=member.id,
            is_owner=member.role == MemberRole.OWNER.value,
            role=member.role,
            status=member_status,
            tenant_status=tenant.status if tenant.status else TenantStatus.ACTIVE.value,
            permission_codes=codes,
            role_codes=role_codes,
            authz_version=version,
            token_version=token_version,
            is_platform_admin=bool(user.is_platform_admin) if user else False,
            must_change_password=bool(user.must_change_password) if user else False,
            display_name=(member.display_name or (user.display_name if user else "")) or "",
            email=(user.email if user else "") or "",
        )
        self.store.save(snapshot)
        self.store.set_authz_version(user_id, tenant.id, version)

    def drain_outbox(self, *, limit: int = 200) -> int:
        """把事务内登记的授权变更刷进 Redis。崩溃后下次 IAM 请求会补刷。"""
        rows = list(
            self.session.scalars(
                select(AuthzOutbox)
                .where(AuthzOutbox.processed_at.is_(None))
                .order_by(AuthzOutbox.id.asc())
                .limit(limit)
            ).all()
        )
        for row in rows:
            self.refresh_member(user_id=row.user_id, tenant_id=row.tenant_id)
            row.processed_at = datetime.now()
        if rows:
            self.session.commit()
        return len(rows)


def sweep_committed_outbox(*, limit: int = 100) -> int:
    """补刷已经提交、但所属租户还没有再次发请求的授权 Outbox。

    和请求内 drain 分开。请求内 drain 必须看见本事务尚未提交的行；
    这里只处理其他租户已经提交的积压，所以使用新的特权会话读取，再用该租户的会话写回。
    """
    from neorvion_db import PrivilegedOperation, open_privileged_session, privileged_option

    from app.db.isolation import REGISTRY
    from app.db.session import engine, open_tenant_session
    from app.db.system_access import PRIVILEGED_CALLERS, PRIVILEGED_FLUSH_MODELS

    claim = open_privileged_session(
        PrivilegedOperation.OUTBOX_SCAN,
        registry=REGISTRY,
        allowed_callers=PRIVILEGED_CALLERS[PrivilegedOperation.OUTBOX_SCAN],
        bind=engine,
        flush_models=PRIVILEGED_FLUSH_MODELS[PrivilegedOperation.OUTBOX_SCAN],
    )
    try:
        rows = list(
            claim.scalars(
                select(AuthzOutbox)
                .where(AuthzOutbox.processed_at.is_(None))
                .order_by(AuthzOutbox.id.asc())
                .limit(limit)
                .execution_options(**privileged_option(PrivilegedOperation.OUTBOX_SCAN))
            ).all()
        )
        pending = [
            (row.id, row.user_id, row.tenant_id)
            for row in rows
            if type(row.tenant_id) is int and row.tenant_id > 0
        ]
    finally:
        claim.close()
    done = 0
    for outbox_id, user_id, tenant_id in pending:
        session = open_tenant_session(int(tenant_id))
        try:
            SnapshotService(session).refresh_member(user_id=user_id, tenant_id=int(tenant_id))
            row = session.scalar(
                select(AuthzOutbox).where(
                    AuthzOutbox.id == outbox_id,
                    AuthzOutbox.tenant_id == tenant_id,
                )
            )
            if row is not None and row.processed_at is None:
                row.processed_at = datetime.now()
            session.commit()
            done += 1
        except Exception:
            session.rollback()
            logger.exception("outbox sweep failed id=%s tenant=%s", outbox_id, tenant_id)
        finally:
            session.close()
    return done

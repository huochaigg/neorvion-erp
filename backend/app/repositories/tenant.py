from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.models.rbac import MemberRoleGrant
from app.models.tenant import Tenant, TenantMember
from app.models.user import User
from app.repositories.base import BaseRepository


class TenantRepository(BaseRepository):
    def __init__(self, session: Session) -> None:
        super().__init__(session)

    def get_by_id(self, tenant_id: int) -> Tenant | None:
        return self.session.get(Tenant, tenant_id)

    def get_by_code(self, code: str) -> Tenant | None:
        stmt = select(Tenant).where(Tenant.code == code)
        return self.session.scalars(stmt).first()

    def add(self, tenant: Tenant) -> Tenant:
        self.session.add(tenant)
        return tenant


class TenantMemberRepository(BaseRepository):
    def __init__(self, session: Session) -> None:
        super().__init__(session)

    def _member_load_options(self):
        """一次查出 user 和角色，避免列表 N+1。不用 joinedload，防止成员×角色笛卡尔积。"""
        return (
            selectinload(TenantMember.user),
            selectinload(TenantMember.member_roles).selectinload(MemberRoleGrant.role),
            selectinload(TenantMember.tenant),
        )

    def get_by_id(self, member_id: int) -> TenantMember | None:
        return self.session.get(TenantMember, member_id)

    def get_by_tenant_user(self, tenant_id: int, user_id: int) -> TenantMember | None:
        stmt = (
            select(TenantMember)
            .options(*self._member_load_options())
            .where(
                TenantMember.tenant_id == tenant_id,
                TenantMember.user_id == user_id,
            )
            .execution_options(populate_existing=True)
        )
        return self.session.scalars(stmt).first()

    def list_for_user(self, user_id: int) -> list[TenantMember]:
        stmt = (
            select(TenantMember)
            .options(selectinload(TenantMember.tenant))
            .where(TenantMember.user_id == user_id)
            .order_by(TenantMember.id.asc())
        )
        return list(self.session.scalars(stmt).all())

    def list_for_tenant(self, tenant_id: int) -> list[TenantMember]:
        # 成员列表必须带 tenant_id，避免只按 member.id 读到别的企业。
        stmt = (
            select(TenantMember)
            .options(*self._member_load_options())
            .where(TenantMember.tenant_id == tenant_id)
            .order_by(TenantMember.id.asc())
            .execution_options(populate_existing=True)
        )
        return list(self.session.scalars(stmt).all())

    def list_page(
        self,
        *,
        tenant_id: int,
        q: str | None,
        status: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[TenantMember], int]:
        """按当前租户分页查成员。搜索走 display_name/email，不会跨租户匹配。"""
        filters = [TenantMember.tenant_id == tenant_id]
        if status:
            filters.append(TenantMember.status == status)

        count_stmt = select(func.count(TenantMember.id)).where(*filters)
        list_stmt = (
            select(TenantMember)
            .options(*self._member_load_options())
            .where(*filters)
            .execution_options(populate_existing=True)
        )
        if q:
            pattern = f"%{q}%"
            search = or_(User.display_name.like(pattern), User.email.like(pattern))
            count_stmt = count_stmt.join(User, User.id == TenantMember.user_id).where(search)
            list_stmt = list_stmt.join(User, User.id == TenantMember.user_id).where(search)

        total = int(self.session.scalar(count_stmt) or 0)
        rows = list(
            self.session.scalars(
                list_stmt.order_by(TenantMember.id.asc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).all()
        )
        return rows, total

    def get_in_tenant(self, *, tenant_id: int, member_id: int) -> TenantMember | None:
        stmt = (
            select(TenantMember)
            .options(*self._member_load_options())
            .where(
                TenantMember.id == member_id,
                TenantMember.tenant_id == tenant_id,
            )
            .execution_options(populate_existing=True)
        )
        return self.session.scalars(stmt).first()

    def lock_in_tenant(self, *, tenant_id: int, member_id: int) -> TenantMember | None:
        """行锁当前租户的成员行。

        两个管理员同时改同一人角色时，后到的请求会等到前一个事务提交，
        而不是各改一半。只锁本租户这一行，不会锁到别的企业。
        """
        stmt = (
            select(TenantMember)
            .where(
                TenantMember.id == member_id,
                TenantMember.tenant_id == tenant_id,
            )
            .with_for_update()
        )
        member = self.session.scalars(stmt).first()
        if member is None:
            return None
        # FOR UPDATE 之后再 selectinload，拿到与锁同一快照上的角色。
        return self.get_in_tenant(tenant_id=tenant_id, member_id=member_id)

    def count_active_owners(self, tenant_id: int) -> int:
        stmt = select(TenantMember.id).where(
            TenantMember.tenant_id == tenant_id,
            TenantMember.role == "OWNER",
            TenantMember.status == "ACTIVE",
        )
        return len(list(self.session.scalars(stmt).all()))

    def add(self, member: TenantMember) -> TenantMember:
        self.session.add(member)
        return member

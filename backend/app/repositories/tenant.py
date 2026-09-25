from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.tenant import Tenant, TenantMember
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

    def get_by_id(self, member_id: int) -> TenantMember | None:
        return self.session.get(TenantMember, member_id)

    def get_by_tenant_user(self, tenant_id: int, user_id: int) -> TenantMember | None:
        stmt = (
            select(TenantMember)
            .options(selectinload(TenantMember.tenant), selectinload(TenantMember.user))
            .where(
                TenantMember.tenant_id == tenant_id,
                TenantMember.user_id == user_id,
            )
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
            .options(selectinload(TenantMember.user))
            .where(TenantMember.tenant_id == tenant_id)
            .order_by(TenantMember.id.asc())
        )
        return list(self.session.scalars(stmt).all())

    def get_in_tenant(self, *, tenant_id: int, member_id: int) -> TenantMember | None:
        stmt = (
            select(TenantMember)
            .options(selectinload(TenantMember.user))
            .where(
                TenantMember.id == member_id,
                TenantMember.tenant_id == tenant_id,
            )
        )
        return self.session.scalars(stmt).first()

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

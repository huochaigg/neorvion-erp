import re
from uuid import uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.models.tenant import MemberRole, MemberStatus, Tenant, TenantMember, TenantStatus
from app.models.user import User, UserStatus
from app.repositories.tenant import TenantMemberRepository, TenantRepository
from app.repositories.user import UserRepository
from app.schemas.tenant import MemberOut, TenantOut

_CODE_PATTERN = re.compile(r"^[a-z][a-z0-9-]{1,31}$")

_UNAVAILABLE = "租户不存在或不可访问"


class TenantService:
    """租户事务在本层 commit。Repository 只写 session.add。"""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.tenants = TenantRepository(session)
        self.members = TenantMemberRepository(session)
        self.users = UserRepository(session)

    def create_tenant(self, *, user: User, name: str, code: str | None) -> TenantOut:
        code = self._resolve_code(code)
        tenant = Tenant(
            name=name,
            code=code,
            status=TenantStatus.ACTIVE.value,
            created_by=user.id,
        )
        try:
            self.tenants.add(tenant)
            self.session.flush()
            member = TenantMember(
                tenant_id=tenant.id,
                user_id=user.id,
                status=MemberStatus.ACTIVE.value,
                role=MemberRole.OWNER.value,
            )
            self.members.add(member)
            self.session.commit()
        except IntegrityError:
            self.session.rollback()
            raise AppError("租户编码已存在", code=40910, status_code=409) from None
        except Exception:
            # 成员写入失败时租户必须一起回滚，避免出现无 Owner 的空企业。
            self.session.rollback()
            raise
        return self._tenant_out(tenant, member)

    def list_my_tenants(self, user: User) -> list[TenantOut]:
        rows = self.members.list_for_user(user.id)
        return [self._tenant_out(row.tenant, row) for row in rows]

    def get_tenant(self, *, user: User, tenant_id: int) -> TenantOut:
        member = self._require_membership(user_id=user.id, tenant_id=tenant_id)
        return self._tenant_out(member.tenant, member)

    def list_members(self, *, user: User, tenant_id: int) -> list[MemberOut]:
        self._require_active_access(user_id=user.id, tenant_id=tenant_id)
        return [self._member_out(row) for row in self.members.list_for_tenant(tenant_id)]

    def add_member(self, *, user: User, tenant_id: int, target_user_id: int) -> MemberOut:
        self._require_owner(user_id=user.id, tenant_id=tenant_id)
        target = self.users.get_by_id(target_user_id)
        if target is None or target.status != UserStatus.ACTIVE.value:
            raise AppError("用户不存在", code=40411, status_code=404)
        if self.members.get_by_tenant_user(tenant_id, target_user_id) is not None:
            raise AppError("该用户已是租户成员", code=40911, status_code=409)
        member = TenantMember(
            tenant_id=tenant_id,
            user_id=target_user_id,
            status=MemberStatus.ACTIVE.value,
            role=MemberRole.MEMBER.value,
        )
        try:
            self.members.add(member)
            self.session.commit()
            self.session.refresh(member)
        except IntegrityError:
            self.session.rollback()
            raise AppError("该用户已是租户成员", code=40911, status_code=409) from None
        member.user = target
        return self._member_out(member)

    def update_member(
        self,
        *,
        user: User,
        tenant_id: int,
        member_id: int,
        status: str,
    ) -> MemberOut:
        self._require_owner(user_id=user.id, tenant_id=tenant_id)
        if status not in {MemberStatus.ACTIVE.value, MemberStatus.DISABLED.value}:
            raise AppError("成员状态不合法", code=40035, status_code=400)
        member = self.members.get_in_tenant(tenant_id=tenant_id, member_id=member_id)
        if member is None:
            raise AppError("成员不存在", code=40412, status_code=404)
        if (
            member.role == MemberRole.OWNER.value
            and status == MemberStatus.DISABLED.value
            and self.members.count_active_owners(tenant_id) <= 1
        ):
            raise AppError("不能禁用唯一所有者", code=40034, status_code=400)
        member.status = status
        self.session.commit()
        self.session.refresh(member)
        return self._member_out(member)

    def _require_membership(self, *, user_id: int, tenant_id: int) -> TenantMember:
        member = self.members.get_by_tenant_user(tenant_id, user_id)
        if member is None:
            raise AppError(_UNAVAILABLE, code=40410, status_code=404)
        tenant = member.tenant or self.tenants.get_by_id(tenant_id)
        if tenant is None:
            raise AppError(_UNAVAILABLE, code=40410, status_code=404)
        member.tenant = tenant
        return member

    def _require_active_access(self, *, user_id: int, tenant_id: int) -> TenantMember:
        member = self._require_membership(user_id=user_id, tenant_id=tenant_id)
        if member.status != MemberStatus.ACTIVE.value:
            raise AppError("无权访问该租户", code=40310, status_code=403)
        if member.tenant.status != TenantStatus.ACTIVE.value:
            raise AppError("无权访问该租户", code=40310, status_code=403)
        return member

    def _require_owner(self, *, user_id: int, tenant_id: int) -> TenantMember:
        member = self._require_active_access(user_id=user_id, tenant_id=tenant_id)
        if member.role != MemberRole.OWNER.value:
            raise AppError("无权管理该租户成员", code=40311, status_code=403)
        return member

    def _resolve_code(self, code: str | None) -> str:
        if code:
            if not _CODE_PATTERN.fullmatch(code):
                raise AppError("租户编码不合法", code=40032, status_code=400)
            if self.tenants.get_by_code(code) is not None:
                raise AppError("租户编码已存在", code=40910, status_code=409)
            return code
        for _ in range(5):
            generated = "t" + uuid4().hex[:10]
            if self.tenants.get_by_code(generated) is None:
                return generated
        raise AppError("无法生成租户编码", code=50020, status_code=500)

    @staticmethod
    def _tenant_out(tenant: Tenant, member: TenantMember) -> TenantOut:
        return TenantOut(
            id=tenant.id,
            name=tenant.name,
            code=tenant.code,
            status=tenant.status,
            created_by=tenant.created_by,
            created_at=tenant.created_at,
            updated_at=tenant.updated_at,
            my_role=member.role,
            my_status=member.status,
            is_owner=member.role == MemberRole.OWNER.value,
        )

    @staticmethod
    def _member_out(member: TenantMember) -> MemberOut:
        user = member.user
        return MemberOut(
            id=member.id,
            tenant_id=member.tenant_id,
            user_id=member.user_id,
            role=member.role,
            status=member.status,
            joined_at=member.joined_at,
            display_name=user.display_name if user is not None else "",
            email=user.email if user is not None else "",
        )

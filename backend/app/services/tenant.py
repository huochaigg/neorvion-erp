import re
from uuid import uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.core.permissions import PermissionCode, SystemRoleCode, known_permission_codes
from app.core.security import generate_temporary_password, hash_password
from app.core.tenant import TenantContext
from app.models.tenant import MemberRole, MemberStatus, Tenant, TenantMember, TenantStatus
from app.models.user import User, UserStatus
from app.repositories.rbac import PermissionRepository
from app.repositories.tenant import TenantMemberRepository, TenantRepository
from app.repositories.user import UserRepository
from app.schemas.rbac import PermissionOut
from app.schemas.tenant import (
    MemberCreatedOut,
    MemberDetailOut,
    MemberListOut,
    MemberOut,
    MemberRoleBrief,
    TenantOut,
)
from app.services.authorization import AuthorizationService
from app.services.rbac import RoleService

_CODE_PATTERN = re.compile(r"^[a-z][a-z0-9-]{1,31}$")

_UNAVAILABLE = "租户不存在或不可访问"


class TenantService:
    """租户事务在本层 commit。Repository 只写 session.add。"""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.tenants = TenantRepository(session)
        self.members = TenantMemberRepository(session)
        self.users = UserRepository(session)
        self.auth = AuthorizationService(session)
        self.rbac = RoleService(session)
        self.permission_rows = PermissionRepository(session)

    def create_tenant(self, *, user: User, name: str, code: str | None) -> TenantOut:
        """同一事务：企业 + OWNER 成员 + 默认角色 + 创建者挂上 OWNER 角色。"""
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
            self.session.flush()
            self.rbac.bootstrap_tenant(tenant_id=tenant.id, owner_member_id=member.id)
            self.session.commit()
        except IntegrityError:
            self.session.rollback()
            raise AppError("租户编码已存在", code=40910, status_code=409) from None
        except Exception:
            # 角色引导失败时租户必须一起回滚，避免出现没有默认角色的半成品企业。
            self.session.rollback()
            raise
        return self._tenant_out(tenant, member)

    def list_my_tenants(self, user: User) -> list[TenantOut]:
        rows = self.members.list_for_user(user.id)
        return [self._tenant_out(row.tenant, row) for row in rows]

    def get_tenant(self, *, user: User, tenant_id: int) -> TenantOut:
        member = self._require_membership(user_id=user.id, tenant_id=tenant_id)
        return self._tenant_out(member.tenant, member)

    def list_members(
        self,
        *,
        context: TenantContext,
        tenant_id: int,
        q: str | None = None,
        status: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> MemberListOut:
        """列出当前租户成员。

        路径上的 tenant_id 必须等于 TenantContext，防止拿 A 的头去翻 B 的名单。
        """
        self._assert_same_tenant(context, tenant_id)
        self.auth.require_all(context, (PermissionCode.TENANT_MEMBER_READ,))
        if status and status not in {MemberStatus.ACTIVE.value, MemberStatus.DISABLED.value}:
            raise AppError("成员状态不合法", code=40035, status_code=400)
        keyword = (q or "").strip() or None
        rows, total = self.members.list_page(
            tenant_id=context.tenant_id,
            q=keyword,
            status=status,
            page=page,
            page_size=page_size,
        )
        return MemberListOut(
            items=[self._member_out(row) for row in rows],
            total=total,
            page=page,
            page_size=page_size,
        )

    def get_member(
        self,
        *,
        context: TenantContext,
        tenant_id: int,
        member_id: int,
    ) -> MemberDetailOut:
        """成员详情含角色并集后的有效权限。

        找不到时 404，避免用不同状态码暴露其他租户是否存在该成员 ID。
        """
        self._assert_same_tenant(context, tenant_id)
        self.auth.require_all(context, (PermissionCode.TENANT_MEMBER_READ,))
        member = self.members.get_in_tenant(tenant_id=context.tenant_id, member_id=member_id)
        if member is None:
            raise AppError("成员不存在", code=40412, status_code=404)
        return self._member_detail_out(member)

    def add_member(
        self,
        *,
        context: TenantContext,
        tenant_id: int,
        email: str | None = None,
        target_user_id: int | None = None,
        role_ids: list[int] | None = None,
    ) -> MemberOut:
        """按邮箱把已注册用户加入当前租户，并在同一事务里写入角色。

        功能：创建 tenant_members 行 + member_roles。
        参数：email 优先；role_ids 为空则默认 VIEWER。
        异常：用户不存在 40411；已是成员 40911；非法 OWNER 40321；跨租户角色 40420。
        关键流程：先校验全部角色，再 insert。并发重复加入靠 UNIQUE(tenant_id, user_id) 转 409。
        """
        self._assert_same_tenant(context, tenant_id)
        self.auth.require_all(context, (PermissionCode.TENANT_MEMBER_MANAGE,))
        target = self._resolve_target_user(email=email, user_id=target_user_id)
        if self.members.get_by_tenant_user(context.tenant_id, target.id) is not None:
            raise AppError("该用户已是租户成员", code=40911, status_code=409)
        assigned_ids = self.rbac.resolve_assignable_role_ids(
            tenant_id=context.tenant_id,
            role_ids=role_ids or [],
            default_viewer=True,
        )
        member = TenantMember(
            tenant_id=context.tenant_id,
            user_id=target.id,
            status=MemberStatus.ACTIVE.value,
            role=MemberRole.MEMBER.value,
        )
        try:
            self.members.add(member)
            # flush 后才有 member.id，才能写 member_roles 的复合外键。
            self.session.flush()
            self.rbac.grant_roles(
                tenant_id=context.tenant_id,
                member_id=member.id,
                role_ids=assigned_ids,
            )
            self.session.commit()
            self.session.refresh(member)
        except IntegrityError:
            # 两个管理员同时添加同一邮箱时，第二次撞唯一约束，而不是插入半成品。
            self.session.rollback()
            raise AppError("该用户已是租户成员", code=40911, status_code=409) from None
        except Exception:
            self.session.rollback()
            raise
        member.user = target
        reloaded = self.members.get_in_tenant(tenant_id=context.tenant_id, member_id=member.id)
        return self._member_out(reloaded or member)

    def create_member_account(
        self,
        *,
        context: TenantContext,
        tenant_id: int,
        display_name: str,
        email: str,
        role_ids: list[int] | None = None,
    ) -> MemberCreatedOut:
        """代建全局 User，并在同一事务加入当前企业、写入角色。

        管理员不能设长期密码：后端用 secrets 生成一次性明文，只放进本次响应。
        数据库只存 Argon2id。must_change_password=True，首次业务请求会被 40350 拦住。

        先校验角色再创建 User。否则邮箱唯一键已经占用，角色非法时虽然能 rollback，
        但调用方会先看到含糊的 IntegrityError，而不是 40420 / 40321。
        """
        self._assert_same_tenant(context, tenant_id)
        self.auth.require_all(context, (PermissionCode.TENANT_MEMBER_MANAGE,))
        assigned_ids = self.rbac.resolve_assignable_role_ids(
            tenant_id=context.tenant_id,
            role_ids=role_ids or [],
            default_viewer=True,
        )
        if self.users.get_by_email(email) is not None:
            raise AppError("该邮箱已被注册", code=40011, status_code=409)
        temporary_password = generate_temporary_password()
        user = User(
            email=email,
            password_hash=hash_password(temporary_password),
            display_name=display_name,
            status=UserStatus.ACTIVE.value,
            must_change_password=True,
        )
        try:
            self.users.add(user)
            # flush 后才有 user.id，才能写 tenant_members.user_id。
            self.session.flush()
            member = TenantMember(
                tenant_id=context.tenant_id,
                user_id=user.id,
                status=MemberStatus.ACTIVE.value,
                role=MemberRole.MEMBER.value,
            )
            self.members.add(member)
            self.session.flush()
            self.rbac.grant_roles(
                tenant_id=context.tenant_id,
                member_id=member.id,
                role_ids=assigned_ids,
            )
            self.session.commit()
            self.session.refresh(member)
        except IntegrityError:
            # 并发注册同一邮箱，或同一用户被并发加入本企业。回滚后按库状态区分文案。
            self.session.rollback()
            if self.users.get_by_email(email) is not None:
                raise AppError("该邮箱已被注册", code=40011, status_code=409) from None
            raise AppError("该用户已是租户成员", code=40911, status_code=409) from None
        except Exception:
            self.session.rollback()
            raise
        reloaded = self.members.get_in_tenant(tenant_id=context.tenant_id, member_id=member.id)
        base = self._member_out(reloaded or member)
        return MemberCreatedOut(**base.model_dump(), temporary_password=temporary_password)

    def replace_member_roles(
        self,
        *,
        context: TenantContext,
        tenant_id: int,
        member_id: int,
        role_ids: list[int],
    ) -> MemberOut:
        """全量替换成员角色。OWNER 成员不能走这个接口改角色（转移是独立流程）。"""
        self._assert_same_tenant(context, tenant_id)
        self.auth.require_all(context, (PermissionCode.TENANT_MEMBER_MANAGE,))
        try:
            member = self.members.lock_in_tenant(
                tenant_id=context.tenant_id,
                member_id=member_id,
            )
            if member is None:
                raise AppError("成员不存在", code=40412, status_code=404)
            if self._is_owner_member(member):
                raise AppError("不能修改所有者的角色", code=40322, status_code=403)
            assigned_ids = self.rbac.resolve_assignable_role_ids(
                tenant_id=context.tenant_id,
                role_ids=role_ids,
                default_viewer=False,
            )
            self.rbac.replace_member_role_grants(
                tenant_id=context.tenant_id,
                member_id=member.id,
                role_ids=assigned_ids,
            )
            # 行锁加载过旧的 member_roles；过期后再查，
            # 避免 expire_on_commit=False 把 VIEWER 带回响应。
            self.session.expire(member, ["member_roles"])
            self.session.commit()
        except AppError:
            self.session.rollback()
            raise
        except Exception:
            self.session.rollback()
            raise
        reloaded = self.members.get_in_tenant(tenant_id=context.tenant_id, member_id=member_id)
        if reloaded is None:
            raise AppError("成员不存在", code=40412, status_code=404)
        return self._member_out(reloaded)

    def update_member(
        self,
        *,
        context: TenantContext,
        tenant_id: int,
        member_id: int,
        status: str,
    ) -> MemberOut:
        """启用或禁用成员。

        禁用后下一次请求走 get_tenant_context 立刻 40310，
        不看 Access Token 是否仍在有效期内。
        """
        self._assert_same_tenant(context, tenant_id)
        self.auth.require_all(context, (PermissionCode.TENANT_MEMBER_MANAGE,))
        if status not in {MemberStatus.ACTIVE.value, MemberStatus.DISABLED.value}:
            raise AppError("成员状态不合法", code=40035, status_code=400)
        member = self.members.lock_in_tenant(tenant_id=context.tenant_id, member_id=member_id)
        if member is None:
            raise AppError("成员不存在", code=40412, status_code=404)
        if (
            self._is_owner_member(member)
            and status == MemberStatus.DISABLED.value
            and self.members.count_active_owners(context.tenant_id) <= 1
        ):
            raise AppError("不能禁用唯一所有者", code=40034, status_code=400)
        member.status = status
        try:
            self.session.commit()
            self.session.refresh(member)
        except Exception:
            self.session.rollback()
            raise
        reloaded = self.members.get_in_tenant(tenant_id=context.tenant_id, member_id=member_id)
        return self._member_out(reloaded or member)

    def remove_member(
        self,
        *,
        context: TenantContext,
        tenant_id: int,
        member_id: int,
    ) -> None:
        """解除当前企业的成员关系，不删除全局 User。

        禁用只改 status，成员行还在；移除会删 TenantMember 和 MemberRoleGrant。
        OWNER 不能走本接口：所有权转移是独立流程。即便还有其他 OWNER，也禁止用删除绕过。
        """
        self._assert_same_tenant(context, tenant_id)
        self.auth.require_all(context, (PermissionCode.TENANT_MEMBER_MANAGE,))
        try:
            member = self.members.lock_in_tenant(
                tenant_id=context.tenant_id,
                member_id=member_id,
            )
            if member is None:
                raise AppError("成员不存在", code=40412, status_code=404)
            if self._is_owner_member(member):
                raise AppError("不能移除所有者", code=40322, status_code=403)
            self.rbac.roles.delete_grants_for_member(
                tenant_id=context.tenant_id,
                member_id=member.id,
            )
            self.members.delete(member)
            self.session.commit()
        except AppError:
            self.session.rollback()
            raise
        except Exception:
            self.session.rollback()
            raise

    def _resolve_target_user(self, *, email: str | None, user_id: int | None) -> User:
        if email:
            target = self.users.get_by_email(email)
        else:
            target = self.users.get_by_id(user_id) if user_id is not None else None
        # 未注册或已禁用都说「用户不存在」，避免用不同文案证明邮箱是否在系统里。
        if target is None or target.status != UserStatus.ACTIVE.value:
            raise AppError("用户不存在", code=40411, status_code=404)
        return target

    def _require_membership(self, *, user_id: int, tenant_id: int) -> TenantMember:
        member = self.members.get_by_tenant_user(tenant_id, user_id)
        if member is None:
            raise AppError(_UNAVAILABLE, code=40410, status_code=404)
        tenant = member.tenant or self.tenants.get_by_id(tenant_id)
        if tenant is None:
            raise AppError(_UNAVAILABLE, code=40410, status_code=404)
        member.tenant = tenant
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
    def _assert_same_tenant(context: TenantContext, tenant_id: int) -> None:
        if tenant_id != context.tenant_id:
            raise AppError(_UNAVAILABLE, code=40410, status_code=404)

    @staticmethod
    def _is_owner_member(member: TenantMember) -> bool:
        if member.role == MemberRole.OWNER.value:
            return True
        return any(
            grant.role and grant.role.code == SystemRoleCode.OWNER for grant in member.member_roles
        )

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

    def _member_out(self, member: TenantMember) -> MemberOut:
        user = member.user
        roles = [
            MemberRoleBrief(
                id=grant.role.id,
                code=grant.role.code,
                name=grant.role.name,
                is_system=grant.role.is_system,
            )
            for grant in member.member_roles
            if grant.role is not None
        ]
        roles.sort(key=lambda item: item.code)
        return MemberOut(
            id=member.id,
            tenant_id=member.tenant_id,
            user_id=member.user_id,
            role=member.role,
            status=member.status,
            joined_at=member.joined_at,
            display_name=user.display_name if user is not None else "",
            email=user.email if user is not None else "",
            is_owner=self._is_owner_member(member),
            roles=roles,
        )

    def _member_detail_out(self, member: TenantMember) -> MemberDetailOut:
        base = self._member_out(member)
        permissions = self._effective_permissions(member)
        return MemberDetailOut(
            **base.model_dump(),
            permission_codes=[item.code for item in permissions],
            permissions=permissions,
        )

    def _effective_permissions(self, member: TenantMember) -> list[PermissionOut]:
        """OWNER 列拥有目录全部权限；其他人按角色并集。与 AuthorizationService 判定保持一致。"""
        if member.role == MemberRole.OWNER.value:
            rows = self.permission_rows.list_all()
        else:
            rows = self.rbac.roles.list_permissions_for_member(
                tenant_id=member.tenant_id,
                member_id=member.id,
            )
        catalog = known_permission_codes()
        return [
            PermissionOut(
                id=item.id,
                code=item.code,
                name=item.name,
                module=item.module,
                description=item.description,
            )
            for item in rows
            if item.code in catalog
        ]

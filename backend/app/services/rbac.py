"""角色与权限目录。Repository 不 commit；对外写操作由本层提交，引导租户时不提交。"""

from __future__ import annotations

import re

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.core.permissions import (
    DEFAULT_ROLE_TEMPLATES,
    PERMISSION_CATALOG,
    PermissionCode,
    SystemRoleCode,
)
from app.core.tenant import TenantContext
from app.models.rbac import MemberRoleGrant, Permission, Role, RolePermission
from app.models.tenant import MemberRole, Tenant
from app.repositories.rbac import PermissionRepository, RoleRepository
from app.repositories.tenant import TenantMemberRepository
from app.schemas.rbac import PermissionOut, RoleCreate, RoleOut, RoleUpdate
from app.services.authorization import AuthorizationService

_ROLE_CODE = re.compile(r"^[A-Z][A-Z0-9_-]{0,31}$")
_UNAVAILABLE = "角色不存在或不可访问"


class RoleService:
    """租户内角色 CRUD、权限绑定与成员授权。对外 API 在本层 commit；bootstrap 由调用方管事务。"""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.permissions = PermissionRepository(session)
        self.roles = RoleRepository(session)
        self.members = TenantMemberRepository(session)
        self.auth = AuthorizationService(session)

    def seed_permission_catalog(self) -> int:
        """幂等写入权限目录：已有 code 只更新名称/模块/说明，不删行。不 commit。"""
        created = 0
        for code, name, module, description in PERMISSION_CATALOG:
            row = self.permissions.get_by_code(code)
            if row is None:
                self.permissions.add(
                    Permission(code=code, name=name, module=module, description=description)
                )
                created += 1
            else:
                row.name = name
                row.module = module
                row.description = description
        self.session.flush()
        return created

    def bootstrap_tenant(self, *, tenant_id: int, owner_member_id: int | None) -> None:
        """为租户创建默认系统角色；OWNER 成员挂 OWNER，其余成员挂 VIEWER。调用方负责事务。"""
        self.seed_permission_catalog()
        permission_by_code = {item.code: item for item in self.permissions.list_all()}
        viewer: Role | None = None
        owner_role: Role | None = None
        for code, name, description, perm_codes in DEFAULT_ROLE_TEMPLATES:
            role = self._ensure_system_role(
                tenant_id=tenant_id,
                code=code,
                name=name,
                description=description,
                permission_codes=perm_codes,
                permission_by_code=permission_by_code,
            )
            if code == SystemRoleCode.VIEWER:
                viewer = role
            if code == SystemRoleCode.OWNER:
                owner_role = role
        if owner_role is not None and owner_member_id is not None:
            self._grant_role(
                tenant_id=tenant_id,
                member_id=owner_member_id,
                role=owner_role,
                allow_owner_role=True,
            )
        if viewer is not None:
            for member in self.members.list_for_tenant(tenant_id):
                if member.id == owner_member_id:
                    continue
                self._grant_role(
                    tenant_id=tenant_id,
                    member_id=member.id,
                    role=viewer,
                    allow_owner_role=False,
                )

    def backfill_existing_tenants(self) -> int:
        """给历史租户补默认角色。已有 OWNER 成员列的人挂上 OWNER 角色。"""
        self.seed_permission_catalog()
        tenants = list(self.session.scalars(select(Tenant).order_by(Tenant.id.asc())).all())
        for tenant in tenants:
            members = self.members.list_for_tenant(tenant.id)
            owner = next((row for row in members if row.role == MemberRole.OWNER.value), None)
            if owner is None and tenant.created_by:
                owner = self.members.get_by_tenant_user(tenant.id, tenant.created_by)
            self.bootstrap_tenant(
                tenant_id=tenant.id,
                owner_member_id=owner.id if owner is not None else None,
            )
        return len(tenants)

    def list_permissions(self, context: TenantContext) -> list[PermissionOut]:
        """列出全局权限目录。需 tenant:role:read。"""
        self.auth.require_all(context, (PermissionCode.TENANT_ROLE_READ,))
        return [self._permission_out(item) for item in self.permissions.list_all()]

    def list_roles(self, context: TenantContext) -> list[RoleOut]:
        """列出当前租户下全部角色（含系统角色）。需 tenant:role:read。"""
        self.auth.require_all(context, (PermissionCode.TENANT_ROLE_READ,))
        return [self._role_out(item) for item in self.roles.list_in_tenant(context.tenant_id)]

    def get_role(self, context: TenantContext, role_id: int) -> RoleOut:
        """按 ID 取本租户角色详情。跨租户或不存在统一 404。"""
        self.auth.require_all(context, (PermissionCode.TENANT_ROLE_READ,))
        return self._role_out(self._require_role(context.tenant_id, role_id))

    def create_role(self, context: TenantContext, payload: RoleCreate) -> RoleOut:
        """创建自定义角色并绑定权限。系统角色码冲突走 409；本方法 commit。"""
        self.auth.require_all(context, (PermissionCode.TENANT_ROLE_MANAGE,))
        code = self._normalize_code(payload.code)
        if self.roles.get_by_code(context.tenant_id, code) is not None:
            raise AppError("角色编码已存在", code=40920, status_code=409)
        permission_ids = self._validate_permission_ids(payload.permission_ids)
        role = Role(
            tenant_id=context.tenant_id,
            name=payload.name.strip(),
            code=code,
            description=(payload.description or "").strip(),
            is_system=False,
        )
        try:
            self.roles.add(role)
            self.session.flush()
            self.roles.replace_permissions(
                tenant_id=context.tenant_id,
                role_id=role.id,
                permission_ids=permission_ids,
            )
            self.session.commit()
        except IntegrityError:
            self.session.rollback()
            raise AppError("角色编码已存在", code=40920, status_code=409) from None
        except Exception:
            self.session.rollback()
            raise
        return self.get_role(context, role.id)

    def update_role(self, context: TenantContext, role_id: int, payload: RoleUpdate) -> RoleOut:
        """更新自定义角色名称/描述。系统角色禁止改；不改权限列表。"""
        self.auth.require_all(context, (PermissionCode.TENANT_ROLE_MANAGE,))
        role = self._require_role(context.tenant_id, role_id)
        if role.is_system:
            raise AppError("系统角色不允许修改", code=40040, status_code=400)
        if payload.name is not None:
            role.name = payload.name.strip()
        if payload.description is not None:
            role.description = payload.description.strip()
        try:
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        return self.get_role(context, role.id)

    def replace_role_permissions(
        self,
        context: TenantContext,
        role_id: int,
        permission_ids: list[int],
    ) -> RoleOut:
        """全量替换自定义角色的权限集合。系统角色禁止改。"""
        self.auth.require_all(context, (PermissionCode.TENANT_ROLE_MANAGE,))
        role = self._require_role(context.tenant_id, role_id)
        if role.is_system:
            raise AppError("系统角色不允许修改", code=40040, status_code=400)
        ids = self._validate_permission_ids(permission_ids)
        try:
            self.roles.replace_permissions(
                tenant_id=context.tenant_id,
                role_id=role.id,
                permission_ids=ids,
            )
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        return self.get_role(context, role.id)

    def delete_role(self, context: TenantContext, role_id: int) -> None:
        """删除自定义角色。系统角色、仍有成员占用的角色不可删；顺带清 role_permissions。"""
        self.auth.require_all(context, (PermissionCode.TENANT_ROLE_MANAGE,))
        role = self._require_role(context.tenant_id, role_id)
        if role.is_system:
            raise AppError("系统角色不允许删除", code=40040, status_code=400)
        if self.roles.count_grants(tenant_id=context.tenant_id, role_id=role.id) > 0:
            raise AppError("角色仍被成员使用，不能删除", code=40041, status_code=400)
        try:
            self.session.execute(
                delete(RolePermission).where(
                    RolePermission.tenant_id == context.tenant_id,
                    RolePermission.role_id == role.id,
                )
            )
            self.roles.delete(role)
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise

    def assign_member_role(
        self,
        *,
        tenant_id: int,
        member_id: int,
        role_id: int,
        actor: TenantContext | None = None,
        commit: bool = True,
    ) -> None:
        """给成员加角色。传 actor 时需 member:manage，且不能授 OWNER；bootstrap 不传 actor。"""
        if actor is not None:
            self.auth.require_all(actor, (PermissionCode.TENANT_MEMBER_MANAGE,))
        role = self._require_role(tenant_id, role_id)
        member = self.members.get_in_tenant(tenant_id=tenant_id, member_id=member_id)
        if member is None:
            raise AppError("成员不存在", code=40412, status_code=404)
        # 普通分配接口不能授予 OWNER。创建租户 / 历史回填不传 actor。
        allow_owner = actor is None
        try:
            self._grant_role(
                tenant_id=tenant_id,
                member_id=member.id,
                role=role,
                allow_owner_role=allow_owner,
            )
            if commit:
                self.session.commit()
        except IntegrityError:
            self.session.rollback()
            raise AppError(_UNAVAILABLE, code=40420, status_code=404) from None
        except Exception:
            self.session.rollback()
            raise

    def revoke_member_role(self, *, tenant_id: int, member_id: int, role_id: int) -> None:
        """撤销成员的某个角色授权。最后一个 OWNER 不可撤；无授权则静默成功。"""
        role = self._require_role(tenant_id, role_id)
        grant = self.roles.get_grant(tenant_id=tenant_id, member_id=member_id, role_id=role_id)
        if grant is None:
            return
        if role.code == SystemRoleCode.OWNER:
            if self.roles.count_active_owner_grants(tenant_id) <= 1:
                raise AppError("不能移除唯一所有者", code=40034, status_code=400)
        self.roles.delete_grant(grant)
        self.session.commit()

    def grant_default_member_role(self, *, tenant_id: int, member_id: int) -> None:
        """新成员默认挂 VIEWER。不 commit，由租户加人事务一并提交。"""
        viewer = self.roles.get_by_code(tenant_id, SystemRoleCode.VIEWER)
        if viewer is None:
            raise AppError("默认角色未初始化", code=50022, status_code=500)
        self._grant_role(
            tenant_id=tenant_id,
            member_id=member_id,
            role=viewer,
            allow_owner_role=False,
        )

    def _ensure_system_role(
        self,
        *,
        tenant_id: int,
        code: str,
        name: str,
        description: str,
        permission_codes: tuple[str, ...],
        permission_by_code: dict[str, Permission],
    ) -> Role:
        """幂等确保系统角色存在，并补齐模板里缺失的权限关联（只增不删）。"""
        role = self.roles.get_by_code(tenant_id, code)
        if role is None:
            role = Role(
                tenant_id=tenant_id,
                name=name,
                code=code,
                description=description,
                is_system=True,
            )
            self.roles.add(role)
            self.session.flush()
        current = set(
            self.session.scalars(
                select(RolePermission.permission_id).where(
                    RolePermission.tenant_id == tenant_id,
                    RolePermission.role_id == role.id,
                )
            ).all()
        )
        for perm_code in permission_codes:
            permission = permission_by_code.get(perm_code)
            if permission is None:
                raise AppError("权限编码未定义", code=50021, status_code=500)
            if permission.id not in current:
                self.roles.add_permission_link(
                    RolePermission(
                        tenant_id=tenant_id,
                        role_id=role.id,
                        permission_id=permission.id,
                    )
                )
        self.session.flush()
        return role

    def _grant_role(
        self,
        *,
        tenant_id: int,
        member_id: int,
        role: Role,
        allow_owner_role: bool,
    ) -> None:
        """写入 member_role_grants。已授权则跳过；默认禁止授 OWNER。"""
        if role.tenant_id != tenant_id:
            raise AppError(_UNAVAILABLE, code=40420, status_code=404)
        if role.code == SystemRoleCode.OWNER and not allow_owner_role:
            raise AppError("不能授予所有者角色", code=40321, status_code=403)
        if self.roles.get_grant(tenant_id=tenant_id, member_id=member_id, role_id=role.id):
            return
        self.roles.add_grant(
            MemberRoleGrant(tenant_id=tenant_id, member_id=member_id, role_id=role.id)
        )
        self.session.flush()

    def _require_role(self, tenant_id: int, role_id: int) -> Role:
        """在本租户内取角色，否则 404（文案故意模糊）。"""
        role = self.roles.get_in_tenant(tenant_id, role_id)
        if role is None:
            raise AppError(_UNAVAILABLE, code=40420, status_code=404)
        return role

    def _validate_permission_ids(self, permission_ids: list[int]) -> list[int]:
        """去重并确认权限 ID 均存在于全局目录。"""
        unique_ids = list(dict.fromkeys(permission_ids))
        rows = self.permissions.get_by_ids(unique_ids)
        if len(rows) != len(unique_ids):
            raise AppError("权限不存在", code=40042, status_code=400)
        return unique_ids

    @staticmethod
    def _normalize_code(code: str) -> str:
        """角色 code：去空白、转大写，并校验命名规则。"""
        normalized = code.strip().upper()
        if not _ROLE_CODE.fullmatch(normalized):
            raise AppError("角色编码不合法", code=40043, status_code=400)
        return normalized

    @staticmethod
    def _permission_out(item: Permission) -> PermissionOut:
        """Permission ORM → API schema。"""
        return PermissionOut(
            id=item.id,
            code=item.code,
            name=item.name,
            module=item.module,
            description=item.description,
        )

    @staticmethod
    def _role_out(role: Role) -> RoleOut:
        """Role ORM → API schema（含按 code 排序的权限列表）。"""
        permissions = [
            RoleService._permission_out(link.permission)
            for link in role.role_permissions
            if link.permission is not None
        ]
        permissions.sort(key=lambda item: item.code)
        return RoleOut(
            id=role.id,
            tenant_id=role.tenant_id,
            name=role.name,
            code=role.code,
            description=role.description,
            is_system=role.is_system,
            created_at=role.created_at,
            updated_at=role.updated_at,
            permissions=permissions,
        )

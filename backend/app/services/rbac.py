"""角色与权限目录。Repository 不 commit；对外写操作由本层提交，引导租户时不提交。"""

from __future__ import annotations

import re

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.core.permissions import (
    ADMIN_REQUIRED_PERMISSION_CODES,
    DEFAULT_ROLE_TEMPLATES,
    LEGACY_MANAGE_EXPANSION,
    PERMISSION_CATALOG,
    PERMISSION_TREE,
    PermissionCode,
    PermissionTreeDef,
    SystemRoleCode,
    is_deprecated_permission,
)
from app.core.tenant import TenantContext
from app.models.rbac import MemberRoleGrant, Permission, Role, RolePermission
from app.models.tenant import MemberRole, Tenant
from app.repositories.rbac import PermissionRepository, RoleRepository
from app.repositories.tenant import TenantMemberRepository
from app.schemas.rbac import PermissionOut, PermissionTreeNodeOut, RoleCreate, RoleOut, RoleUpdate
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

    def expand_legacy_manage_permissions(self) -> int:
        """把旧 tenant:*:manage 展开成细粒度权限。

        功能：历史角色只挂了 manage 时，补上 create/update 等新 code。
        参数：无。扫描全部 role_permissions。
        返回：新插入的关联行数。
        异常：新 code 未 seed 时 50021。
        核心流程：先建 code→Permission 映射，再按角色已有 permission_id 判断是否缺行。
        不删除旧 manage：立刻删会导致尚未升级的校验或展示对不上。
        """
        self.seed_permission_catalog()
        by_code = {item.code: item for item in self.permissions.list_all()}
        permission_id_to_code = {item.id: item.code for item in by_code.values()}
        links = list(self.session.scalars(select(RolePermission)).all())
        owned: dict[int, set[int]] = {}
        for link in links:
            owned.setdefault(link.role_id, set()).add(link.permission_id)
        added = 0
        for link in links:
            extras = LEGACY_MANAGE_EXPANSION.get(permission_id_to_code.get(link.permission_id, ""))
            if not extras:
                continue
            for extra_code in extras:
                permission = by_code.get(extra_code)
                if permission is None:
                    raise AppError("权限编码未定义", code=50021, status_code=500)
                if permission.id in owned.get(link.role_id, set()):
                    continue
                self.roles.add_permission_link(
                    RolePermission(
                        tenant_id=link.tenant_id,
                        role_id=link.role_id,
                        permission_id=permission.id,
                    )
                )
                owned.setdefault(link.role_id, set()).add(permission.id)
                added += 1
        self.session.flush()
        return added

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
        """列出全局权限目录。目录只读，租户不能 CRUD Permission。"""
        self.auth.require_any(
            context,
            (
                PermissionCode.TENANT_PERMISSION_READ,
                PermissionCode.TENANT_ROLE_READ,
            ),
        )
        return [self._permission_out(item) for item in self.permissions.list_all()]

    def list_permission_tree(self, context: TenantContext) -> list[PermissionTreeNodeOut]:
        """把程序定义的资源树转成带 permission_id 的配置树。

        功能：给角色授权 UI 展示 目录 → 菜单 → 按钮。
        参数：已校验的 TenantContext。
        返回：DIRECTORY/MENU 可以没有 permission_id；ACTION 才对应真实权限。
        异常：缺少查看/配置相关权限时 403。
        核心流程：只查全局 permissions 表补 id，不写租户菜单表。
        """
        self.auth.require_any(
            context,
            (
                PermissionCode.TENANT_PERMISSION_READ,
                PermissionCode.TENANT_ROLE_READ,
                PermissionCode.TENANT_ROLE_CREATE,
                PermissionCode.TENANT_ROLE_PERMISSION_UPDATE,
            ),
        )
        by_code = {item.code: item for item in self.permissions.list_all()}
        nodes: list[PermissionTreeNodeOut] = []
        for item in PERMISSION_TREE:
            mapped = self._tree_node_out(item, by_code)
            if mapped is not None:
                nodes.append(mapped)
        return nodes

    def list_roles(self, context: TenantContext) -> list[RoleOut]:
        """列出当前租户下全部角色（含系统角色）。需 tenant:role:read。"""
        self.auth.require_all(context, (PermissionCode.TENANT_ROLE_READ,))
        counts = self.roles.count_grants_grouped(context.tenant_id)
        return [
            self._role_out(item, member_count=counts.get(item.id, 0))
            for item in self.roles.list_in_tenant(context.tenant_id)
        ]

    def get_role(self, context: TenantContext, role_id: int) -> RoleOut:
        """按 ID 取本租户角色详情。跨租户或不存在统一 404。"""
        self.auth.require_all(context, (PermissionCode.TENANT_ROLE_READ,))
        role = self._require_role(context.tenant_id, role_id)
        return self._role_out(
            role,
            member_count=self.roles.count_grants(tenant_id=context.tenant_id, role_id=role.id),
        )

    def create_role(self, context: TenantContext, payload: RoleCreate) -> RoleOut:
        """创建自定义角色并绑定权限。系统角色码冲突走 409；本方法 commit。"""
        self.auth.require_all(context, (PermissionCode.TENANT_ROLE_CREATE,))
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
        """更新自定义角色名称/描述。系统角色禁止改；不改权限列表。code 创建后只读。"""
        self.auth.require_all(context, (PermissionCode.TENANT_ROLE_UPDATE,))
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
        """全量替换角色权限。OWNER 核心权限冻结；其他系统角色允许调业务权限。

        先校验全部 permission_id 都存在，再删除旧关联。否则会出现
        「旧权限已经清空、新权限因无效 ID 失败」的半更新。
        没有 Redis 权限缓存：提交后下一次 require_permission / my-permissions
        都会重新 JOIN 数据库。
        """
        self.auth.require_all(context, (PermissionCode.TENANT_ROLE_PERMISSION_UPDATE,))
        role = self._require_role(context.tenant_id, role_id)
        if role.code == SystemRoleCode.OWNER:
            raise AppError("所有者角色的核心权限不可通过管理接口修改", code=40040, status_code=400)
        ids = self._validate_permission_ids(permission_ids)
        if role.code == SystemRoleCode.ADMIN:
            self._assert_admin_keeps_tenant_management(ids)
        try:
            self.roles.replace_permissions(
                tenant_id=context.tenant_id,
                role_id=role.id,
                permission_ids=ids,
            )
            # bulk DELETE 不会自动过期已加载的 role_permissions。
            self.session.expire(role, ["role_permissions"])
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        return self.get_role(context, role.id)

    def delete_role(self, context: TenantContext, role_id: int) -> None:
        """删除自定义角色。系统角色、仍有成员占用的角色不可删；顺带清 role_permissions。

        有人还在用时禁止静默清 MemberRoleGrant，否则成员会突然失去全部权限。
        """
        self.auth.require_all(context, (PermissionCode.TENANT_ROLE_DELETE,))
        role = self._require_role(context.tenant_id, role_id)
        # 不能只靠前端藏按钮：系统角色必须由 is_system 在服务端拒绝。
        if role.is_system:
            raise AppError("系统角色不允许删除", code=40040, status_code=400)
        # 先查询该角色是否仍被 MemberRoleGrant 引用，
        # 如果直接删除角色并级联删除关联，会导致成员权限被静默改变。
        # 因此这里明确拒绝删除，并要求管理员先调整成员角色。
        used = self.roles.count_grants(tenant_id=context.tenant_id, role_id=role.id)
        if used > 0:
            raise AppError(
                f"当前角色仍有 {used} 名成员使用，请先调整这些成员的角色。",
                code=40041,
                status_code=400,
                data={"error": "ROLE_IN_USE", "member_count": used},
            )
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
        """给成员加角色。传 actor 时需 member:role:update，且不能授 OWNER；bootstrap 不传 actor。"""
        if actor is not None:
            self.auth.require_all(actor, (PermissionCode.TENANT_MEMBER_ROLE_UPDATE,))
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

    def resolve_assignable_role_ids(
        self,
        *,
        tenant_id: int,
        role_ids: list[int],
        default_viewer: bool,
    ) -> list[int]:
        """校验角色全部属于当前租户，并禁止 OWNER。

        必须在写入 member_roles 之前一次校验完。否则会出现「前两个角色写进去了，
        第三个是别的租户角色才失败」的半成品。
        """
        unique_ids = list(dict.fromkeys(role_ids))
        if not unique_ids and default_viewer:
            viewer = self.roles.get_by_code(tenant_id, SystemRoleCode.VIEWER)
            if viewer is None:
                raise AppError("默认角色未初始化", code=50022, status_code=500)
            return [viewer.id]
        rows = self.roles.list_in_tenant_by_ids(tenant_id, unique_ids)
        if len(rows) != len(unique_ids):
            raise AppError(_UNAVAILABLE, code=40420, status_code=404)
        if any(row.code == SystemRoleCode.OWNER for row in rows):
            raise AppError("不能授予所有者角色", code=40321, status_code=403)
        return unique_ids

    def grant_roles(self, *, tenant_id: int, member_id: int, role_ids: list[int]) -> None:
        """给新成员挂上已经校验过的角色。不 commit。"""
        for role_id in role_ids:
            role = self._require_role(tenant_id, role_id)
            self._grant_role(
                tenant_id=tenant_id,
                member_id=member_id,
                role=role,
                allow_owner_role=False,
            )

    def replace_member_role_grants(
        self,
        *,
        tenant_id: int,
        member_id: int,
        role_ids: list[int],
    ) -> None:
        """删除旧授权再写入新授权。调用方必须已持有成员行锁并处于同一事务。"""
        self.roles.replace_member_roles(
            tenant_id=tenant_id,
            member_id=member_id,
            role_ids=role_ids,
        )
        self.session.flush()

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

    def _assert_admin_keeps_tenant_management(self, permission_ids: list[int]) -> None:
        """ADMIN 可以调整业务权限，但不能拿掉租户管理入口。"""
        rows = self.permissions.get_by_ids(permission_ids)
        codes = {item.code for item in rows}
        missing = ADMIN_REQUIRED_PERMISSION_CODES - codes
        if missing:
            raise AppError("管理员角色必须保留租户管理能力", code=40040, status_code=400)

    @staticmethod
    def _normalize_code(code: str) -> str:
        """角色 code：去空白、转大写，并校验命名规则。"""
        normalized = code.strip().upper()
        if not _ROLE_CODE.fullmatch(normalized):
            raise AppError("角色编码不合法", code=40043, status_code=400)
        return normalized

    @staticmethod
    def _tree_node_out(
        node: PermissionTreeDef,
        by_code: dict[str, Permission],
    ) -> PermissionTreeNodeOut | None:
        """递归映射权限树。废弃 code 不出现在树上，避免再授权旧 manage。"""
        if node.permission_code and is_deprecated_permission(node.permission_code):
            return None
        permission = by_code.get(node.permission_code) if node.permission_code else None
        if node.permission_code and permission is None:
            return None
        children = [
            child
            for child in (RoleService._tree_node_out(item, by_code) for item in node.children)
            if child is not None
        ]
        if permission is None and not children:
            return None
        return PermissionTreeNodeOut(
            key=node.key,
            title=node.title,
            type=node.type,
            permission_id=permission.id if permission is not None else None,
            permission_code=permission.code if permission is not None else None,
            children=children,
        )

    @staticmethod
    def _permission_out(item: Permission) -> PermissionOut:
        """Permission ORM → API schema。"""
        return PermissionOut(
            id=item.id,
            code=item.code,
            name=item.name,
            module=item.module,
            description=item.description,
            deprecated=is_deprecated_permission(item.code),
        )

    @staticmethod
    def _role_out(role: Role, *, member_count: int = 0) -> RoleOut:
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
            member_count=member_count,
        )

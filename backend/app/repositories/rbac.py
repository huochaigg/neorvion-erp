from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from app.core.permissions import SystemRoleCode
from app.models.rbac import MemberRoleGrant, Permission, Role, RolePermission
from app.models.tenant import TenantMember
from app.repositories.base import BaseRepository


class PermissionRepository(BaseRepository):
    def __init__(self, session: Session) -> None:
        super().__init__(session)

    def list_all(self) -> list[Permission]:
        stmt = select(Permission).order_by(Permission.module.asc(), Permission.code.asc())
        return list(self.session.scalars(stmt).all())

    def get_by_code(self, code: str) -> Permission | None:
        stmt = select(Permission).where(Permission.code == code)
        return self.session.scalars(stmt).first()

    def get_by_ids(self, permission_ids: list[int]) -> list[Permission]:
        if not permission_ids:
            return []
        stmt = select(Permission).where(Permission.id.in_(permission_ids))
        return list(self.session.scalars(stmt).all())

    def add(self, permission: Permission) -> Permission:
        self.session.add(permission)
        return permission


class RoleRepository(BaseRepository):
    def __init__(self, session: Session, tenant_id: int | None = None) -> None:
        super().__init__(session, tenant_id)

    def list_in_tenant(self, tenant_id: int) -> list[Role]:
        stmt = (
            select(Role)
            .options(selectinload(Role.role_permissions).selectinload(RolePermission.permission))
            .where(Role.tenant_id == tenant_id)
            .order_by(Role.id.asc())
            .execution_options(populate_existing=True)
        )
        return list(self.session.scalars(stmt).all())

    def get_in_tenant(self, tenant_id: int, role_id: int) -> Role | None:
        stmt = (
            select(Role)
            .options(selectinload(Role.role_permissions).selectinload(RolePermission.permission))
            .where(Role.tenant_id == tenant_id, Role.id == role_id)
            .execution_options(populate_existing=True)
        )
        return self.session.scalars(stmt).first()

    def get_by_code(self, tenant_id: int, code: str) -> Role | None:
        stmt = select(Role).where(Role.tenant_id == tenant_id, Role.code == code)
        return self.session.scalars(stmt).first()

    def add(self, role: Role) -> Role:
        self.session.add(role)
        return role

    def delete(self, role: Role) -> None:
        self.session.delete(role)

    def count_grants(self, *, tenant_id: int, role_id: int) -> int:
        stmt = select(MemberRoleGrant.id).where(
            MemberRoleGrant.tenant_id == tenant_id,
            MemberRoleGrant.role_id == role_id,
        )
        return len(list(self.session.scalars(stmt).all()))

    def count_active_owner_grants(self, tenant_id: int) -> int:
        """有效 OWNER 角色授权人数。用来挡住「卸掉最后一个所有者」。"""
        stmt = (
            select(MemberRoleGrant.id)
            .join(Role, Role.id == MemberRoleGrant.role_id)
            .join(TenantMember, TenantMember.id == MemberRoleGrant.member_id)
            .where(
                MemberRoleGrant.tenant_id == tenant_id,
                Role.tenant_id == tenant_id,
                Role.code == SystemRoleCode.OWNER,
                TenantMember.status == "ACTIVE",
            )
        )
        return len(list(self.session.scalars(stmt).all()))

    def replace_permissions(
        self,
        *,
        tenant_id: int,
        role_id: int,
        permission_ids: list[int],
    ) -> None:
        self.session.execute(
            delete(RolePermission).where(
                RolePermission.tenant_id == tenant_id,
                RolePermission.role_id == role_id,
            )
        )
        for permission_id in permission_ids:
            self.session.add(
                RolePermission(
                    tenant_id=tenant_id,
                    role_id=role_id,
                    permission_id=permission_id,
                )
            )

    def add_permission_link(self, link: RolePermission) -> RolePermission:
        self.session.add(link)
        return link

    def list_permission_codes_for_member(self, *, tenant_id: int, member_id: int) -> set[str]:
        """当前成员所有有效角色的权限并集。JOIN 出 code，不做 joinedload。"""
        stmt = (
            select(Permission.code)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .join(MemberRoleGrant, MemberRoleGrant.role_id == RolePermission.role_id)
            .where(
                MemberRoleGrant.tenant_id == tenant_id,
                MemberRoleGrant.member_id == member_id,
                RolePermission.tenant_id == tenant_id,
            )
        )
        return set(self.session.scalars(stmt).all())

    def get_grant(self, *, tenant_id: int, member_id: int, role_id: int) -> MemberRoleGrant | None:
        stmt = select(MemberRoleGrant).where(
            MemberRoleGrant.tenant_id == tenant_id,
            MemberRoleGrant.member_id == member_id,
            MemberRoleGrant.role_id == role_id,
        )
        return self.session.scalars(stmt).first()

    def add_grant(self, grant: MemberRoleGrant) -> MemberRoleGrant:
        self.session.add(grant)
        return grant

    def delete_grant(self, grant: MemberRoleGrant) -> None:
        self.session.delete(grant)

    def list_grants_for_member(self, *, tenant_id: int, member_id: int) -> list[MemberRoleGrant]:
        stmt = (
            select(MemberRoleGrant)
            .options(selectinload(MemberRoleGrant.role))
            .where(
                MemberRoleGrant.tenant_id == tenant_id,
                MemberRoleGrant.member_id == member_id,
            )
        )
        return list(self.session.scalars(stmt).all())

    def list_in_tenant_by_ids(self, tenant_id: int, role_ids: list[int]) -> list[Role]:
        """只返回属于当前租户的角色。调用方用数量比对，发现少了就是跨租户或伪造 ID。"""
        if not role_ids:
            return []
        stmt = select(Role).where(Role.tenant_id == tenant_id, Role.id.in_(role_ids))
        return list(self.session.scalars(stmt).all())

    def replace_member_roles(
        self,
        *,
        tenant_id: int,
        member_id: int,
        role_ids: list[int],
    ) -> None:
        """全量替换成员角色。先删后插必须在同一事务里，否则会出现「旧角色没了、新角色没写上」。

        bulk DELETE 默认不会把 Session 里已加载的 MemberRoleGrant 标成 deleted。
        若不 synchronize_session，commit 时 identity map 里的旧 VIEWER 可能被当成仍存在的行，
        返回给前端的 member_roles 就会继续显示替换前的角色。
        """
        self.session.execute(
            delete(MemberRoleGrant)
            .where(
                MemberRoleGrant.tenant_id == tenant_id,
                MemberRoleGrant.member_id == member_id,
            )
            .execution_options(synchronize_session="fetch")
        )
        for role_id in role_ids:
            self.session.add(
                MemberRoleGrant(tenant_id=tenant_id, member_id=member_id, role_id=role_id)
            )

    def list_permissions_for_member(self, *, tenant_id: int, member_id: int) -> list[Permission]:
        """多角色权限并集。JOIN 三张表只取 Permission 行，不把整棵树载入内存。"""
        stmt = (
            select(Permission)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .join(MemberRoleGrant, MemberRoleGrant.role_id == RolePermission.role_id)
            .where(
                MemberRoleGrant.tenant_id == tenant_id,
                MemberRoleGrant.member_id == member_id,
                RolePermission.tenant_id == tenant_id,
            )
            .order_by(Permission.module.asc(), Permission.code.asc())
            .distinct()
        )
        return list(self.session.scalars(stmt).all())

"""从 ERP MySQL 一次性搬迁身份数据到 IAM。禁止长期双写。

用法：配置 IAM .env 后：

    uv run python -m app.scripts.migrate_from_erp

默认读取 ERP 库 neorvion_erp。已存在相同 email/code 时跳过，保持幂等。
ERP `20261018_0022` 之后身份表已删除，本脚本只适用于尚未 DROP 的旧库。
"""

from __future__ import annotations

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.rbac import MemberRoleGrant, Permission, Role, RolePermission
from app.models.tenant import Tenant, TenantMember
from app.models.user import User
from app.services.rbac import RoleService


def _erp_engine():
    url = settings.build_database_url("neorvion_erp")
    return create_engine(url, pool_pre_ping=True)


def main() -> None:
    source = _erp_engine()
    session: Session = SessionLocal()
    try:
        with source.connect() as conn:
            users = conn.execute(text("SELECT * FROM users")).mappings().all()
            tenants = conn.execute(text("SELECT * FROM tenants")).mappings().all()
            members = conn.execute(text("SELECT * FROM tenant_members")).mappings().all()
            roles = conn.execute(text("SELECT * FROM roles")).mappings().all()
            permissions = conn.execute(text("SELECT * FROM permissions")).mappings().all()
            member_roles = conn.execute(text("SELECT * FROM member_roles")).mappings().all()
            role_perms = conn.execute(text("SELECT * FROM role_permissions")).mappings().all()
        existing_emails = {row.email for row in session.query(User).all()}
        for row in users:
            if row["email"] in existing_emails:
                continue
            session.add(
                User(
                    id=row["id"],
                    email=row["email"],
                    password_hash=row["password_hash"] or hash_password("Migrated1"),
                    display_name=row["display_name"],
                    status=row["status"],
                    last_login_at=row["last_login_at"],
                    must_change_password=bool(row.get("must_change_password") or False),
                    is_platform_admin=False,
                )
            )
        session.flush()
        existing_codes = {row.code for row in session.query(Tenant).all()}
        for row in tenants:
            if row["code"] in existing_codes:
                continue
            session.add(
                Tenant(
                    id=row["id"],
                    name=row["name"],
                    code=row["code"],
                    status=row["status"],
                    created_by=row["created_by"],
                )
            )
        session.flush()
        RoleService(session).seed_permission_catalog()
        perm_by_code = {item.code: item for item in session.query(Permission).all()}
        for row in permissions:
            if row["code"] not in perm_by_code:
                session.add(
                    Permission(
                        code=row["code"],
                        name=row["name"],
                        module=row["module"],
                        description=row["description"] or "",
                    )
                )
        session.flush()
        existing_member_ids = {item.id for item in session.query(TenantMember).all()}
        for row in members:
            if row["id"] in existing_member_ids:
                continue
            session.add(
                TenantMember(
                    id=row["id"],
                    tenant_id=row["tenant_id"],
                    user_id=row["user_id"],
                    status=row["status"],
                    role=row["role"],
                    display_name=row.get("display_name"),
                )
            )
        session.flush()
        existing_role_ids = {item.id for item in session.query(Role).all()}
        for row in roles:
            if row["id"] in existing_role_ids:
                continue
            session.add(
                Role(
                    id=row["id"],
                    tenant_id=row["tenant_id"],
                    name=row["name"],
                    code=row["code"],
                    description=row["description"] or "",
                    is_system=bool(row["is_system"]),
                )
            )
        session.flush()
        for row in member_roles:
            session.add(
                MemberRoleGrant(
                    tenant_id=row["tenant_id"],
                    member_id=row["member_id"],
                    role_id=row["role_id"],
                )
            )
        perm_id_by_code = {item.code: item.id for item in session.query(Permission).all()}
        old_perm = {row["id"]: row["code"] for row in permissions}
        for row in role_perms:
            code = old_perm.get(row["permission_id"])
            if code is None or code not in perm_id_by_code:
                continue
            session.add(
                RolePermission(
                    tenant_id=row["tenant_id"],
                    role_id=row["role_id"],
                    permission_id=perm_id_by_code[code],
                )
            )
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
        source.dispose()
    print("identity data copied from neorvion_erp to neorvion_iam")


if __name__ == "__main__":
    main()

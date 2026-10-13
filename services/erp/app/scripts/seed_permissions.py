"""幂等写入平台权限目录。重复运行只更新名称/说明，不删已有权限。

用法（在 backend 目录）：

    uv run python -m app.scripts.seed_permissions
"""

from app.db.session import SessionLocal
from app.services.rbac import RoleService


def main() -> None:
    session = SessionLocal()
    try:
        service = RoleService(session)
        created = service.seed_permission_catalog()
        expanded = service.expand_legacy_manage_permissions()
        tenants = service.backfill_existing_tenants()
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
    print(
        "permissions seeded, "
        f"newly created={created}, legacy expanded={expanded}, tenants backfilled={tenants}"
    )


if __name__ == "__main__":
    main()

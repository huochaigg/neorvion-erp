"""幂等写入平台权限目录。重复运行只更新名称/说明，不删已有权限。

用法（在 backend 目录）：

    uv run python -m app.scripts.seed_permissions
"""

from app.db.session import SessionLocal
from app.services.rbac import RoleService


def main() -> None:
    session = SessionLocal()
    try:
        created = RoleService(session).seed_permission_catalog()
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
    print(f"permissions seeded, newly created={created}")


if __name__ == "__main__":
    main()

"""幂等写入权限目录与内置应用。"""

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.catalog import Application
from app.services.rbac import RoleService

_APPS = (
    ("iam", "IAM 权限中心", "neorvion-iam", "统一身份与权限"),
    ("erp", "ERP 业务", "neorvion-erp", "跨境电商 ERP"),
    ("knowledge", "AI 知识库", "neorvion-knowledge", "企业知识检索与问答"),
)


def main() -> None:
    session = SessionLocal()
    try:
        service = RoleService(session)
        created = service.seed_permission_catalog()
        expanded = service.expand_legacy_manage_permissions()
        tenants = service.backfill_existing_tenants()
        for code, name, audience, description in _APPS:
            exists = session.scalars(select(Application).where(Application.code == code)).first()
            if exists is None:
                session.add(
                    Application(code=code, name=name, audience=audience, description=description)
                )
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
    print(
        "IAM catalog seeded, "
        f"permissions created={created}, legacy expanded={expanded}, tenants backfilled={tenants}"
    )


if __name__ == "__main__":
    main()

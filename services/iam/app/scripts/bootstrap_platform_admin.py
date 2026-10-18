"""引导平台超级管理员。密码只从环境变量读取，禁止写日志。"""

from sqlalchemy import select

from app.core.config import settings
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.user import User, UserStatus


def main() -> None:
    email = (settings.bootstrap_admin_email or "").strip().lower()
    password = settings.bootstrap_admin_password
    if not email or not password:
        print("skip bootstrap: IAM_BOOTSTRAP_ADMIN_EMAIL / IAM_BOOTSTRAP_ADMIN_PASSWORD 未配置")
        return
    session = SessionLocal()
    try:
        existing = session.scalars(select(User).where(User.email == email)).first()
        if existing is not None:
            if not existing.is_platform_admin:
                existing.is_platform_admin = True
                existing.status = UserStatus.ACTIVE.value
                session.commit()
                print(f"promoted existing user to platform admin: {email}")
            else:
                print(f"platform admin already exists: {email}")
            return
        session.add(
            User(
                email=email,
                password_hash=hash_password(password),
                display_name="Platform Admin",
                status=UserStatus.ACTIVE.value,
                is_platform_admin=True,
            )
        )
        session.commit()
        print(f"created platform admin: {email}")
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()

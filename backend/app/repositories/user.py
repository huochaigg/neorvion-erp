from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user import User
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository):
    """用户是全局身份，查询不按 tenant_id 过滤。"""

    def __init__(self, session: Session) -> None:
        super().__init__(session)

    def get_by_id(self, user_id: int) -> User | None:
        return self.session.get(User, user_id)

    def get_by_email(self, email: str) -> User | None:
        stmt = select(User).where(User.email == email.strip().lower())
        return self.session.scalars(stmt).first()

    def add(self, user: User) -> User:
        self.session.add(user)
        return user

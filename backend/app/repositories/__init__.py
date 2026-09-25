"""Repository 层只负责查询与持久化。"""

from app.repositories.base import BaseRepository
from app.repositories.tenant import TenantMemberRepository, TenantRepository
from app.repositories.user import UserRepository

__all__ = ["BaseRepository", "TenantMemberRepository", "TenantRepository", "UserRepository"]


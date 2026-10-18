"""Repository 层只负责查询与持久化。身份仓储已迁到 IAM。"""

from app.repositories.base import BaseRepository

__all__ = ["BaseRepository"]

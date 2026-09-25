"""ORM 模型。M1 仅建立基类，业务表从 M2 开始通过 Alembic 添加。"""

from app.db.base import Base

__all__ = ["Base"]

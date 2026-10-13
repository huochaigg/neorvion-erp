from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """SQLAlchemy 2.x 声明式基类。所有 ORM 模型继承它，Alembic 读取其 metadata。"""

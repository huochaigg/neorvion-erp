from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """SQLAlchemy 2.x 声明式基类。Alembic 读取其 metadata。"""

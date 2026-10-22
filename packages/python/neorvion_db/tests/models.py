"""测试用的最小模型。不代表生产表。"""

from sqlalchemy import ForeignKeyConstraint, Integer, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Widget(Base):
    """租户业务主表。"""

    __tablename__ = "widgets"
    __table_args__ = (UniqueConstraint("tenant_id", "id", name="uq_widgets_tenant_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(32), nullable=False)
    parts: Mapped[list["Part"]] = relationship(back_populates="widget")


class Part(Base):
    """租户子表。复合外键禁止指向其他租户的 Widget。"""

    __tablename__ = "parts"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "widget_id"],
            ["widgets.tenant_id", "widgets.id"],
            name="fk_parts_widget",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False)
    widget_id: Mapped[int] = mapped_column(Integer, nullable=False)
    widget: Mapped[Widget] = relationship(back_populates="parts")


class Note(Base):
    """全局资源。"""

    __tablename__ = "notes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    body: Mapped[str] = mapped_column(String(64), nullable=False)


class Job(Base):
    """系统与租户混合表。空 tenant_id 表示系统行。"""

    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    title: Mapped[str] = mapped_column(String(32), nullable=False)

"""ERP 侧身份快照。身份所有权在 IAM，这里只存展示名供单据 JOIN。"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class IdentityNameSnapshot(Base):
    """IAM user_id 对应的展示名快照。

    不是登录表：无密码、无状态、无租户成员关系。写入来源只有 JWT 上下文或迁移回填。
    """

    __tablename__ = "identity_name_snapshots"

    user_id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=False,
        comment="IAM users.id，跨服务整数契约，无外键",
    )
    display_name: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="单据列表展示用，可落后于 IAM",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        comment="最近一次由 JWT 投影或回填更新的时间",
    )

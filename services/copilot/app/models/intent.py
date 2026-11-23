from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TenantMixin, TimestampMixin


class IntentContext(TimestampMixin, TenantMixin, Base):
    """按会话隔离的意图上下文与 Pending；不是第二套 Skill Pending 状态机。"""

    __tablename__ = "copilot_intent_contexts"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_copilot_intent_contexts_tenant_id"),
        UniqueConstraint(
            "tenant_id",
            "user_id",
            "conversation_id",
            name="uq_copilot_intent_contexts_owner_conversation",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "user_id", "conversation_id"],
            [
                "copilot_conversations.tenant_id",
                "copilot_conversations.user_id",
                "copilot_conversations.id",
            ],
            ondelete="CASCADE",
            name="fk_copilot_intent_context_conversation_owner",
        ),
        Index("ix_copilot_intent_contexts_expiry", "status", "expires_at"),
        CheckConstraint(
            "status IN ('IDLE','COLLECTING','READY','CANCELLED','EXPIRED')",
            name="ck_copilot_intent_context_status",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    conversation_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="IDLE")
    intent_key: Mapped[str | None] = mapped_column(String(64))
    collected_slots: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    missing_slots: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    entities: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    last_resolution: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    message_summaries: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    last_request_id: Mapped[str] = mapped_column(String(64), nullable=False, server_default="")
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

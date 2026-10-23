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


class ActionProposal(TimestampMixin, TenantMixin, Base):
    __tablename__ = "copilot_action_proposals"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_copilot_action_proposals_tenant_id"),
        UniqueConstraint("tenant_id", "user_id", "id", name="uq_copilot_action_proposals_owner"),
        UniqueConstraint(
            "tenant_id",
            "user_id",
            "idempotency_key",
            name="uq_copilot_action_proposals_idempotency",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "user_id", "conversation_id"],
            [
                "copilot_conversations.tenant_id",
                "copilot_conversations.user_id",
                "copilot_conversations.id",
            ],
            ondelete="CASCADE",
            name="fk_copilot_action_proposals_conversation_owner",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "source_message_id"],
            ["copilot_messages.tenant_id", "copilot_messages.id"],
            name="fk_copilot_action_proposals_source_message",
        ),
        CheckConstraint(
            "status IN ('DRAFT','NEEDS_INPUT','READY','STALE','CANCELLED','EXPIRED')",
            name="ck_copilot_action_proposals_status",
        ),
        Index("ix_copilot_action_proposals_owner_updated", "tenant_id", "user_id", "updated_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    conversation_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    source_message_id: Mapped[int | None] = mapped_column(BigInteger)
    action_type: Mapped[str] = mapped_column(String(64), nullable=False)
    schema_version: Mapped[int] = mapped_column(nullable=False, server_default="1")
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    current_revision: Mapped[int] = mapped_column(nullable=False, server_default="1")
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ProposalRevision(TenantMixin, Base):
    __tablename__ = "copilot_proposal_revisions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "proposal_id"],
            ["copilot_action_proposals.tenant_id", "copilot_action_proposals.id"],
            ondelete="CASCADE",
            name="fk_copilot_proposal_revisions_proposal",
        ),
        UniqueConstraint(
            "tenant_id", "proposal_id", "revision", name="uq_copilot_proposal_revision"
        ),
        Index("ix_copilot_proposal_revisions_proposal", "tenant_id", "proposal_id"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    proposal_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    revision: Mapped[int] = mapped_column(nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    editor_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )


class ProposalValidation(TenantMixin, Base):
    __tablename__ = "copilot_proposal_validations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "proposal_id"],
            ["copilot_action_proposals.tenant_id", "copilot_action_proposals.id"],
            ondelete="CASCADE",
            name="fk_copilot_proposal_validations_proposal",
        ),
        UniqueConstraint(
            "tenant_id", "proposal_id", "revision", name="uq_copilot_proposal_validation_revision"
        ),
        Index("ix_copilot_proposal_validations_proposal", "tenant_id", "proposal_id"),
        CheckConstraint(
            "status IN ('VALID','INVALID','UNAVAILABLE')",
            name="ck_copilot_proposal_validations_status",
        ),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    proposal_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    revision: Mapped[int] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    errors: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, server_default="[]")
    warnings: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, server_default="[]"
    )
    missing_fields: Mapped[list[str]] = mapped_column(JSONB, nullable=False, server_default="[]")
    preview_data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    resource_versions: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default="{}"
    )
    validated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

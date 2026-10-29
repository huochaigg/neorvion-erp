from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TenantMixin, TimestampMixin


class ConversationStatus(StrEnum):
    ACTIVE = "ACTIVE"
    DELETED = "DELETED"


class MessageStatus(StrEnum):
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class ToolRunStatus(StrEnum):
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class Conversation(TimestampMixin, TenantMixin, Base):
    __tablename__ = "copilot_conversations"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_copilot_conversations_tenant_id"),
        UniqueConstraint("tenant_id", "user_id", "id", name="uq_copilot_conversations_owner"),
        Index("ix_copilot_conversations_owner_updated", "tenant_id", "user_id", "updated_at"),
        CheckConstraint("status IN ('ACTIVE', 'DELETED')", name="ck_copilot_conversations_status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    title: Mapped[str] = mapped_column(
        String(128), nullable=False, server_default="New conversation"
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="ACTIVE")
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Message(TimestampMixin, TenantMixin, Base):
    __tablename__ = "copilot_messages"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_copilot_messages_tenant_id"),
        ForeignKeyConstraint(
            ["tenant_id", "user_id", "conversation_id"],
            [
                "copilot_conversations.tenant_id",
                "copilot_conversations.user_id",
                "copilot_conversations.id",
            ],
            ondelete="CASCADE",
            name="fk_copilot_messages_conversation_owner",
        ),
        UniqueConstraint(
            "tenant_id",
            "conversation_id",
            "client_request_id",
            "role",
            name="uq_copilot_messages_idempotency",
        ),
        Index(
            "ix_copilot_messages_conversation_created", "tenant_id", "conversation_id", "created_at"
        ),
        Index("ix_copilot_messages_running", "tenant_id", "conversation_id", "status"),
        CheckConstraint("role IN ('user', 'assistant')", name="ck_copilot_messages_role"),
        CheckConstraint(
            "status IN ('RUNNING', 'COMPLETED', 'FAILED', 'CANCELLED')",
            name="ck_copilot_messages_status",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    client_request_id: Mapped[str] = mapped_column(String(64), nullable=False)
    request_id: Mapped[str] = mapped_column(String(64), nullable=False, server_default="")
    protocol_data: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    error_code: Mapped[int | None] = mapped_column()
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ToolRun(TenantMixin, Base):
    __tablename__ = "copilot_tool_runs"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_copilot_tool_runs_tenant_id"),
        ForeignKeyConstraint(
            ["tenant_id", "conversation_id"],
            ["copilot_conversations.tenant_id", "copilot_conversations.id"],
            ondelete="CASCADE",
            name="fk_copilot_tool_runs_conversation_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "message_id"],
            ["copilot_messages.tenant_id", "copilot_messages.id"],
            ondelete="CASCADE",
            name="fk_copilot_tool_runs_message_tenant",
        ),
        UniqueConstraint("tenant_id", "message_id", "tool_call_id", name="uq_copilot_tool_call"),
        Index("ix_copilot_tool_runs_message", "tenant_id", "message_id"),
        CheckConstraint(
            "status IN ('RUNNING', 'SUCCEEDED', 'FAILED', 'CANCELLED')",
            name="ck_copilot_tool_runs_status",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    message_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    tool_call_id: Mapped[str] = mapped_column(String(128), nullable=False)
    tool_name: Mapped[str] = mapped_column(String(64), nullable=False)
    agent_task_id: Mapped[str | None] = mapped_column(String(96))
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="RUNNING")
    duration_ms: Mapped[int | None] = mapped_column()
    input_summary: Mapped[str | None] = mapped_column(Text)
    output_summary: Mapped[str | None] = mapped_column(Text)
    error_code: Mapped[int | None] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Evidence(TenantMixin, Base):
    __tablename__ = "copilot_evidences"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "conversation_id"],
            ["copilot_conversations.tenant_id", "copilot_conversations.id"],
            ondelete="CASCADE",
            name="fk_copilot_evidences_conversation_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "message_id"],
            ["copilot_messages.tenant_id", "copilot_messages.id"],
            ondelete="CASCADE",
            name="fk_copilot_evidences_message_tenant",
        ),
        UniqueConstraint(
            "tenant_id", "message_id", "citation_id", name="uq_copilot_evidence_citation"
        ),
        Index("ix_copilot_evidences_message", "tenant_id", "message_id"),
        CheckConstraint(
            "source_type IN ('ERP', 'KNOWLEDGE', 'MCP')",
            name="ck_copilot_evidences_source",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    message_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    tool_call_id: Mapped[str] = mapped_column(String(128), nullable=False)
    source_agent: Mapped[str | None] = mapped_column(String(64))
    agent_task_id: Mapped[str | None] = mapped_column(String(96))
    citation_id: Mapped[str] = mapped_column(String(32), nullable=False)
    source_type: Mapped[str] = mapped_column(String(16), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_id: Mapped[str | None] = mapped_column(String(128))
    knowledge_base_id: Mapped[int | None] = mapped_column(BigInteger)
    document_id: Mapped[int | None] = mapped_column(BigInteger)
    chunk_id: Mapped[int | None] = mapped_column(BigInteger)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    excerpt: Mapped[str | None] = mapped_column(Text)
    source_version: Mapped[int | None] = mapped_column()
    evidence_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, server_default="{}"
    )
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )

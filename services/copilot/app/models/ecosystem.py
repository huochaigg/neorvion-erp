from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TenantMixin, TimestampMixin


class McpServer(TimestampMixin, TenantMixin, Base):
    __tablename__ = "copilot_mcp_servers"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_mcp_server_tenant"),
        UniqueConstraint("tenant_id", "server_key", name="uq_mcp_server_key"),
        Index("ix_mcp_server_status", "tenant_id", "enabled", "approval_status"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    server_key: Mapped[str] = mapped_column(String(64), nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    scope_type: Mapped[str] = mapped_column(String(16), nullable=False, server_default="TENANT")
    transport_type: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="STREAMABLE_HTTP"
    )
    endpoint: Mapped[str] = mapped_column(String(500), nullable=False)
    authentication_type: Mapped[str] = mapped_column(
        String(24), nullable=False, server_default="NONE"
    )
    credential_reference: Mapped[str | None] = mapped_column(String(128))
    allowed_tools: Mapped[list[str]] = mapped_column(JSONB, nullable=False, server_default="[]")
    denied_tools: Mapped[list[str]] = mapped_column(JSONB, nullable=False, server_default="[]")
    allowed_resources: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default="{}"
    )
    timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False, server_default="10")
    max_retries: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    concurrency_limit: Mapped[int] = mapped_column(Integer, nullable=False, server_default="2")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    approval_status: Mapped[str] = mapped_column(
        String(24), nullable=False, server_default="PENDING_APPROVAL"
    )
    health_status: Mapped[str] = mapped_column(String(24), nullable=False, server_default="UNKNOWN")
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    configuration_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    created_by: Mapped[int] = mapped_column(BigInteger, nullable=False)
    updated_by: Mapped[int] = mapped_column(BigInteger, nullable=False)


class McpToolVersion(TimestampMixin, TenantMixin, Base):
    __tablename__ = "copilot_mcp_tool_versions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "server_id"],
            ["copilot_mcp_servers.tenant_id", "copilot_mcp_servers.id"],
            ondelete="RESTRICT",
            name="fk_mcp_tool_server",
        ),
        UniqueConstraint(
            "tenant_id", "server_id", "tool_name", "schema_hash", name="uq_mcp_tool_schema"
        ),
        Index("ix_mcp_tool_active", "tenant_id", "enabled", "approval_status"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    server_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    tool_name: Mapped[str] = mapped_column(String(128), nullable=False)
    qualified_name: Mapped[str] = mapped_column(String(240), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    input_schema: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    schema_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    configuration_version: Mapped[int] = mapped_column(Integer, nullable=False)
    required_permissions: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default="[]"
    )
    resource_requirements: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default="{}"
    )
    allowed_agents: Mapped[list[str]] = mapped_column(JSONB, nullable=False, server_default="[]")
    risk_level: Mapped[str] = mapped_column(String(24), nullable=False, server_default="READ_ONLY")
    timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False, server_default="10")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    approval_status: Mapped[str] = mapped_column(
        String(24), nullable=False, server_default="PENDING_APPROVAL"
    )
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_by: Mapped[int | None] = mapped_column(BigInteger)


class Skill(TimestampMixin, TenantMixin, Base):
    __tablename__ = "copilot_skills"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_skill_tenant"),
        UniqueConstraint("tenant_id", "skill_key", name="uq_skill_key"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    skill_key: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    current_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    approval_status: Mapped[str] = mapped_column(
        String(24), nullable=False, server_default="PENDING_APPROVAL"
    )
    created_by: Mapped[int] = mapped_column(BigInteger, nullable=False)
    updated_by: Mapped[int] = mapped_column(BigInteger, nullable=False)


class SkillVersion(TenantMixin, Base):
    __tablename__ = "copilot_skill_versions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "skill_id"],
            ["copilot_skills.tenant_id", "copilot_skills.id"],
            ondelete="RESTRICT",
            name="fk_skill_version_skill",
        ),
        UniqueConstraint("tenant_id", "skill_id", "version", name="uq_skill_version"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    skill_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    instructions: Mapped[str] = mapped_column(Text, nullable=False)
    input_schema: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    output_schema: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    allowed_agents: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    required_permissions: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    allowed_tools: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    required_evidence: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    risk_level: Mapped[str] = mapped_column(String(24), nullable=False, server_default="READ_ONLY")
    timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False, server_default="30")
    token_budget: Mapped[int] = mapped_column(Integer, nullable=False, server_default="3000")
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    approval_status: Mapped[str] = mapped_column(
        String(24), nullable=False, server_default="PENDING_APPROVAL"
    )
    created_by: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class SkillRun(TimestampMixin, TenantMixin, Base):
    __tablename__ = "copilot_skill_runs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "skill_id"],
            ["copilot_skills.tenant_id", "copilot_skills.id"],
            ondelete="RESTRICT",
            name="fk_skill_run_skill",
        ),
        UniqueConstraint("tenant_id", "user_id", "idempotency_key", name="uq_skill_run_key"),
        Index("ix_skill_run_status", "tenant_id", "status", "created_at"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    skill_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    skill_version: Mapped[int] = mapped_column(Integer, nullable=False)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    conversation_id: Mapped[int | None] = mapped_column(BigInteger)
    idempotency_key: Mapped[str] = mapped_column(String(96), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, server_default="CREATED")
    input_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    output_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default="{}"
    )
    safe_error: Mapped[str | None] = mapped_column(String(255))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

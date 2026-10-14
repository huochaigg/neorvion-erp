"""操作审计。禁止写入密码、Token、原文密钥。"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.request_id import get_request_id
from app.core.tenant import TenantContext
from app.models.ops import KnowledgeAuditLog

_SECRET_KEYS = {
    "password",
    "encrypted_password",
    "token",
    "access_token",
    "refresh_token",
    "authorization",
    "api_key",
    "secret",
    "key_hash",
    "plaintext",
}


def redact(value: Any) -> Any:
    """递归脱敏敏感字段，审计日志只保留业务上下文。"""
    if isinstance(value, dict):
        cleaned = {}
        for key, item in value.items():
            if str(key).lower() in _SECRET_KEYS or "password" in str(key).lower() or "secret" in str(key).lower():
                cleaned[key] = "[redacted]"
            else:
                cleaned[key] = redact(item)
        return cleaned
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, str) and len(value) > 500:
        return value[:500]
    return value


async def write_audit(
    session: AsyncSession,
    context: TenantContext,
    *,
    action: str,
    resource_type: str,
    resource_id: int | None = None,
    detail: dict | None = None,
    ip_address: str | None = None,
) -> None:
    """写入一条审计。调用方负责随后 commit；失败不得阻断主业务时可忽略。"""
    now = datetime.now(UTC)
    session.add(
        KnowledgeAuditLog(
            tenant_id=context.tenant_id,
            actor_user_id=context.user_id,
            actor_key_id=context.api_key_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            detail=redact(detail) if detail else None,
            ip_address=ip_address,
            request_id=get_request_id(),
            created_at=now,
            updated_at=now,
        )
    )

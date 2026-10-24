from __future__ import annotations

import hashlib
import hmac
import time

from app.core.config import settings
from app.core.exceptions import AppError


def canonical_execution_claim(
    *,
    tenant_id: int,
    user_id: int,
    action_type: str,
    execution_key: str,
    proposal_revision: int,
    payload_hash: str,
    expires_at: int,
) -> str:
    return "\n".join(
        map(
            str,
            (
                tenant_id,
                user_id,
                action_type,
                execution_key,
                proposal_revision,
                payload_hash,
                expires_at,
            ),
        )
    )


def verify_execution_authorization(
    signature: str,
    expires_at_raw: str,
    *,
    tenant_id: int,
    user_id: int,
    action_type: str,
    execution_key: str,
    proposal_revision: int,
    payload_hash: str,
) -> None:
    """校验 Copilot 服务签发的短期执行授权；用户 JWT 与 ERP 权限仍独立校验。"""
    secret = settings.copilot_execution_secret.get_secret_value()
    if not secret:
        raise AppError("ERP 未配置 Copilot 执行授权", code=50382, status_code=503)
    try:
        expires_at = int(expires_at_raw)
    except (TypeError, ValueError) as exc:
        raise AppError("执行授权无效", code=40382, status_code=403) from exc
    now = int(time.time())
    if expires_at < now or expires_at > now + settings.copilot_execution_max_ttl_seconds:
        raise AppError("执行授权已过期或有效期非法", code=40383, status_code=403)
    claim = canonical_execution_claim(
        tenant_id=tenant_id,
        user_id=user_id,
        action_type=action_type,
        execution_key=execution_key,
        proposal_revision=proposal_revision,
        payload_hash=payload_hash,
        expires_at=expires_at,
    )
    expected = hmac.new(secret.encode(), claim.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        raise AppError("执行授权无效", code=40382, status_code=403)

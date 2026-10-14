"""外部检索 API Key。明文只在创建时返回一次。"""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import AppError
from app.core.permissions import PermissionCode
from app.core.tenant import TenantContext
from app.models.ops import KnowledgeApiKey
from app.repositories.ops import ApiKeyRepository
from app.schemas.ops import ApiKeyCreatedOut, ApiKeyCreateIn, ApiKeyListOut, ApiKeyOut
from app.services.audit import write_audit
from app.services.authorization import AuthorizationService

_SCOPES = {"search", "chat", "stats"}
_RATE: dict[int, list[float]] = {}


def hash_api_key(plaintext: str) -> str:
    return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()


def issue_plaintext() -> str:
    return "nk_" + secrets.token_hex(24)


class ApiKeyService:
    def __init__(self, session: AsyncSession, context: TenantContext) -> None:
        self.session = session
        self.context = context
        self.auth = AuthorizationService()
        self.keys = ApiKeyRepository(session, context.tenant_id)

    async def list_keys(self, page: int, page_size: int) -> ApiKeyListOut:
        self.auth.require_all(self.context, (PermissionCode.KNOWLEDGE_READ,))
        rows, total = await self.keys.list_page(page=page, page_size=page_size)
        return ApiKeyListOut(
            items=[self._to_out(row) for row in rows],
            total=total,
            page=page,
            page_size=page_size,
        )

    async def create_key(self, payload: ApiKeyCreateIn) -> ApiKeyCreatedOut:
        """创建 Key。返回体含 api_key 明文，只此一次。"""
        self.auth.require_all(self.context, (PermissionCode.KNOWLEDGE_UPDATE,))
        if self.context.api_key_id is not None:
            raise AppError("不能用 API Key 创建新的 Key", code=40361, status_code=403)
        scopes = [item for item in payload.scopes if item in _SCOPES] or ["search"]
        plaintext = issue_plaintext()
        row = KnowledgeApiKey(
            tenant_id=self.context.tenant_id,
            name=payload.name.strip(),
            prefix=plaintext[:10],
            key_hash=hash_api_key(plaintext),
            scopes=scopes,
            knowledge_base_ids=payload.knowledge_base_ids,
            expires_at=payload.expires_at,
            created_by=self.context.user_id,
        )
        self.session.add(row)
        await write_audit(
            self.session,
            self.context,
            action="api_key.create",
            resource_type="api_key",
            detail={"name": row.name, "scopes": scopes, "prefix": row.prefix},
        )
        await self.session.commit()
        await self.session.refresh(row)
        return ApiKeyCreatedOut(**self._to_out(row).model_dump(), api_key=plaintext)

    async def revoke_key(self, key_id: int) -> ApiKeyOut:
        self.auth.require_all(self.context, (PermissionCode.KNOWLEDGE_UPDATE,))
        row = await self.keys.get_in_tenant(key_id)
        if row is None:
            raise AppError("API Key 不存在或不可访问", code=40460, status_code=404)
        if row.revoked_at is not None:
            return self._to_out(row)
        row.revoked_at = datetime.now(UTC)
        await write_audit(
            self.session,
            self.context,
            action="api_key.revoke",
            resource_type="api_key",
            resource_id=row.id,
            detail={"prefix": row.prefix},
        )
        await self.session.commit()
        await self.session.refresh(row)
        return self._to_out(row)

    @staticmethod
    def _to_out(row: KnowledgeApiKey) -> ApiKeyOut:
        return ApiKeyOut(
            id=row.id,
            tenant_id=row.tenant_id,
            name=row.name,
            prefix=row.prefix,
            scopes=list(row.scopes or []),
            knowledge_base_ids=[int(item) for item in (row.knowledge_base_ids or [])],
            expires_at=row.expires_at,
            revoked_at=row.revoked_at,
            last_used_at=row.last_used_at,
            created_by=row.created_by,
            created_at=row.created_at,
        )


def enforce_rate_limit(key_id: int) -> None:
    """进程内简易限流。多 Worker 生产环境应换成 Redis；测试环境足够。"""
    now = datetime.now(UTC).timestamp()
    window = _RATE.setdefault(key_id, [])
    cutoff = now - 60
    alive = [item for item in window if item > cutoff]
    if len(alive) >= settings.api_key_rate_limit_per_minute:
        raise AppError("API Key 调用过于频繁", code=42910, status_code=429)
    alive.append(now)
    _RATE[key_id] = alive

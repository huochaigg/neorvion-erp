from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.actions.registry import ActionRegistry, build_action_registry
from app.core.exceptions import AppError
from app.core.tenant import TenantContext
from app.erp.client import ErpApiClient
from app.models.action_proposal import ActionProposal, ProposalRevision, ProposalValidation
from app.repositories.action_proposals import ActionProposalRepository
from app.schemas.action_proposal import (
    ActionProposalCreate,
    ActionProposalListOut,
    ActionProposalOut,
    ActionProposalUpdate,
    ProposalRevisionListOut,
    ProposalRevisionOut,
    ProposalValidationOut,
)
from app.services.authorization import AuthorizationService


class ActionProposalService:
    def __init__(
        self,
        session: AsyncSession,
        context: TenantContext,
        *,
        erp_client: ErpApiClient,
        access_token: str,
        request_id: str = "",
        registry: ActionRegistry | None = None,
    ) -> None:
        self.session = session
        self.context = context
        self.repo = ActionProposalRepository(session, context.tenant_id, context.user_id)
        self.erp_client = erp_client
        self.access_token = access_token
        self.request_id = request_id
        self.registry = registry or build_action_registry()
        self.auth = AuthorizationService()

    @staticmethod
    def _hash(value: dict[str, Any]) -> str:
        return hashlib.sha256(
            json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
        ).hexdigest()

    @staticmethod
    def _missing(payload: dict[str, Any], required_fields: tuple[str, ...]) -> list[str]:
        missing = [name for name in required_fields if payload.get(name) in (None, [], "")]
        for index, item in enumerate(payload.get("items") or []):
            if item.get("sku_id") is None:
                missing.append(f"items.{index}.sku_id")
            if item.get("quantity") is None:
                missing.append(f"items.{index}.quantity")
        return missing

    def _authorize(self, action_type: str):
        spec = self.registry.get(action_type)
        self.auth.require_all(self.context, (spec.permission,))
        return spec

    async def _out(self, row: ActionProposal) -> ActionProposalOut:
        spec = self.registry.get(row.action_type)
        validation = await self.repo.validation(row.id, row.current_revision)
        now = datetime.now(UTC)
        status = row.status
        if status not in {"CANCELLED", "EXPIRED"}:
            if row.expires_at <= now:
                status = "EXPIRED"
            elif status == "READY" and (validation is None or validation.expires_at <= now):
                status = "STALE"
        validation_out = (
            None
            if validation is None
            else ProposalValidationOut(
                status=validation.status,
                revision=validation.revision,
                errors=validation.errors,
                warnings=validation.warnings,
                missing_fields=validation.missing_fields,
                preview_data=validation.preview_data,
                resource_versions=validation.resource_versions,
                validated_at=validation.validated_at,
                expires_at=validation.expires_at,
            )
        )
        return ActionProposalOut(
            id=row.id,
            conversation_id=row.conversation_id,
            source_message_id=row.source_message_id,
            action_type=row.action_type,
            schema_version=row.schema_version,
            status=status,
            current_revision=row.current_revision,
            payload=row.payload,
            editable_fields=list(spec.editable_fields),
            validation=validation_out,
            expires_at=row.expires_at,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    async def create(self, data: ActionProposalCreate) -> ActionProposalOut:
        """以稳定幂等键创建提案；相同键的不同内容返回冲突。"""
        body = data.action.model_dump(mode="json")
        spec = self._authorize(body["action_type"])
        payload = body["payload"]
        identity = {
            "conversation_id": data.conversation_id,
            "source_message_id": data.source_message_id,
            "action_type": spec.action_type,
            "payload": payload,
        }
        payload_hash = self._hash(identity)
        existing = await self.repo.by_idempotency(data.idempotency_key)
        if existing is not None:
            if existing.payload_hash != payload_hash:
                raise AppError("幂等键已用于不同的业务草稿", code=40991, status_code=409)
            return await self._out(existing)
        if await self.repo.owned_conversation(data.conversation_id) is None:
            raise AppError("会话不存在", code=40480, status_code=404)
        if (
            data.source_message_id
            and await self.repo.owned_message(data.source_message_id, data.conversation_id) is None
        ):
            raise AppError("来源消息不存在", code=40481, status_code=404)
        missing = self._missing(payload, spec.required_fields)
        row = ActionProposal(
            tenant_id=self.context.tenant_id,
            user_id=self.context.user_id,
            conversation_id=data.conversation_id,
            source_message_id=data.source_message_id,
            action_type=spec.action_type,
            schema_version=spec.schema_version,
            status="NEEDS_INPUT" if missing else "DRAFT",
            current_revision=1,
            payload=payload,
            payload_hash=payload_hash,
            idempotency_key=data.idempotency_key,
            expires_at=datetime.now(UTC) + timedelta(days=7),
        )
        self.session.add(row)
        await self.session.flush()
        self.session.add(
            ProposalRevision(
                tenant_id=self.context.tenant_id,
                proposal_id=row.id,
                revision=1,
                payload=payload,
                editor_user_id=self.context.user_id,
            )
        )
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raced = await self.repo.by_idempotency(data.idempotency_key)
            if raced is not None and raced.payload_hash == payload_hash:
                return await self._out(raced)
            if raced is not None:
                raise AppError("幂等键已用于不同的业务草稿", code=40991, status_code=409) from exc
            raise
        await self.session.refresh(row)
        return await self._out(row)

    async def get(self, proposal_id: int) -> ActionProposalOut:
        row = await self.repo.get(proposal_id)
        if row is None:
            raise AppError("业务草稿不存在", code=40490, status_code=404)
        self._authorize(row.action_type)
        return await self._out(row)

    async def list(
        self, page: int, page_size: int, conversation_id: int | None = None
    ) -> ActionProposalListOut:
        allowed_types = tuple(
            spec.action_type
            for spec in self.registry.all()
            if self.context.has_all(spec.permission)
        )
        if not allowed_types:
            return ActionProposalListOut(items=[], total=0, page=page, page_size=page_size)
        rows, total = await self.repo.list(page, page_size, conversation_id, allowed_types)
        return ActionProposalListOut(
            items=[await self._out(row) for row in rows],
            total=total,
            page=page,
            page_size=page_size,
        )

    async def update(self, proposal_id: int, data: ActionProposalUpdate) -> ActionProposalOut:
        """短事务内锁定并检查 revision，避免两个编辑者静默覆盖。"""
        row = await self.repo.get(proposal_id, lock=True)
        if row is None:
            raise AppError("业务草稿不存在", code=40490, status_code=404)
        self._authorize(row.action_type)
        body = data.action.model_dump(mode="json")
        if body["action_type"] != row.action_type:
            raise AppError("不能修改业务草稿类型", code=40992, status_code=409)
        if row.status in {"CANCELLED", "EXPIRED"} or row.expires_at <= datetime.now(UTC):
            raise AppError("当前草稿状态不允许编辑", code=40993, status_code=409)
        if row.current_revision != data.expected_revision:
            raise AppError(
                "草稿已被更新，请刷新后重试",
                code=40994,
                status_code=409,
                data={"current_revision": row.current_revision},
            )
        payload = body["payload"]
        row.current_revision += 1
        row.payload = payload
        row.payload_hash = self._hash(
            {
                "conversation_id": row.conversation_id,
                "source_message_id": row.source_message_id,
                "action_type": row.action_type,
                "payload": payload,
            }
        )
        row.status = (
            "NEEDS_INPUT"
            if self._missing(payload, self.registry.get(row.action_type).required_fields)
            else "STALE"
        )
        self.session.add(
            ProposalRevision(
                tenant_id=self.context.tenant_id,
                proposal_id=row.id,
                revision=row.current_revision,
                payload=payload,
                editor_user_id=self.context.user_id,
            )
        )
        await self.session.commit()
        await self.session.refresh(row)
        return await self._out(row)

    async def validate(self, proposal_id: int, expected_revision: int) -> ActionProposalOut:
        """事务外调用 ERP Preview，随后用 revision 条件重新锁定并保存结果。"""
        row = await self.repo.get(proposal_id)
        if row is None:
            raise AppError("业务草稿不存在", code=40490, status_code=404)
        spec = self._authorize(row.action_type)
        if row.status in {"CANCELLED", "EXPIRED"} or row.expires_at <= datetime.now(UTC):
            raise AppError("当前草稿状态不允许预检", code=40995, status_code=409)
        if row.current_revision != expected_revision:
            raise AppError(
                "草稿版本冲突",
                code=40994,
                status_code=409,
                data={"current_revision": row.current_revision},
            )
        proposal_payload = dict(row.payload)
        missing = self._missing(proposal_payload, spec.required_fields)
        # 首次读取会自动开启事务；远程 ERP 请求前结束它，绝不跨网络调用持有连接或行锁。
        await self.session.rollback()
        if missing:
            result = {
                "valid": False,
                "blocking_errors": [],
                "warnings": [],
                "missing_fields": missing,
                "preview_summary": {},
                "resource_versions": {},
            }
            validation_status = "INVALID"
        else:
            try:
                result = await self.erp_client.preview(
                    spec.preview_path,
                    payload=proposal_payload,
                    access_token=self.access_token,
                    tenant_id=self.context.tenant_id,
                    request_id=self.request_id,
                )
                validation_status = "VALID" if result.get("valid") else "INVALID"
            except AppError as exc:
                if exc.status_code in {401, 403}:
                    raise
                result = {
                    "blocking_errors": [{"code": str(exc.code), "message": exc.message}],
                    "warnings": [],
                    "missing_fields": [],
                    "preview_summary": {},
                    "resource_versions": {},
                }
                validation_status = "UNAVAILABLE"
        locked = await self.repo.get(proposal_id, lock=True)
        if (
            locked is None
            or locked.current_revision != expected_revision
            or locked.status == "CANCELLED"
        ):
            await self.session.rollback()
            raise AppError("预检期间草稿已更新，请重新预检", code=40994, status_code=409)
        existing = await self.repo.validation(proposal_id, expected_revision)
        now = datetime.now(UTC)
        expiry_raw = result.get("expires_at")
        expiry = (
            datetime.fromisoformat(expiry_raw.replace("Z", "+00:00"))
            if isinstance(expiry_raw, str)
            else now + timedelta(minutes=5)
        )
        values = dict(
            status=validation_status,
            errors=list(result.get("blocking_errors") or []),
            warnings=list(result.get("warnings") or []),
            missing_fields=list(result.get("missing_fields") or []),
            preview_data=dict(result.get("preview_summary") or {}),
            resource_versions=dict(result.get("resource_versions") or {}),
            validated_at=now,
            expires_at=expiry,
        )
        if existing is None:
            self.session.add(
                ProposalValidation(
                    tenant_id=self.context.tenant_id,
                    proposal_id=proposal_id,
                    revision=expected_revision,
                    **values,
                )
            )
        else:
            for key, value in values.items():
                setattr(existing, key, value)
        locked.status = (
            "READY"
            if validation_status == "VALID"
            else ("NEEDS_INPUT" if values["missing_fields"] else "DRAFT")
        )
        await self.session.commit()
        await self.session.refresh(locked)
        return await self._out(locked)

    async def cancel(self, proposal_id: int, expected_revision: int) -> ActionProposalOut:
        row = await self.repo.get(proposal_id, lock=True)
        if row is None:
            raise AppError("业务草稿不存在", code=40490, status_code=404)
        self._authorize(row.action_type)
        if row.current_revision != expected_revision:
            raise AppError(
                "草稿版本冲突",
                code=40994,
                status_code=409,
                data={"current_revision": row.current_revision},
            )
        if row.status == "EXPIRED" or row.expires_at <= datetime.now(UTC):
            raise AppError("当前草稿状态不允许取消", code=40995, status_code=409)
        if row.status == "CANCELLED":
            return await self._out(row)
        row.status = "CANCELLED"
        await self.session.commit()
        await self.session.refresh(row)
        return await self._out(row)

    async def revisions(self, proposal_id: int) -> ProposalRevisionListOut:
        row = await self.repo.get(proposal_id)
        if row is None:
            raise AppError("业务草稿不存在", code=40490, status_code=404)
        self._authorize(row.action_type)
        rows = await self.repo.revisions(proposal_id)
        return ProposalRevisionListOut(
            items=[ProposalRevisionOut.model_validate(item, from_attributes=True) for item in rows]
        )

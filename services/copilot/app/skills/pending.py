from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import AppError
from app.core.tenant import TenantContext
from app.models.ecosystem import PendingSkillInvocation, Skill, SkillVersion
from app.services.skill_execution import SkillExecutionService
from app.skills.applicability import assess_skill, pending_relation
from app.skills.catalog import SkillCatalogEntry
from app.skills.inputs import SkillInputCollector

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class PendingSkillPrompt:
    answer: str
    public_data: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ResumedSkillInput:
    entry: SkillCatalogEntry
    values: dict[str, Any]
    pending: PendingSkillInvocation


@dataclass(frozen=True, slots=True)
class ResumedSkillPlan:
    entries: tuple[SkillCatalogEntry, ...]
    values: dict[str, dict[str, Any]]
    pending: PendingSkillInvocation


class PendingSkillService:
    """管理绑定 tenant/user/conversation 的参数收集状态，并固定原 SkillVersion。"""

    def __init__(self, session: AsyncSession, context: TenantContext) -> None:
        self.session = session
        self.context = context
        self.collector = SkillInputCollector()

    async def needs_order_id(self, conversation_id: int, request_id: str) -> bool:
        """只读检查当前用户会话的 Pending，避免普通订单号查询发生额外 ERP 调用。"""
        row = await self.session.scalar(select(PendingSkillInvocation).where(
            PendingSkillInvocation.tenant_id == self.context.tenant_id,
            PendingSkillInvocation.user_id == self.context.user_id,
            PendingSkillInvocation.conversation_id == conversation_id,
            PendingSkillInvocation.status == "COLLECTING_INPUT",
        ))
        return bool(row and row.last_client_request_id != request_id[:64] and "order_id" in row.missing_fields and row.expires_at > datetime.now(UTC))

    async def cancel_active(self, conversation_id: int, request_id: str) -> bool:
        """NONE/MANUAL 新任务可显式终止旧参数收集，避免把无关消息套入旧 Skill。"""
        row = await self.session.scalar(
            select(PendingSkillInvocation)
            .where(
                PendingSkillInvocation.tenant_id == self.context.tenant_id,
                PendingSkillInvocation.user_id == self.context.user_id,
                PendingSkillInvocation.conversation_id == conversation_id,
                PendingSkillInvocation.status == "COLLECTING_INPUT",
            )
            .with_for_update()
        )
        if row is None:
            return False
        row.status = "CANCELLED"
        row.last_client_request_id = request_id[:64]
        await self.session.commit()
        return True

    async def resume(
        self, conversation_id: int, task: str, request_id: str, *, verified_order_id: int | None = None
    ) -> ResumedSkillInput | ResumedSkillPlan | PendingSkillPrompt | None:
        row = await self.session.scalar(
            select(PendingSkillInvocation)
            .where(
                PendingSkillInvocation.tenant_id == self.context.tenant_id,
                PendingSkillInvocation.user_id == self.context.user_id,
                PendingSkillInvocation.conversation_id == conversation_id,
                PendingSkillInvocation.status == "COLLECTING_INPUT",
            )
            .with_for_update()
        )
        if row is None:
            return None
        if row.last_client_request_id == request_id[:64]:
            return PendingSkillPrompt(row.clarification, self._public(row, "pending") | {"relation": "DUPLICATE"})
        key = next(iter(row.selection_snapshot.get("selected_skill_keys", [])), "")
        relation = pending_relation(task, missing_fields=list(row.missing_fields), skill_key=key)
        logger.info("pending_relation request_id=%s pending_id=%s relation=%s skill=%s version_id=%s", request_id, row.id, relation, key, row.skill_version_id)
        if row.expires_at <= datetime.now(UTC):
            row.status = "EXPIRED"
            row.last_client_request_id = request_id[:64]
            await self.session.commit()
            logger.info("pending_expired request_id=%s pending_id=%s relation=%s", request_id, row.id, relation)
            if relation == "CANCEL":
                return PendingSkillPrompt("之前的参数收集已结束。", {"pending_id": row.id, "status": "EXPIRED"})
            if relation in {"SUPPLEMENT", "MODIFY", "AMBIGUOUS"}:
                return PendingSkillPrompt("之前的参数收集已过期，请说明现在要处理的任务。", {"pending_id": row.id, "status": "EXPIRED"})
            # 完整任务即使仍与旧 Skill 相关，也应当在本轮作为新请求继续选择。
            return None
        if relation == "NEW_TASK":
            row.status = "CANCELLED"
            row.last_client_request_id = request_id[:64]
            await self.session.commit()
            logger.info("pending_replaced request_id=%s pending_id=%s skill=%s version_id=%s", request_id, row.id, key, row.skill_version_id)
            return None
        if relation == "AMBIGUOUS":
            return PendingSkillPrompt("请说明是继续补充之前的参数，还是开始新的查询。", self._public(row, key) | {"relation": relation})
        if relation == "CANCEL" or self.collector.cancelled(task):
            row.status = "CANCELLED"
            row.last_client_request_id = request_id[:64]
            await self.session.commit()
            return PendingSkillPrompt("已取消本次 Skill 参数收集。", {"pending_id": row.id, "status": "CANCELLED"})
        if row.plan_snapshot.get("items"):
            return await self._resume_plan(row, task, request_id)
        pair = (
            await self.session.execute(
                select(Skill, SkillVersion)
                .join(SkillVersion, (SkillVersion.tenant_id == Skill.tenant_id) & (SkillVersion.skill_id == Skill.id))
                .where(
                    Skill.tenant_id == self.context.tenant_id,
                    Skill.id == row.skill_id,
                    SkillVersion.id == row.skill_version_id,
                    Skill.enabled.is_(True),
                    Skill.approval_status == "APPROVED",
                    SkillVersion.approval_status == "APPROVED",
                )
            )
        ).first()
        if pair is None:
            row.status = "CANCELLED"
            await self.session.commit()
            raise AppError("待补全 Skill 已停用或版本不可用", code=40987, status_code=409)
        skill, version = pair
        if not set(version.required_permissions).issubset(self.context.permission_codes):
            row.status = "CANCELLED"
            await self.session.commit()
            raise AppError("权限已变化，待补全 Skill 已取消", code=40385, status_code=403)
        applicable, reason = assess_skill(
            task, version.allowed_tools, version.source_metadata, version.allowed_agents,
            version.input_schema, skill_key=skill.skill_key if relation != "SUPPLEMENT" else None,
        )
        if not applicable:
            # Pending 的固定版本也必须先通过适用性检查，不能绕过新候选的门禁直接补参。
            row.status = "CANCELLED"
            row.last_client_request_id = request_id[:64]
            await self.session.commit()
            logger.info(
                "pending_inapplicable request_id=%s pending_id=%s skill=%s version_id=%s reason=%s",
                request_id, row.id, skill.skill_key, version.id, reason[:200],
            )
            return None
        collection_text = f"订单主键 {verified_order_id}" if verified_order_id else (f"订单主键 {task.strip()}" if "order_id" in row.missing_fields and task.strip().isdigit() else task)
        collected = self.collector.collect(collection_text, version.input_schema, row.collected_input)
        row.collected_input = SkillExecutionService._redact(collected.values)
        row.missing_fields = list(collected.missing)
        row.last_client_request_id = request_id[:64]
        if not collected.ready:
            row.clarification = collected.clarification or "请补充必填参数。"
            await self.session.commit()
            return PendingSkillPrompt(row.clarification, self._public(row, skill.skill_key))
        row.status = "READY"
        await self.session.commit()
        return ResumedSkillInput(
            SkillCatalogEntry(skill.id, version.id, skill.skill_key, skill.name, skill.description, version.version, version.source_metadata or {}),
            collected.values,
            row,
        )

    async def create_multi(
        self,
        conversation_id: int,
        entries: tuple[SkillCatalogEntry, ...],
        values: dict[str, dict[str, Any]],
        missing: dict[str, tuple[str, ...]],
        request_id: str,
        selection_snapshot: dict[str, Any],
    ) -> PendingSkillPrompt:
        first = entries[0]
        labels = [f"{key}.{field}" for key, fields in missing.items() for field in fields]
        clarification = "请补充多 Skill 计划所需参数：" + "、".join(labels) + "。"
        now = datetime.now(UTC)
        row = PendingSkillInvocation(
            tenant_id=self.context.tenant_id,
            user_id=self.context.user_id,
            conversation_id=conversation_id,
            skill_id=first.skill_id,
            skill_version_id=first.version_id,
            status="COLLECTING_INPUT",
            collected_input={},
            missing_fields=labels,
            selection_snapshot=selection_snapshot,
            plan_snapshot={
                "items": [
                    {
                        "skill_id": item.skill_id,
                        "version_id": item.version_id,
                        "skill_key": item.skill_key,
                        "name": item.name,
                        "description": item.description,
                        "version": item.version,
                        "metadata": item.metadata,
                        "input": SkillExecutionService._redact(values.get(item.skill_key, {})),
                    }
                    for item in entries
                ]
            },
            clarification=clarification,
            last_client_request_id=request_id[:64],
            expires_at=now + timedelta(seconds=settings.skill_pending_ttl_seconds),
        )
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        return PendingSkillPrompt(clarification, self._public(row, "multi-skill-plan") | {"plan_skills": [item.skill_key for item in entries]})

    async def _resume_plan(
        self, row: PendingSkillInvocation, task: str, request_id: str
    ) -> ResumedSkillPlan | PendingSkillPrompt | None:
        snapshots = row.plan_snapshot.get("items", [])
        version_ids = {int(item["version_id"]) for item in snapshots if isinstance(item, dict)}
        pairs = (
            await self.session.execute(
                select(Skill, SkillVersion)
                .join(SkillVersion, (SkillVersion.tenant_id == Skill.tenant_id) & (SkillVersion.skill_id == Skill.id))
                .where(
                    Skill.tenant_id == self.context.tenant_id,
                    SkillVersion.id.in_(version_ids),
                    Skill.enabled.is_(True),
                    Skill.approval_status == "APPROVED",
                    SkillVersion.approval_status == "APPROVED",
                )
            )
        ).all()
        by_version = {version.id: (skill, version) for skill, version in pairs}
        if set(by_version) != version_ids:
            row.status = "CANCELLED"
            await self.session.commit()
            raise AppError("待补全 Skill Plan 的版本已不可用", code=40987, status_code=409)
        entries: list[SkillCatalogEntry] = []
        values: dict[str, dict[str, Any]] = {}
        missing: dict[str, tuple[str, ...]] = {}
        updated_items: list[dict[str, Any]] = []
        for snapshot in snapshots:
            skill, version = by_version[int(snapshot["version_id"])]
            if not set(version.required_permissions).issubset(self.context.permission_codes):
                row.status = "CANCELLED"
                await self.session.commit()
                raise AppError("权限已变化，待补全 Skill Plan 已取消", code=40385, status_code=403)
            applicable, reason = assess_skill(
                task, version.allowed_tools, version.source_metadata, version.allowed_agents,
                version.input_schema,
            )
            if not applicable:
                row.status = "CANCELLED"
                row.last_client_request_id = request_id[:64]
                await self.session.commit()
                logger.info(
                    "pending_plan_inapplicable request_id=%s pending_id=%s skill=%s version_id=%s reason=%s",
                    request_id, row.id, skill.skill_key, version.id, reason[:200],
                )
                return None
            collected = self.collector.collect(task, version.input_schema, snapshot.get("input") or {})
            values[skill.skill_key] = collected.values
            if collected.missing:
                missing[skill.skill_key] = collected.missing
            updated_items.append(snapshot | {"input": SkillExecutionService._redact(collected.values)})
            entries.append(SkillCatalogEntry(skill.id, version.id, skill.skill_key, skill.name, skill.description, version.version, version.source_metadata or {}))
        row.plan_snapshot = {"items": updated_items}
        row.last_client_request_id = request_id[:64]
        row.missing_fields = [f"{key}.{field}" for key, fields in missing.items() for field in fields]
        if missing:
            row.clarification = "请继续补充：" + "、".join(row.missing_fields) + "。"
            await self.session.commit()
            return PendingSkillPrompt(row.clarification, self._public(row, "multi-skill-plan") | {"plan_skills": [item.skill_key for item in entries]})
        row.status = "READY"
        await self.session.commit()
        return ResumedSkillPlan(tuple(entries), values, row)

    async def create(
        self,
        conversation_id: int,
        entry: SkillCatalogEntry,
        values: dict[str, Any],
        missing: tuple[str, ...],
        clarification: str,
        request_id: str,
        selection_snapshot: dict[str, Any],
    ) -> PendingSkillPrompt:
        now = datetime.now(UTC)
        row = PendingSkillInvocation(
            tenant_id=self.context.tenant_id,
            user_id=self.context.user_id,
            conversation_id=conversation_id,
            skill_id=entry.skill_id,
            skill_version_id=entry.version_id,
            status="COLLECTING_INPUT",
            collected_input=SkillExecutionService._redact(values),
            missing_fields=list(missing),
            selection_snapshot=selection_snapshot,
            clarification=clarification,
            last_client_request_id=request_id[:64],
            expires_at=now + timedelta(seconds=settings.skill_pending_ttl_seconds),
        )
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        return PendingSkillPrompt(clarification, self._public(row, entry.skill_key))

    @staticmethod
    def _public(row: PendingSkillInvocation, skill_key: str) -> dict[str, Any]:
        return {
            "pending_id": row.id,
            "skill_key": skill_key,
            "status": row.status,
            "missing_fields": list(row.missing_fields),
            "expires_at": row.expires_at.isoformat(),
        }

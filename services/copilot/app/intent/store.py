"""会话级意图上下文持久化。Skill Pending 仍由 PendingSkillService 管理。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.tenant import TenantContext
from app.intent.context import context_expired
from app.intent.schemas import IntentResolution
from app.models.intent import IntentContext


class IntentContextStore:
    """tenant/user/conversation 三元组隔离；过期后不得继续补参或引用实体。"""

    def __init__(self, session: AsyncSession, context: TenantContext) -> None:
        self.session = session
        self.context = context

    async def load(self, conversation_id: int) -> IntentContext | None:
        row = await self.session.scalar(
            select(IntentContext).where(
                IntentContext.tenant_id == self.context.tenant_id,
                IntentContext.user_id == self.context.user_id,
                IntentContext.conversation_id == conversation_id,
            )
        )
        if row is None:
            return None
        if row.status == "COLLECTING" and context_expired(row.expires_at):
            row.status = "EXPIRED"
            await self.session.commit()
        return row

    async def save_resolution(
        self,
        conversation_id: int,
        resolution: IntentResolution,
        *,
        request_id: str,
        message_id: int | None = None,
        persist_pending: bool = True,
    ) -> IntentContext:
        row = await self.load(conversation_id)
        now = datetime.now(UTC)
        entities = [
            {"name": name, "value": value, "source": "current_message", "trusted": True}
            for task in resolution.tasks
            for name, value in task.slots.items()
        ]
        if row is None:
            row = IntentContext(
                tenant_id=self.context.tenant_id,
                user_id=self.context.user_id,
                conversation_id=conversation_id,
            )
            self.session.add(row)
        row.last_resolution = resolution.diagnostic_payload()
        row.last_request_id = request_id[:64]
        if entities:
            row.entities = entities[-20:]
        summaries = list(row.message_summaries or [])
        if message_id is not None:
            summaries.append(
                {"message_id": message_id, "summary": resolution.public_payload()}
            )
            row.message_summaries = summaries[-20:]
        if persist_pending and resolution.pending and resolution.resolved_intents:
            row.status = "COLLECTING"
            row.intent_key = resolution.resolved_intents[0]
            row.collected_slots = {
                name: value for task in resolution.tasks for name, value in task.slots.items()
            }
            row.missing_slots = list(resolution.missing_slots)
            row.expires_at = now + timedelta(seconds=settings.intent_pending_ttl_seconds)
        elif resolution.cancel_pending:
            row.status = "CANCELLED"
            row.intent_key = None
            row.missing_slots = []
        elif persist_pending and row.status == "COLLECTING" and not resolution.pending:
            row.status = "READY" if not resolution.missing_slots else row.status
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def cancel(self, conversation_id: int, request_id: str) -> bool:
        row = await self.load(conversation_id)
        if row is None or row.status != "COLLECTING":
            return False
        row.status = "CANCELLED"
        row.last_request_id = request_id[:64]
        await self.session.commit()
        return True

    def pending_payload(self, row: IntentContext | None) -> dict[str, Any]:
        if row is None or row.status != "COLLECTING":
            return {}
        return {
            "intent_key": row.intent_key,
            "slots": row.collected_slots,
            "missing": list(row.missing_slots or []),
        }

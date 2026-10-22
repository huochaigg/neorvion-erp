from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.core.tenant import TenantContext
from app.models.conversation import Conversation
from app.repositories.conversations import ConversationRepository
from app.schemas.conversation import (
    ConversationDetailOut,
    ConversationListOut,
    ConversationOut,
    MessageOut,
    ToolRunOut,
)


class ConversationService:
    def __init__(self, session: AsyncSession, context: TenantContext) -> None:
        self.session = session
        self.repo = ConversationRepository(session, context.tenant_id, context.user_id)

    @staticmethod
    def _out(row: Conversation) -> ConversationOut:
        return ConversationOut.model_validate(row, from_attributes=True)

    async def create(self, title: str) -> ConversationOut:
        row = await self.repo.create(title.strip())
        await self.session.commit()
        return self._out(row)

    async def list(self, page: int, page_size: int) -> ConversationListOut:
        rows, total = await self.repo.list(page, page_size)
        return ConversationListOut(items=[self._out(row) for row in rows], total=total, page=page, page_size=page_size)

    async def get(self, conversation_id: int) -> ConversationDetailOut:
        row = await self.repo.get(conversation_id)
        if row is None:
            raise AppError("会话不存在", code=40480, status_code=404)
        messages = await self.repo.messages(conversation_id)
        runs = await self.repo.tool_runs(conversation_id)
        by_message: dict[int, list[ToolRunOut]] = {}
        for run in runs:
            by_message.setdefault(run.message_id, []).append(ToolRunOut.model_validate(run, from_attributes=True))
        return ConversationDetailOut(
            **self._out(row).model_dump(),
            messages=[MessageOut(**{
                "id": item.id, "role": item.role, "content": item.content, "status": item.status,
                "request_id": item.request_id, "created_at": item.created_at, "updated_at": item.updated_at,
                "tool_runs": by_message.get(item.id, []),
            }) for item in messages],
        )

    async def rename(self, conversation_id: int, title: str) -> ConversationOut:
        row = await self.repo.get(conversation_id, lock=True)
        if row is None:
            raise AppError("会话不存在", code=40480, status_code=404)
        row.title = title.strip()
        await self.session.commit()
        return self._out(row)

    async def delete(self, conversation_id: int) -> None:
        row = await self.repo.get(conversation_id, lock=True)
        if row is None:
            raise AppError("会话不存在", code=40480, status_code=404)
        row.status = "DELETED"
        row.deleted_at = datetime.now(UTC)
        await self.session.commit()

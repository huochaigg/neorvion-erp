from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import cast

from sqlalchemy import func, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Conversation, Message, MessageStatus, ToolRun, ToolRunStatus


class ConversationRepository:
    """所有会话查询同时绑定 tenant_id 与 user_id，权限不能扩大私人会话范围。"""

    def __init__(self, session: AsyncSession, tenant_id: int, user_id: int) -> None:
        self.session = session
        self.tenant_id = tenant_id
        self.user_id = user_id

    async def create(self, title: str) -> Conversation:
        row = Conversation(tenant_id=self.tenant_id, user_id=self.user_id, title=title)
        self.session.add(row)
        await self.session.flush()
        return row

    async def get(self, conversation_id: int, *, lock: bool = False) -> Conversation | None:
        statement = select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.tenant_id == self.tenant_id,
            Conversation.user_id == self.user_id,
            Conversation.status == "ACTIVE",
            Conversation.deleted_at.is_(None),
        )
        if lock:
            # NO KEY UPDATE 仍能串行化同一会话的生成请求，同时与消息外键检查所需的
            # KEY SHARE 兼容；FOR UPDATE 会在并发等待队列中造成父子表插入互锁。
            statement = statement.with_for_update(key_share=True)
        return await self.session.scalar(statement)

    async def list(self, page: int, page_size: int) -> tuple[list[Conversation], int]:
        filters = (
            Conversation.tenant_id == self.tenant_id,
            Conversation.user_id == self.user_id,
            Conversation.status == "ACTIVE",
            Conversation.deleted_at.is_(None),
        )
        total = int(await self.session.scalar(select(func.count()).select_from(Conversation).where(*filters)) or 0)
        rows = list(
            (
                await self.session.scalars(
                    select(Conversation)
                    .where(*filters)
                    .order_by(Conversation.updated_at.desc(), Conversation.id.desc())
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                )
            ).all()
        )
        return rows, total

    async def messages(self, conversation_id: int) -> list[Message]:
        return list(
            (
                await self.session.scalars(
                    select(Message)
                    .where(
                        Message.tenant_id == self.tenant_id,
                        Message.user_id == self.user_id,
                        Message.conversation_id == conversation_id,
                    )
                    .order_by(Message.created_at, Message.id)
                )
            ).all()
        )

    async def tool_runs(self, conversation_id: int) -> list[ToolRun]:
        return list(
            (
                await self.session.scalars(
                    select(ToolRun)
                    .join(Message, (Message.id == ToolRun.message_id) & (Message.tenant_id == ToolRun.tenant_id))
                    .where(
                        ToolRun.tenant_id == self.tenant_id,
                        ToolRun.conversation_id == conversation_id,
                        Message.user_id == self.user_id,
                    )
                    .order_by(ToolRun.created_at, ToolRun.id)
                )
            ).all()
        )

    async def running_message(self, conversation_id: int) -> Message | None:
        return await self.session.scalar(
            select(Message).where(
                Message.tenant_id == self.tenant_id,
                Message.user_id == self.user_id,
                Message.conversation_id == conversation_id,
                Message.role == "assistant",
                Message.status == MessageStatus.RUNNING.value,
            )
        )

    async def find_request(self, conversation_id: int, client_request_id: str) -> Message | None:
        return await self.session.scalar(
            select(Message).where(
                Message.tenant_id == self.tenant_id,
                Message.user_id == self.user_id,
                Message.conversation_id == conversation_id,
                Message.client_request_id == client_request_id,
                Message.role == "assistant",
            )
        )

    async def begin_turn(self, conversation_id: int, content: str, client_request_id: str, request_id: str) -> tuple[Message, Message]:
        user = Message(
            tenant_id=self.tenant_id, conversation_id=conversation_id, user_id=self.user_id,
            role="user", content=content, status=MessageStatus.COMPLETED.value,
            client_request_id=client_request_id, request_id=request_id, completed_at=datetime.now(UTC),
        )
        assistant = Message(
            tenant_id=self.tenant_id, conversation_id=conversation_id, user_id=self.user_id,
            role="assistant", content="", status=MessageStatus.RUNNING.value,
            client_request_id=client_request_id, request_id=request_id,
        )
        self.session.add_all([user, assistant])
        await self.session.flush()
        return user, assistant

    async def finish_message(self, message_id: int, *, content: str, status: str, protocol_data=None, error_code=None) -> None:
        await self.session.execute(
            update(Message)
            .where(Message.id == message_id, Message.tenant_id == self.tenant_id, Message.user_id == self.user_id)
            .values(content=content, status=status, protocol_data=protocol_data, error_code=error_code, completed_at=datetime.now(UTC))
        )

    async def record_tool_event(self, conversation_id: int, message_id: int, event: str, data: dict) -> None:
        call_id = str(data.get("tool_call_id") or "")
        if event == "tool_start":
            existing = await self.session.scalar(select(ToolRun).where(ToolRun.tenant_id == self.tenant_id, ToolRun.message_id == message_id, ToolRun.tool_call_id == call_id))
            if existing is None:
                self.session.add(ToolRun(tenant_id=self.tenant_id, conversation_id=conversation_id, message_id=message_id, tool_call_id=call_id, tool_name=str(data.get("name") or ""), status=ToolRunStatus.RUNNING.value, input_summary=str(data.get("input_summary") or "")[:1000]))
            return
        values = {
            "status": ToolRunStatus.SUCCEEDED.value if event == "tool_end" else ToolRunStatus.FAILED.value,
            "duration_ms": data.get("duration_ms"),
            "output_summary": str(data.get("summary") or ("查询完成" if event == "tool_end" else data.get("message") or "调用失败"))[:1000],
            "error_code": data.get("code"),
            "completed_at": datetime.now(UTC),
        }
        await self.session.execute(update(ToolRun).where(ToolRun.tenant_id == self.tenant_id, ToolRun.message_id == message_id, ToolRun.tool_call_id == call_id).values(**values))

    async def recover_stale(self, seconds: int) -> int:
        cutoff = datetime.now(UTC) - timedelta(seconds=seconds)
        # execute 静态类型是 Result（无 rowcount）；Core UPDATE 实际返回 CursorResult。
        result = cast(
            CursorResult[tuple[()]],
            await self.session.execute(
                update(Message)
                .where(
                    Message.tenant_id == self.tenant_id,
                    Message.user_id == self.user_id,
                    Message.status == MessageStatus.RUNNING.value,
                    Message.created_at < cutoff,
                )
                .values(
                    status=MessageStatus.FAILED.value,
                    error_code=50079,
                    completed_at=datetime.now(UTC),
                )
            ),
        )
        owned_message_ids = select(Message.id).where(
            Message.tenant_id == self.tenant_id,
            Message.user_id == self.user_id,
        )
        await self.session.execute(
            update(ToolRun)
            .where(
                ToolRun.tenant_id == self.tenant_id,
                ToolRun.message_id.in_(owned_message_ids),
                ToolRun.status == ToolRunStatus.RUNNING.value,
                ToolRun.created_at < cutoff,
            )
            .values(
                status=ToolRunStatus.FAILED.value,
                error_code=50079,
                completed_at=datetime.now(UTC),
            )
        )
        return int(result.rowcount or 0)

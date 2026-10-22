from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import cast

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.types import ModelMessage
from app.core.config import settings
from app.core.exceptions import AppError
from app.core.tenant import TenantContext
from app.graph.workflow import AgentRuntime, CopilotWorkflow
from app.models.conversation import MessageStatus
from app.repositories.conversations import ConversationRepository


@dataclass(slots=True)
class PersistentTurn:
    conversation_id: int
    message_id: int
    request_id: str
    history: list[ModelMessage]
    duplicate_answer: str | None = None


class PersistentChatService:
    def __init__(self, session: AsyncSession, context: TenantContext, workflow: CopilotWorkflow) -> None:
        self.session = session
        self.repo = ConversationRepository(session, context.tenant_id, context.user_id)
        self.workflow = workflow

    async def prepare(self, conversation_id: int, content: str, client_request_id: str, request_id: str) -> PersistentTurn:
        """短事务锁定会话并建立本轮占位；模型网络调用不持有数据库事务。"""
        try:
            await self.repo.recover_stale(settings.stale_run_seconds)
            conversation = await self.repo.get(conversation_id, lock=True)
            if conversation is None:
                raise AppError("会话不存在", code=40480, status_code=404)
            duplicate = await self.repo.find_request(conversation_id, client_request_id)
            if duplicate is not None:
                await self.session.commit()
                if duplicate.status == MessageStatus.RUNNING.value:
                    raise AppError("该请求仍在运行", code=40981, status_code=409)
                if duplicate.status != MessageStatus.COMPLETED.value:
                    raise AppError("该请求已终止，请使用新的 client_request_id 重试", code=40982, status_code=409)
                return PersistentTurn(conversation_id, duplicate.id, duplicate.request_id, [], duplicate.content)
            if await self.repo.running_message(conversation_id) is not None:
                raise AppError("该会话已有生成任务", code=40980, status_code=409)
            history = self._build_history(await self.repo.messages(conversation_id))
            _, assistant = await self.repo.begin_turn(conversation_id, content, client_request_id, request_id)
            conversation.updated_at = __import__("datetime").datetime.now(__import__("datetime").UTC)
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise AppError("重复请求或并发生成冲突", code=40981, status_code=409) from exc
        except BaseException:
            # 锁定会话后的任意异常都必须结束事务，否则连接归还前会一直持有行锁，
            # 让后续详情/聊天请求表现为无期限等待；取消异常也需要走同一清理路径。
            await self.session.rollback()
            raise
        history.append({"role": "user", "content": content})
        return PersistentTurn(conversation_id, assistant.id, request_id, history)

    @staticmethod
    def _build_history(rows) -> list[ModelMessage]:
        """按完整 turn 从最近向前裁剪；用保守估算控制 Token 且不拆工具协议。"""
        turns: list[list[ModelMessage]] = []
        pending: list[ModelMessage] = []
        for row in rows:
            if row.status != MessageStatus.COMPLETED.value:
                continue
            if row.role == "user":
                if pending:
                    turns.append(pending)
                pending = [{"role": "user", "content": row.content}]
            elif pending:
                protocol = row.protocol_data
                if protocol:
                    pending.extend(cast(list[ModelMessage], protocol))
                else:
                    pending.append({"role": "assistant", "content": row.content})
        if pending:
            turns.append(pending)
        selected: list[list[ModelMessage]] = []
        used = 0
        for turn in reversed(turns):
            size = sum(max(1, (len(str(item)) + 2) // 3) for item in turn)
            if selected and used + size > settings.conversation_context_tokens:
                break
            selected.append(turn)
            used += size
        return [item for turn in reversed(selected) for item in turn]

    async def events(
        self,
        turn: PersistentTurn,
        runtime: AgentRuntime,
        disconnected: Callable[[], Awaitable[bool]],
    ) -> AsyncIterator[dict]:
        if turn.duplicate_answer is not None:
            yield {"event": "run_start", "data": self._ids(turn) | {"replayed": True}}
            yield {"event": "done", "data": self._ids(turn) | {"answer": turn.duplicate_answer, "replayed": True}}
            return
        runtime.protocol_messages = []
        runtime.disconnected = disconnected
        yield {"event": "run_start", "data": self._ids(turn)}
        completed = False
        terminal_written = False
        try:
            async for event in self.workflow.stream(turn.history, context=runtime):
                name = str(event.get("event") or "message")
                raw = event.get("data")
                data = raw if isinstance(raw, dict) else {}
                if name.startswith("tool_"):
                    await self.repo.record_tool_event(turn.conversation_id, turn.message_id, name, data)
                    await self.session.commit()
                enriched = data | self._ids(turn)
                if name == "done":
                    await self.repo.finish_message(
                        turn.message_id,
                        content=str(data.get("answer") or ""),
                        status=MessageStatus.COMPLETED.value,
                        protocol_data=runtime.protocol_messages,
                    )
                    await self.session.commit()
                    completed = True
                    terminal_written = True
                yield {"event": name, "data": enriched}
        except Exception as exc:
            code = exc.code if isinstance(exc, AppError) else 50268
            status = (
                MessageStatus.CANCELLED.value
                if isinstance(exc, AppError) and exc.code == 49900
                else MessageStatus.FAILED.value
            )
            await self.repo.finish_message(
                turn.message_id, content="", status=status, error_code=code
            )
            await self.session.commit()
            terminal_written = True
            raise
        finally:
            if not completed and not terminal_written:
                await self.repo.finish_message(turn.message_id, content="", status=MessageStatus.CANCELLED.value, error_code=49900)
                await self.session.commit()

    @staticmethod
    def _ids(turn: PersistentTurn) -> dict:
        return {"request_id": turn.request_id, "conversation_id": turn.conversation_id, "message_id": turn.message_id}

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import cast

from sqlalchemy import func, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.agent_trace import AgentRun, AgentTaskRun
from app.models.conversation import (
    Conversation,
    Evidence,
    Message,
    MessageStatus,
    ToolRun,
    ToolRunStatus,
)


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
        total = int(
            await self.session.scalar(
                select(func.count()).select_from(Conversation).where(*filters)
            )
            or 0
        )
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
                    .join(
                        Message,
                        (Message.id == ToolRun.message_id)
                        & (Message.tenant_id == ToolRun.tenant_id),
                    )
                    .where(
                        ToolRun.tenant_id == self.tenant_id,
                        ToolRun.conversation_id == conversation_id,
                        Message.user_id == self.user_id,
                    )
                    .order_by(ToolRun.created_at, ToolRun.id)
                )
            ).all()
        )

    async def evidences(self, conversation_id: int) -> list[Evidence]:
        return list(
            (
                await self.session.scalars(
                    select(Evidence)
                    .join(
                        Message,
                        (Message.id == Evidence.message_id)
                        & (Message.tenant_id == Evidence.tenant_id),
                    )
                    .where(
                        Evidence.tenant_id == self.tenant_id,
                        Evidence.conversation_id == conversation_id,
                        Message.user_id == self.user_id,
                    )
                    .order_by(Evidence.created_at, Evidence.id)
                    .limit(settings.evidence_history_limit)
                )
            ).all()
        )

    async def agent_runs(self, conversation_id: int) -> list[AgentRun]:
        return list(
            (
                await self.session.scalars(
                    select(AgentRun)
                    .where(
                        AgentRun.tenant_id == self.tenant_id,
                        AgentRun.user_id == self.user_id,
                        AgentRun.conversation_id == conversation_id,
                    )
                    .order_by(AgentRun.started_at, AgentRun.id)
                )
            ).all()
        )

    async def agent_tasks(self, run_ids: list[int]) -> list[AgentTaskRun]:
        if not run_ids:
            return []
        return list(
            (
                await self.session.scalars(
                    select(AgentTaskRun)
                    .where(
                        AgentTaskRun.tenant_id == self.tenant_id,
                        AgentTaskRun.agent_run_id.in_(run_ids),
                    )
                    .order_by(AgentTaskRun.started_at, AgentTaskRun.id)
                )
            ).all()
        )

    async def begin_agent_run(
        self, conversation_id: int, message_id: int, request_id: str
    ) -> AgentRun:
        row = AgentRun(
            tenant_id=self.tenant_id,
            user_id=self.user_id,
            conversation_id=conversation_id,
            message_id=message_id,
            request_id=request_id,
            graph_type="PENDING",
            status="RUNNING",
        )
        self.session.add(row)
        await self.session.flush()
        return row

    async def record_agent_event(self, run_id: int, event: str, data: dict) -> None:
        """按稳定 task_id 幂等记录 Agent 生命周期，不保存完整 Prompt。"""
        if event == "agent_route":
            await self.session.execute(
                update(AgentRun)
                .where(
                    AgentRun.id == run_id,
                    AgentRun.tenant_id == self.tenant_id,
                    AgentRun.user_id == self.user_id,
                )
                .values(
                    graph_type="MULTI_AGENT" if data.get("mode") == "multi" else "SINGLE_AGENT",
                    route_reason=str(data.get("reason") or "")[:255],
                )
            )
            return
        task_id = str(data.get("agent_task_id") or "")[:96]
        if not task_id:
            return
        task = await self.session.scalar(
            select(AgentTaskRun).where(
                AgentTaskRun.tenant_id == self.tenant_id,
                AgentTaskRun.agent_run_id == run_id,
                AgentTaskRun.task_id == task_id,
            )
        )
        if event == "agent_start":
            if task is None:
                self.session.add(
                    AgentTaskRun(
                        tenant_id=self.tenant_id,
                        agent_run_id=run_id,
                        agent_name=str(data.get("agent_name") or "")[:64],
                        task_id=task_id,
                        status="RUNNING",
                        input_summary="受控结构化任务",
                    )
                )
            return
        if event == "agent_progress":
            if task is not None:
                task.output_summary = str(data.get("message") or "处理中")[:1000]
            return
        if task is None:
            return
        task.status = (
            "FAILED" if event == "agent_error" else str(data.get("status") or "SUCCEEDED")[:16]
        )
        task.completed_at = datetime.now(UTC)
        task.duration_ms = data.get("duration_ms")
        task.model_calls = int(data.get("model_calls") or 0)
        task.tool_calls = int(data.get("tool_calls") or 0)
        task.evidence_count = int(data.get("evidence_count") or 0)
        task.error_code = data.get("error_code")
        task.usage = data.get("usage") if isinstance(data.get("usage"), dict) else None
        task.output_summary = "执行失败" if event == "agent_error" else "执行完成"

    async def finish_agent_run(
        self,
        run_id: int,
        *,
        status: str,
        error_code: int | None = None,
        usage: dict | None = None,
    ) -> None:
        row = await self.session.scalar(
            select(AgentRun).where(
                AgentRun.id == run_id,
                AgentRun.tenant_id == self.tenant_id,
                AgentRun.user_id == self.user_id,
            )
        )
        if row is None:
            return
        now = datetime.now(UTC)
        row.status = status
        row.completed_at = now
        row.total_duration_ms = round((now - row.started_at).total_seconds() * 1000)
        row.error_code = error_code
        row.usage = usage

    async def record_evidence(self, conversation_id: int, message_id: int, data: dict) -> None:
        """证据字段采用白名单落库，客户端和模型均不能指定租户、用户或消息归属。"""
        self.session.add(
            Evidence(
                tenant_id=self.tenant_id,
                conversation_id=conversation_id,
                message_id=message_id,
                user_id=self.user_id,
                tool_call_id=str(data.get("tool_call_id") or "")[:128],
                citation_id=str(data.get("citation_id") or "")[:32],
                source_type=str(data.get("source_type") or "")[:16],
                resource_type=str(data.get("resource_type") or "")[:64],
                resource_id=str(data["resource_id"])[:128]
                if data.get("resource_id") is not None
                else None,
                knowledge_base_id=data.get("knowledge_base_id"),
                document_id=data.get("document_id"),
                chunk_id=data.get("chunk_id"),
                title=str(data.get("title") or "来源")[:255],
                excerpt=str(data.get("excerpt") or "")[: settings.knowledge_evidence_excerpt_chars],
                source_version=data.get("source_version"),
                evidence_metadata=data.get("metadata")
                if isinstance(data.get("metadata"), dict)
                else {},
                observed_at=datetime.fromisoformat(str(data.get("observed_at"))),
                source_agent=str(data.get("source_agent") or "")[:64] or None,
                agent_task_id=str(data.get("agent_task_id") or "")[:96] or None,
            )
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

    async def begin_turn(
        self, conversation_id: int, content: str, client_request_id: str, request_id: str
    ) -> tuple[Message, Message]:
        user = Message(
            tenant_id=self.tenant_id,
            conversation_id=conversation_id,
            user_id=self.user_id,
            role="user",
            content=content,
            status=MessageStatus.COMPLETED.value,
            client_request_id=client_request_id,
            request_id=request_id,
            completed_at=datetime.now(UTC),
        )
        assistant = Message(
            tenant_id=self.tenant_id,
            conversation_id=conversation_id,
            user_id=self.user_id,
            role="assistant",
            content="",
            status=MessageStatus.RUNNING.value,
            client_request_id=client_request_id,
            request_id=request_id,
        )
        self.session.add_all([user, assistant])
        await self.session.flush()
        return user, assistant

    async def finish_message(
        self, message_id: int, *, content: str, status: str, protocol_data=None, error_code=None
    ) -> None:
        await self.session.execute(
            update(Message)
            .where(
                Message.id == message_id,
                Message.tenant_id == self.tenant_id,
                Message.user_id == self.user_id,
            )
            .values(
                content=content,
                status=status,
                protocol_data=protocol_data,
                error_code=error_code,
                completed_at=datetime.now(UTC),
            )
        )

    async def record_tool_event(
        self, conversation_id: int, message_id: int, event: str, data: dict
    ) -> None:
        call_id = str(data.get("tool_call_id") or "")
        if event == "tool_start":
            existing = await self.session.scalar(
                select(ToolRun).where(
                    ToolRun.tenant_id == self.tenant_id,
                    ToolRun.message_id == message_id,
                    ToolRun.tool_call_id == call_id,
                )
            )
            if existing is None:
                self.session.add(
                    ToolRun(
                        tenant_id=self.tenant_id,
                        conversation_id=conversation_id,
                        message_id=message_id,
                        tool_call_id=call_id,
                        tool_name=str(data.get("name") or ""),
                        agent_task_id=str(data.get("agent_task_id") or "")[:96] or None,
                        status=ToolRunStatus.RUNNING.value,
                        input_summary=str(data.get("input_summary") or "")[:1000],
                    )
                )
            return
        values = {
            "status": ToolRunStatus.SUCCEEDED.value
            if event == "tool_end"
            else ToolRunStatus.FAILED.value,
            "duration_ms": data.get("duration_ms"),
            "output_summary": str(
                data.get("summary")
                or ("查询完成" if event == "tool_end" else data.get("message") or "调用失败")
            )[:1000],
            "error_code": data.get("code"),
            "completed_at": datetime.now(UTC),
        }
        await self.session.execute(
            update(ToolRun)
            .where(
                ToolRun.tenant_id == self.tenant_id,
                ToolRun.message_id == message_id,
                ToolRun.tool_call_id == call_id,
            )
            .values(**values)
        )

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

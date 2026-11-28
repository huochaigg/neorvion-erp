from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import AppError
from app.core.tenant import TenantContext
from app.knowledge.client import KnowledgeApiClient
from app.models.conversation import Conversation, MessageStatus
from app.repositories.conversations import ConversationRepository
from app.schemas.conversation import (
    AgentRunOut,
    AgentTaskRunOut,
    ConversationDetailOut,
    ConversationListOut,
    ConversationOut,
    EvidenceOut,
    MessageOut,
    SkillRunSummaryOut,
    ToolRunOut,
)


_RETRYABLE_STATUSES = {
    MessageStatus.FAILED.value,
    MessageStatus.INTERRUPTED.value,
    MessageStatus.TIMED_OUT.value,
    MessageStatus.CANCELLED.value,
}
_WRITE_TOOL_NAMES = {"propose_action", "validate_action_proposal"}
_RETRY_BLOCKED_TOOL_STATUSES = {"SUCCEEDED", "RUNNING", "UNKNOWN"}


def _retry_denied_reason(status: str, tool_runs: list) -> str | None:
    if status not in _RETRYABLE_STATUSES:
        return None
    if any(getattr(run, "status", "") == "SUCCEEDED" for run in tool_runs):
        return "已有成功的工具结果，禁止盲目重试，以免重复执行业务操作。"
    if any(
        str(getattr(run, "tool_name", "") or "") in _WRITE_TOOL_NAMES
        and str(getattr(run, "status", "") or "") in _RETRY_BLOCKED_TOOL_STATUSES
        for run in tool_runs
    ):
        return "存在结果未知的写操作，请先核对执行状态，不能直接重试。"
    return None


def _can_retry(status: str, tool_runs: list) -> bool:
    """以后端安全策略为准：终态且无成功/未知写副作用才允许新的执行尝试。"""
    return status in _RETRYABLE_STATUSES and _retry_denied_reason(status, tool_runs) is None


def _can_reconnect(status: str) -> bool:
    return status == MessageStatus.RUNNING.value


def _can_cancel(status: str) -> bool:
    return status == MessageStatus.RUNNING.value


class ConversationService:
    def __init__(
        self,
        session: AsyncSession,
        context: TenantContext,
        *,
        knowledge_client: KnowledgeApiClient | None = None,
        access_token: str = "",
        knowledge_audience_authorized: bool = False,
        request_id: str = "",
    ) -> None:
        self.session = session
        self.repo = ConversationRepository(session, context.tenant_id, context.user_id)
        self.context = context
        self.knowledge_client = knowledge_client
        self.access_token = access_token
        self.knowledge_audience_authorized = knowledge_audience_authorized
        self.request_id = request_id

    @staticmethod
    def _out(row: Conversation) -> ConversationOut:
        return ConversationOut.model_validate(row, from_attributes=True)

    async def create(self, title: str) -> ConversationOut:
        row = await self.repo.create(title.strip())
        await self.session.commit()
        return self._out(row)

    async def list(self, page: int, page_size: int) -> ConversationListOut:
        rows, total = await self.repo.list(page, page_size)
        return ConversationListOut(
            items=[self._out(row) for row in rows], total=total, page=page, page_size=page_size
        )

    async def get(self, conversation_id: int) -> ConversationDetailOut:
        from app.services.chat_reconcile import reconcile_session
        from app.services.chat_run import hub, lease_alive

        row = await self.repo.get(conversation_id)
        if row is None:
            raise AppError("会话不存在", code=40480, status_code=404)
        await reconcile_session(self.session, self.context.tenant_id, self.context.user_id)
        messages = await self.repo.messages(conversation_id)
        runs = await self.repo.tool_runs(conversation_id)
        evidence_rows = await self.repo.evidences(conversation_id)
        agent_runs = await self.repo.agent_runs(conversation_id)
        skill_runs = await self.repo.skill_runs(conversation_id)
        from app.intent.store import IntentContextStore

        intent_by_message: dict[int, dict] = {}
        intent_row = await IntentContextStore(self.session, self.context).load(conversation_id)
        if intent_row is not None:
            for item in intent_row.message_summaries or []:
                if isinstance(item, dict) and item.get("message_id"):
                    intent_by_message[int(item["message_id"])] = item.get("summary") or {}
        agent_tasks = await self.repo.agent_tasks([item.id for item in agent_runs])
        by_message: dict[int, list[ToolRunOut]] = {}
        for run in runs:
            by_message.setdefault(run.message_id, []).append(
                ToolRunOut.model_validate(run, from_attributes=True)
            )
        evidence_by_message: dict[int, list[EvidenceOut]] = {}
        try:
            outputs = await asyncio.wait_for(
                asyncio.gather(*(self._evidence_out(item) for item in evidence_rows)),
                timeout=settings.knowledge_history_revalidation_timeout_seconds,
            )
        except TimeoutError:
            outputs = [self._evidence_out_without_knowledge(item) for item in evidence_rows]
        for evidence, output in zip(evidence_rows, outputs, strict=True):
            evidence_by_message.setdefault(evidence.message_id, []).append(output)
        tasks_by_run: dict[int, list[AgentTaskRunOut]] = {}
        for task in agent_tasks:
            tasks_by_run.setdefault(task.agent_run_id, []).append(
                AgentTaskRunOut.model_validate(task, from_attributes=True)
            )
        runs_by_message: dict[int, list[AgentRunOut]] = {}
        orm_runs_by_message: dict[int, list] = {}
        for run in agent_runs:
            orm_runs_by_message.setdefault(run.message_id, []).append(run)
            runs_by_message.setdefault(run.message_id, []).append(
                AgentRunOut(
                    id=run.id,
                    graph_type=run.graph_type,
                    status=run.status,
                    route_reason=run.route_reason,
                    total_duration_ms=run.total_duration_ms,
                    tasks=tasks_by_run.get(run.id, []),
                    event_seq=int(getattr(run, "event_seq", 0) or 0),
                    interrupt_reason=getattr(run, "interrupt_reason", None),
                )
            )
        skills_by_message: dict[int, list[SkillRunSummaryOut]] = {}
        for skill_run, skill in skill_runs:
            if skill_run.message_id is None:
                continue
            snapshot = skill_run.output_snapshot if isinstance(skill_run.output_snapshot, dict) else {}
            resources = snapshot.get("loaded_resources", [])
            skills_by_message.setdefault(skill_run.message_id, []).append(
                SkillRunSummaryOut(
                    id=skill_run.id,
                    skill_id=skill.id,
                    skill_key=skill.skill_key,
                    skill_name=skill.name,
                    skill_version=skill_run.skill_version,
                    status=skill_run.status,
                    selection_method=skill_run.selection_method,
                    selection_reason=(skill_run.selection_snapshot or {}).get("reason"),
                    plan_id=skill_run.plan_id,
                    plan_step_key=skill_run.plan_step_key,
                    loaded_resources=resources if isinstance(resources, list) else [],
                    safe_error=skill_run.safe_error,
                )
            )
        live_map: dict[int, bool] = {}
        for item in messages:
            if item.role == "assistant" and item.status == MessageStatus.RUNNING.value:
                live_map[item.id] = hub.is_live(self.context.tenant_id, item.id) or await lease_alive(
                    self.context.tenant_id, item.id
                )
        debug_execution = settings.debug_execution_enabled()
        return ConversationDetailOut(
            **self._out(row).model_dump(),
            messages=[
                MessageOut(
                    **{
                        "id": item.id,
                        "role": item.role,
                        "content": item.content,
                        "status": item.status,
                        "request_id": item.request_id,
                        "created_at": item.created_at,
                        "updated_at": item.updated_at,
                        "tool_runs": by_message.get(item.id, []),
                        "evidences": evidence_by_message.get(item.id, []),
                        "agent_runs": runs_by_message.get(item.id, []),
                        "skill_runs": skills_by_message.get(item.id, []),
                        "intent_status": intent_by_message.get(item.id),
                        "last_event_seq": max(
                            (int(getattr(run, "event_seq", 0) or 0) for run in orm_runs_by_message.get(item.id, [])),
                            default=0,
                        ),
                        "live": live_map.get(item.id, False),
                        "interrupt_reason": next(
                            (
                                getattr(run, "interrupt_reason", None)
                                for run in orm_runs_by_message.get(item.id, [])
                                if getattr(run, "interrupt_reason", None)
                            ),
                            None,
                        ),
                        "can_retry": _can_retry(item.status, by_message.get(item.id, [])),
                        "retry_denied_reason": _retry_denied_reason(
                            item.status, by_message.get(item.id, [])
                        ),
                        "can_reconnect": _can_reconnect(item.status),
                        "can_cancel": _can_cancel(item.status),
                        "debug_execution": debug_execution,
                    }
                )
                for item in messages
            ],
        )

    async def _evidence_out(self, row) -> EvidenceOut:
        """历史 Knowledge 证据展示前重新鉴权；失权或删除时不返回旧摘录。"""
        status = "ACTIVE"
        excerpt = row.excerpt
        if row.source_type == "KNOWLEDGE":
            if (
                not self.knowledge_client
                or not self.access_token
                or not self.knowledge_audience_authorized
            ):
                status, excerpt = "FORBIDDEN", None
            else:
                try:
                    current = await self.knowledge_client.get_chunk(
                        row.chunk_id,
                        access_token=self.access_token,
                        tenant_id=self.context.tenant_id,
                        request_id=self.request_id,
                    )
                except AppError as exc:
                    if exc.status_code == 404:
                        status = "MISSING"
                    elif exc.status_code == 403:
                        status = "FORBIDDEN"
                    else:
                        status = "UNAVAILABLE"
                    excerpt = None
                else:
                    if (
                        current.get("knowledge_base_id") != row.knowledge_base_id
                        or current.get("document_id") != row.document_id
                    ):
                        status, excerpt = "MISSING", None
                    elif current.get("version") != row.source_version:
                        status = "STALE"
        return EvidenceOut(
            citation_id=row.citation_id,
            source_type=row.source_type,
            resource_type=row.resource_type,
            resource_id=row.resource_id,
            knowledge_base_id=row.knowledge_base_id,
            document_id=row.document_id,
            chunk_id=row.chunk_id,
            title=row.title,
            excerpt=excerpt,
            source_version=row.source_version,
            metadata=row.evidence_metadata,
            observed_at=row.observed_at,
            access_status=status,
            source_agent=getattr(row, "source_agent", None),
            agent_task_id=getattr(row, "agent_task_id", None),
        )

    @staticmethod
    def _evidence_out_without_knowledge(row) -> EvidenceOut:
        """整批来源复核超时时采用拒绝展示策略，ERP 本地快照仍可正常返回。"""
        knowledge = row.source_type == "KNOWLEDGE"
        return EvidenceOut(
            citation_id=row.citation_id,
            source_type=row.source_type,
            resource_type=row.resource_type,
            resource_id=row.resource_id,
            knowledge_base_id=row.knowledge_base_id,
            document_id=row.document_id,
            chunk_id=row.chunk_id,
            title=row.title,
            excerpt=None if knowledge else row.excerpt,
            source_version=row.source_version,
            metadata=row.evidence_metadata,
            observed_at=row.observed_at,
            access_status="UNAVAILABLE" if knowledge else "ACTIVE",
            source_agent=getattr(row, "source_agent", None),
            agent_task_id=getattr(row, "agent_task_id", None),
        )

    async def require_message(self, conversation_id: int, message_id: int):
        row = await self.repo.get(conversation_id)
        if row is None:
            raise AppError("会话不存在", code=40480, status_code=404)
        message = await self.repo.get_owned_message(conversation_id, message_id)
        if message is None:
            raise AppError("消息不存在", code=40481, status_code=404)
        return message

    async def prepare_subscribe(self, conversation_id: int, message_id: int):
        """订阅前核对执行者；不可恢复时写入 INTERRUPTED 并返回协议内终态。"""
        from sqlalchemy import select

        from app.models.conversation import ToolRun
        from app.services.chat_reconcile import SubscribeSnapshot, settle_running_message

        message = await self.require_message(conversation_id, message_id)
        message, kind, reason = await settle_running_message(self.session, message)
        tool_runs = list(
            (
                await self.session.scalars(
                    select(ToolRun).where(
                        ToolRun.tenant_id == self.context.tenant_id,
                        ToolRun.message_id == message.id,
                    )
                )
            ).all()
        )
        return SubscribeSnapshot(
            kind=kind,
            message_id=message.id,
            request_id=message.request_id,
            status=message.status,
            content=message.content or "",
            reason=reason,
            live=kind == "live",
            can_retry=_can_retry(message.status, tool_runs),
            can_reconnect=_can_reconnect(message.status),
            can_cancel=_can_cancel(message.status),
            debug_execution=settings.debug_execution_enabled(),
        )

    async def cancel_message(self, conversation_id: int, message_id: int) -> dict:
        """用户主动取消。在线执行者收到取消信号；失活任务直接写入 CANCELLED。"""
        from sqlalchemy import select, update

        from app.models.agent_trace import AgentRun
        from app.services.chat_reconcile import interrupt_message_without_run, interrupt_run
        from app.services.chat_run import hub, lease_alive, request_cancel

        message = await self.require_message(conversation_id, message_id)
        if message.role != "assistant":
            raise AppError("只能取消助手生成任务", code=42294, status_code=422)
        if message.status != MessageStatus.RUNNING.value:
            return {"status": message.status, "cancel_requested": False, "message_id": message.id}
        alive = hub.is_live(self.context.tenant_id, message.id) or await lease_alive(
            self.context.tenant_id, message.id
        )
        await request_cancel(self.context.tenant_id, message.id)
        run = await self.session.scalar(
            select(AgentRun).where(
                AgentRun.tenant_id == self.context.tenant_id,
                AgentRun.message_id == message.id,
            )
        )
        if not alive:
            if run is not None:
                await interrupt_run(
                    self.session,
                    run,
                    reason="user_cancel",
                    status=MessageStatus.CANCELLED.value,
                    error_code=49900,
                )
            else:
                await interrupt_message_without_run(
                    self.session,
                    message,
                    reason="user_cancel",
                    status=MessageStatus.CANCELLED.value,
                    error_code=49900,
                )
            await self.session.commit()
            return {"status": "CANCELLED", "cancel_requested": True, "message_id": message.id}
        if run is not None:
            await self.session.execute(
                update(AgentRun)
                .where(AgentRun.id == run.id, AgentRun.status == "RUNNING")
                .values(interrupt_reason="cancel_requested")
            )
            await self.session.commit()
        return {"status": "CANCEL_REQUESTED", "cancel_requested": True, "message_id": message.id}

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

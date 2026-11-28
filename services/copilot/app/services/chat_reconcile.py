"""Chat Run 孤儿补偿。PostgreSQL 为权威状态，Redis 租约只证明存活。

不 Resume LangGraph 半截流式调用。原执行者丢失且无合法 Checkpoint 时标记 INTERRUPTED。
已完成的子任务不会被改写成 FAILED。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import engine, open_tenant_session
from app.models.agent_trace import AgentRun, AgentTaskRun
from app.models.conversation import Message, MessageStatus, ToolRun, ToolRunStatus
from app.services.chat_run import WORKER_INSTANCE_ID, hub, lease_alive

logger = logging.getLogger(__name__)

INTERRUPT_CODE = 50081
TIMEOUT_CODE = 50082


@dataclass(frozen=True, slots=True)
class SubscribeSnapshot:
    """订阅前的可恢复性判定。unknown 表示执行者无法确认，不得假装已结束。"""

    kind: str
    message_id: int
    request_id: str
    status: str
    content: str
    reason: str | None = None
    live: bool = False
    can_retry: bool = False
    can_reconnect: bool = False
    can_cancel: bool = False
    debug_execution: bool = False

    def event_name(self) -> str:
        return "run_status" if self.kind == "unknown" else "done"

    def to_event(self) -> dict:
        return {
            "request_id": self.request_id,
            "message_id": self.message_id,
            "answer": self.content,
            "status": self.status,
            "replayed": True,
            "reason": self.reason,
            "live": self.live,
            "can_retry": self.can_retry,
            "can_reconnect": self.can_reconnect,
            "can_cancel": self.can_cancel,
            "debug_execution": self.debug_execution,
            "subscribe_status": self.kind,
        }


async def run_is_alive(run: AgentRun) -> bool:
    """只有当前进程 Hub 或 Redis 租约能证明执行者仍在。

    历史 RUNNING 行可能缺少 worker_instance_id / heartbeat_at / lease_until，
    缺失这些字段不能当作存活，也不能因为 Debug Mode 或同进程残留而永久跳过。
    断点暂停时任务仍登记在 Hub 且 task 未 done，会被视为存活。
    """
    if getattr(run, "status", None) != "RUNNING":
        return False
    if hub.is_live(run.tenant_id, run.message_id):
        return True
    if await lease_alive(run.tenant_id, run.message_id):
        return True
    return False


async def settle_running_message(
    session: AsyncSession,
    message: Message,
) -> tuple[Message, str, str | None]:
    """核对单条助手消息。返回 (message, kind, reason)。"""
    if message.role != "assistant" or message.status != MessageStatus.RUNNING.value:
        return message, "terminal", None
    run = await session.scalar(
        select(AgentRun).where(
            AgentRun.tenant_id == message.tenant_id,
            AgentRun.message_id == message.id,
        )
    )
    if run is None:
        created = message.created_at or datetime.now(UTC)
        if created.tzinfo is None:
            created = created.replace(tzinfo=UTC)
        age = datetime.now(UTC) - created
        if age.total_seconds() < max(15, settings.chat_heartbeat_seconds * 2):
            return message, "unknown", "run_not_ready"
        await interrupt_message_without_run(session, message, reason="missing_agent_run")
        await session.commit()
        message.status = MessageStatus.INTERRUPTED.value
        message.error_code = INTERRUPT_CODE
        return message, "unavailable", "missing_agent_run"
    if await run_is_alive(run):
        return message, "live", None
    await interrupt_run(session, run, reason="worker_lost")
    await session.commit()
    message.status = MessageStatus.INTERRUPTED.value
    message.error_code = INTERRUPT_CODE
    return message, "unavailable", "worker_lost"


async def interrupt_run(
    session: AsyncSession,
    run: AgentRun,
    *,
    reason: str,
    status: str = MessageStatus.INTERRUPTED.value,
    error_code: int = INTERRUPT_CODE,
) -> bool:
    """仅当仍为 RUNNING 时写入终态，避免覆盖已完成结果。"""
    now = datetime.now(UTC)
    result = await session.execute(
        update(Message)
        .where(
            Message.id == run.message_id,
            Message.tenant_id == run.tenant_id,
            Message.status == MessageStatus.RUNNING.value,
        )
        .values(status=status, error_code=error_code, completed_at=now)
    )
    run_status = "INTERRUPTED" if status == MessageStatus.INTERRUPTED.value else status
    run_result = await session.execute(
        update(AgentRun)
        .where(AgentRun.id == run.id, AgentRun.tenant_id == run.tenant_id, AgentRun.status == "RUNNING")
        .values(
            status=run_status,
            error_code=error_code,
            interrupt_reason=reason[:64],
            completed_at=now,
            lease_until=None,
        )
    )
    if not result.rowcount and not run_result.rowcount:
        return False
    await session.execute(
        update(AgentTaskRun)
        .where(
            AgentTaskRun.tenant_id == run.tenant_id,
            AgentTaskRun.agent_run_id == run.id,
            AgentTaskRun.status == "RUNNING",
        )
        .values(status="CANCELLED", completed_at=now, error_code=error_code)
    )
    await session.execute(
        update(ToolRun)
        .where(
            ToolRun.tenant_id == run.tenant_id,
            ToolRun.message_id == run.message_id,
            ToolRun.status == ToolRunStatus.RUNNING.value,
        )
        .values(status=ToolRunStatus.CANCELLED.value, completed_at=now, error_code=error_code)
    )
    logger.info(
        "ORPHAN_RUN_RECONCILED tenant_id=%s message_id=%s agent_run_id=%s reason=%s",
        run.tenant_id,
        run.message_id,
        run.id,
        reason,
    )
    return True


async def interrupt_message_without_run(
    session: AsyncSession,
    message: Message,
    *,
    reason: str,
    status: str = MessageStatus.INTERRUPTED.value,
    error_code: int = INTERRUPT_CODE,
) -> None:
    now = datetime.now(UTC)
    await session.execute(
        update(Message)
        .where(
            Message.id == message.id,
            Message.tenant_id == message.tenant_id,
            Message.status == MessageStatus.RUNNING.value,
        )
        .values(
            status=status,
            error_code=error_code,
            completed_at=now,
        )
    )
    logger.info(
        "ORPHAN_RUN_RECONCILED tenant_id=%s message_id=%s agent_run_id=none reason=%s",
        message.tenant_id,
        message.id,
        reason,
    )


async def reconcile_session(session: AsyncSession, tenant_id: int, user_id: int | None = None) -> int:
    """核对当前租户会话中的 RUNNING 助手消息。"""
    statement = select(Message).where(
        Message.tenant_id == tenant_id,
        Message.role == "assistant",
        Message.status == MessageStatus.RUNNING.value,
    )
    if user_id is not None:
        statement = statement.where(Message.user_id == user_id)
    messages = list((await session.scalars(statement)).all())
    interrupted = 0
    for message in messages:
        run = await session.scalar(
            select(AgentRun).where(
                AgentRun.tenant_id == tenant_id,
                AgentRun.message_id == message.id,
            )
        )
        if run is None:
            age = datetime.now(UTC) - (message.created_at or datetime.now(UTC))
            if age.total_seconds() < max(15, settings.chat_heartbeat_seconds * 2):
                continue
            await interrupt_message_without_run(session, message, reason="missing_agent_run")
            interrupted += 1
            continue
        if await run_is_alive(run):
            continue
        if await interrupt_run(session, run, reason="worker_lost"):
            interrupted += 1
    if interrupted:
        await session.commit()
    return interrupted


async def scan_orphan_runs(limit: int = 100) -> list[tuple[int, int]]:
    statement = text(
        """
        SELECT tenant_id, id
        FROM copilot_agent_runs
        WHERE status = 'RUNNING'
        ORDER BY started_at ASC
        LIMIT :limit
        """
    )
    async with engine.connect() as connection:
        rows = (await connection.execute(statement, {"limit": limit})).all()
    return [(int(row.tenant_id), int(row.id)) for row in rows]


async def recover_agent_run(tenant_id: int, agent_run_id: int) -> None:
    session = open_tenant_session(tenant_id)
    try:
        run = await session.scalar(
            select(AgentRun).where(AgentRun.tenant_id == tenant_id, AgentRun.id == agent_run_id)
        )
        if run is None or run.status != "RUNNING":
            return
        if await run_is_alive(run):
            return
        logger.info(
            "ORPHAN_RUN_DETECTED tenant_id=%s message_id=%s agent_run_id=%s instance=%s current=%s",
            tenant_id,
            run.message_id,
            run.id,
            run.worker_instance_id,
            WORKER_INSTANCE_ID,
        )
        await interrupt_run(session, run, reason="worker_lost")
        await session.commit()
    finally:
        await session.close()


async def recover_running_messages_without_run(limit: int = 100) -> None:
    statement = text(
        """
        SELECT m.tenant_id, m.id
        FROM copilot_messages m
        WHERE m.role = 'assistant'
          AND m.status = 'RUNNING'
          AND m.created_at < now() - interval '60 seconds'
          AND NOT EXISTS (
            SELECT 1 FROM copilot_agent_runs r
            WHERE r.tenant_id = m.tenant_id AND r.message_id = m.id
          )
        ORDER BY m.created_at ASC
        LIMIT :limit
        """
    )
    async with engine.connect() as connection:
        rows = (await connection.execute(statement, {"limit": limit})).all()
    for tenant_id, message_id in rows:
        session = open_tenant_session(int(tenant_id))
        try:
            message = await session.scalar(
                select(Message).where(Message.tenant_id == int(tenant_id), Message.id == int(message_id))
            )
            if message is not None and message.status == MessageStatus.RUNNING.value:
                await interrupt_message_without_run(session, message, reason="missing_agent_run")
                await session.commit()
        finally:
            await session.close()


async def reconcile_all() -> None:
    try:
        for tenant_id, agent_run_id in await scan_orphan_runs():
            await recover_agent_run(tenant_id, agent_run_id)
        await recover_running_messages_without_run()
    except Exception:
        logger.exception("chat run reconciliation scan failed")

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, text

from app.core.config import settings
from app.db.session import engine, open_tenant_session
from app.erp.client import get_erp_client
from app.models.action_execution import ActionAuditEvent, ActionExecution
from app.models.workflow import WorkflowEvent, WorkflowInstance
from app.tasks.queue import pop_workflow

logger = logging.getLogger(__name__)


async def scan_recoverable_items(limit: int = 100) -> list[tuple[int, int]]:
    """从权威数据库发现失联任务；仅返回租户和任务 ID，后续仍由租户会话领取租约。"""
    statement = text(
        """
        SELECT tenant_id, id
        FROM copilot_workflow_instances
        WHERE status IN ('QUEUED', 'RUNNING', 'RECONCILING')
          AND (lease_until IS NULL OR lease_until <= now())
        ORDER BY updated_at ASC
        LIMIT :limit
        """
    )
    async with engine.connect() as connection:
        rows = (await connection.execute(statement, {"limit": limit})).all()
    return [(int(row.tenant_id), int(row.id)) for row in rows]


def _schedule_reconciliation_retry(row: WorkflowInstance, tenant_id: int) -> WorkflowEvent:
    """为 UNKNOWN 对账安排有限退避；耗尽预算后保留未知语义并转人工介入。"""
    row.run_attempts += 1
    row.lease_owner = None
    if row.run_attempts >= settings.workflow_reconcile_max_attempts:
        row.status = "NEEDS_MANUAL_INTERVENTION"
        row.lease_until = None
        event_type = "WORKFLOW_RECONCILIATION_EXHAUSTED"
        event_data = {"result": "UNKNOWN", "attempt": row.run_attempts}
    else:
        delay = min(
            300,
            max(1, settings.workflow_worker_poll_seconds) * (2 ** max(0, row.run_attempts - 1)),
        )
        row.lease_until = datetime.now(UTC) + timedelta(seconds=delay)
        event_type = "WORKFLOW_RECONCILIATION_RETRY"
        event_data = {"result": "UNKNOWN", "attempt": row.run_attempts, "retry_after": delay}
    row.heartbeat_at = datetime.now(UTC)
    return WorkflowEvent(
        tenant_id=tenant_id,
        workflow_id=row.id,
        event_type=event_type,
        event_data=event_data,
    )


async def recover_item(tenant_id: int, workflow_id: int, owner: str) -> None:
    """领取过期租约并恢复为可继续状态；没有当前用户 JWT 时绝不执行下游业务步骤。"""
    session = open_tenant_session(tenant_id)
    try:
        row = await session.scalar(
            select(WorkflowInstance)
            .where(WorkflowInstance.tenant_id == tenant_id, WorkflowInstance.id == workflow_id)
            .with_for_update()
        )
        if row is None or row.status in {
            "SUCCEEDED",
            "FAILED",
            "CANCELLED",
            "EXPIRED",
            "NEEDS_MANUAL_INTERVENTION",
        }:
            return
        now = datetime.now(UTC)
        if row.lease_until is not None and row.lease_until > now and row.lease_owner != owner:
            return
        row.lease_owner = owner
        row.lease_until = now + timedelta(seconds=settings.workflow_lease_seconds)
        row.heartbeat_at = now
        if row.status == "RECONCILING" and row.execution_id is not None:
            execution = await session.scalar(
                select(ActionExecution).where(
                    ActionExecution.tenant_id == tenant_id,
                    ActionExecution.id == row.execution_id,
                )
            )
            if execution is None:
                row.status = "NEEDS_MANUAL_INTERVENTION"
                session.add(
                    WorkflowEvent(
                        tenant_id=tenant_id,
                        workflow_id=row.id,
                        event_type="WORKFLOW_RECONCILIATION_FAILED",
                        event_data={"reason": "execution_missing"},
                    )
                )
                row.lease_owner = None
                row.lease_until = None
                await session.commit()
                return
            execution_key = execution.execution_key
            await session.commit()
            try:
                receipt = await get_erp_client().system_execution_receipt(
                    execution_key,
                    tenant_id=tenant_id,
                    request_id=f"workflow-reconcile-{workflow_id}",
                )
            except Exception:
                row = await session.scalar(
                    select(WorkflowInstance)
                    .where(
                        WorkflowInstance.tenant_id == tenant_id, WorkflowInstance.id == workflow_id
                    )
                    .with_for_update()
                )
                if row is not None:
                    session.add(_schedule_reconciliation_retry(row, tenant_id))
                    await session.commit()
                return
            row = await session.scalar(
                select(WorkflowInstance)
                .where(WorkflowInstance.tenant_id == tenant_id, WorkflowInstance.id == workflow_id)
                .with_for_update()
            )
            execution = (
                await session.scalar(
                    select(ActionExecution)
                    .where(
                        ActionExecution.tenant_id == tenant_id,
                        ActionExecution.id == row.execution_id,
                    )
                    .with_for_update()
                )
                if row is not None
                else None
            )
            if (
                row is not None
                and execution is not None
                and receipt
                and receipt.get("status") == "SUCCEEDED"
            ):
                execution.status = "SUCCEEDED"
                execution.erp_resource_type = receipt.get("resource_type")
                execution.erp_resource_id = receipt.get("resource_id")
                execution.erp_resource_no = receipt.get("resource_no")
                execution.completed_at = datetime.now(UTC)
                execution.error_code = None
                row.status = "SUCCEEDED"
                row.current_step = "finalize"
                row.completed_at = datetime.now(UTC)
                row.result_summary = {
                    **row.result_summary,
                    "erp": {
                        "resource_type": execution.erp_resource_type,
                        "resource_id": execution.erp_resource_id,
                        "resource_no": execution.erp_resource_no,
                    },
                }
                session.add(
                    ActionAuditEvent(
                        tenant_id=tenant_id,
                        actor_user_id=None,
                        proposal_id=execution.proposal_id,
                        execution_id=execution.id,
                        event_type="RECONCILIATION_RESULT",
                        outcome="SUCCEEDED",
                        details={"source": "workflow_worker"},
                    )
                )
                session.add(
                    WorkflowEvent(
                        tenant_id=tenant_id,
                        workflow_id=row.id,
                        event_type="WORKFLOW_RECONCILED",
                        event_data={"execution_id": execution.id},
                    )
                )
            elif row is not None:
                session.add(_schedule_reconciliation_retry(row, tenant_id))
            if row is not None:
                row.lease_owner = None
                if row.status != "RECONCILING":
                    row.lease_until = None
            await session.commit()
            return
        if row.status in {"RUNNING", "QUEUED"}:
            row.status = "PAUSED"
            session.add(
                WorkflowEvent(
                    tenant_id=tenant_id,
                    workflow_id=row.id,
                    event_type="WORKFLOW_RECOVERED",
                    event_data={"reason": "worker_restart", "authorization_required": True},
                )
            )
        row.lease_owner = None
        row.lease_until = None
        await session.commit()
    finally:
        await session.close()


async def main() -> None:
    owner = f"copilot-workflow:{os.getpid()}:{uuid.uuid4().hex[:8]}"
    logger.info("copilot workflow worker started")
    while True:
        item = await pop_workflow(settings.workflow_worker_poll_seconds)
        if item is None:
            try:
                recoverable = await scan_recoverable_items()
                for tenant_id, workflow_id in recoverable:
                    await recover_item(tenant_id, workflow_id, owner)
            except Exception:
                logger.exception("workflow database recovery scan failed")
            await asyncio.sleep(max(1, settings.workflow_worker_poll_seconds))
            continue
        try:
            await recover_item(*item, owner)
        except Exception:
            logger.exception("workflow recovery failed tenant_id=%s workflow_id=%s", *item)


if __name__ == "__main__":
    asyncio.run(main())

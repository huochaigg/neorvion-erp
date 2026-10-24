from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import AppError
from app.core.permissions import PermissionCode
from app.core.tenant import TenantContext
from app.erp.client import ErpApiClient
from app.executions.registry import ExecutionRegistry, build_execution_registry
from app.graph.action_execution import action_execution_graph
from app.models.action_execution import (
    ActionApproval,
    ActionAuditEvent,
    ActionExecution,
    ActionExecutionAttempt,
    ActionGraphCheckpoint,
)
from app.models.action_proposal import ActionProposal, ProposalValidation
from app.schemas.action_execution import (
    ActionApprovalListOut,
    ActionApprovalOut,
    ActionAuditEventOut,
    ActionAuditListOut,
    ActionExecutionListOut,
    ActionExecutionOut,
    ConfirmationCreate,
    ConfirmationTicketOut,
)
from app.services.authorization import AuthorizationService


class ActionExecutionService:
    def __init__(
        self,
        session: AsyncSession,
        context: TenantContext,
        *,
        erp_client: ErpApiClient,
        access_token: str,
        request_id: str = "",
        registry: ExecutionRegistry | None = None,
    ) -> None:
        self.session = session
        self.context = context
        self.erp = erp_client
        self.access_token = access_token
        self.request_id = request_id
        self.registry = registry or build_execution_registry()
        self.auth = AuthorizationService()

    @staticmethod
    def _nonce_hash(value: str) -> str:
        return hashlib.sha256(value.encode()).hexdigest()

    @staticmethod
    def _execution_out(row: ActionExecution) -> ActionExecutionOut:
        return ActionExecutionOut.model_validate(row, from_attributes=True)

    @staticmethod
    def _approval_out(row: ActionApproval) -> ActionApprovalOut:
        return ActionApprovalOut.model_validate(row, from_attributes=True)

    def _audit(
        self,
        row: ActionExecution,
        event: str,
        outcome: str,
        details: dict | None = None,
        actor_user_id: int | None = None,
    ) -> None:
        safe = {
            key: value
            for key, value in (details or {}).items()
            if key not in {"token", "nonce", "payload"}
        }
        self.session.add(
            ActionAuditEvent(
                tenant_id=self.context.tenant_id,
                actor_user_id=self.context.user_id if actor_user_id is None else actor_user_id,
                proposal_id=row.proposal_id,
                execution_id=row.id,
                event_type=event,
                outcome=outcome,
                details=safe,
            )
        )

    async def _owned(self, execution_id: int, *, lock: bool = False) -> ActionExecution:
        statement = select(ActionExecution).where(
            ActionExecution.id == execution_id,
            ActionExecution.tenant_id == self.context.tenant_id,
            ActionExecution.user_id == self.context.user_id,
        )
        if lock:
            statement = statement.with_for_update()
        row = await self.session.scalar(statement)
        if row is None:
            raise AppError("执行记录不存在", code=40484, status_code=404)
        return row

    async def create_confirmation(
        self, proposal_id: int, data: ConfirmationCreate
    ) -> ConfirmationTicketOut:
        """锁定 READY Proposal，冻结 payload，并签发只返回一次明文的短期确认票据。"""
        existing = await self.session.scalar(
            select(ActionExecution).where(
                ActionExecution.tenant_id == self.context.tenant_id,
                ActionExecution.user_id == self.context.user_id,
                ActionExecution.client_request_id == data.client_request_id,
            )
        )
        if existing is not None:
            raise AppError(
                "该确认请求已创建，请读取现有执行记录",
                code=40984,
                status_code=409,
                data={"execution_id": existing.id},
            )
        proposal = await self.session.scalar(
            select(ActionProposal)
            .where(
                ActionProposal.id == proposal_id,
                ActionProposal.tenant_id == self.context.tenant_id,
                ActionProposal.user_id == self.context.user_id,
                ActionProposal.deleted_at.is_(None),
            )
            .with_for_update()
        )
        if proposal is None:
            raise AppError("业务草稿不存在", code=40490, status_code=404)
        spec = self.registry.get(proposal.action_type)
        self.auth.require_all(self.context, (spec.permission,))
        now = datetime.now(UTC)
        validation = await self.session.scalar(
            select(ProposalValidation).where(
                ProposalValidation.tenant_id == self.context.tenant_id,
                ProposalValidation.proposal_id == proposal.id,
                ProposalValidation.revision == data.expected_revision,
            )
        )
        if proposal.current_revision != data.expected_revision:
            raise AppError("草稿版本冲突", code=40994, status_code=409)
        if (
            proposal.status != "READY"
            or proposal.expires_at <= now
            or validation is None
            or validation.status != "VALID"
            or validation.expires_at <= now
        ):
            raise AppError("草稿预检无效或已过期，请重新预检", code=40985, status_code=409)
        nonce = secrets.token_urlsafe(32)
        row = ActionExecution(
            tenant_id=self.context.tenant_id,
            user_id=self.context.user_id,
            proposal_id=proposal.id,
            proposal_revision=proposal.current_revision,
            action_type=proposal.action_type,
            execution_key=f"cpx_{uuid.uuid4().hex}",
            client_request_id=data.client_request_id,
            payload_hash=proposal.payload_hash,
            payload=dict(proposal.payload),
            status="PENDING_CONFIRMATION",
            risk_level=spec.risk_level,
            confirmation_nonce_hash=self._nonce_hash(nonce),
            confirmation_expires_at=now + timedelta(seconds=settings.confirmation_ttl_seconds),
        )
        self.session.add(row)
        try:
            await self.session.flush()
            self.session.add(
                ActionGraphCheckpoint(
                    tenant_id=self.context.tenant_id,
                    execution_id=row.id,
                    thread_id=f"action-execution:{row.id}",
                    node="request_confirmation",
                    state={
                        "execution_id": row.id,
                        "proposal_revision": row.proposal_revision,
                        "status": row.status,
                    },
                    updated_at=now,
                )
            )
            self._audit(
                row,
                "CONFIRMATION_REQUESTED",
                "SUCCESS",
                {"revision": row.proposal_revision, "risk_level": row.risk_level},
            )
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise AppError("该草稿版本已有执行流程", code=40986, status_code=409) from exc
        if settings.action_graph_enabled:
            await action_execution_graph.begin(
                {
                    "execution_id": row.id,
                    "tenant_id": row.tenant_id,
                    "user_id": row.user_id,
                    "proposal_revision": row.proposal_revision,
                    "requires_approval": spec.requires_approval,
                    "phase": "request_confirmation",
                }
            )
        return ConfirmationTicketOut(
            execution_id=row.id,
            confirmation_nonce=nonce,
            expires_at=row.confirmation_expires_at,
            requires_approval=spec.requires_approval,
            risk_level=spec.risk_level,
            proposal_revision=row.proposal_revision,
            payload_hash=row.payload_hash,
        )

    async def confirm(
        self, execution_id: int, expected_revision: int, nonce: str
    ) -> ActionExecutionOut:
        row = await self._owned(execution_id, lock=True)
        spec = self.registry.get(row.action_type)
        self.auth.require_all(self.context, (spec.permission,))
        now = datetime.now(UTC)
        if row.status != "PENDING_CONFIRMATION" or row.confirmed_at is not None:
            raise AppError("确认票据已使用或执行状态已变化", code=40987, status_code=409)
        if row.confirmation_expires_at <= now:
            row.status = "EXPIRED"
            self._audit(row, "CONFIRMATION_EXPIRED", "DENIED")
            await self.session.commit()
            raise AppError("确认票据已过期", code=40988, status_code=409)
        if expected_revision != row.proposal_revision or not hmac.compare_digest(
            self._nonce_hash(nonce), row.confirmation_nonce_hash
        ):
            raise AppError("确认票据与草稿版本不匹配", code=40384, status_code=403)
        proposal = await self.session.scalar(
            select(ActionProposal)
            .where(
                ActionProposal.id == row.proposal_id,
                ActionProposal.tenant_id == row.tenant_id,
                ActionProposal.user_id == row.user_id,
            )
            .with_for_update()
        )
        if (
            proposal is None
            or proposal.current_revision != row.proposal_revision
            or proposal.payload_hash != row.payload_hash
        ):
            raise AppError("草稿已变化，旧确认失效", code=40989, status_code=409)
        row.confirmed_at = now
        if spec.requires_approval:
            approval = ActionApproval(
                tenant_id=row.tenant_id,
                proposal_id=row.proposal_id,
                proposal_revision=row.proposal_revision,
                execution_id=row.id,
                applicant_user_id=row.user_id,
                status="PENDING",
                requested_at=now,
                expires_at=now + timedelta(seconds=settings.approval_ttl_seconds),
            )
            self.session.add(approval)
            await self.session.flush()
            row.approval_id = approval.id
            row.status = "WAITING_APPROVAL"
            self._audit(row, "CONFIRMATION_SUBMITTED", "WAITING_APPROVAL")
            await self._checkpoint(row, "wait_approval")
            await self.session.commit()
            if settings.action_graph_enabled:
                await action_execution_graph.resume(
                    row.id,
                    {
                        "confirmed": True,
                        "execution_id": row.id,
                        "tenant_id": row.tenant_id,
                        "user_id": row.user_id,
                        "proposal_revision": row.proposal_revision,
                    },
                )
            return self._execution_out(row)
        row.status = "APPROVED"
        self._audit(row, "CONFIRMATION_SUBMITTED", "APPROVED")
        await self._checkpoint(row, "final_revalidation")
        await self.session.commit()
        if settings.action_graph_enabled:
            await action_execution_graph.resume(
                row.id,
                {
                    "confirmed": True,
                    "execution_id": row.id,
                    "tenant_id": row.tenant_id,
                    "user_id": row.user_id,
                    "proposal_revision": row.proposal_revision,
                },
            )
        return await self.execute(execution_id, expected_revision)

    async def _checkpoint(self, row: ActionExecution, node: str) -> None:
        checkpoint = await self.session.scalar(
            select(ActionGraphCheckpoint)
            .where(
                ActionGraphCheckpoint.tenant_id == row.tenant_id,
                ActionGraphCheckpoint.execution_id == row.id,
            )
            .with_for_update()
        )
        if checkpoint is not None:
            checkpoint.node = node
            checkpoint.state = {
                "execution_id": row.id,
                "proposal_revision": row.proposal_revision,
                "status": row.status,
            }
            checkpoint.updated_at = datetime.now(UTC)

    async def execute(self, execution_id: int, expected_revision: int) -> ActionExecutionOut:
        """执行前重新预检；远程写入前提交本地状态，未知结果只能通过 Receipt 对账。"""
        row = await self._owned(execution_id, lock=True)
        spec = self.registry.get(row.action_type)
        self.auth.require_all(self.context, (spec.permission,))
        if row.proposal_revision != expected_revision:
            raise AppError("执行版本冲突", code=40994, status_code=409)
        if row.status == "SUCCEEDED":
            return self._execution_out(row)
        if row.status != "APPROVED":
            raise AppError("当前状态不允许执行", code=40990, status_code=409)
        proposal = await self.session.scalar(
            select(ActionProposal).where(
                ActionProposal.id == row.proposal_id,
                ActionProposal.tenant_id == row.tenant_id,
                ActionProposal.user_id == row.user_id,
            )
        )
        if (
            proposal is None
            or proposal.current_revision != row.proposal_revision
            or proposal.payload_hash != row.payload_hash
        ):
            raise AppError("草稿已变化，禁止执行旧版本", code=40989, status_code=409)
        payload = dict(row.payload)
        await self.session.rollback()
        preview = await self.erp.preview(
            spec.execute_path.replace("action-executions", "action-previews"),
            payload=payload,
            access_token=self.access_token,
            tenant_id=self.context.tenant_id,
            request_id=self.request_id,
        )
        if not preview.get("valid"):
            locked = await self._owned(execution_id, lock=True)
            locked.status = "FAILED"
            locked.error_code = "FINAL_REVALIDATION_FAILED"
            self._audit(
                locked,
                "FINAL_REVALIDATION",
                "FAILED",
                {"errors": preview.get("blocking_errors", [])},
            )
            await self._checkpoint(locked, "failed")
            await self.session.commit()
            return self._execution_out(locked)
        locked = await self._owned(execution_id, lock=True)
        if locked.status != "APPROVED":
            raise AppError("执行状态已变化", code=40990, status_code=409)
        locked.status = "EXECUTING"
        locked.started_at = datetime.now(UTC)
        locked.error_code = None
        attempt_no = (
            int(
                await self.session.scalar(
                    select(func.count())
                    .select_from(ActionExecutionAttempt)
                    .where(
                        ActionExecutionAttempt.tenant_id == locked.tenant_id,
                        ActionExecutionAttempt.execution_id == locked.id,
                    )
                )
                or 0
            )
            + 1
        )
        attempt = ActionExecutionAttempt(
            tenant_id=locked.tenant_id,
            execution_id=locked.id,
            attempt_no=attempt_no,
            started_at=datetime.now(UTC),
            outcome="EXECUTING",
            erp_request_id=self.request_id or None,
        )
        self.session.add(attempt)
        self._audit(locked, "ERP_EXECUTION_STARTED", "EXECUTING")
        await self._checkpoint(locked, "execute_erp")
        await self.session.commit()
        try:
            receipt = await self.erp.execute(
                spec.execute_path,
                execution_key=locked.execution_key,
                action_type=locked.action_type,
                revision=locked.proposal_revision,
                payload_hash=locked.payload_hash,
                payload=payload,
                user_id=locked.user_id,
                access_token=self.access_token,
                tenant_id=locked.tenant_id,
                request_id=self.request_id,
            )
        except AppError as exc:
            current = await self._owned(execution_id, lock=True)
            db_attempt = await self.session.scalar(
                select(ActionExecutionAttempt).where(
                    ActionExecutionAttempt.id == attempt.id,
                    ActionExecutionAttempt.tenant_id == current.tenant_id,
                )
            )
            unknown = exc.status_code >= 500
            current.status = "UNKNOWN" if unknown else "FAILED"
            current.error_code = str(exc.code)
            if db_attempt:
                db_attempt.outcome = current.status
                db_attempt.error_code = str(exc.code)
                db_attempt.completed_at = datetime.now(UTC)
            self._audit(
                current, "ERP_EXECUTION_RESULT", current.status, {"error_code": str(exc.code)}
            )
            await self._checkpoint(current, "reconcile" if unknown else "failed")
            await self.session.commit()
            return self._execution_out(current)
        current = await self._owned(execution_id, lock=True)
        current.status = "SUCCEEDED"
        current.erp_resource_type = receipt.get("resource_type")
        current.erp_resource_id = receipt.get("resource_id")
        current.erp_resource_no = receipt.get("resource_no")
        current.completed_at = datetime.now(UTC)
        db_attempt = await self.session.scalar(
            select(ActionExecutionAttempt).where(
                ActionExecutionAttempt.id == attempt.id,
                ActionExecutionAttempt.tenant_id == current.tenant_id,
            )
        )
        if db_attempt:
            db_attempt.outcome = "SUCCEEDED"
            db_attempt.completed_at = datetime.now(UTC)
        self._audit(
            current,
            "ERP_EXECUTION_RESULT",
            "SUCCEEDED",
            {
                "resource_type": current.erp_resource_type,
                "resource_id": current.erp_resource_id,
                "resource_no": current.erp_resource_no,
            },
        )
        await self._checkpoint(current, "end")
        await self.session.commit()
        return self._execution_out(current)

    async def decide(
        self, approval_id: int, *, approve: bool, reason: str | None
    ) -> ActionExecutionOut:
        self.auth.require_all(self.context, (PermissionCode.COPILOT_APPROVE,))
        approval = await self.session.scalar(
            select(ActionApproval)
            .where(
                ActionApproval.id == approval_id, ActionApproval.tenant_id == self.context.tenant_id
            )
            .with_for_update()
        )
        if approval is None:
            raise AppError("审批任务不存在", code=40485, status_code=404)
        execution = await self.session.scalar(
            select(ActionExecution)
            .where(
                ActionExecution.id == approval.execution_id,
                ActionExecution.tenant_id == approval.tenant_id,
            )
            .with_for_update()
        )
        if (
            execution is None
            or approval.status != "PENDING"
            or execution.status != "WAITING_APPROVAL"
        ):
            raise AppError("审批状态已变化", code=40992, status_code=409)
        now = datetime.now(UTC)
        if approval.expires_at <= now:
            approval.status = "EXPIRED"
            execution.status = "EXPIRED"
            self._audit(execution, "APPROVAL_EXPIRED", "EXPIRED")
            await self.session.commit()
            raise AppError("审批已过期", code=40993, status_code=409)
        if approval.applicant_user_id == self.context.user_id:
            raise AppError("申请人不能审批自己的执行", code=40385, status_code=403)
        proposal = await self.session.scalar(
            select(ActionProposal).where(
                ActionProposal.id == execution.proposal_id,
                ActionProposal.tenant_id == execution.tenant_id,
            )
        )
        if (
            proposal is None
            or proposal.current_revision != execution.proposal_revision
            or proposal.payload_hash != execution.payload_hash
        ):
            approval.status = "REVOKED"
            execution.status = "CANCELLED"
            self._audit(execution, "APPROVAL_REVOKED", "STALE_REVISION")
            await self.session.commit()
            raise AppError("草稿已更新，旧版本审批已撤销", code=40989, status_code=409)
        approval.approver_user_id = self.context.user_id
        approval.decided_at = now
        approval.decision_reason = reason
        approval.decision = "APPROVE" if approve else "REJECT"
        approval.status = "APPROVED" if approve else "REJECTED"
        execution.status = "APPROVED" if approve else "REJECTED"
        self._audit(execution, "APPROVAL_DECIDED", approval.status, {"approval_id": approval.id})
        await self._checkpoint(execution, "final_revalidation" if approve else "end")
        await self.session.commit()
        if settings.action_graph_enabled:
            await action_execution_graph.resume(
                execution.id,
                {
                    "approved": approve,
                    "execution_id": execution.id,
                    "tenant_id": execution.tenant_id,
                    "approver_user_id": self.context.user_id,
                    "proposal_revision": execution.proposal_revision,
                },
            )
        return self._execution_out(execution)

    async def revoke(self, approval_id: int) -> ActionExecutionOut:
        """仅申请人可在待审批阶段撤销；撤销后旧确认不能再次使用。"""
        approval = await self.session.scalar(
            select(ActionApproval)
            .where(
                ActionApproval.id == approval_id,
                ActionApproval.tenant_id == self.context.tenant_id,
                ActionApproval.applicant_user_id == self.context.user_id,
            )
            .with_for_update()
        )
        if approval is None:
            raise AppError("审批任务不存在", code=40485, status_code=404)
        execution = await self._owned(approval.execution_id, lock=True)
        if approval.status != "PENDING" or execution.status != "WAITING_APPROVAL":
            raise AppError("当前审批状态不允许撤销", code=40992, status_code=409)
        approval.status = "REVOKED"
        approval.decision = "REVOKE"
        approval.approver_user_id = self.context.user_id
        approval.decided_at = datetime.now(UTC)
        execution.status = "CANCELLED"
        self._audit(execution, "APPROVAL_REVOKED", "CANCELLED")
        await self._checkpoint(execution, "end")
        await self.session.commit()
        if settings.action_graph_enabled:
            await action_execution_graph.resume(
                execution.id,
                {
                    "approved": False,
                    "execution_id": execution.id,
                    "tenant_id": execution.tenant_id,
                    "proposal_revision": execution.proposal_revision,
                },
            )
        return self._execution_out(execution)

    async def reconcile(self, execution_id: int) -> ActionExecutionOut:
        row = await self._owned(execution_id, lock=True)
        spec = self.registry.get(row.action_type)
        self.auth.require_all(self.context, (spec.permission,))
        if row.status not in {"UNKNOWN", "RECONCILING", "EXECUTING"}:
            return self._execution_out(row)
        row.status = "RECONCILING"
        self._audit(row, "RECONCILIATION_STARTED", "RECONCILING")
        await self.session.commit()
        try:
            receipt = await self.erp.execution_receipt(
                row.execution_key,
                access_token=self.access_token,
                tenant_id=row.tenant_id,
                request_id=self.request_id,
            )
        except AppError:
            current = await self._owned(execution_id, lock=True)
            current.status = "UNKNOWN"
            self._audit(current, "RECONCILIATION_RESULT", "UNKNOWN")
            await self.session.commit()
            return self._execution_out(current)
        current = await self._owned(execution_id, lock=True)
        if receipt and receipt.get("status") == "SUCCEEDED":
            current.status = "SUCCEEDED"
            current.erp_resource_type = receipt.get("resource_type")
            current.erp_resource_id = receipt.get("resource_id")
            current.erp_resource_no = receipt.get("resource_no")
            current.completed_at = datetime.now(UTC)
            current.error_code = None
            self._audit(
                current,
                "RECONCILIATION_RESULT",
                "SUCCEEDED",
                {"resource_id": current.erp_resource_id},
            )
            await self._checkpoint(current, "end")
        else:
            current.status = "UNKNOWN"
            self._audit(current, "RECONCILIATION_RESULT", "UNKNOWN")
        await self.session.commit()
        return self._execution_out(current)

    async def get(self, execution_id: int) -> ActionExecutionOut:
        return self._execution_out(await self._owned(execution_id))

    async def list(self, page: int, page_size: int) -> ActionExecutionListOut:
        filters = (
            ActionExecution.tenant_id == self.context.tenant_id,
            ActionExecution.user_id == self.context.user_id,
        )
        total = int(
            await self.session.scalar(
                select(func.count()).select_from(ActionExecution).where(*filters)
            )
            or 0
        )
        rows = list(
            (
                await self.session.scalars(
                    select(ActionExecution)
                    .where(*filters)
                    .order_by(ActionExecution.created_at.desc())
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                )
            ).all()
        )
        return ActionExecutionListOut(
            items=[self._execution_out(x) for x in rows],
            total=total,
            page=page,
            page_size=page_size,
        )

    async def approvals(self, page: int, page_size: int) -> ActionApprovalListOut:
        self.auth.require_all(self.context, (PermissionCode.COPILOT_APPROVE,))
        filters = (ActionApproval.tenant_id == self.context.tenant_id,)
        total = int(
            await self.session.scalar(
                select(func.count()).select_from(ActionApproval).where(*filters)
            )
            or 0
        )
        rows = list(
            (
                await self.session.scalars(
                    select(ActionApproval)
                    .where(*filters)
                    .order_by(ActionApproval.requested_at.desc())
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                )
            ).all()
        )
        return ActionApprovalListOut(
            items=[self._approval_out(x) for x in rows], total=total, page=page, page_size=page_size
        )

    async def audit(self, execution_id: int) -> ActionAuditListOut:
        await self._owned(execution_id)
        rows = list(
            (
                await self.session.scalars(
                    select(ActionAuditEvent)
                    .where(
                        ActionAuditEvent.tenant_id == self.context.tenant_id,
                        ActionAuditEvent.execution_id == execution_id,
                    )
                    .order_by(ActionAuditEvent.created_at)
                )
            ).all()
        )
        return ActionAuditListOut(
            items=[ActionAuditEventOut.model_validate(x, from_attributes=True) for x in rows]
        )

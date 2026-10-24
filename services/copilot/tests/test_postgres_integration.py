from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime, timedelta
from time import monotonic

import pytest
from app.core.config import settings
from app.core.exceptions import AppError
from app.core.tenant import TenantContext
from app.db.base import Base
from app.db.isolation import REGISTRY
from app.graph.action_execution import ActionExecutionGraph
from app.graph.business_workflow import BusinessWorkflowGraph
from app.models.conversation import MessageStatus
from app.models.workflow import WorkflowInstance
from app.repositories.action_proposals import ActionProposalRepository
from app.repositories.conversations import ConversationRepository
from app.schemas.action_execution import ConfirmationCreate
from app.schemas.action_proposal import ActionProposalCreate, ActionProposalUpdate
from app.schemas.workflow import WorkflowCreate
from app.services.action_executions import ActionExecutionService
from app.services.action_proposals import ActionProposalService
from app.services.conversations import ConversationService
from app.services.persistent_chat import PersistentChatService, PersistentTurn
from app.services.workflows import WorkflowService
from app.tasks.worker import recover_item
from neorvion_db import TenantAsyncSession
from sqlalchemy import select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import TimeoutError as SqlAlchemyTimeoutError
from sqlalchemy.ext.asyncio import create_async_engine


class _WorkflowErp:
    async def get(self, path: str, **_kwargs):
        assert path == "/api/v1/sales-orders/71"
        return {"id": 71, "status": "WAITING_OUTBOUND", "items": []}


class _WorkflowKnowledge:
    pass


@pytest.mark.asyncio
async def test_workflow_idempotency_persistence_and_owner_isolation() -> None:
    engine = create_async_engine(_integration_url())
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
            await connection.run_sync(Base.metadata.create_all)
        context = TenantContext(
            user_id=7201,
            tenant_id=702,
            member_id=1,
            is_owner=False,
            role="OPERATOR",
            role_codes=("OPERATOR",),
            permission_codes=frozenset({"copilot:use", "order:read", "inventory:read"}),
            token_jti="workflow",
            token_version=0,
            authz_version=1,
        )
        session = TenantAsyncSession(
            702, registry=REGISTRY, bind=engine, expire_on_commit=False, autoflush=False
        )
        try:
            service = WorkflowService(
                session,
                context,
                access_token="token",
                request_id="wf-test",
                erp=_WorkflowErp(),
                knowledge=_WorkflowKnowledge(),
                audiences=(settings.erp_jwt_audience,),
            )
            payload = WorkflowCreate(
                workflow_type="SALES_ORDER_REVIEW_WORKFLOW",
                idempotency_key="workflow-order-71",
                input={"order_id": 71},
            )
            first = await service.create(payload)
            second = await service.create(payload)
            assert first.id == second.id
            assert first.status == "SUCCEEDED"
            detail = await service.detail(first.id)
            assert detail.result_summary["conclusion"] == "UNABLE_TO_DETERMINE"
            assert any(item.event_type == "WORKFLOW_SUCCEEDED" for item in detail.events)
        finally:
            await session.close()
        foreign_context = TenantContext(
            user_id=7202,
            tenant_id=702,
            member_id=2,
            is_owner=False,
            role="OPERATOR",
            role_codes=("OPERATOR",),
            permission_codes=context.permission_codes,
            token_jti="foreign",
            token_version=0,
            authz_version=1,
        )
        foreign = TenantAsyncSession(
            702, registry=REGISTRY, bind=engine, expire_on_commit=False, autoflush=False
        )
        try:
            with pytest.raises(AppError, match="不存在"):
                await WorkflowService(
                    foreign,
                    foreign_context,
                    access_token="token",
                    request_id="wf-foreign",
                    erp=_WorkflowErp(),
                    knowledge=_WorkflowKnowledge(),
                    audiences=(settings.erp_jwt_audience,),
                ).detail(first.id)
        finally:
            await foreign.close()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_workflow_worker_reclaims_stale_without_reusing_user_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_async_engine(_integration_url())
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
            await connection.run_sync(Base.metadata.create_all)
        session = TenantAsyncSession(
            703, registry=REGISTRY, bind=engine, expire_on_commit=False, autoflush=False
        )
        try:
            row = WorkflowInstance(
                tenant_id=703,
                user_id=7301,
                workflow_type="SALES_ORDER_REVIEW_WORKFLOW",
                schema_version=1,
                status="RUNNING",
                current_step="order_lookup",
                graph_thread_id="business-workflow:stale-test",
                idempotency_key="stale-worker-test",
                input_snapshot={"order_id": 1},
                result_summary={},
                lease_owner="dead",
                lease_until=datetime.now(UTC) - timedelta(seconds=1),
            )
            session.add(row)
            await session.commit()
            workflow_id = row.id
        finally:
            await session.close()
        monkeypatch.setattr(
            "app.tasks.worker.open_tenant_session",
            lambda tenant_id: TenantAsyncSession(
                tenant_id, registry=REGISTRY, bind=engine, expire_on_commit=False, autoflush=False
            ),
        )
        await recover_item(703, workflow_id, "worker-new")
        verify = TenantAsyncSession(
            703, registry=REGISTRY, bind=engine, expire_on_commit=False, autoflush=False
        )
        try:
            restored = await verify.scalar(
                select(WorkflowInstance).where(
                    WorkflowInstance.id == workflow_id, WorkflowInstance.tenant_id == 703
                )
            )
            assert restored is not None and restored.status == "PAUSED"
            assert restored.lease_owner is None
        finally:
            await verify.close()
    finally:
        await engine.dispose()


class _ExecutionErp:
    def __init__(self) -> None:
        self.execute_calls = 0

    async def preview(self, _path: str, **_kwargs):
        return {
            "valid": True,
            "blocking_errors": [],
            "warnings": [],
            "missing_fields": [],
            "preview_summary": {},
            "resource_versions": {},
            "expires_at": (datetime.now(UTC) + timedelta(minutes=5)).isoformat(),
        }

    async def execute(self, path: str, **_kwargs):
        self.execute_calls += 1
        transfer = path.endswith("inventory-transfer")
        return {
            "status": "SUCCEEDED",
            "resource_type": "STOCK_TRANSFER" if transfer else "PURCHASE_ORDER",
            "resource_id": 8802 if transfer else 8801,
            "resource_no": "TR8802" if transfer else "PO8801",
        }

    async def execution_receipt(self, _key: str, **_kwargs):
        return {
            "status": "SUCCEEDED",
            "resource_type": "PURCHASE_ORDER",
            "resource_id": 8801,
            "resource_no": "PO8801",
        }


def _integration_url() -> str:
    url = os.getenv("COPILOT_TEST_DATABASE_URL", "").strip()
    if not url:
        pytest.skip("未配置 COPILOT_TEST_DATABASE_URL，跳过真实 PostgreSQL 集成测试")
    database = make_url(url).database or ""
    if not database.endswith("_test"):
        pytest.fail("COPILOT_TEST_DATABASE_URL 必须指向名称以 _test 结尾的专用测试数据库")
    return url


@pytest.mark.asyncio
async def test_postgres_owner_and_tenant_isolation() -> None:
    """在专用测试库验证 CRUD、ToolRun、幂等、并发及租户/用户隔离。"""
    engine = create_async_engine(_integration_url())
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
            await connection.run_sync(Base.metadata.create_all)

        owner = TenantAsyncSession(
            101, registry=REGISTRY, bind=engine, expire_on_commit=False, autoflush=False
        )
        try:
            context = TenantContext(
                user_id=1001,
                tenant_id=101,
                member_id=5001,
                is_owner=False,
                role="OPERATOR",
                role_codes=("OPERATOR",),
                permission_codes=frozenset({"copilot:use"}),
                token_jti="integration",
                token_version=0,
                authz_version=1,
            )
            service = ConversationService(owner, context)
            created = await service.create("隔离测试")
            assert (await service.list(1, 20)).total == 1
            renamed = await service.rename(created.id, "已重命名")
            assert renamed.title == "已重命名"
            repo = ConversationRepository(owner, tenant_id=101, user_id=1001)
            conversation = await repo.get(created.id)
            assert conversation is not None
            conversation_id = created.id
            _, assistant = await repo.begin_turn(
                conversation_id, "查询库存", "integration-request", "integration-run"
            )
            await owner.commit()
            await repo.record_tool_event(
                conversation_id,
                assistant.id,
                "tool_start",
                {
                    "tool_call_id": "tool-1",
                    "name": "get_inventory",
                    "input_summary": "sku=SKU-001",
                },
            )
            await repo.record_evidence(
                conversation_id,
                assistant.id,
                {
                    "tool_call_id": "tool-1",
                    "citation_id": "E1",
                    "source_type": "ERP",
                    "resource_type": "get_inventory",
                    "resource_id": "SKU-001",
                    "title": "ERP 库存查询",
                    "excerpt": "SKU-001 可用库存 7",
                    "metadata": {},
                    "observed_at": datetime.now(UTC).isoformat(),
                },
            )
            await owner.commit()
            await repo.record_tool_event(
                conversation_id,
                assistant.id,
                "tool_end",
                {"tool_call_id": "tool-1", "duration_ms": 12, "summary": "库存 7"},
            )
            await repo.finish_message(
                assistant.id,
                content="库存为 7",
                status=MessageStatus.COMPLETED.value,
                protocol_data=[{"role": "assistant", "content": "库存为 7"}],
            )
            conversation.updated_at = datetime.now(UTC)
            await owner.commit()
            detail = await service.get(conversation_id)
            assert [item.role for item in detail.messages] == ["user", "assistant"]
            assert detail.messages[-1].tool_runs[0].status == "SUCCEEDED"
            assert detail.messages[-1].evidences[0].citation_id == "E1"
            assert detail.messages[-1].evidences[0].excerpt == "SKU-001 可用库存 7"
        finally:
            await owner.close()

        same_tenant_other_user = TenantAsyncSession(
            101, registry=REGISTRY, bind=engine, expire_on_commit=False
        )
        try:
            assert (
                await ConversationRepository(
                    same_tenant_other_user, tenant_id=101, user_id=1002
                ).get(conversation_id)
                is None
            )
        finally:
            await same_tenant_other_user.close()

        other_tenant = TenantAsyncSession(
            202, registry=REGISTRY, bind=engine, expire_on_commit=False
        )
        try:
            assert (
                await ConversationRepository(other_tenant, tenant_id=202, user_id=1001).get(
                    conversation_id
                )
                is None
            )
        finally:
            await other_tenant.close()

        first_session = TenantAsyncSession(
            101, registry=REGISTRY, bind=engine, expire_on_commit=False, autoflush=False
        )
        second_session = TenantAsyncSession(
            101, registry=REGISTRY, bind=engine, expire_on_commit=False, autoflush=False
        )
        try:
            first = PersistentChatService(first_session, context, None)  # type: ignore[arg-type]
            second = PersistentChatService(second_session, context, None)  # type: ignore[arg-type]
            results = await asyncio.gather(
                first.prepare(conversation_id, "并发一", "concurrent-one", "run-one"),
                second.prepare(conversation_id, "并发二", "concurrent-two", "run-two"),
                return_exceptions=True,
            )
            turns = [item for item in results if isinstance(item, PersistentTurn)]
            conflicts = [item for item in results if isinstance(item, AppError)]
            assert len(turns) == 1, repr(results)
            assert len(conflicts) == 1
            assert conflicts[0].code == 40980

            winner = first if results[0] is turns[0] else second
            winner_session = first_session if winner is first else second_session
            with pytest.raises(AppError) as duplicate:
                await winner.prepare(
                    conversation_id,
                    "重复",
                    "concurrent-one" if results[0] is turns[0] else "concurrent-two",
                    "ignored-run",
                )
            assert duplicate.value.code == 40981
            await winner.repo.finish_message(
                turns[0].message_id,
                content="并发完成",
                status=MessageStatus.COMPLETED.value,
                protocol_data=[{"role": "assistant", "content": "并发完成"}],
            )
            await winner_session.commit()
            replay = await winner.prepare(
                conversation_id,
                "重复",
                "concurrent-one" if results[0] is turns[0] else "concurrent-two",
                "ignored-run",
            )
            assert replay.duplicate_answer == "并发完成"
        finally:
            await first_session.close()
            await second_session.close()

        delete_session = TenantAsyncSession(
            101, registry=REGISTRY, bind=engine, expire_on_commit=False, autoflush=False
        )
        try:
            service = ConversationService(delete_session, context)
            await service.delete(conversation_id)
            with pytest.raises(AppError) as missing:
                await service.get(conversation_id)
            assert missing.value.status_code == 404
        finally:
            await delete_session.close()
    finally:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
            # 专用测试库保留 Alembic 版本表；重建 ORM 表，避免版本号与物理表不一致。
            await connection.run_sync(Base.metadata.create_all)
        await engine.dispose()


@pytest.mark.asyncio
async def test_postgres_pool_exhaustion_fails_within_configured_timeout() -> None:
    engine = create_async_engine(
        _integration_url(),
        pool_size=1,
        max_overflow=0,
        pool_timeout=0.2,
    )
    try:
        async with engine.connect() as held:
            await held.execute(text("SELECT 1"))
            started = monotonic()
            with pytest.raises(SqlAlchemyTimeoutError):
                async with engine.connect():
                    pass
            assert monotonic() - started < 1.0
    finally:
        await engine.dispose()


class _PreviewClient:
    async def preview(self, _path: str, **_kwargs) -> dict:
        now = datetime.now(UTC)
        return {
            "valid": True,
            "blocking_errors": [],
            "warnings": [],
            "missing_fields": [],
            "preview_summary": {"total_quantity": 10},
            "resource_versions": {"supplier": {"id": 3, "status": "ACTIVE"}},
            "validated_at": now.isoformat(),
            "expires_at": (now + timedelta(minutes=5)).isoformat(),
        }


@pytest.mark.asyncio
async def test_postgres_action_proposal_idempotency_revision_and_isolation() -> None:
    engine = create_async_engine(_integration_url())
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
            await connection.run_sync(Base.metadata.create_all)
        context = TenantContext(
            user_id=1001,
            tenant_id=101,
            member_id=5001,
            is_owner=False,
            role="OPERATOR",
            role_codes=("OPERATOR",),
            permission_codes=frozenset({"copilot:use", "purchase:create"}),
            token_jti="proposal-integration",
            token_version=0,
            authz_version=1,
        )
        session = TenantAsyncSession(101, registry=REGISTRY, bind=engine, expire_on_commit=False)
        try:
            conversation = await ConversationService(session, context).create("草稿测试")
            service = ActionProposalService(
                session,
                context,
                erp_client=_PreviewClient(),  # type: ignore[arg-type]
                access_token="test-token",
            )
            create = ActionProposalCreate.model_validate(
                {
                    "conversation_id": conversation.id,
                    "idempotency_key": "proposal-idempotency-1",
                    "action": {
                        "action_type": "PURCHASE_ORDER_CREATE",
                        "payload": {"items": [{"sku_id": 8, "quantity": 10}]},
                    },
                }
            )
            proposal = await service.create(create)
            assert proposal.status == "NEEDS_INPUT"
            assert (await service.create(create)).id == proposal.id
            conflicting = create.model_copy(deep=True)
            conflicting.action.payload.items[0].quantity = 11  # type: ignore[union-attr]
            with pytest.raises(AppError) as idempotency_conflict:
                await service.create(conflicting)
            assert idempotency_conflict.value.code == 40991

            update = ActionProposalUpdate.model_validate(
                {
                    "expected_revision": 1,
                    "action": {
                        "action_type": "PURCHASE_ORDER_CREATE",
                        "payload": {
                            "supplier_id": 3,
                            "warehouse_id": 2,
                            "items": [{"sku_id": 8, "quantity": 10}],
                        },
                    },
                }
            )
            proposal = await service.update(proposal.id, update)
            assert proposal.current_revision == 2
            with pytest.raises(AppError) as revision_conflict:
                await service.update(proposal.id, update)
            assert revision_conflict.value.code == 40994
            proposal = await service.validate(proposal.id, 2)
            assert proposal.status == "READY"
            assert proposal.validation and proposal.validation.status == "VALID"
            revisions = await service.revisions(proposal.id)
            assert [item.revision for item in revisions.items] == [2, 1]
            cancelled = await service.cancel(proposal.id, 2)
            assert cancelled.status == "CANCELLED"
            with pytest.raises(AppError):
                await service.validate(proposal.id, 2)
        finally:
            await session.close()

        other_user = TenantAsyncSession(101, registry=REGISTRY, bind=engine, expire_on_commit=False)
        try:
            assert await ActionProposalRepository(other_user, 101, 1002).get(proposal.id) is None
        finally:
            await other_user.close()
        other_tenant = TenantAsyncSession(
            202, registry=REGISTRY, bind=engine, expire_on_commit=False
        )
        try:
            assert await ActionProposalRepository(other_tenant, 202, 1001).get(proposal.id) is None
        finally:
            await other_tenant.close()
    finally:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
            await connection.run_sync(Base.metadata.create_all)
        await engine.dispose()


@pytest.mark.asyncio
async def test_postgres_confirmation_execution_audit_and_nonce_replay() -> None:
    """真实 PostgreSQL 验证确认票据、单 revision 唯一执行、审计与最终结果持久化。"""
    engine = create_async_engine(_integration_url())
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
            await connection.run_sync(Base.metadata.create_all)
        session = TenantAsyncSession(
            301, registry=REGISTRY, bind=engine, expire_on_commit=False, autoflush=False
        )
        context = TenantContext(
            user_id=3001,
            tenant_id=301,
            member_id=9301,
            is_owner=False,
            role="OPERATOR",
            role_codes=("OPERATOR",),
            permission_codes=frozenset({"copilot:use", "purchase:create"}),
            token_jti="v6",
            token_version=0,
            authz_version=1,
        )
        erp = _ExecutionErp()
        try:
            conversation = await ConversationService(session, context).create("V6")
            proposal_service = ActionProposalService(
                session,
                context,
                erp_client=erp,
                access_token="not-persisted",
                request_id="v6-request",
            )
            proposal = await proposal_service.create(
                ActionProposalCreate.model_validate(
                    {
                        "conversation_id": conversation.id,
                        "idempotency_key": "v6-proposal-001",
                        "action": {
                            "action_type": "PURCHASE_ORDER_CREATE",
                            "payload": {
                                "supplier_id": 1,
                                "warehouse_id": 2,
                                "items": [{"sku_id": 3, "quantity": 4}],
                            },
                        },
                    }
                )
            )
            ready = await proposal_service.validate(proposal.id, proposal.current_revision)
            service = ActionExecutionService(
                session,
                context,
                erp_client=erp,
                access_token="not-persisted",
                request_id="v6-request",
            )
            ticket = await service.create_confirmation(
                ready.id,
                ConfirmationCreate(
                    expected_revision=ready.current_revision, client_request_id="v6-confirm-001"
                ),
            )
            completed = await service.confirm(
                ticket.execution_id, ticket.proposal_revision, ticket.confirmation_nonce
            )
            assert completed.status == "SUCCEEDED"
            assert completed.erp_resource_id == 8801
            assert erp.execute_calls == 1
            with pytest.raises(AppError, match="已使用"):
                await service.confirm(
                    ticket.execution_id, ticket.proposal_revision, ticket.confirmation_nonce
                )
            assert (await service.audit(ticket.execution_id)).items[-1].outcome == "SUCCEEDED"
            with pytest.raises(AppError, match="已有执行流程"):
                await service.create_confirmation(
                    ready.id,
                    ConfirmationCreate(
                        expected_revision=ready.current_revision, client_request_id="v6-confirm-002"
                    ),
                )
        finally:
            await session.close()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_langgraph_postgres_checkpoint_survives_restart(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """官方 PostgresSaver 保存 interrupt，关闭并重建 Graph 后仍可 Command(resume)。"""
    monkeypatch.setattr(settings, "database_url", _integration_url())
    first = ActionExecutionGraph()
    await first.start()
    try:
        await first.begin(
            {
                "execution_id": 99001,
                "tenant_id": 301,
                "user_id": 3001,
                "proposal_revision": 1,
                "requires_approval": True,
                "phase": "request_confirmation",
            }
        )
    finally:
        await first.close()
    restarted = ActionExecutionGraph()
    await restarted.start()
    try:
        await restarted.resume(
            99001,
            {
                "confirmed": True,
                "execution_id": 99001,
                "tenant_id": 301,
                "user_id": 3001,
                "proposal_revision": 1,
            },
        )
        await restarted.resume(
            99001,
            {
                "approved": True,
                "execution_id": 99001,
                "tenant_id": 301,
                "approver_user_id": 3002,
                "proposal_revision": 1,
            },
        )
    finally:
        await restarted.close()


@pytest.mark.asyncio
async def test_business_workflow_checkpoint_survives_restart(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """V7 业务图在进程重建后从同一稳定 thread_id 恢复 interrupt。"""
    monkeypatch.setattr(settings, "database_url", _integration_url())
    workflow_id = 99101
    first = BusinessWorkflowGraph()
    await asyncio.wait_for(first.start(), timeout=10)
    try:
        await asyncio.wait_for(
            first.begin(
                {
                    "workflow_id": workflow_id,
                    "tenant_id": 302,
                    "user_id": 3002,
                    "workflow_type": "INVENTORY_REPLENISHMENT_WORKFLOW",
                    "phase": "created",
                }
            ),
            timeout=10,
        )
    finally:
        await asyncio.wait_for(first.close(), timeout=10)

    restarted = BusinessWorkflowGraph()
    await asyncio.wait_for(restarted.start(), timeout=10)
    try:
        await asyncio.wait_for(
            restarted.resume(
                workflow_id,
                {
                    "supplier_id": 11,
                    "warehouse_id": 22,
                    "quantity": "10",
                },
            ),
            timeout=10,
        )
    finally:
        await asyncio.wait_for(restarted.close(), timeout=10)


@pytest.mark.asyncio
async def test_high_risk_transfer_requires_separate_approver() -> None:
    engine = create_async_engine(_integration_url())
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
            await connection.run_sync(Base.metadata.create_all)
        applicant_context = TenantContext(
            user_id=4101,
            tenant_id=401,
            member_id=9411,
            is_owner=False,
            role="OPERATOR",
            role_codes=("OPERATOR",),
            permission_codes=frozenset({"copilot:use", "stock_transfer:create"}),
            token_jti="applicant",
            token_version=0,
            authz_version=1,
        )
        applicant = TenantAsyncSession(
            401, registry=REGISTRY, bind=engine, expire_on_commit=False, autoflush=False
        )
        erp = _ExecutionErp()
        try:
            conversation = await ConversationService(applicant, applicant_context).create("审批")
            proposals = ActionProposalService(
                applicant, applicant_context, erp_client=erp, access_token="applicant-token"
            )
            proposal = await proposals.create(
                ActionProposalCreate.model_validate(
                    {
                        "conversation_id": conversation.id,
                        "idempotency_key": "transfer-proposal-1",
                        "action": {
                            "action_type": "INVENTORY_TRANSFER_CREATE",
                            "payload": {
                                "source_warehouse_id": 1,
                                "target_warehouse_id": 2,
                                "items": [{"sku_id": 3, "quantity": 2}],
                            },
                        },
                    }
                )
            )
            ready = await proposals.validate(proposal.id, 1)
            service = ActionExecutionService(
                applicant, applicant_context, erp_client=erp, access_token="applicant-token"
            )
            ticket = await service.create_confirmation(
                ready.id,
                ConfirmationCreate(expected_revision=1, client_request_id="transfer-confirm-1"),
            )
            waiting = await service.confirm(ticket.execution_id, 1, ticket.confirmation_nonce)
            assert waiting.status == "WAITING_APPROVAL"
            assert erp.execute_calls == 0
        finally:
            await applicant.close()

        approver_context = TenantContext(
            user_id=4102,
            tenant_id=401,
            member_id=9412,
            is_owner=False,
            role="ADMIN",
            role_codes=("ADMIN",),
            permission_codes=frozenset({"copilot:use", "copilot:approve"}),
            token_jti="approver",
            token_version=0,
            authz_version=1,
        )
        approver = TenantAsyncSession(
            401, registry=REGISTRY, bind=engine, expire_on_commit=False, autoflush=False
        )
        try:
            approved = await ActionExecutionService(
                approver, approver_context, erp_client=erp, access_token="approver-token"
            ).decide(waiting.approval_id, approve=True, reason="业务复核通过")
            assert approved.status == "APPROVED"
            assert erp.execute_calls == 0
        finally:
            await approver.close()

        resumed = TenantAsyncSession(
            401, registry=REGISTRY, bind=engine, expire_on_commit=False, autoflush=False
        )
        try:
            completed = await ActionExecutionService(
                resumed, applicant_context, erp_client=erp, access_token="applicant-token"
            ).execute(waiting.id, 1)
            assert completed.status == "SUCCEEDED"
            assert completed.erp_resource_type == "STOCK_TRANSFER"
            assert erp.execute_calls == 1
        finally:
            await resumed.close()
    finally:
        await engine.dispose()

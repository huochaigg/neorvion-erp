from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime
from time import monotonic

import pytest
from app.core.exceptions import AppError
from app.core.tenant import TenantContext
from app.db.base import Base
from app.db.isolation import REGISTRY
from app.models.conversation import MessageStatus
from app.repositories.conversations import ConversationRepository
from app.services.conversations import ConversationService
from app.services.persistent_chat import PersistentChatService, PersistentTurn
from neorvion_db import TenantAsyncSession
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import TimeoutError as SqlAlchemyTimeoutError
from sqlalchemy.ext.asyncio import create_async_engine


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
                await ConversationRepository(
                    other_tenant, tenant_id=202, user_id=1001
                ).get(conversation_id)
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

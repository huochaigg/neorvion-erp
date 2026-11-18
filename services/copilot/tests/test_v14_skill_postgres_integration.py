from __future__ import annotations

import os
from datetime import UTC, datetime

import pytest
from app.core.config import settings
from app.core.exceptions import AppError
from app.core.tenant import TenantContext
from app.db.base import Base
from app.db.isolation import REGISTRY
from app.schemas.ecosystem import SkillRunIn
from app.services.ecosystem import EcosystemService
from app.services.skill_execution import SkillExecutionService
from neorvion_db import TenantAsyncSession
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine


def _integration_url() -> str:
    url = os.getenv("COPILOT_TEST_DATABASE_URL", "").strip()
    if not url:
        pytest.skip("未配置 COPILOT_TEST_DATABASE_URL，跳过 Skill 真实 PostgreSQL 集成测试")
    if not (make_url(url).database or "").endswith("_test"):
        pytest.fail("COPILOT_TEST_DATABASE_URL 必须指向名称以 _test 结尾的专用测试数据库")
    return url


def _context(tenant_id: int, user_id: int, permissions: set[str]) -> TenantContext:
    return TenantContext(
        user_id=user_id,
        tenant_id=tenant_id,
        member_id=user_id + 1000,
        is_owner=False,
        role="OPERATOR",
        role_codes=("OPERATOR",),
        permission_codes=frozenset(permissions),
        token_jti=f"v14-{tenant_id}-{user_id}",
        token_version=1,
        authz_version=1,
    )


class _Workflow:
    async def invoke(self, _messages, *, context):
        context.model_calls = 1
        context.tools.evidences.append(
            {
                "citation_id": "E1",
                "source_type": "ERP",
                "tool_call_id": "tool-1",
                "resource_type": "get_sales_order",
                "resource_id": "71",
                "title": "ERP 查询：get_sales_order",
                "observed_at": datetime.now(UTC).isoformat(),
            }
        )
        context.tools.tool_events.append(
            {"tool_call_id": "tool-1", "name": "get_sales_order", "status": "SUCCEEDED"}
        )
        return '{"summary":"订单已读取 [E1]","issues":[],"evidence_refs":["E1"]}', {
            "prompt_tokens": 20,
            "completion_tokens": 10,
        }


@pytest.mark.asyncio
async def test_skill_template_import_run_idempotency_and_tenant_isolation_in_postgres(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_async_engine(_integration_url())
    monkeypatch.setattr(settings, "quota_enforcement_enabled", False)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
            await connection.run_sync(Base.metadata.create_all)
        permissions = {
            "copilot:skill:read",
            "copilot:skill:run",
            "copilot:skill:manage",
            "order:read",
        }
        context = _context(1401, 1411, permissions)
        session = TenantAsyncSession(
            1401, registry=REGISTRY, bind=engine, expire_on_commit=False, autoflush=False
        )
        try:
            ecosystem = EcosystemService(session, context, "v14-import")
            first = await ecosystem.import_skill_templates(["sales-order-review"])
            second = await ecosystem.import_skill_templates(["sales-order-review"])
            assert first[0].status == "IMPORTED"
            assert second[0].status == "UNCHANGED"
            assert first[0].version == second[0].version == 1

            skill_id = first[0].skill_id
            await ecosystem.review_skill(skill_id, True)
            with pytest.raises(AppError):
                await SkillExecutionService(
                    session,
                    context,
                    _Workflow(),  # type: ignore[arg-type]
                    access_token="test-token",
                    audiences=frozenset({settings.erp_jwt_audience}),
                    request_id="v14-disabled",
                ).run(skill_id, SkillRunIn(input={"order_id": 71}, idempotency_key="disabled-0001"))
            await ecosystem.set_skill_enabled(skill_id, True)
            service = SkillExecutionService(
                session,
                context,
                _Workflow(),  # type: ignore[arg-type]
                access_token="test-token",
                audiences=frozenset({settings.erp_jwt_audience}),
                request_id="v14-run",
            )
            payload = SkillRunIn(input={"order_id": 71}, idempotency_key="skill-run-0001")
            run = await service.run(skill_id, payload)
            retried = await service.run(skill_id, payload)
            assert run.status == "SUCCEEDED"
            assert retried.id == run.id
            assert run.output_snapshot["evidence"][0]["tool_call_id"] == "tool-1"
            assert (await ecosystem.skill_runs(skill_id))[0].id == run.id

            denied = _context(1401, 1412, {"copilot:skill:read", "copilot:skill:run"})
            denied_service = SkillExecutionService(
                session,
                denied,
                _Workflow(),  # type: ignore[arg-type]
                access_token="test-token",
                audiences=frozenset({settings.erp_jwt_audience}),
                request_id="v14-denied",
            )
            with pytest.raises(AppError) as permission_error:
                await denied_service.run(
                    skill_id,
                    SkillRunIn(input={"order_id": 71}, idempotency_key="skill-run-denied"),
                )
            assert permission_error.value.status_code == 403
        finally:
            await session.close()

        other_session = TenantAsyncSession(
            1402, registry=REGISTRY, bind=engine, expire_on_commit=False, autoflush=False
        )
        try:
            with pytest.raises(AppError) as tenant_error:
                await EcosystemService(
                    other_session, _context(1402, 1422, permissions)
                ).skill(skill_id)
            assert tenant_error.value.status_code == 404
        finally:
            await other_session.close()
    finally:
        await engine.dispose()

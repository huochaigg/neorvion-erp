from __future__ import annotations

import io
import os
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import pytest
from app.core.config import settings
from app.core.exceptions import AppError
from app.core.tenant import TenantContext
from app.db.base import Base
from app.db.isolation import REGISTRY
from app.schemas.ecosystem import SkillRunIn, SkillVersionIn
from app.services.ecosystem import EcosystemService
from app.services.skill_execution import SkillExecutionService
from app.skills.catalog import SkillCatalog
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


def _dynamic_package(key: str) -> bytes:
    root = Path(__file__).parent / "fixtures" / "skills" / key
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for source in sorted(root.rglob("*")):
            if source.is_file():
                archive.write(source, f"{key}/{source.relative_to(root).as_posix()}")
    return output.getvalue()


@pytest.mark.asyncio
async def test_dynamic_package_catalog_lifecycle_and_version_switch_in_postgres() -> None:
    """真实数据库证明动态包无需修改 Selector/Catalog 即可进入当前租户目录。"""
    engine = create_async_engine(_integration_url())
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
            await connection.run_sync(Base.metadata.create_all)
        permissions = {
            "copilot:skill:read",
            "copilot:skill:run",
            "copilot:skill:manage",
            "inventory:read",
            "analytics:sales:read",
        }
        context = _context(1431, 1441, permissions)
        session = TenantAsyncSession(
            1431, registry=REGISTRY, bind=engine, expire_on_commit=False, autoflush=False
        )
        try:
            service = EcosystemService(session, context, "v14-3-dynamic")
            assert await SkillCatalog(session, context).available() == []
            imported = await service.import_skill_package(
                _dynamic_package("inventory-coverage-summary")
            )
            assert imported.status == "IMPORTED"
            assert await SkillCatalog(session, context).available() == []
            await service.review_skill(imported.skill_id, True)
            assert await SkillCatalog(session, context).available() == []
            await service.set_skill_enabled(imported.skill_id, True)
            first_catalog = await SkillCatalog(session, context).available()
            assert [item.skill_key for item in first_catalog] == [
                "inventory-coverage-summary"
            ]
            assert first_catalog[0].version == 1

            detail = await service.skill(imported.skill_id)
            version_data = detail.versions[0].model_dump()
            payload = SkillVersionIn.model_validate(
                {key: version_data[key] for key in SkillVersionIn.model_fields}
            ).model_copy(
                update={
                    "instructions": detail.versions[0].instructions
                    + "\n新版本必须额外说明数据观察时间。"
                }
            )
            await service.add_skill_version(imported.skill_id, payload)
            assert await SkillCatalog(session, context).available() == []
            await service.review_skill(imported.skill_id, True)
            await service.set_skill_enabled(imported.skill_id, True)
            latest = await SkillCatalog(session, context).available()
            assert latest[0].version == 2
            await service.set_skill_enabled(imported.skill_id, False)
            assert await SkillCatalog(session, context).available() == []
            assert len((await service.skill(imported.skill_id)).versions) == 2
        finally:
            await session.close()
    finally:
        await engine.dispose()

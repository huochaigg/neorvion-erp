from collections.abc import AsyncIterator
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, Request
from neorvion_security import SecurityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.factory import get_chat_adapter
from app.core.context import set_tenant_context
from app.core.exceptions import AppError, from_security_error
from app.core.iam import verify_tenant_access
from app.core.permissions import PermissionCode
from app.core.tenant import TENANT_HEADER, TenantContext
from app.db.session import open_tenant_session
from app.erp.client import get_erp_client
from app.graph.workflow import CopilotWorkflow
from app.services.authorization import AuthorizationService
from app.tools.executor import ToolExecutor
from app.tools.registry import build_tool_registry


def _extract_bearer_token(request: Request) -> str:
    header = request.headers.get("Authorization")
    if not header or not header.startswith("Bearer "):
        raise AppError("未登录", code=40100, status_code=401)
    token = header.removeprefix("Bearer ").strip()
    if not token:
        raise AppError("未登录", code=40100, status_code=401)
    return token


def _parse_tenant_id(raw: str | None) -> int:
    if raw is None or not raw.strip():
        raise AppError("缺少租户上下文", code=40030, status_code=400)
    try:
        tenant_id = int(raw.strip())
    except ValueError as exc:
        raise AppError("租户上下文无效", code=40030, status_code=400) from exc
    if tenant_id <= 0:
        raise AppError("租户上下文无效", code=40030, status_code=400)
    return tenant_id


async def get_tenant_context(request: Request) -> TenantContext:
    """JWT 只证明用户身份；租户成员关系与权限必须再从 IAM 快照校验。"""
    token = _extract_bearer_token(request)
    tenant_id = _parse_tenant_id(request.headers.get(TENANT_HEADER))
    try:
        claims, context = await verify_tenant_access(token, tenant_id)
    except TimeoutError as exc:
        raise AppError("身份授权服务响应超时", code=50313, status_code=503) from exc
    except SecurityError as exc:
        raise from_security_error(exc) from exc
    set_tenant_context(tenant_id=context.tenant_id, user_id=context.user_id)
    request.state.access_token = token
    request.state.jwt_audiences = claims.audience
    return context


TenantContextDep = Annotated[TenantContext, Depends(get_tenant_context)]


async def get_copilot_context(context: TenantContextDep) -> TenantContext:
    AuthorizationService().require_all(context, (PermissionCode.COPILOT_USE,))
    return context


CopilotContext = Annotated[TenantContext, Depends(get_copilot_context)]


async def get_db(context: CopilotContext) -> AsyncIterator[AsyncSession]:
    """只为已认证租户打开带 SQL 守卫的会话。"""
    session = open_tenant_session(context.tenant_id)
    try:
        yield session
    finally:
        await session.close()


DbSession = Annotated[AsyncSession, Depends(get_db)]


@lru_cache
def get_workflow() -> CopilotWorkflow:
    return CopilotWorkflow(
        get_chat_adapter(),
        ToolExecutor(build_tool_registry(), get_erp_client()),
    )


WorkflowDep = Annotated[CopilotWorkflow, Depends(get_workflow)]

from functools import lru_cache
from typing import Annotated

from fastapi import Depends, Request
from neorvion_security import SecurityError

from app.ai.factory import get_chat_adapter
from app.core.context import set_tenant_context
from app.core.exceptions import AppError, from_security_error
from app.core.iam import jwt_verifier, snapshot_store
from app.core.permissions import PermissionCode
from app.core.tenant import TENANT_HEADER, TenantContext
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
        claims = jwt_verifier().verify_access(token)
        context = snapshot_store().load(claims=claims, tenant_id=tenant_id)
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


@lru_cache
def get_workflow() -> CopilotWorkflow:
    return CopilotWorkflow(
        get_chat_adapter(),
        ToolExecutor(build_tool_registry(), get_erp_client()),
    )


WorkflowDep = Annotated[CopilotWorkflow, Depends(get_workflow)]

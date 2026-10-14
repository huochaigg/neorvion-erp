from fastapi import APIRouter, Query

from app.api.deps import DbSession, KnowledgeReadContext, KnowledgeUpdateContext
from app.repositories.ops import AuditRepository
from app.schemas.common import ApiResponse, ok
from app.schemas.ops import (
    ApiKeyCreatedOut,
    ApiKeyCreateIn,
    ApiKeyListOut,
    ApiKeyOut,
    AuditLogListOut,
    AuditLogOut,
    RecycleListOut,
)
from app.services.api_keys import ApiKeyService
from app.services.documents import DocumentService

router = APIRouter(tags=["knowledge-ops"])


@router.get("/recycle", response_model=ApiResponse[RecycleListOut], summary="回收站")
async def list_recycle(
    context: KnowledgeReadContext,
    session: DbSession,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> ApiResponse[RecycleListOut]:
    return ok(await DocumentService(session, context).list_recycle(page=page, page_size=page_size))


@router.get("/api-keys", response_model=ApiResponse[ApiKeyListOut], summary="API Key 列表")
async def list_api_keys(
    context: KnowledgeReadContext,
    session: DbSession,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> ApiResponse[ApiKeyListOut]:
    return ok(await ApiKeyService(session, context).list_keys(page, page_size))


@router.post("/api-keys", response_model=ApiResponse[ApiKeyCreatedOut], summary="创建 API Key（明文只返回一次）")
async def create_api_key(
    payload: ApiKeyCreateIn,
    context: KnowledgeUpdateContext,
    session: DbSession,
) -> ApiResponse[ApiKeyCreatedOut]:
    return ok(await ApiKeyService(session, context).create_key(payload), "请立即保存明文密钥")


@router.post("/api-keys/{key_id}/revoke", response_model=ApiResponse[ApiKeyOut], summary="撤销 API Key")
async def revoke_api_key(
    key_id: int,
    context: KnowledgeUpdateContext,
    session: DbSession,
) -> ApiResponse[ApiKeyOut]:
    return ok(await ApiKeyService(session, context).revoke_key(key_id), "已撤销")


@router.get("/audit-logs", response_model=ApiResponse[AuditLogListOut], summary="操作审计")
async def list_audit_logs(
    context: KnowledgeReadContext,
    session: DbSession,
    action: str | None = Query(default=None, max_length=64),
    resource_type: str | None = Query(default=None, max_length=32),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> ApiResponse[AuditLogListOut]:
    rows, total = await AuditRepository(session, context.tenant_id).list_page(
        action=action,
        resource_type=resource_type,
        page=page,
        page_size=page_size,
    )
    return ok(
        AuditLogListOut(
            items=[
                AuditLogOut(
                    id=item.id,
                    actor_user_id=item.actor_user_id,
                    actor_key_id=item.actor_key_id,
                    action=item.action,
                    resource_type=item.resource_type,
                    resource_id=item.resource_id,
                    detail=item.detail,
                    ip_address=item.ip_address,
                    request_id=item.request_id,
                    created_at=item.created_at,
                )
                for item in rows
            ],
            total=total,
            page=page,
            page_size=page_size,
        )
    )

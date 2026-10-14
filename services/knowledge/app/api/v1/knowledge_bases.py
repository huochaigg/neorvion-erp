from fastapi import APIRouter, Query

from app.api.deps import (
    DbSession,
    KnowledgeCreateContext,
    KnowledgeDeleteContext,
    KnowledgeReadContext,
    KnowledgeUpdateContext,
)
from app.schemas.common import ApiResponse, ok
from app.schemas.knowledge import (
    KnowledgeBaseCreate,
    KnowledgeBaseListOut,
    KnowledgeBaseOut,
    KnowledgeBaseUpdate,
)
from app.schemas.ops import GrantCreateIn, GrantListOut, GrantOut
from app.services.knowledge import KnowledgeBaseService

router = APIRouter(prefix="/knowledge-bases", tags=["knowledge-bases"])


@router.get("", response_model=ApiResponse[KnowledgeBaseListOut], summary="知识库列表")
async def list_knowledge_bases(
    context: KnowledgeReadContext,
    session: DbSession,
    q: str | None = Query(default=None, max_length=64),
    status: str | None = Query(default=None, max_length=16),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> ApiResponse[KnowledgeBaseListOut]:
    return ok(
        await KnowledgeBaseService(session, context).list_knowledge_bases(
            q=q,
            status=status,
            page=page,
            page_size=page_size,
        )
    )


@router.get(
    "/{knowledge_base_id}",
    response_model=ApiResponse[KnowledgeBaseOut],
    summary="知识库详情",
)
async def get_knowledge_base(
    knowledge_base_id: int,
    context: KnowledgeReadContext,
    session: DbSession,
) -> ApiResponse[KnowledgeBaseOut]:
    return ok(await KnowledgeBaseService(session, context).get_knowledge_base(knowledge_base_id))


@router.post("", response_model=ApiResponse[KnowledgeBaseOut], summary="创建知识库")
async def create_knowledge_base(
    payload: KnowledgeBaseCreate,
    context: KnowledgeCreateContext,
    session: DbSession,
) -> ApiResponse[KnowledgeBaseOut]:
    return ok(
        await KnowledgeBaseService(session, context).create_knowledge_base(payload),
        "创建成功",
    )


@router.patch(
    "/{knowledge_base_id}",
    response_model=ApiResponse[KnowledgeBaseOut],
    summary="编辑知识库",
)
async def update_knowledge_base(
    knowledge_base_id: int,
    payload: KnowledgeBaseUpdate,
    context: KnowledgeUpdateContext,
    session: DbSession,
) -> ApiResponse[KnowledgeBaseOut]:
    return ok(
        await KnowledgeBaseService(session, context).update_knowledge_base(
            knowledge_base_id,
            payload,
        )
    )


@router.delete(
    "/{knowledge_base_id}",
    response_model=ApiResponse[None],
    summary="删除知识库",
)
async def delete_knowledge_base(
    knowledge_base_id: int,
    context: KnowledgeDeleteContext,
    session: DbSession,
) -> ApiResponse[None]:
    await KnowledgeBaseService(session, context).delete_knowledge_base(knowledge_base_id)
    return ok(None, "已移入回收站")


@router.post(
    "/{knowledge_base_id}/restore",
    response_model=ApiResponse[KnowledgeBaseOut],
    summary="从回收站恢复知识库",
)
async def restore_knowledge_base(
    knowledge_base_id: int,
    context: KnowledgeUpdateContext,
    session: DbSession,
) -> ApiResponse[KnowledgeBaseOut]:
    return ok(await KnowledgeBaseService(session, context).restore_knowledge_base(knowledge_base_id), "已恢复")


@router.delete(
    "/{knowledge_base_id}/purge",
    response_model=ApiResponse[None],
    summary="彻底删除知识库",
)
async def purge_knowledge_base(
    knowledge_base_id: int,
    context: KnowledgeDeleteContext,
    session: DbSession,
) -> ApiResponse[None]:
    await KnowledgeBaseService(session, context).purge_knowledge_base(knowledge_base_id)
    return ok(None, "已彻底删除")


@router.get("/{knowledge_base_id}/grants", response_model=ApiResponse[GrantListOut], summary="知识库授权")
async def list_grants(
    knowledge_base_id: int,
    context: KnowledgeReadContext,
    session: DbSession,
) -> ApiResponse[GrantListOut]:
    return ok(await KnowledgeBaseService(session, context).list_grants(knowledge_base_id))


@router.post("/{knowledge_base_id}/grants", response_model=ApiResponse[GrantOut], summary="授予知识库权限")
async def upsert_grant(
    knowledge_base_id: int,
    payload: GrantCreateIn,
    context: KnowledgeUpdateContext,
    session: DbSession,
) -> ApiResponse[GrantOut]:
    return ok(await KnowledgeBaseService(session, context).upsert_grant(knowledge_base_id, payload), "已授权")


@router.delete("/{knowledge_base_id}/grants/{grant_id}", response_model=ApiResponse[None], summary="撤销知识库授权")
async def delete_grant(
    knowledge_base_id: int,
    grant_id: int,
    context: KnowledgeUpdateContext,
    session: DbSession,
) -> ApiResponse[None]:
    await KnowledgeBaseService(session, context).delete_grant(knowledge_base_id, grant_id)
    return ok(None, "已撤销授权")

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
    return ok(None, "删除成功")

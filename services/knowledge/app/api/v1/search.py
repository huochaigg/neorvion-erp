from fastapi import APIRouter

from app.api.deps import DbSession, KnowledgeReadContext, KnowledgeUpdateContext
from app.schemas.common import ApiResponse, ok
from app.schemas.rag import IndexStatusOut, SearchHitOut, SearchIn, SearchOut
from app.services.index_status import IndexService
from app.services.retrieval import RetrievalService

router = APIRouter(tags=["knowledge-rag"])


def _to_out(result) -> SearchOut:
    return SearchOut(
        items=[
            SearchHitOut(
                chunk_id=item.chunk_id,
                document_id=item.document_id,
                knowledge_base_id=item.knowledge_base_id,
                filename=item.filename,
                content=item.content,
                page_no=item.page_no,
                heading=item.heading,
                chunk_index=item.chunk_index,
                version=item.version,
                final_rank=item.final_rank,
                vector_score=item.vector_score,
                keyword_score=item.keyword_score,
                rrf_score=item.rrf_score,
                rerank_score=item.rerank_score,
            )
            for item in result.hits
        ],
        strategy=result.strategy,
        rerank_applied=result.rerank_applied,
        rerank_degraded=result.rerank_degraded,
        stages=result.stages,
        latency_ms=result.latency_ms,
        knowledge_base_ids=result.knowledge_base_ids,
    )


@router.post("/search", response_model=ApiResponse[SearchOut], summary="智能搜索")
async def search(
    payload: SearchIn,
    context: KnowledgeReadContext,
    session: DbSession,
) -> ApiResponse[SearchOut]:
    result = await RetrievalService(session, context).search(
        payload.query,
        knowledge_base_ids=payload.knowledge_base_ids,
        strategy=payload.strategy,
        top_k=payload.top_k,
        candidate_k=payload.candidate_k,
        similarity_threshold=payload.similarity_threshold,
        rerank=payload.rerank,
    )
    return ok(_to_out(result))


@router.post("/retrieval/test", response_model=ApiResponse[SearchOut], summary="检索测试（与问答共用检索引擎）")
async def retrieval_test(
    payload: SearchIn,
    context: KnowledgeReadContext,
    session: DbSession,
) -> ApiResponse[SearchOut]:
    result = await RetrievalService(session, context).search(
        payload.query,
        knowledge_base_ids=payload.knowledge_base_ids,
        strategy=payload.strategy,
        top_k=payload.top_k,
        candidate_k=payload.candidate_k,
        similarity_threshold=payload.similarity_threshold,
        rerank=payload.rerank,
    )
    return ok(_to_out(result))


@router.get(
    "/knowledge-bases/{knowledge_base_id}/index-status",
    response_model=ApiResponse[IndexStatusOut],
    summary="向量索引状态",
)
async def index_status(
    knowledge_base_id: int,
    context: KnowledgeReadContext,
    session: DbSession,
) -> ApiResponse[IndexStatusOut]:
    return ok(await IndexService(session, context).status(knowledge_base_id))


@router.post(
    "/knowledge-bases/{knowledge_base_id}/reindex",
    response_model=ApiResponse[dict],
    summary="重建向量索引",
)
async def reindex(
    knowledge_base_id: int,
    context: KnowledgeUpdateContext,
    session: DbSession,
) -> ApiResponse[dict]:
    queued = await IndexService(session, context).reindex(knowledge_base_id)
    return ok({"queued": queued}, "已排队重建索引")

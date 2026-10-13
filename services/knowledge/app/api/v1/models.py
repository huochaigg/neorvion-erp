from fastapi import APIRouter

from app.api.deps import DbSession, KnowledgeReadContext, KnowledgeUpdateContext
from app.schemas.common import ApiResponse, ok
from app.schemas.rag import ModelProfileOut, ModelTestIn
from app.services.models import ModelService

router = APIRouter(tags=["knowledge-models"])


@router.get("/models", response_model=ApiResponse[list[ModelProfileOut]], summary="模型配置（不含密钥）")
async def list_models(context: KnowledgeReadContext, session: DbSession) -> ApiResponse[list[ModelProfileOut]]:
    return ok(await ModelService(session).list_profiles())


@router.post("/models/test", response_model=ApiResponse[ModelProfileOut], summary="模型连通性测试")
async def test_model(
    payload: ModelTestIn,
    context: KnowledgeUpdateContext,
    session: DbSession,
) -> ApiResponse[ModelProfileOut]:
    return ok(await ModelService(session).test(payload.kind), "连通性测试完成")

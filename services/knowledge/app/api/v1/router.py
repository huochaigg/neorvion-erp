from fastapi import APIRouter

from app.api.v1.conversations import router as conversation_router
from app.api.v1.documents import router as document_router
from app.api.v1.health import router as health_router
from app.api.v1.knowledge_bases import router as knowledge_base_router
from app.api.v1.me import router as me_router
from app.api.v1.models import router as model_router
from app.api.v1.search import router as search_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health_router, tags=["health"])
api_router.include_router(me_router)
api_router.include_router(knowledge_base_router)
api_router.include_router(document_router)
api_router.include_router(search_router)
api_router.include_router(conversation_router)
api_router.include_router(model_router)

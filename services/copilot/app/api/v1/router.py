from fastapi import APIRouter

from app.api.v1.action_proposals import router as action_proposals_router
from app.api.v1.chat import router as chat_router
from app.api.v1.conversations import router as conversations_router
from app.api.v1.health import router as health_router
from app.api.v1.me import router as me_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health_router, tags=["health"])
api_router.include_router(me_router)
api_router.include_router(chat_router)
api_router.include_router(conversations_router)
api_router.include_router(action_proposals_router)

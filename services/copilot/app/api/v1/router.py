from fastapi import APIRouter

from app.api.v1.action_executions import router as action_executions_router
from app.api.v1.action_proposals import router as action_proposals_router
from app.api.v1.agent_runs import router as agent_runs_router
from app.api.v1.chat import router as chat_router
from app.api.v1.conversations import router as conversations_router
from app.api.v1.ecosystem import router as ecosystem_router
from app.api.v1.evaluations import router as evaluations_router
from app.api.v1.governance import router as governance_router
from app.api.v1.health import router as health_router
from app.api.v1.insights import router as insights_router
from app.api.v1.me import router as me_router
from app.api.v1.workflows import router as workflows_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health_router, tags=["health"])
api_router.include_router(me_router)
api_router.include_router(chat_router)
api_router.include_router(conversations_router)
api_router.include_router(action_proposals_router)
api_router.include_router(action_executions_router)
api_router.include_router(workflows_router)
api_router.include_router(evaluations_router)
api_router.include_router(agent_runs_router)
api_router.include_router(insights_router)
api_router.include_router(governance_router)
api_router.include_router(ecosystem_router)

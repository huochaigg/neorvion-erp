from fastapi import APIRouter, Request

from app.api.deps import CurrentUser, IdentityDb
from app.schemas.common import ApiResponse, ok
from app.schemas.session import SessionOut
from app.services.session import SessionService

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.get("", response_model=ApiResponse[list[SessionOut]], summary="我的登录会话")
def list_sessions(
    request: Request,
    user: CurrentUser,
    session: IdentityDb,
) -> ApiResponse[list[SessionOut]]:
    current_id = str(getattr(request.state, "session_id", "") or "")
    return ok(SessionService(session).list_mine(user.id, current_public_id=current_id))


@router.delete("/{session_id}", response_model=ApiResponse[None], summary="撤销指定会话")
def revoke_session(
    session_id: str,
    user: CurrentUser,
    session: IdentityDb,
) -> ApiResponse[None]:
    SessionService(session).revoke_one(user.id, session_id)
    return ok(None, "已撤销会话")


@router.post("/revoke-all", response_model=ApiResponse[dict], summary="退出所有设备")
def revoke_all_sessions(user: CurrentUser, session: IdentityDb) -> ApiResponse[dict]:
    count = SessionService(session).revoke_all(user.id, reason="LOGOUT_ALL")
    return ok({"revoked": count}, "已退出所有设备")

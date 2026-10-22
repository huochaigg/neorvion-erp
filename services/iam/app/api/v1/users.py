"""平台用户管理。租户管理员不能调用本路由。"""

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import BootstrapDb, PlatformAdmin
from app.core.exceptions import AppError
from app.models.user import User, UserStatus
from app.schemas.auth import UserOut
from app.schemas.common import ApiResponse, ok
from app.services.snapshots import SnapshotService

router = APIRouter(prefix="/users", tags=["users"])


class UserStatusUpdate(BaseModel):
    status: str = Field(description="ACTIVE 或 DISABLED")


@router.get("", response_model=ApiResponse[list[UserOut]], summary="平台用户列表")
def list_users(
    _admin: PlatformAdmin,
    session: BootstrapDb,
    q: str | None = Query(default=None, max_length=64),
) -> ApiResponse[list[UserOut]]:
    stmt = select(User).order_by(User.id.asc())
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(User.email.like(like) | User.display_name.like(like))
    rows = list(session.scalars(stmt).all())
    return ok([UserOut.model_validate(row) for row in rows])


@router.patch("/{user_id}", response_model=ApiResponse[UserOut], summary="停用或启用用户")
def update_user_status(
    user_id: int,
    payload: UserStatusUpdate,
    admin: PlatformAdmin,
    session: BootstrapDb,
) -> ApiResponse[UserOut]:
    if payload.status not in {UserStatus.ACTIVE.value, UserStatus.DISABLED.value}:
        raise AppError("用户状态无效", code=40040, status_code=400)
    user = session.get(User, user_id)
    if user is None:
        raise AppError("用户不存在", code=40420, status_code=404)
    if user.id == admin.id and payload.status == UserStatus.DISABLED.value:
        raise AppError("不能停用当前登录的平台管理员", code=40041, status_code=400)
    user.status = payload.status
    session.commit()
    snapshots = SnapshotService(session)
    if payload.status == UserStatus.DISABLED.value:
        snapshots.invalidate_sessions(user.id)
    snapshots.refresh_user(user.id)
    return ok(UserOut.model_validate(user), "已更新用户状态")

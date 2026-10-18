"""应用注册、菜单、审计与受控权限同步。"""

from fastapi import APIRouter, Header, Query
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import DbSession, PlatformAdmin, TenantContextDep
from app.core.config import settings
from app.core.exceptions import AppError
from app.core.permissions import PERMISSION_CATALOG, PermissionCode
from app.models.catalog import Application, AuditLog, Menu
from app.models.rbac import Permission
from app.schemas.common import ApiResponse, ok

router = APIRouter(tags=["catalog"])


class ApplicationOut(BaseModel):
    id: int
    code: str
    name: str
    audience: str
    status: str
    description: str

    model_config = {"from_attributes": True}


class ApplicationIn(BaseModel):
    code: str = Field(min_length=2, max_length=32)
    name: str = Field(min_length=1, max_length=64)
    audience: str = Field(min_length=2, max_length=64)
    description: str = ""


class MenuOut(BaseModel):
    id: int
    application_id: int
    parent_id: int | None
    menu_key: str
    title: str
    menu_type: str
    path: str
    permission_code: str | None
    sort_no: int
    visible: bool
    locked: bool

    model_config = {"from_attributes": True}


class MenuUpdateIn(BaseModel):
    title: str | None = None
    path: str | None = None
    visible: bool | None = None
    sort_no: int | None = None
    permission_code: str | None = None


class PermissionSyncItem(BaseModel):
    code: str
    name: str
    module: str
    description: str = ""


class PermissionSyncIn(BaseModel):
    application_code: str
    permissions: list[PermissionSyncItem]


class AuditOut(BaseModel):
    id: int
    tenant_id: int | None
    actor_user_id: int
    action: str
    target_type: str
    target_id: str
    detail: str
    created_at: str

    model_config = {"from_attributes": True}


def _write_audit(session, *, actor_user_id: int, action: str, target_type: str, target_id: str, detail: str, tenant_id: int | None = None) -> None:
    session.add(
        AuditLog(
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            detail=detail,
        )
    )
    session.commit()


@router.get("/applications", response_model=ApiResponse[list[ApplicationOut]], summary="应用列表")
def list_applications(_admin: PlatformAdmin, session: DbSession) -> ApiResponse[list[ApplicationOut]]:
    rows = list(session.scalars(select(Application).order_by(Application.id.asc())).all())
    return ok([ApplicationOut.model_validate(row) for row in rows])


@router.post("/applications", response_model=ApiResponse[ApplicationOut], summary="注册应用")
def create_application(
    payload: ApplicationIn,
    admin: PlatformAdmin,
    session: DbSession,
) -> ApiResponse[ApplicationOut]:
    exists = session.scalars(select(Application).where(Application.code == payload.code.strip().lower())).first()
    if exists is not None:
        raise AppError("应用编码已存在", code=40930, status_code=409)
    row = Application(
        code=payload.code.strip().lower(),
        name=payload.name.strip(),
        audience=payload.audience.strip(),
        description=payload.description.strip(),
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    _write_audit(
        session,
        actor_user_id=admin.id,
        action="application.create",
        target_type="application",
        target_id=str(row.id),
        detail=row.code,
    )
    return ok(ApplicationOut.model_validate(row), "已注册应用")


@router.get("/menus", response_model=ApiResponse[list[MenuOut]], summary="菜单列表")
def list_menus(
    context: TenantContextDep,
    session: DbSession,
    application_code: str | None = Query(default=None),
) -> ApiResponse[list[MenuOut]]:
    if PermissionCode.IAM_MENUS_READ.value not in context.permission_codes and not context.is_platform_admin:
        raise AppError("缺少权限", code=40320, status_code=403)
    stmt = select(Menu).order_by(Menu.sort_no.asc(), Menu.id.asc())
    if application_code:
        app = session.scalars(select(Application).where(Application.code == application_code)).first()
        if app is None:
            return ok([])
        stmt = stmt.where(Menu.application_id == app.id)
    rows = list(session.scalars(stmt).all())
    return ok([MenuOut.model_validate(row) for row in rows])


@router.patch("/menus/{menu_id}", response_model=ApiResponse[MenuOut], summary="更新菜单")
def update_menu(
    menu_id: int,
    payload: MenuUpdateIn,
    admin: PlatformAdmin,
    session: DbSession,
) -> ApiResponse[MenuOut]:
    row = session.get(Menu, menu_id)
    if row is None:
        raise AppError("菜单不存在", code=40430, status_code=404)
    if payload.title is not None:
        row.title = payload.title.strip()
    if payload.path is not None:
        row.path = payload.path.strip()
    if payload.visible is not None:
        row.visible = payload.visible
    if payload.sort_no is not None:
        row.sort_no = payload.sort_no
    if payload.permission_code is not None:
        row.permission_code = payload.permission_code.strip() or None
    row.locked = True
    session.commit()
    session.refresh(row)
    _write_audit(
        session,
        actor_user_id=admin.id,
        action="menu.update",
        target_type="menu",
        target_id=str(row.id),
        detail=row.menu_key,
    )
    return ok(MenuOut.model_validate(row), "已更新菜单")


@router.get("/audit-logs", response_model=ApiResponse[list[AuditOut]], summary="审计日志")
def list_audit_logs(
    admin: PlatformAdmin,
    session: DbSession,
    tenant_id: int | None = Query(default=None),
) -> ApiResponse[list[AuditOut]]:
    stmt = select(AuditLog).order_by(AuditLog.id.desc()).limit(200)
    if tenant_id is not None:
        stmt = stmt.where(AuditLog.tenant_id == tenant_id)
    rows = list(session.scalars(stmt).all())
    return ok(
        [
            AuditOut(
                id=row.id,
                tenant_id=row.tenant_id,
                actor_user_id=row.actor_user_id,
                action=row.action,
                target_type=row.target_type,
                target_id=row.target_id,
                detail=row.detail,
                created_at=row.created_at.isoformat(),
            )
            for row in rows
        ]
    )


@router.post("/internal/permissions/sync", response_model=ApiResponse[dict], summary="受控同步权限编码")
def sync_permissions(
    payload: PermissionSyncIn,
    session: DbSession,
    x_permission_sync_key: str | None = Header(default=None, alias="X-Permission-Sync-Key"),
) -> ApiResponse[dict]:
    """只插入尚不存在的权限编码，不覆盖管理员已锁定的目录项，不删除。"""
    expected = settings.permission_sync_key
    if not expected or not x_permission_sync_key or x_permission_sync_key != expected:
        raise AppError("权限同步密钥无效", code=40331, status_code=403)
    existing = {row.code: row for row in session.scalars(select(Permission)).all()}
    inserted = 0
    skipped = 0
    catalog = {item[0] for item in PERMISSION_CATALOG}
    for item in payload.permissions:
        if item.code in existing:
            skipped += 1
            continue
        if item.code not in catalog and not item.code.startswith(f"{payload.application_code}:"):
            skipped += 1
            continue
        session.add(
            Permission(
                code=item.code,
                name=item.name,
                module=item.module,
                description=item.description,
            )
        )
        inserted += 1
    session.commit()
    return ok({"inserted": inserted, "skipped": skipped}, "已同步权限目录")

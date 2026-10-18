"""任务处理器。报表导出分阶段更新进度，避免逐行 UPDATE。"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

from app.core.async_tasks import REPORT_EXPORT_KINDS, TaskLogLevel
from app.core.config import settings
from app.core.exceptions import AppError, from_security_error
from app.core.iam import snapshot_store
from app.core.permissions import PermissionCode
from app.core.tenant import TenantContext
from app.models.async_task import AsyncTask, AsyncTaskLog
from app.services.analytics import AnalyticsService
from app.services.authorization import AuthorizationService
from neorvion_security import SecurityError

_EXPORT_PERMISSIONS = {
    "sales_trend": PermissionCode.ANALYTICS_SALES_READ,
    "purchase_trend": PermissionCode.ANALYTICS_PURCHASE_READ,
    "low_stock": PermissionCode.ANALYTICS_INVENTORY_READ,
}


def _context(task: AsyncTask) -> TenantContext:
    """后台任务使用创建者当时的授权快照，禁止空身份或隐式高权限。"""
    if not task.created_by or not task.tenant_id:
        raise AppError("任务缺少可审计的执行身份", code=40330, status_code=403)
    try:
        return snapshot_store().load_for_principal(
            user_id=int(task.created_by),
            tenant_id=int(task.tenant_id),
        )
    except SecurityError as exc:
        raise from_security_error(exc) from exc


def export_dir_for(tenant_id: int | None, task_id: str) -> Path:
    root = Path(settings.export_dir)
    tenant_part = str(tenant_id) if tenant_id is not None else "system"
    directory = root / tenant_part
    directory.mkdir(parents=True, exist_ok=True)
    return directory / f"{task_id}.csv"


def append_log(
    session: Session, task: AsyncTask, message: str, level: str = TaskLogLevel.INFO.value
) -> None:
    session.add(
        AsyncTaskLog(
            tenant_id=task.tenant_id,
            task_id=task.task_id,
            level=level,
            message=message,
        )
    )


def handle_report_export(session: Session, task: AsyncTask) -> dict:
    """
    功能：根据 payload.kind 生成 CSV 到受控导出目录。
    参数：已锁定为 RUNNING 的 AsyncTask。
    返回：result JSON（file_name / row_count / kind），不含绝对路径。
    异常：未知 kind、缺少租户、Analytics 业务错误。
    """
    payload = task.payload or {}
    kind = str(payload.get("kind") or "")
    if kind not in REPORT_EXPORT_KINDS:
        raise AppError("不支持的导出类型", code=40720, status_code=400)
    if task.tenant_id is None:
        raise AppError("报表导出必须属于具体租户", code=40721, status_code=400)

    append_log(session, task, "开始查询统计数据")
    task.progress = 20
    session.flush()

    context = _context(task)
    required = _EXPORT_PERMISSIONS.get(kind)
    if required:
        AuthorizationService(session).require_all(context, (required,))
    service = AnalyticsService(session, context)
    start_date = payload.get("start_date")
    end_date = payload.get("end_date")
    warehouse_id = payload.get("warehouse_id")
    threshold = payload.get("low_stock_threshold")
    if kind == "sales_trend":
        filename, content = service.export_sales_trend_csv(start_date, end_date, warehouse_id)
    elif kind == "purchase_trend":
        filename, content = service.export_purchase_trend_csv(start_date, end_date, warehouse_id)
    else:
        filename, content = service.export_low_stock_csv(threshold, warehouse_id)

    task.progress = 60
    append_log(session, task, "正在生成 CSV")
    session.flush()

    path = export_dir_for(task.tenant_id, task.task_id)
    path.write_text(content, encoding="utf-8")
    rows = max(content.count("\n") - 1, 0)
    task.progress = 90
    append_log(session, task, f"已写入 {rows} 行")
    session.flush()
    return {"file_name": filename, "row_count": rows, "kind": kind}


HANDLERS = {
    "REPORT_EXPORT": handle_report_export,
}

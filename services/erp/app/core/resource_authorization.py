from __future__ import annotations

from collections.abc import Iterable

from fastapi import Request

from app.core.exceptions import AppError
from app.core.tenant import TenantContext


def is_service(context: TenantContext) -> bool:
    return context.subject_type == "SERVICE"


def require_service_resource(
    context: TenantContext,
    kind: str,
    value: int | str | None,
    *,
    allow_single_default: bool = False,
) -> int | str | None:
    """把 Service Token 的资源 Claim 绑定到真实路径或查询参数。

    USER 请求不受此层影响；SERVICE 默认拒绝缺失、空授权和越权资源。列表接口只有
    在该维度恰好授权一个值时才能自动补上过滤条件，避免先查全量再响应过滤。
    """
    if not is_service(context):
        return value
    granted = {str(item) for item in context.service_resources.get(kind, ())}
    if not granted:
        raise AppError("服务 Token 缺少资源授权", code=40373, status_code=403)
    if value is None:
        if allow_single_default and len(granted) == 1:
            raw = next(iter(granted))
            return int(raw) if all(item.isdigit() for item in granted) else raw
        raise AppError("服务 Token 必须提供明确资源过滤条件", code=40373, status_code=403)
    if str(value) not in granted:
        raise AppError("服务 Token 资源范围不足", code=40373, status_code=403)
    return value


def require_any_service_resource(
    context: TenantContext,
    candidates: Iterable[tuple[str, int | str | None]],
) -> None:
    """多维查询至少有一个显式且获授权的资源维度，其余已提供维度也必须获授权。"""
    if not is_service(context):
        return
    matched = False
    for kind, value in candidates:
        if value is None:
            continue
        require_service_resource(context, kind, value)
        matched = True
    if not matched:
        raise AppError("服务 Token 查询缺少明确资源范围", code=40373, status_code=403)


def require_service_resources(
    context: TenantContext, kind: str, values: Iterable[int | str]
) -> None:
    """批量参数必须整体落在同一种资源 Claim 内，不能部分授权后继续查询。"""
    if not is_service(context):
        return
    granted = {str(item) for item in context.service_resources.get(kind, ())}
    wanted = {str(item) for item in values}
    if not wanted or not wanted.issubset(granted):
        raise AppError("服务 Token 资源范围不足", code=40373, status_code=403)


def authorize_service_request_resources(request: Request, context: TenantContext) -> None:
    """在进入 Repository 前把 Service Token 资源绑定到 ERP 查询条件。

    这里只处理服务身份且仅允许已审查的只读路由。需要多值或默认资源的
    库存查询仍由具体 Router 执行，其余列表和聚合查询必须显式携带
    可验证的资源维度，避免先读全租户数据再过滤。
    """
    if not is_service(context) or request.method.upper() not in {"GET", "HEAD"}:
        return

    path = request.url.path.rstrip("/")
    params = request.query_params
    path_parts = path.split("/")

    if path.endswith("/inventory") or "/inventory/" in path:
        return
    if path.endswith("/warehouses"):
        raise AppError("服务身份不能枚举全部仓库", code=40373, status_code=403)
    if "/warehouses/" in path:
        require_service_resource(context, "warehouse", path_parts[-1])
        return
    if path.endswith("/products"):
        require_service_resource(context, "sku", params.get("sku_code"))
        return
    if "/products/" in path:
        require_service_resource(context, "product", path_parts[-1])
        return
    if path.endswith("/sales-orders"):
        require_any_service_resource(
            context,
            (("warehouse", params.get("warehouse_id")), ("sku", params.get("sku_code"))),
        )
        return
    if "/sales-orders/" in path:
        require_service_resource(context, "sales_order", path_parts[-1])
        return
    if path.endswith("/purchase-orders"):
        require_service_resource(context, "warehouse", params.get("warehouse_id"))
        return
    if "/purchase-orders/" in path:
        require_service_resource(context, "purchase_order", path_parts[-1])
        return
    if path.endswith("/after-sales"):
        require_any_service_resource(
            context,
            (("sales_order", params.get("sales_order_id")), ("sku", params.get("sku_code"))),
        )
        return
    if path.endswith("/after-sales/preview"):
        require_service_resource(context, "sales_order", params.get("sales_order_id"))
        return
    if "/after-sales/" in path:
        require_service_resource(context, "after_sale", path_parts[-1])
        return
    if "/analytics/" in path:
        require_service_resource(context, "warehouse", params.get("warehouse_id"))
        if path.endswith("/sales/sku"):
            require_service_resource(context, "sku", params.get("sku_code"))
        return
    raise AppError("服务身份不能访问未审查的 ERP 路由", code=40374, status_code=403)

from urllib.parse import urlencode

import pytest
from app.core.exceptions import AppError
from app.core.resource_authorization import (
    authorize_service_request_resources,
    require_service_resource,
)
from app.core.tenant import TenantContext
from fastapi import Request


def _context(*, subject_type: str = "SERVICE") -> TenantContext:
    return TenantContext(
        user_id=0,
        tenant_id=7,
        member_id=0,
        is_owner=False,
        role="SERVICE",
        subject_type=subject_type,
        service_id="copilot-insights",
        service_resources={
            "warehouse": ("3",),
            "sku": ("SKU-001",),
            "sales_order": ("19",),
        },
    )


def _request(path: str, **params: str | int) -> Request:
    query = urlencode(params).encode()
    return Request(
        {
            "type": "http",
            "method": "GET",
            "scheme": "http",
            "path": path,
            "raw_path": path.encode(),
            "query_string": query,
            "headers": [],
            "client": ("127.0.0.1", 50000),
            "server": ("testserver", 80),
        }
    )


def test_user_requests_are_not_changed_by_service_resource_layer() -> None:
    context = _context(subject_type="USER")
    assert require_service_resource(context, "warehouse", 999) == 999
    authorize_service_request_resources(_request("/api/v1/analytics/sales/summary"), context)


def test_service_analytics_requires_explicit_authorized_warehouse() -> None:
    with pytest.raises(AppError) as missing:
        authorize_service_request_resources(
            _request("/api/v1/analytics/sales/summary"), _context()
        )
    assert missing.value.code == 40373

    with pytest.raises(AppError) as unauthorized:
        authorize_service_request_resources(
            _request("/api/v1/analytics/sales/summary", warehouse_id=4), _context()
        )
    assert unauthorized.value.code == 40373

    authorize_service_request_resources(
        _request("/api/v1/analytics/sales/summary", warehouse_id=3), _context()
    )


def test_service_sku_analytics_binds_both_resource_dimensions() -> None:
    authorize_service_request_resources(
        _request(
            "/api/v1/analytics/sales/sku",
            warehouse_id=3,
            sku_code="SKU-001",
        ),
        _context(),
    )
    with pytest.raises(AppError) as error:
        authorize_service_request_resources(
            _request(
                "/api/v1/analytics/sales/sku",
                warehouse_id=3,
                sku_code="SKU-OTHER",
            ),
            _context(),
        )
    assert error.value.code == 40373


def test_service_list_and_detail_queries_cannot_escape_claims() -> None:
    authorize_service_request_resources(
        _request("/api/v1/sales-orders", warehouse_id=3), _context()
    )
    authorize_service_request_resources(_request("/api/v1/sales-orders/19"), _context())

    with pytest.raises(AppError):
        authorize_service_request_resources(_request("/api/v1/sales-orders"), _context())
    with pytest.raises(AppError):
        authorize_service_request_resources(_request("/api/v1/sales-orders/20"), _context())


def test_service_cannot_enumerate_warehouses() -> None:
    with pytest.raises(AppError) as error:
        authorize_service_request_resources(_request("/api/v1/warehouses"), _context())
    assert error.value.code == 40373


def test_service_unknown_read_route_is_denied_by_default() -> None:
    with pytest.raises(AppError) as error:
        authorize_service_request_resources(_request("/api/v1/customers"), _context())
    assert error.value.code == 40374

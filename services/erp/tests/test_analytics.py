from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

from app.db.session import SessionLocal
from app.models.after_sale import AfterSaleItem, AfterSaleOrder, AfterSaleStatus, AfterSaleType
from app.models.inventory import Inventory, InventoryTransaction, InventoryTransactionType
from app.models.purchase_return import (
    PURCHASE_RETURN_REFERENCE,
    PurchaseReturn,
    PurchaseReturnStatus,
)
from app.models.refund import RefundRecord, RefundRecordStatus
from app.models.sales_order import SalesOrder
from app.models.supplier_refund import SupplierRefundRecord, SupplierRefundRecordStatus
from fastapi.testclient import TestClient
from sqlalchemy import select, text

from tests.helpers.auth_api import auth_header, register_and_login


def _tenant(client: TestClient, token: str, name: str, code: str) -> int:
    response = client.post(
        "/api/v1/tenants",
        json={"name": name, "code": code},
        headers=auth_header(token),
    )
    assert response.status_code == 200, response.text
    return int(response.json()["data"]["id"])


def _roles(client: TestClient, token: str, tenant_id: int) -> dict[str, dict]:
    response = client.get("/api/v1/roles", headers=auth_header(token, tenant_id))
    assert response.status_code == 200, response.text
    return {item["code"]: item for item in response.json()["data"]}


def _add_member(
    client: TestClient, owner: str, tenant_id: int, email: str, role_ids: list[int]
) -> str:
    member_token, _ = register_and_login(client, email)
    response = client.post(
        f"/api/v1/tenants/{tenant_id}/members",
        json={"email": email, "role_ids": role_ids},
        headers=auth_header(owner, tenant_id),
    )
    assert response.status_code == 200, response.text
    return member_token


def _user_id(client: TestClient, token: str, tenant_id: int) -> int:
    response = client.get("/api/v1/tenants/current", headers=auth_header(token, tenant_id))
    assert response.status_code == 200, response.text
    return int(response.json()["data"]["user_id"])


def _warehouse(client: TestClient, token: str, tenant_id: int, name: str) -> dict:
    response = client.post(
        "/api/v1/warehouses",
        json={"name": name, "type": "DOMESTIC"},
        headers=auth_header(token, tenant_id),
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


def _product(client: TestClient, token: str, tenant_id: int, name: str, skus: list[dict]) -> dict:
    category = client.post(
        "/api/v1/product-categories",
        json={"name": f"{name}-类目"},
        headers=auth_header(token, tenant_id),
    )
    assert category.status_code == 200, category.text
    created = client.post(
        "/api/v1/products",
        json={"name": name, "category_id": category.json()["data"]["id"], "skus": skus},
        headers=auth_header(token, tenant_id),
    )
    assert created.status_code == 200, created.text
    return created.json()["data"]


def _customer(client: TestClient, token: str, tenant_id: int, name: str) -> dict:
    response = client.post(
        "/api/v1/customers",
        json={"name": name, "country_code": "CN", "city": "深圳", "address": "科技园 1 号"},
        headers=auth_header(token, tenant_id),
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


def _supplier(client: TestClient, token: str, tenant_id: int, name: str) -> dict:
    response = client.post(
        "/api/v1/suppliers", json={"name": name}, headers=auth_header(token, tenant_id)
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


def _init_stock(
    client: TestClient, token: str, tenant_id: int, warehouse_id: int, sku_id: int, qty: int
) -> None:
    response = client.post(
        "/api/v1/inventory/initialize",
        json={"warehouse_id": warehouse_id, "sku_id": sku_id, "quantity": qty},
        headers=auth_header(token, tenant_id),
    )
    assert response.status_code == 200, response.text


def _create_order(
    client: TestClient,
    token: str,
    tenant_id: int,
    *,
    customer_id: int,
    warehouse_id: int,
    items: list[dict],
) -> dict:
    response = client.post(
        "/api/v1/sales-orders",
        json={
            "customer_id": customer_id,
            "warehouse_id": warehouse_id,
            "recipient_name": "John",
            "address": "科技园 1 号",
            "items": items,
        },
        headers=auth_header(token, tenant_id),
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


def _submit_confirm(client: TestClient, token: str, tenant_id: int, order_id: int) -> None:
    header = auth_header(token, tenant_id)
    submitted = client.post(f"/api/v1/sales-orders/{order_id}/submit", headers=header)
    assert submitted.status_code == 200, submitted.text
    confirmed = client.post(f"/api/v1/sales-orders/{order_id}/confirm", headers=header)
    assert confirmed.status_code == 200, confirmed.text


def _create_po(
    client: TestClient,
    token: str,
    tenant_id: int,
    *,
    supplier_id: int,
    warehouse_id: int,
    items: list[dict],
) -> dict:
    response = client.post(
        "/api/v1/purchase-orders",
        json={
            "supplier_id": supplier_id,
            "warehouse_id": warehouse_id,
            "expected_arrival_date": "2026-10-20",
            "items": items,
        },
        headers=auth_header(token, tenant_id),
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


def _today_range() -> tuple[str, str]:
    today = datetime.now().date().isoformat()
    return today, today


def test_analytics_empty_and_date_validation(client: TestClient) -> None:
    owner, _ = register_and_login(client, "an-empty@example.com")
    tenant_id = _tenant(client, owner, "AnEmpty", "an-empty")
    header = auth_header(owner, tenant_id)
    start, end = _today_range()
    empty = client.get(
        "/api/v1/analytics/sales/summary",
        params={"start_date": start, "end_date": end},
        headers=header,
    )
    assert empty.status_code == 200, empty.text
    data = empty.json()["data"]
    assert data["order_count"] == 0
    assert data["gross_sales_amount"] == 0
    assert data["refund_amount"] == 0
    assert data["net_sales_amount"] == 0
    assert data["average_order_value"] == 0
    assert data["return_rate"] == 0
    trend = client.get(
        "/api/v1/analytics/sales/trend",
        params={"start_date": start, "end_date": end},
        headers=header,
    )
    assert trend.status_code == 200
    assert trend.json()["data"][0]["date"] == start
    assert trend.json()["data"][0]["order_count"] == 0
    bad = client.get(
        "/api/v1/analytics/sales/summary",
        params={"start_date": "2026-10-12", "end_date": "2026-10-01"},
        headers=header,
    )
    assert bad.status_code == 400
    assert bad.json()["data"]["error"] == "START_AFTER_END"


def test_sales_purchase_inventory_after_sale_口径(client: TestClient) -> None:
    owner, _ = register_and_login(client, "an-kpi@example.com")
    tenant_id = _tenant(client, owner, "AnKpi", "an-kpi")
    header = auth_header(owner, tenant_id)
    other_owner, _ = register_and_login(client, "an-kpi-b@example.com")
    other_tenant = _tenant(client, other_owner, "AnKpiB", "an-kpi-b")
    other_header = auth_header(other_owner, other_tenant)

    warehouse = _warehouse(client, owner, tenant_id, "深圳仓")
    product = _product(
        client,
        owner,
        tenant_id,
        "手机",
        [
            {"name": "黑", "spec_values": {"color": "黑"}},
            {"name": "白", "spec_values": {"color": "白"}},
        ],
    )
    sku_a = product["skus"][0]["id"]
    sku_b = product["skus"][1]["id"]
    _init_stock(client, owner, tenant_id, warehouse["id"], sku_a, 100)
    _init_stock(client, owner, tenant_id, warehouse["id"], sku_b, 10)
    alice = _customer(client, owner, tenant_id, "Alice")
    bob = _customer(client, owner, tenant_id, "Bob")

    other_wh = _warehouse(client, other_owner, other_tenant, "外仓")
    other_product = _product(
        client, other_owner, other_tenant, "平板", [{"name": "默认", "spec_values": {}}]
    )
    other_sku = other_product["skus"][0]["id"]
    _init_stock(client, other_owner, other_tenant, other_wh["id"], other_sku, 999)
    other_cus = _customer(client, other_owner, other_tenant, "Other")
    other_order = _create_order(
        client,
        other_owner,
        other_tenant,
        customer_id=other_cus["id"],
        warehouse_id=other_wh["id"],
        items=[{"sku_id": other_sku, "quantity": 5, "unit_price": 1000}],
    )
    _submit_confirm(client, other_owner, other_tenant, other_order["id"])

    valid_a = _create_order(
        client,
        owner,
        tenant_id,
        customer_id=alice["id"],
        warehouse_id=warehouse["id"],
        items=[{"sku_id": sku_a, "quantity": 2, "unit_price": 100}],
    )
    _submit_confirm(client, owner, tenant_id, valid_a["id"])
    valid_b = _create_order(
        client,
        owner,
        tenant_id,
        customer_id=bob["id"],
        warehouse_id=warehouse["id"],
        items=[
            {"sku_id": sku_a, "quantity": 3, "unit_price": 100},
            {"sku_id": sku_b, "quantity": 1, "unit_price": 50},
        ],
    )
    _submit_confirm(client, owner, tenant_id, valid_b["id"])
    _create_order(
        client,
        owner,
        tenant_id,
        customer_id=alice["id"],
        warehouse_id=warehouse["id"],
        items=[{"sku_id": sku_a, "quantity": 9, "unit_price": 100}],
    )
    cancelled = _create_order(
        client,
        owner,
        tenant_id,
        customer_id=alice["id"],
        warehouse_id=warehouse["id"],
        items=[{"sku_id": sku_a, "quantity": 4, "unit_price": 100}],
    )
    client.post(f"/api/v1/sales-orders/{cancelled['id']}/submit", headers=header)
    client.post(
        f"/api/v1/sales-orders/{cancelled['id']}/cancel",
        json={"reason": "不要了"},
        headers=header,
    )

    supplier = _supplier(client, owner, tenant_id, "华南供应")
    valid_po = _create_po(
        client,
        owner,
        tenant_id,
        supplier_id=supplier["id"],
        warehouse_id=warehouse["id"],
        items=[{"sku_id": sku_a, "quantity": 8, "unit_price": 40}],
    )
    client.post(f"/api/v1/purchase-orders/{valid_po['id']}/submit", headers=header)
    client.post(f"/api/v1/purchase-orders/{valid_po['id']}/approve", headers=header)
    draft_po = _create_po(
        client,
        owner,
        tenant_id,
        supplier_id=supplier["id"],
        warehouse_id=warehouse["id"],
        items=[{"sku_id": sku_a, "quantity": 99, "unit_price": 40}],
    )
    rejected_po = _create_po(
        client,
        owner,
        tenant_id,
        supplier_id=supplier["id"],
        warehouse_id=warehouse["id"],
        items=[{"sku_id": sku_a, "quantity": 7, "unit_price": 40}],
    )
    client.post(f"/api/v1/purchase-orders/{rejected_po['id']}/submit", headers=header)
    client.post(
        f"/api/v1/purchase-orders/{rejected_po['id']}/reject",
        json={"reason": "价格不对"},
        headers=header,
    )

    receipt = client.post(
        "/api/v1/purchase-receipts",
        json={
            "purchase_order_id": valid_po["id"],
            "items": [
                {"purchase_order_item_id": valid_po["items"][0]["id"], "received_quantity": 5}
            ],
        },
        headers=header,
    )
    assert receipt.status_code == 200, receipt.text
    confirmed_receipt = client.post(
        f"/api/v1/purchase-receipts/{receipt.json()['data']['id']}/confirm",
        headers=header,
    )
    assert confirmed_receipt.status_code == 200, confirmed_receipt.text

    user_id = _user_id(client, owner, tenant_id)
    now = datetime.now()
    with SessionLocal() as session:
        session.add(
            AfterSaleOrder(
                tenant_id=tenant_id,
                after_sale_no="AS2026000001",
                sales_order_id=valid_a["id"],
                customer_id=alice["id"],
                type=AfterSaleType.REFUND_ONLY.value,
                status=AfterSaleStatus.WAITING_REFUND.value,
                reason="质量问题",
                currency_code="CNY",
                requested_refund_amount=Decimal("50.00"),
                requested_by=user_id,
            )
        )
        session.add(
            AfterSaleOrder(
                tenant_id=tenant_id,
                after_sale_no="AS2026000002",
                sales_order_id=valid_a["id"],
                customer_id=alice["id"],
                type=AfterSaleType.REFUND_ONLY.value,
                status=AfterSaleStatus.WAITING_REFUND.value,
                reason="少件",
                currency_code="CNY",
                requested_refund_amount=Decimal("20.00"),
                requested_by=user_id,
            )
        )
        session.flush()
        after_sales = list(
            session.scalars(select(AfterSaleOrder).where(AfterSaleOrder.tenant_id == tenant_id))
        )
        session.add(
            AfterSaleItem(
                tenant_id=tenant_id,
                after_sale_order_id=after_sales[0].id,
                sales_order_item_id=valid_a["items"][0]["id"],
                sku_id=sku_a,
                original_quantity=2,
                return_quantity=1,
                requested_refund_amount=Decimal("50.00"),
            )
        )
        session.add(
            RefundRecord(
                tenant_id=tenant_id,
                after_sale_order_id=after_sales[0].id,
                refund_no="RF2026000001",
                amount=Decimal("30.00"),
                status=RefundRecordStatus.SUCCESS.value,
                refunded_at=now,
                created_by=user_id,
            )
        )
        session.add(
            RefundRecord(
                tenant_id=tenant_id,
                after_sale_order_id=after_sales[1].id,
                refund_no="RF2026000002",
                amount=Decimal("20.00"),
                status=RefundRecordStatus.PENDING.value,
                created_by=user_id,
            )
        )
        session.add(
            RefundRecord(
                tenant_id=tenant_id,
                after_sale_order_id=after_sales[1].id,
                refund_no="RF2026000003",
                amount=Decimal("15.00"),
                status=RefundRecordStatus.FAILED.value,
                created_by=user_id,
            )
        )
        cancelled_as = AfterSaleOrder(
            tenant_id=tenant_id,
            after_sale_no="AS2026000003",
            sales_order_id=valid_b["id"],
            customer_id=bob["id"],
            type=AfterSaleType.RETURN_ONLY.value,
            status=AfterSaleStatus.CANCELLED.value,
            reason="取消",
            currency_code="CNY",
            requested_refund_amount=Decimal("0"),
            requested_by=user_id,
        )
        session.add(cancelled_as)
        session.add(
            PurchaseReturn(
                tenant_id=tenant_id,
                purchase_return_no="PRT2026000001",
                supplier_id=supplier["id"],
                purchase_order_id=valid_po["id"],
                warehouse_id=warehouse["id"],
                status=PurchaseReturnStatus.WAITING_OUTBOUND.value,
                settlement_type="REFUND",
                reason="质量",
                requested_refund_amount=Decimal("80.00"),
                created_by=user_id,
            )
        )
        session.flush()
        pr = session.scalars(
            select(PurchaseReturn).where(PurchaseReturn.tenant_id == tenant_id)
        ).one()
        inv = session.scalars(
            select(Inventory).where(
                Inventory.tenant_id == tenant_id,
                Inventory.sku_id == sku_a,
            )
        ).one()
        session.add(
            InventoryTransaction(
                tenant_id=tenant_id,
                warehouse_id=warehouse["id"],
                sku_id=sku_a,
                inventory_id=inv.id,
                type=InventoryTransactionType.PURCHASE_RETURN_OUTBOUND.value,
                change_quantity=-2,
                before_quantity=inv.quantity,
                after_quantity=inv.quantity,
                before_reserved_quantity=inv.reserved_quantity,
                after_reserved_quantity=inv.reserved_quantity,
                reference_type=PURCHASE_RETURN_REFERENCE,
                reference_id=pr.id,
            )
        )
        session.add(
            SupplierRefundRecord(
                tenant_id=tenant_id,
                purchase_return_id=pr.id,
                refund_no="SRF2026000001",
                amount=Decimal("40.00"),
                status=SupplierRefundRecordStatus.SUCCESS.value,
                received_at=now,
                created_by=user_id,
            )
        )
        session.add(
            SupplierRefundRecord(
                tenant_id=tenant_id,
                purchase_return_id=pr.id,
                refund_no="SRF2026000002",
                amount=Decimal("99.00"),
                status=SupplierRefundRecordStatus.PENDING.value,
                created_by=user_id,
            )
        )
        session.commit()

    start, end = _today_range()
    sales = client.get(
        "/api/v1/analytics/sales/summary",
        params={"start_date": start, "end_date": end},
        headers=header,
    )
    assert sales.status_code == 200, sales.text
    s = sales.json()["data"]
    assert s["order_count"] == 2
    assert s["gross_sales_amount"] == 550.0
    assert s["refund_amount"] == 30.0
    assert s["net_sales_amount"] == 520.0
    assert s["average_order_value"] == 275.0
    assert s["cancelled_order_count"] == 1
    assert s["draft_order_count"] == 1
    assert s["after_sale_sales_order_count"] == 1
    assert s["return_rate"] == 0.5

    other_sales = client.get(
        "/api/v1/analytics/sales/summary",
        params={"start_date": start, "end_date": end},
        headers=other_header,
    ).json()["data"]
    assert other_sales["gross_sales_amount"] == 5000.0
    assert other_sales["order_count"] == 1

    top_skus = client.get(
        "/api/v1/analytics/sales/top-skus",
        params={"start_date": start, "end_date": end},
        headers=header,
    ).json()["data"]
    assert top_skus[0]["sku_id"] == sku_a
    assert top_skus[0]["sales_quantity"] == 5
    assert top_skus[0]["sales_amount"] == 500.0

    top_customers = client.get(
        "/api/v1/analytics/sales/top-customers",
        params={"start_date": start, "end_date": end},
        headers=header,
    ).json()["data"]
    assert top_customers[0]["customer_name"] == "Bob"
    assert top_customers[0]["sales_amount"] == 350.0
    alice_row = next(item for item in top_customers if item["customer_name"] == "Alice")
    assert alice_row["refund_amount"] == 30.0
    assert alice_row["net_sales_amount"] == 170.0

    purchases = client.get(
        "/api/v1/analytics/purchases/summary",
        params={"start_date": start, "end_date": end},
        headers=header,
    ).json()["data"]
    assert purchases["purchase_order_count"] == 1
    assert purchases["purchase_amount"] == 320.0
    assert purchases["received_quantity"] == 5
    assert purchases["pending_receipt_order_count"] == 1
    assert purchases["purchase_return_quantity"] == 2
    assert purchases["supplier_refund_amount"] == 40.0
    assert draft_po["id"]
    assert purchases["purchase_return_order_count"] == 1

    top_suppliers = client.get(
        "/api/v1/analytics/purchases/top-suppliers",
        params={"start_date": start, "end_date": end},
        headers=header,
    ).json()["data"]
    assert top_suppliers[0]["supplier_name"] == "华南供应"
    assert top_suppliers[0]["purchase_amount"] == 320.0
    assert top_suppliers[0]["received_quantity"] == 5
    assert top_suppliers[0]["purchase_return_quantity"] == 2

    inventory = client.get("/api/v1/analytics/inventory/summary", headers=header).json()["data"]
    assert inventory["total_quantity"] > 0
    assert inventory["total_available_quantity"] == (
        inventory["total_quantity"] - inventory["total_reserved_quantity"]
    )
    low5 = client.get(
        "/api/v1/analytics/inventory/summary",
        params={"low_stock_threshold": 5},
        headers=header,
    ).json()["data"]
    low50 = client.get(
        "/api/v1/analytics/inventory/summary",
        params={"low_stock_threshold": 50},
        headers=header,
    ).json()["data"]
    assert low50["low_stock_sku_count"] >= low5["low_stock_sku_count"]

    by_wh = client.get(
        "/api/v1/analytics/inventory/by-warehouse",
        params={"start_date": start, "end_date": end},
        headers=header,
    ).json()["data"]
    assert by_wh[0]["warehouse_name"] == "深圳仓"
    assert by_wh[0]["available_quantity"] == by_wh[0]["quantity"] - by_wh[0]["reserved_quantity"]

    after = client.get(
        "/api/v1/analytics/after-sales/summary",
        params={"start_date": start, "end_date": end},
        headers=header,
    ).json()["data"]
    assert after["after_sale_count"] == 2
    assert after["after_sale_sales_order_count"] == 1
    assert after["after_sale_rate"] == 0.5
    assert after["refund_amount"] == 30.0

    yesterday = (datetime.now() - timedelta(days=1)).date().isoformat()
    with SessionLocal() as session:
        order_row = session.get(SalesOrder, valid_a["id"])
        assert order_row is not None
        order_row.created_at = datetime.combine(
            datetime.now().date() - timedelta(days=1), datetime.min.time()
        ) + timedelta(hours=23, minutes=59, seconds=59)
        session.commit()
    today_only = client.get(
        "/api/v1/analytics/sales/summary",
        params={"start_date": start, "end_date": end},
        headers=header,
    ).json()["data"]
    assert today_only["order_count"] == 1
    yday = client.get(
        "/api/v1/analytics/sales/summary",
        params={"start_date": yesterday, "end_date": yesterday},
        headers=header,
    ).json()["data"]
    assert yday["order_count"] == 1

    csv_resp = client.get(
        "/api/v1/analytics/sales/trend.csv",
        params={"start_date": start, "end_date": end},
        headers=header,
    )
    assert csv_resp.status_code == 200
    assert "销售金额" in csv_resp.text

    viewer_role = _roles(client, owner, tenant_id)["VIEWER"]
    operator_role = _roles(client, owner, tenant_id)["OPERATOR"]
    warehouse_role = _roles(client, owner, tenant_id)["WAREHOUSE"]
    viewer = _add_member(client, owner, tenant_id, "an-view@example.com", [viewer_role["id"]])
    operator = _add_member(client, owner, tenant_id, "an-op@example.com", [operator_role["id"]])
    warehouse_user = _add_member(
        client, owner, tenant_id, "an-wh@example.com", [warehouse_role["id"]]
    )
    assert (
        client.get(
            "/api/v1/analytics/sales/summary", headers=auth_header(viewer, tenant_id)
        ).status_code
        == 200
    )
    assert (
        client.get(
            "/api/v1/analytics/inventory/summary", headers=auth_header(operator, tenant_id)
        ).status_code
        == 403
    )
    assert (
        client.get(
            "/api/v1/analytics/sales/summary", headers=auth_header(warehouse_user, tenant_id)
        ).status_code
        == 403
    )
    assert (
        client.get(
            "/api/v1/analytics/inventory/summary", headers=auth_header(warehouse_user, tenant_id)
        ).status_code
        == 200
    )

    none_role = client.post(
        "/api/v1/roles",
        json={"name": "无报表", "code": "NO_ANALYTICS", "description": "none"},
        headers=header,
    )
    assert none_role.status_code == 200, none_role.text
    member = _add_member(
        client, owner, tenant_id, "an-none@example.com", [none_role.json()["data"]["id"]]
    )
    denied = client.get("/api/v1/analytics/overview", headers=auth_header(member, tenant_id))
    assert denied.status_code == 403


def test_zero_available_and_transaction_types(client: TestClient) -> None:
    owner, _ = register_and_login(client, "an-inv@example.com")
    tenant_id = _tenant(client, owner, "AnInv", "an-inv")
    header = auth_header(owner, tenant_id)
    warehouse = _warehouse(client, owner, tenant_id, "仓A")
    product = _product(client, owner, tenant_id, "配件", [{"name": "默认", "spec_values": {}}])
    sku_id = product["skus"][0]["id"]
    _init_stock(client, owner, tenant_id, warehouse["id"], sku_id, 10)
    customer = _customer(client, owner, tenant_id, "C1")
    order = _create_order(
        client,
        owner,
        tenant_id,
        customer_id=customer["id"],
        warehouse_id=warehouse["id"],
        items=[{"sku_id": sku_id, "quantity": 10, "unit_price": 1}],
    )
    _submit_confirm(client, owner, tenant_id, order["id"])
    summary = client.get("/api/v1/analytics/inventory/summary", headers=header).json()["data"]
    assert summary["total_quantity"] == 10
    assert summary["total_reserved_quantity"] == 10
    assert summary["total_available_quantity"] == 0
    assert summary["zero_stock_sku_count"] >= 1
    start, end = _today_range()
    types = client.get(
        "/api/v1/analytics/inventory/transactions-by-type",
        params={"start_date": start, "end_date": end},
        headers=header,
    ).json()["data"]
    type_map = {item["type"]: item["quantity"] for item in types}
    assert "INITIALIZE" in type_map
    assert "RESERVE" in type_map
    explain = SessionLocal()
    try:
        result = explain.execute(
            text("EXPLAIN SELECT tenant_id, created_at FROM sales_orders WHERE tenant_id = :tid"),
            {"tid": tenant_id},
        )
        rows = [dict(row._mapping) for row in result]
        assert rows
    finally:
        explain.close()

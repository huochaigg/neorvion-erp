"""采购退货、退货出库、供应商退款。不改 PurchaseOrderItem.quantity / received_quantity。"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from app.core.exceptions import AppError
from app.core.permissions import PermissionCode
from app.core.tenant import TenantContext
from app.db.session import SessionLocal
from app.models.tenant import MemberRole
from app.services.purchase_return import PurchaseReturnService
from app.services.purchase_return_outbound import PurchaseReturnOutboundService
from fastapi.testclient import TestClient

from tests.helpers.auth_api import auth_header, register_and_login
from tests.test_purchase import (
    _add_member,
    _create_po,
    _create_product,
    _create_supplier,
    _create_tenant,
    _create_warehouse,
    _roles,
)
from tests.test_sales_orders import _customer, _member_id, _order


def _header(token: str, tenant_id: int) -> dict[str, str]:
    return auth_header(token, tenant_id)


def _inventory_row(client: TestClient, data: dict, sku_id: int) -> dict:
    items = client.get(
        "/api/v1/inventory",
        params={"warehouse_id": data["warehouse_id"]},
        headers=data["header"],
    ).json()["data"]["items"]
    return next(row for row in items if row["sku_id"] == sku_id)


def _approve_po(client: TestClient, token: str, tenant_id: int, order_id: int) -> dict:
    header = _header(token, tenant_id)
    submitted = client.post(f"/api/v1/purchase-orders/{order_id}/submit", headers=header)
    assert submitted.status_code == 200, submitted.text
    approved = client.post(f"/api/v1/purchase-orders/{order_id}/approve", headers=header)
    assert approved.status_code == 200, approved.text
    return approved.json()["data"]


def _confirm_receipt(client: TestClient, token: str, tenant_id: int, order: dict, qty: int | None = None) -> dict:
    header = _header(token, tenant_id)
    items = [
        {
            "purchase_order_item_id": row["id"],
            "received_quantity": qty if qty is not None else row["quantity"],
        }
        for row in order["items"]
    ]
    draft = client.post(
        "/api/v1/purchase-receipts",
        json={"purchase_order_id": order["id"], "items": items},
        headers=header,
    )
    assert draft.status_code == 200, draft.text
    confirmed = client.post(f"/api/v1/purchase-receipts/{draft.json()['data']['id']}/confirm", headers=header)
    assert confirmed.status_code == 200, confirmed.text
    return client.get(f"/api/v1/purchase-orders/{order['id']}", headers=header).json()["data"]


def _received_po(
    client: TestClient,
    token: str,
    tenant_id: int,
    *,
    ordered: int = 100,
    received: int = 100,
    extra_skus: list[dict] | None = None,
    sku_code: str = "PRT-A",
) -> dict:
    supplier = _create_supplier(client, token, tenant_id, "退货供应商")
    warehouse = _create_warehouse(client, token, tenant_id, "退货仓")
    skus = [{"sku_code": sku_code, "name": "A", "spec_values": {}}, *(extra_skus or [])]
    product = _create_product(client, token, tenant_id, f"退货货-{sku_code}", skus)
    items = [{"sku_id": sku["id"], "quantity": ordered, "unit_price": 10} for sku in product["skus"]]
    created = _create_po(
        client,
        token,
        tenant_id,
        supplier_id=supplier["id"],
        warehouse_id=warehouse["id"],
        items=items,
    )
    assert created.status_code == 200, created.text
    waiting = _approve_po(client, token, tenant_id, created.json()["data"]["id"])
    order = _confirm_receipt(client, token, tenant_id, waiting, received)
    return {
        "header": _header(token, tenant_id),
        "order": order,
        "order_id": order["id"],
        "warehouse_id": warehouse["id"],
        "supplier_id": supplier["id"],
        "sku_ids": [sku["id"] for sku in product["skus"]],
    }


def _create_pr(client: TestClient, data: dict, payload: dict):
    return client.post("/api/v1/purchase-returns", json=payload, headers=data["header"])


def _submit_approve(client: TestClient, data: dict, return_id: int, items: list[dict] | None = None) -> dict:
    submitted = client.post(f"/api/v1/purchase-returns/{return_id}/submit", headers=data["header"])
    assert submitted.status_code == 200, submitted.text
    approved = client.post(
        f"/api/v1/purchase-returns/{return_id}/approve",
        json={"items": items or []},
        headers=data["header"],
    )
    assert approved.status_code == 200, approved.text
    return approved.json()["data"]


def test_received_po_can_create_draft_and_unreceived_cannot(client: TestClient) -> None:
    owner, _ = register_and_login(client, "prt-create@example.com")
    tenant_id = _create_tenant(client, owner, "PrtCreate", "prt-create")
    data = _received_po(client, owner, tenant_id, ordered=100, received=60)
    item = data["order"]["items"][0]
    created = _create_pr(
        client,
        data,
        {
            "purchase_order_id": data["order_id"],
            "settlement_type": "REFUND",
            "reason": "质量问题",
            "items": [
                {
                    "purchase_order_item_id": item["id"],
                    "requested_return_quantity": 20,
                    "requested_refund_amount": "200.00",
                }
            ],
        },
    )
    assert created.status_code == 200, created.text
    body = created.json()["data"]
    assert body["purchase_return_no"].startswith("PRT")
    assert body["status"] == "DRAFT"
    preview = client.get(
        "/api/v1/purchase-returns/preview",
        params={"purchase_order_id": data["order_id"]},
        headers=data["header"],
    ).json()["data"]
    assert preview["items"][0]["received_quantity"] == 60
    assert preview["items"][0]["returnable_quantity"] == 60
    assert preview["items"][0]["ordered_quantity"] == 100

    waiting = _create_supplier(client, owner, tenant_id, "未收供应商")
    warehouse = _create_warehouse(client, owner, tenant_id, "未收仓")
    product = _create_product(
        client,
        owner,
        tenant_id,
        "未收货",
        [{"sku_code": "UNRCV", "name": "U", "spec_values": {}}],
    )
    po = _create_po(
        client,
        owner,
        tenant_id,
        supplier_id=waiting["id"],
        warehouse_id=warehouse["id"],
        items=[{"sku_id": product["skus"][0]["id"], "quantity": 10}],
    )
    approved = _approve_po(client, owner, tenant_id, po.json()["data"]["id"])
    refused = _create_pr(
        client,
        data,
        {
            "purchase_order_id": approved["id"],
            "settlement_type": "NO_REFUND",
            "reason": "未收不能退",
            "items": [
                {
                    "purchase_order_item_id": approved["items"][0]["id"],
                    "requested_return_quantity": 1,
                }
            ],
        },
    )
    assert refused.status_code == 400
    assert refused.json()["data"]["error"] == "PURCHASE_RETURN_ORDER_NOT_ELIGIBLE"


def test_returnable_uses_received_not_ordered_and_cannot_over_return(client: TestClient) -> None:
    owner, _ = register_and_login(client, "prt-cap@example.com")
    tenant_id = _create_tenant(client, owner, "PrtCap", "prt-cap")
    data = _received_po(client, owner, tenant_id, ordered=100, received=60)
    item = data["order"]["items"][0]
    over = _create_pr(
        client,
        data,
        {
            "purchase_order_id": data["order_id"],
            "settlement_type": "NO_REFUND",
            "reason": "超量",
            "items": [{"purchase_order_item_id": item["id"], "requested_return_quantity": 61}],
        },
    )
    assert over.status_code == 400
    assert over.json()["data"]["error"] == "PURCHASE_RETURN_EXCEEDS_RETURNABLE"
    first = _create_pr(
        client,
        data,
        {
            "purchase_order_id": data["order_id"],
            "settlement_type": "NO_REFUND",
            "reason": "第一次",
            "items": [{"purchase_order_item_id": item["id"], "requested_return_quantity": 40}],
        },
    )
    assert first.status_code == 200, first.text
    _submit_approve(client, data, first.json()["data"]["id"])
    second = _create_pr(
        client,
        data,
        {
            "purchase_order_id": data["order_id"],
            "settlement_type": "NO_REFUND",
            "reason": "第二次超量",
            "items": [{"purchase_order_item_id": item["id"], "requested_return_quantity": 30}],
        },
    )
    assert second.status_code == 400
    ok_second = _create_pr(
        client,
        data,
        {
            "purchase_order_id": data["order_id"],
            "settlement_type": "NO_REFUND",
            "reason": "第二次刚好",
            "items": [{"purchase_order_item_id": item["id"], "requested_return_quantity": 20}],
        },
    )
    assert ok_second.status_code == 200, ok_second.text


def test_multi_sku_create_and_cross_tenant_rejected(client: TestClient) -> None:
    owner, _ = register_and_login(client, "prt-multi@example.com")
    tenant_id = _create_tenant(client, owner, "PrtMulti", "prt-multi")
    data = _received_po(
        client,
        owner,
        tenant_id,
        ordered=10,
        received=10,
        extra_skus=[{"sku_code": "PRT-B", "name": "B", "spec_values": {}}],
    )
    created = _create_pr(
        client,
        data,
        {
            "purchase_order_id": data["order_id"],
            "settlement_type": "NO_REFUND",
            "reason": "多 SKU",
            "items": [
                {"purchase_order_item_id": data["order"]["items"][0]["id"], "requested_return_quantity": 3},
                {"purchase_order_item_id": data["order"]["items"][1]["id"], "requested_return_quantity": 4},
            ],
        },
    )
    assert created.status_code == 200, created.text
    assert created.json()["data"]["sku_count"] == 2
    other, _ = register_and_login(client, "prt-multi-b@example.com")
    other_tenant = _create_tenant(client, other, "PrtMultiB", "prt-multi-b")
    hidden = client.get(
        f"/api/v1/purchase-returns/{created.json()['data']['id']}",
        headers=_header(other, other_tenant),
    )
    assert hidden.status_code == 404


def test_state_machine_submit_approve_reject_cancel(client: TestClient) -> None:
    owner, _ = register_and_login(client, "prt-sm@example.com")
    tenant_id = _create_tenant(client, owner, "PrtSm", "prt-sm")
    data = _received_po(client, owner, tenant_id, ordered=10, received=10)
    item = data["order"]["items"][0]
    draft = _create_pr(
        client,
        data,
        {
            "purchase_order_id": data["order_id"],
            "settlement_type": "NO_REFUND",
            "reason": "状态机",
            "items": [{"purchase_order_item_id": item["id"], "requested_return_quantity": 2}],
        },
    ).json()["data"]
    submitted = client.post(f"/api/v1/purchase-returns/{draft['id']}/submit", headers=data["header"])
    assert submitted.json()["data"]["status"] == "PENDING_APPROVAL"
    again = client.post(f"/api/v1/purchase-returns/{draft['id']}/submit", headers=data["header"])
    assert again.status_code == 400
    approved = client.post(f"/api/v1/purchase-returns/{draft['id']}/approve", json={}, headers=data["header"])
    assert approved.json()["data"]["status"] == "WAITING_OUTBOUND"
    illegal = client.post(f"/api/v1/purchase-returns/{draft['id']}/cancel", headers=data["header"])
    assert illegal.status_code == 400

    rejected_draft = _create_pr(
        client,
        data,
        {
            "purchase_order_id": data["order_id"],
            "settlement_type": "NO_REFUND",
            "reason": "待拒",
            "items": [{"purchase_order_item_id": item["id"], "requested_return_quantity": 2}],
        },
    ).json()["data"]
    client.post(f"/api/v1/purchase-returns/{rejected_draft['id']}/submit", headers=data["header"])
    rejected = client.post(
        f"/api/v1/purchase-returns/{rejected_draft['id']}/reject",
        json={"reason": "证据不足"},
        headers=data["header"],
    )
    assert rejected.json()["data"]["status"] == "REJECTED"
    retry = _create_pr(
        client,
        data,
        {
            "purchase_order_id": data["order_id"],
            "settlement_type": "NO_REFUND",
            "reason": "拒绝后释放占用",
            "items": [{"purchase_order_item_id": item["id"], "requested_return_quantity": 8}],
        },
    )
    assert retry.status_code == 200, retry.text

    cancel_draft = _create_pr(
        client,
        data,
        {
            "purchase_order_id": data["order_id"],
            "settlement_type": "NO_REFUND",
            "reason": "取消草稿",
            "items": [{"purchase_order_item_id": item["id"], "requested_return_quantity": 1}],
        },
    ).json()["data"]
    cancelled = client.post(f"/api/v1/purchase-returns/{cancel_draft['id']}/cancel", headers=data["header"])
    assert cancelled.json()["data"]["status"] == "CANCELLED"


def test_outbound_deducts_quantity_not_reserved_and_writes_tx(client: TestClient) -> None:
    owner, _ = register_and_login(client, "prt-ob@example.com")
    tenant_id = _create_tenant(client, owner, "PrtOb", "prt-ob")
    data = _received_po(client, owner, tenant_id, ordered=20, received=20)
    sku_id = data["order"]["items"][0]["sku_id"]
    listed = _inventory_row(client, data, sku_id)
    inventory_id = listed["id"]
    reserved_before = listed["reserved_quantity"]
    qty_before = listed["quantity"]
    item = data["order"]["items"][0]
    created = _create_pr(
        client,
        data,
        {
            "purchase_order_id": data["order_id"],
            "settlement_type": "NO_REFUND",
            "reason": "出库",
            "items": [{"purchase_order_item_id": item["id"], "requested_return_quantity": 10}],
        },
    ).json()["data"]
    approved = _submit_approve(client, data, created["id"])
    outbound = client.post(
        f"/api/v1/purchase-returns/{approved['id']}/outbounds",
        json={"items": [{"purchase_return_item_id": approved["items"][0]["id"], "quantity": 6}]},
        headers=data["header"],
    )
    assert outbound.status_code == 200, outbound.text
    assert outbound.json()["data"]["outbound_no"].startswith("PRO")
    assert outbound.json()["data"]["status"] == "DRAFT"
    mid = client.get(f"/api/v1/inventory/{inventory_id}", headers=data["header"]).json()["data"]
    assert mid["quantity"] == qty_before
    confirmed = client.post(
        f"/api/v1/purchase-return-outbounds/{outbound.json()['data']['id']}/confirm",
        headers=data["header"],
    )
    assert confirmed.status_code == 200, confirmed.text
    after = client.get(f"/api/v1/inventory/{inventory_id}", headers=data["header"]).json()["data"]
    assert after["quantity"] == qty_before - 6
    assert after["reserved_quantity"] == reserved_before
    txs = client.get(
        "/api/v1/inventory/transactions",
        params={"type": "PURCHASE_RETURN_OUTBOUND"},
        headers=data["header"],
    ).json()["data"]["items"]
    assert txs[0]["change_quantity"] == -6
    assert txs[0]["reference_type"] == "PURCHASE_RETURN"
    assert txs[0]["reference_id"] == approved["id"]
    again = client.post(
        f"/api/v1/purchase-return-outbounds/{outbound.json()['data']['id']}/confirm",
        headers=data["header"],
    )
    assert again.status_code == 400
    assert again.json()["data"]["error"] == "PURCHASE_RETURN_OUTBOUND_ALREADY_CONFIRMED"
    ret = client.get(f"/api/v1/purchase-returns/{approved['id']}", headers=data["header"]).json()["data"]
    assert ret["status"] == "PARTIALLY_RETURNED"
    second = client.post(
        f"/api/v1/purchase-returns/{approved['id']}/outbounds",
        json={"items": [{"purchase_return_item_id": approved["items"][0]["id"], "quantity": 4}]},
        headers=data["header"],
    ).json()["data"]
    client.post(f"/api/v1/purchase-return-outbounds/{second['id']}/confirm", headers=data["header"])
    done = client.get(f"/api/v1/purchase-returns/{approved['id']}", headers=data["header"]).json()["data"]
    assert done["status"] == "COMPLETED"
    po = client.get(f"/api/v1/purchase-orders/{data['order_id']}", headers=data["header"]).json()["data"]
    assert po["items"][0]["quantity"] == 20
    assert po["items"][0]["received_quantity"] == 20
    assert po["items"][0]["returned_quantity"] == 10
    assert po["status"] in {"RECEIVED", "PARTIALLY_RECEIVED"}


def test_available_shortage_and_multi_sku_rollback(client: TestClient) -> None:
    owner, _ = register_and_login(client, "prt-av@example.com")
    tenant_id = _create_tenant(client, owner, "PrtAv", "prt-av")
    data = _received_po(
        client,
        owner,
        tenant_id,
        ordered=10,
        received=10,
        extra_skus=[{"sku_code": "PRT-C", "name": "C", "spec_values": {}}],
    )
    created = _create_pr(
        client,
        data,
        {
            "purchase_order_id": data["order_id"],
            "settlement_type": "NO_REFUND",
            "reason": "可用不足",
            "items": [
                {"purchase_order_item_id": data["order"]["items"][0]["id"], "requested_return_quantity": 10},
                {"purchase_order_item_id": data["order"]["items"][1]["id"], "requested_return_quantity": 10},
            ],
        },
    ).json()["data"]
    approved = _submit_approve(client, data, created["id"])
    customer = _customer(client, owner, tenant_id, "占库存客户")
    sku_id = data["order"]["items"][0]["sku_id"]
    inv = _inventory_row(client, data, sku_id)
    before = inv["quantity"]
    sales = _order(
        client,
        owner,
        tenant_id,
        customer_id=customer["id"],
        warehouse_id=data["warehouse_id"],
        items=[{"sku_id": sku_id, "quantity": 8, "unit_price": 10}],
    )
    assert sales.status_code == 200, sales.text
    sales_id = sales.json()["data"]["id"]
    submitted = client.post(f"/api/v1/sales-orders/{sales_id}/submit", headers=data["header"])
    assert submitted.status_code == 200, submitted.text
    confirmed_sales = client.post(f"/api/v1/sales-orders/{sales_id}/confirm", headers=data["header"])
    assert confirmed_sales.status_code == 200, confirmed_sales.text
    outbound = client.post(
        f"/api/v1/purchase-returns/{approved['id']}/outbounds",
        json={
            "items": [
                {"purchase_return_item_id": approved["items"][0]["id"], "quantity": 5},
                {"purchase_return_item_id": approved["items"][1]["id"], "quantity": 1},
            ]
        },
        headers=data["header"],
    ).json()["data"]
    failed = client.post(
        f"/api/v1/purchase-return-outbounds/{outbound['id']}/confirm",
        headers=data["header"],
    )
    assert failed.status_code == 400
    assert failed.json()["data"]["error"] == "INSUFFICIENT_AVAILABLE_INVENTORY"
    after = client.get(f"/api/v1/inventory/{inv['id']}", headers=data["header"]).json()["data"]
    assert after["quantity"] == before
    assert after["reserved_quantity"] == 8


def test_no_refund_completes_refund_waits_and_supplier_refund(client: TestClient) -> None:
    owner, _ = register_and_login(client, "prt-rf@example.com")
    tenant_id = _create_tenant(client, owner, "PrtRf", "prt-rf")
    data = _received_po(client, owner, tenant_id, ordered=10, received=10)
    item = data["order"]["items"][0]
    created = _create_pr(
        client,
        data,
        {
            "purchase_order_id": data["order_id"],
            "settlement_type": "REFUND",
            "reason": "要退款",
            "items": [
                {
                    "purchase_order_item_id": item["id"],
                    "requested_return_quantity": 4,
                    "requested_refund_amount": "40.00",
                }
            ],
        },
    ).json()["data"]
    approved = _submit_approve(
        client,
        data,
        created["id"],
        items=[
            {
                "item_id": created["items"][0]["id"],
                "approved_return_quantity": 4,
                "approved_refund_amount": "40.00",
            }
        ],
    )
    outbound = client.post(
        f"/api/v1/purchase-returns/{approved['id']}/outbounds",
        json={"items": [{"purchase_return_item_id": approved["items"][0]["id"], "quantity": 4}]},
        headers=data["header"],
    ).json()["data"]
    client.post(f"/api/v1/purchase-return-outbounds/{outbound['id']}/confirm", headers=data["header"])
    waiting = client.get(f"/api/v1/purchase-returns/{approved['id']}", headers=data["header"]).json()["data"]
    assert waiting["status"] == "WAITING_REFUND"
    inv_before = _inventory_row(client, data, data["sku_ids"][0])["quantity"]
    over = client.post(
        f"/api/v1/purchase-returns/{approved['id']}/refunds",
        json={"amount": "41.00"},
        headers=data["header"],
    )
    assert over.status_code == 400
    first = client.post(
        f"/api/v1/purchase-returns/{approved['id']}/refunds",
        json={"amount": "20.00"},
        headers=data["header"],
    ).json()["data"]
    assert first["refund_no"].startswith("SRF")
    failed = client.post(
        f"/api/v1/supplier-refunds/{first['id']}/fail",
        json={"failure_reason": "银行失败"},
        headers=data["header"],
    )
    assert failed.json()["data"]["status"] == "FAILED"
    retry = client.post(
        f"/api/v1/purchase-returns/{approved['id']}/refunds",
        json={"amount": "40.00"},
        headers=data["header"],
    ).json()["data"]
    confirmed = client.post(f"/api/v1/supplier-refunds/{retry['id']}/confirm", json={}, headers=data["header"])
    assert confirmed.json()["data"]["status"] == "SUCCESS"
    again = client.post(f"/api/v1/supplier-refunds/{retry['id']}/confirm", json={}, headers=data["header"])
    assert again.status_code == 400
    assert again.json()["data"]["error"] == "SUPPLIER_REFUND_ALREADY_SUCCESS"
    done = client.get(f"/api/v1/purchase-returns/{approved['id']}", headers=data["header"]).json()["data"]
    assert done["status"] == "COMPLETED"
    inv_after = _inventory_row(client, data, data["sku_ids"][0])["quantity"]
    assert inv_after == inv_before


def test_concurrent_submit_and_confirm_outbound(client: TestClient) -> None:
    owner, user_id = register_and_login(client, "prt-cc@example.com")
    tenant_id = _create_tenant(client, owner, "PrtCc", "prt-cc")
    _, member_id = _member_id(client, owner, tenant_id)
    data = _received_po(client, owner, tenant_id, ordered=100, received=100)
    item_id = data["order"]["items"][0]["id"]
    first = _create_pr(
        client,
        data,
        {
            "purchase_order_id": data["order_id"],
            "settlement_type": "NO_REFUND",
            "reason": "并发1",
            "items": [{"purchase_order_item_id": item_id, "requested_return_quantity": 80}],
        },
    ).json()["data"]
    second = _create_pr(
        client,
        data,
        {
            "purchase_order_id": data["order_id"],
            "settlement_type": "NO_REFUND",
            "reason": "并发2",
            "items": [{"purchase_order_item_id": item_id, "requested_return_quantity": 80}],
        },
    ).json()["data"]

    def _submit(return_id: int) -> str:
        session = SessionLocal()
        try:
            PurchaseReturnService(
                session,
                TenantContext(
                    user_id=user_id,
                    tenant_id=tenant_id,
                    member_id=member_id,
                    is_owner=True,
                    role=MemberRole.OWNER.value,
                ),
            ).submit_purchase_return(return_id)
            return "ok"
        except AppError as exc:
            return str(exc.data.get("error", exc.code) if exc.data else exc.code)
        finally:
            session.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(_submit, [first["id"], second["id"]]))
    assert results.count("ok") == 1
    assert "PURCHASE_RETURN_EXCEEDS_RETURNABLE" in results

    winner_id = first["id"] if results[0] == "ok" else second["id"]
    approved = client.post(
        f"/api/v1/purchase-returns/{winner_id}/approve",
        json={},
        headers=data["header"],
    ).json()["data"]
    outbound = client.post(
        f"/api/v1/purchase-returns/{approved['id']}/outbounds",
        json={"items": [{"purchase_return_item_id": approved["items"][0]["id"], "quantity": 10}]},
        headers=data["header"],
    ).json()["data"]

    def _confirm(_: int) -> str:
        session = SessionLocal()
        try:
            PurchaseReturnOutboundService(
                session,
                TenantContext(
                    user_id=user_id,
                    tenant_id=tenant_id,
                    member_id=member_id,
                    is_owner=True,
                    role=MemberRole.OWNER.value,
                ),
            ).confirm_purchase_return_outbound(outbound["id"])
            return "ok"
        except AppError as exc:
            return str(exc.data.get("error", exc.code) if exc.data else exc.code)
        finally:
            session.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        confirm_results = list(pool.map(_confirm, [1, 2]))
    assert confirm_results.count("ok") == 1
    assert "PURCHASE_RETURN_OUTBOUND_ALREADY_CONFIRMED" in confirm_results


def test_two_returns_cannot_over_deduct_inventory(client: TestClient) -> None:
    owner, user_id = register_and_login(client, "prt-race@example.com")
    tenant_id = _create_tenant(client, owner, "PrtRace", "prt-race")
    _, member_id = _member_id(client, owner, tenant_id)
    data = _received_po(client, owner, tenant_id, ordered=10, received=10)
    item = data["order"]["items"][0]
    first = _create_pr(
        client,
        data,
        {
            "purchase_order_id": data["order_id"],
            "settlement_type": "NO_REFUND",
            "reason": "A",
            "items": [{"purchase_order_item_id": item["id"], "requested_return_quantity": 8}],
        },
    ).json()["data"]
    second = _create_pr(
        client,
        data,
        {
            "purchase_order_id": data["order_id"],
            "settlement_type": "NO_REFUND",
            "reason": "B",
            "items": [{"purchase_order_item_id": item["id"], "requested_return_quantity": 8}],
        },
    ).json()["data"]
    a = _submit_approve(client, data, first["id"])
    # 第二张不能提交：可退已被占用。改为各退 5，需要先取消第一张占用... 这里直接创建两张已批准出库竞争库存。
    client.post(f"/api/v1/purchase-returns/{second['id']}/cancel", headers=data["header"])
    other = _create_pr(
        client,
        data,
        {
            "purchase_order_id": data["order_id"],
            "settlement_type": "NO_REFUND",
            "reason": "B2",
            "items": [{"purchase_order_item_id": item["id"], "requested_return_quantity": 2}],
        },
    ).json()["data"]
    b = _submit_approve(client, data, other["id"])
    oa = client.post(
        f"/api/v1/purchase-returns/{a['id']}/outbounds",
        json={"items": [{"purchase_return_item_id": a["items"][0]["id"], "quantity": 8}]},
        headers=data["header"],
    ).json()["data"]
    ob = client.post(
        f"/api/v1/purchase-returns/{b['id']}/outbounds",
        json={"items": [{"purchase_return_item_id": b["items"][0]["id"], "quantity": 2}]},
        headers=data["header"],
    ).json()["data"]

    def _confirm(outbound_id: int) -> str:
        session = SessionLocal()
        try:
            PurchaseReturnOutboundService(
                session,
                TenantContext(
                    user_id=user_id,
                    tenant_id=tenant_id,
                    member_id=member_id,
                    is_owner=True,
                    role=MemberRole.OWNER.value,
                ),
            ).confirm_purchase_return_outbound(outbound_id)
            return "ok"
        except AppError as exc:
            return str(exc.data.get("error", exc.code) if exc.data else exc.code)
        finally:
            session.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(_confirm, [oa["id"], ob["id"]]))
    assert results.count("ok") == 2
    inv = _inventory_row(client, data, data["sku_ids"][0])
    assert inv["quantity"] == 0


def test_permissions_operator_and_warehouse(client: TestClient) -> None:
    owner, _ = register_and_login(client, "prt-perm@example.com")
    tenant_id = _create_tenant(client, owner, "PrtPerm", "prt-perm")
    roles = _roles(client, owner, tenant_id)
    operator = _add_member(client, owner, tenant_id, "prt-op@example.com", [roles["OPERATOR"]["id"]])
    warehouse = _add_member(client, owner, tenant_id, "prt-wh@example.com", [roles["WAREHOUSE"]["id"]])
    data = _received_po(client, owner, tenant_id, ordered=5, received=5)
    item = data["order"]["items"][0]
    created = client.post(
        "/api/v1/purchase-returns",
        json={
            "purchase_order_id": data["order_id"],
            "settlement_type": "REFUND",
            "reason": "权限",
            "items": [
                {
                    "purchase_order_item_id": item["id"],
                    "requested_return_quantity": 2,
                    "requested_refund_amount": "20",
                }
            ],
        },
        headers=_header(operator, tenant_id),
    )
    assert created.status_code == 200, created.text
    return_id = created.json()["data"]["id"]
    submitted = client.post(
        f"/api/v1/purchase-returns/{return_id}/submit",
        headers=_header(operator, tenant_id),
    )
    assert submitted.status_code == 200, submitted.text
    approve = client.post(
        f"/api/v1/purchase-returns/{return_id}/approve",
        json={},
        headers=_header(operator, tenant_id),
    )
    assert approve.status_code == 403
    approved = client.post(
        f"/api/v1/purchase-returns/{return_id}/approve",
        json={},
        headers=data["header"],
    )
    assert approved.status_code == 200, approved.text
    outbound = client.post(
        f"/api/v1/purchase-returns/{return_id}/outbounds",
        json={"items": [{"purchase_return_item_id": approved.json()["data"]["items"][0]["id"], "quantity": 2}]},
        headers=_header(warehouse, tenant_id),
    )
    assert outbound.status_code == 200, outbound.text
    confirm = client.post(
        f"/api/v1/purchase-return-outbounds/{outbound.json()['data']['id']}/confirm",
        headers=_header(warehouse, tenant_id),
    )
    assert confirm.status_code == 200, confirm.text
    refund = client.post(
        f"/api/v1/purchase-returns/{return_id}/refunds",
        json={"amount": "20"},
        headers=_header(warehouse, tenant_id),
    )
    assert refund.status_code == 403
    created_refund = client.post(
        f"/api/v1/purchase-returns/{return_id}/refunds",
        json={"amount": "20"},
        headers=data["header"],
    )
    assert created_refund.status_code == 200, created_refund.text
    confirm_refund = client.post(
        f"/api/v1/supplier-refunds/{created_refund.json()['data']['id']}/confirm",
        json={},
        headers=_header(warehouse, tenant_id),
    )
    assert confirm_refund.status_code == 403
    assert PermissionCode.PURCHASE_RETURN_READ.value == "purchase_return:read"

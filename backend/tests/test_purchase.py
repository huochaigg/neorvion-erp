from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from app.core.exceptions import AppError
from app.core.permissions import PermissionCode
from app.core.tenant import TenantContext
from app.db.session import SessionLocal
from app.models.tenant import MemberRole
from app.repositories.purchase import PurchaseOrderRepository
from app.schemas.purchase import PurchaseOrderReject
from app.services.purchase import PurchaseOrderService
from fastapi.testclient import TestClient
from sqlalchemy import func

from tests.helpers.auth_api import auth_header, register_and_login


def _create_tenant(client: TestClient, token: str, name: str, code: str) -> int:
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


def _catalog(client: TestClient, token: str, tenant_id: int) -> dict[str, int]:
    response = client.get("/api/v1/permissions", headers=auth_header(token, tenant_id))
    assert response.status_code == 200, response.text
    return {item["code"]: item["id"] for item in response.json()["data"]}


def _member_id(client: TestClient, token: str, tenant_id: int) -> tuple[int, int]:
    response = client.get("/api/v1/tenants/current", headers=auth_header(token, tenant_id))
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    return int(data["user_id"]), int(data["member_id"])


def _add_member(
    client: TestClient,
    owner_token: str,
    tenant_id: int,
    email: str,
    role_ids: list[int],
) -> str:
    member_token, _ = register_and_login(client, email)
    response = client.post(
        f"/api/v1/tenants/{tenant_id}/members",
        json={"email": email, "role_ids": role_ids},
        headers=auth_header(owner_token, tenant_id),
    )
    assert response.status_code == 200, response.text
    return member_token


def _create_warehouse(client: TestClient, token: str, tenant_id: int, name: str) -> dict:
    response = client.post(
        "/api/v1/warehouses",
        json={"name": name, "type": "DOMESTIC"},
        headers=auth_header(token, tenant_id),
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


def _create_product(
    client: TestClient,
    token: str,
    tenant_id: int,
    name: str,
    skus: list[dict],
) -> dict:
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


def _create_supplier(
    client: TestClient,
    token: str,
    tenant_id: int,
    name: str,
    extra: dict | None = None,
) -> dict:
    payload = {"name": name, **(extra or {})}
    response = client.post("/api/v1/suppliers", json=payload, headers=auth_header(token, tenant_id))
    assert response.status_code == 200, response.text
    return response.json()["data"]


def _create_po(
    client: TestClient,
    token: str,
    tenant_id: int,
    *,
    supplier_id: int,
    warehouse_id: int,
    items: list[dict],
) -> object:
    return client.post(
        "/api/v1/purchase-orders",
        json={
            "supplier_id": supplier_id,
            "warehouse_id": warehouse_id,
            "expected_arrival_date": "2026-10-20",
            "items": items,
        },
        headers=auth_header(token, tenant_id),
    )


def test_supplier_create_auto_code_and_tenant_unique(client: TestClient) -> None:
    owner, _ = register_and_login(client, "sup-code@example.com")
    tenant_id = _create_tenant(client, owner, "SupCode", "sup-code")
    created = _create_supplier(client, owner, tenant_id, "深圳电子")
    assert created["code"].startswith("SUP")
    assert len(created["code"]) == 13
    custom = _create_supplier(client, owner, tenant_id, "广州电子", {"code": "SUP-GZ-1"})
    assert custom["code"] == "SUP-GZ-1"
    dup = client.post(
        "/api/v1/suppliers",
        json={"name": "重复", "code": "SUP-GZ-1"},
        headers=auth_header(owner, tenant_id),
    )
    assert dup.status_code == 409
    other_owner, _ = register_and_login(client, "sup-code-b@example.com")
    other_tenant = _create_tenant(client, other_owner, "SupCodeB", "sup-code-b")
    other = _create_supplier(client, other_owner, other_tenant, "深圳电子", {"code": "SUP-GZ-1"})
    assert other["code"] == "SUP-GZ-1"
    hidden = client.get(
        f"/api/v1/suppliers/{created['id']}",
        headers=auth_header(other_owner, other_tenant),
    )
    assert hidden.status_code == 404


def test_disabled_supplier_cannot_create_po_in_use_cannot_delete(client: TestClient) -> None:
    owner, _ = register_and_login(client, "sup-disable@example.com")
    tenant_id = _create_tenant(client, owner, "SupDisable", "sup-disable")
    supplier = _create_supplier(client, owner, tenant_id, "可停用")
    warehouse = _create_warehouse(client, owner, tenant_id, "深圳仓")
    product = _create_product(
        client,
        owner,
        tenant_id,
        "手机",
        [{"sku_code": "SKU-PO-1", "name": "默认", "spec_values": {}}],
    )
    sku_id = product["skus"][0]["id"]
    disabled = client.patch(
        f"/api/v1/suppliers/{supplier['id']}/status",
        json={"status": "DISABLED"},
        headers=auth_header(owner, tenant_id),
    )
    assert disabled.status_code == 200, disabled.text
    blocked = _create_po(
        client,
        owner,
        tenant_id,
        supplier_id=supplier["id"],
        warehouse_id=warehouse["id"],
        items=[{"sku_id": sku_id, "quantity": 10}],
    )
    assert blocked.status_code == 400
    assert blocked.json()["data"]["error"] == "SUPPLIER_DISABLED"
    enabled = client.patch(
        f"/api/v1/suppliers/{supplier['id']}/status",
        json={"status": "ACTIVE"},
        headers=auth_header(owner, tenant_id),
    )
    assert enabled.status_code == 200
    created = _create_po(
        client,
        owner,
        tenant_id,
        supplier_id=supplier["id"],
        warehouse_id=warehouse["id"],
        items=[{"sku_id": sku_id, "quantity": 10}],
    )
    assert created.status_code == 200, created.text
    delete_used = client.delete(
        f"/api/v1/suppliers/{supplier['id']}",
        headers=auth_header(owner, tenant_id),
    )
    assert delete_used.status_code == 400
    assert delete_used.json()["data"]["error"] == "SUPPLIER_IN_USE"
    idle = _create_supplier(client, owner, tenant_id, "可删除")
    deleted = client.delete(
        f"/api/v1/suppliers/{idle['id']}",
        headers=auth_header(owner, tenant_id),
    )
    assert deleted.status_code == 200


def test_create_purchase_order_single_and_multi_sku(client: TestClient) -> None:
    owner, _ = register_and_login(client, "po-create@example.com")
    tenant_id = _create_tenant(client, owner, "PoCreate", "po-create")
    supplier = _create_supplier(client, owner, tenant_id, "供应商A")
    warehouse = _create_warehouse(client, owner, tenant_id, "深圳仓")
    product = _create_product(
        client,
        owner,
        tenant_id,
        "耳机",
        [
            {"sku_code": "SKU-A", "name": "黑", "spec_values": {"color": "black"}},
            {"sku_code": "SKU-B", "name": "白", "spec_values": {"color": "white"}},
        ],
    )
    sku_a = product["skus"][0]["id"]
    sku_b = product["skus"][1]["id"]
    single = _create_po(
        client,
        owner,
        tenant_id,
        supplier_id=supplier["id"],
        warehouse_id=warehouse["id"],
        items=[{"sku_id": sku_a, "quantity": 100, "unit_price": "12.50"}],
    )
    assert single.status_code == 200, single.text
    data = single.json()["data"]
    assert data["order_no"].startswith("PO2026")
    assert data["status"] == "DRAFT"
    assert data["sku_count"] == 1
    assert data["total_quantity"] == 100
    assert data["total_amount"] == 1250.0
    assert data["items"][0]["received_quantity"] == 0

    multi = _create_po(
        client,
        owner,
        tenant_id,
        supplier_id=supplier["id"],
        warehouse_id=warehouse["id"],
        items=[
            {"sku_id": sku_a, "quantity": 10, "unit_price": "1.00"},
            {"sku_id": sku_b, "quantity": 5},
        ],
    )
    assert multi.status_code == 200, multi.text
    assert multi.json()["data"]["sku_count"] == 2
    assert multi.json()["data"]["total_quantity"] == 15
    assert multi.json()["data"]["total_amount"] == 10.0

    listed = client.get("/api/v1/purchase-orders", headers=auth_header(owner, tenant_id))
    assert listed.status_code == 200
    assert listed.json()["data"]["total"] == 2

    dup = _create_po(
        client,
        owner,
        tenant_id,
        supplier_id=supplier["id"],
        warehouse_id=warehouse["id"],
        items=[
            {"sku_id": sku_a, "quantity": 1},
            {"sku_id": sku_a, "quantity": 2},
        ],
    )
    assert dup.status_code in {400, 422}

    invalid = _create_po(
        client,
        owner,
        tenant_id,
        supplier_id=supplier["id"],
        warehouse_id=warehouse["id"],
        items=[{"sku_id": 999999, "quantity": 1}],
    )
    assert invalid.status_code == 404
    listed_after = client.get("/api/v1/purchase-orders", headers=auth_header(owner, tenant_id))
    assert listed_after.json()["data"]["total"] == 2


def test_cannot_use_other_tenant_resources(client: TestClient) -> None:
    alice, _ = register_and_login(client, "po-alice@example.com")
    bob, _ = register_and_login(client, "po-bob@example.com")
    a_tenant = _create_tenant(client, alice, "AlicePo", "alice-po")
    b_tenant = _create_tenant(client, bob, "BobPo", "bob-po")
    a_supplier = _create_supplier(client, alice, a_tenant, "Alice供应商")
    a_warehouse = _create_warehouse(client, alice, a_tenant, "Alice仓")
    a_product = _create_product(
        client,
        alice,
        a_tenant,
        "Alice货",
        [{"sku_code": "SKU-ALICE", "name": "A", "spec_values": {}}],
    )
    b_supplier = _create_supplier(client, bob, b_tenant, "Bob供应商")
    b_warehouse = _create_warehouse(client, bob, b_tenant, "Bob仓")
    b_product = _create_product(
        client,
        bob,
        b_tenant,
        "Bob货",
        [{"sku_code": "SKU-BOB", "name": "B", "spec_values": {}}],
    )
    other_supplier = _create_po(
        client,
        alice,
        a_tenant,
        supplier_id=b_supplier["id"],
        warehouse_id=a_warehouse["id"],
        items=[{"sku_id": a_product["skus"][0]["id"], "quantity": 1}],
    )
    assert other_supplier.status_code == 404
    other_warehouse = _create_po(
        client,
        alice,
        a_tenant,
        supplier_id=a_supplier["id"],
        warehouse_id=b_warehouse["id"],
        items=[{"sku_id": a_product["skus"][0]["id"], "quantity": 1}],
    )
    assert other_warehouse.status_code == 404
    other_sku = _create_po(
        client,
        alice,
        a_tenant,
        supplier_id=a_supplier["id"],
        warehouse_id=a_warehouse["id"],
        items=[{"sku_id": b_product["skus"][0]["id"], "quantity": 1}],
    )
    assert other_sku.status_code == 404
    created = _create_po(
        client,
        alice,
        a_tenant,
        supplier_id=a_supplier["id"],
        warehouse_id=a_warehouse["id"],
        items=[{"sku_id": a_product["skus"][0]["id"], "quantity": 1}],
    )
    assert created.status_code == 200, created.text
    hidden = client.get(
        f"/api/v1/purchase-orders/{created.json()['data']['id']}",
        headers=auth_header(bob, b_tenant),
    )
    assert hidden.status_code == 404


def test_purchase_state_machine_and_edit_rules(client: TestClient) -> None:
    owner, _ = register_and_login(client, "po-state@example.com")
    tenant_id = _create_tenant(client, owner, "PoState", "po-state")
    header = auth_header(owner, tenant_id)
    supplier = _create_supplier(client, owner, tenant_id, "状态供应商")
    warehouse = _create_warehouse(client, owner, tenant_id, "深圳仓")
    product = _create_product(
        client,
        owner,
        tenant_id,
        "状态货",
        [
            {"sku_code": "SKU-S1", "name": "一", "spec_values": {}},
            {"sku_code": "SKU-S2", "name": "二", "spec_values": {}},
        ],
    )
    sku_1 = product["skus"][0]["id"]
    sku_2 = product["skus"][1]["id"]
    created = _create_po(
        client,
        owner,
        tenant_id,
        supplier_id=supplier["id"],
        warehouse_id=warehouse["id"],
        items=[{"sku_id": sku_1, "quantity": 8, "unit_price": "3.00"}],
    )
    order_id = created.json()["data"]["id"]

    edited = client.patch(
        f"/api/v1/purchase-orders/{order_id}",
        json={
            "remark": "草稿可改",
            "items": [{"sku_id": sku_2, "quantity": 4, "unit_price": "5.00"}],
        },
        headers=header,
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["data"]["items"][0]["sku_id"] == sku_2
    assert edited.json()["data"]["total_quantity"] == 4

    submitted = client.post(f"/api/v1/purchase-orders/{order_id}/submit", headers=header)
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["data"]["status"] == "PENDING_APPROVAL"
    locked = client.patch(
        f"/api/v1/purchase-orders/{order_id}",
        json={"remark": "审核中不能改"},
        headers=header,
    )
    assert locked.status_code == 400
    assert locked.json()["data"]["error"] == "PURCHASE_ORDER_NOT_EDITABLE"

    rejected = client.post(
        f"/api/v1/purchase-orders/{order_id}/reject",
        json={"reason": "数量不对"},
        headers=header,
    )
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["data"]["status"] == "REJECTED"
    assert rejected.json()["data"]["reject_reason"] == "数量不对"
    re_edit = client.patch(
        f"/api/v1/purchase-orders/{order_id}",
        json={"items": [{"sku_id": sku_1, "quantity": 6, "unit_price": "3.00"}]},
        headers=header,
    )
    assert re_edit.status_code == 200, re_edit.text
    resubmit = client.post(f"/api/v1/purchase-orders/{order_id}/submit", headers=header)
    assert resubmit.status_code == 200
    assert resubmit.json()["data"]["status"] == "PENDING_APPROVAL"

    approved = client.post(f"/api/v1/purchase-orders/{order_id}/approve", headers=header)
    assert approved.status_code == 200, approved.text
    assert approved.json()["data"]["status"] == "WAITING_RECEIPT"
    waiting_edit = client.patch(
        f"/api/v1/purchase-orders/{order_id}",
        json={"remark": "待收货不能改"},
        headers=header,
    )
    assert waiting_edit.status_code == 400
    waiting_cancel = client.post(
        f"/api/v1/purchase-orders/{order_id}/cancel",
        json={"reason": "不想要了"},
        headers=header,
    )
    assert waiting_cancel.status_code == 400
    assert waiting_cancel.json()["data"]["error"] == "INVALID_PURCHASE_ORDER_TRANSITION"

    draft = _create_po(
        client,
        owner,
        tenant_id,
        supplier_id=supplier["id"],
        warehouse_id=warehouse["id"],
        items=[{"sku_id": sku_1, "quantity": 1}],
    )
    draft_id = draft.json()["data"]["id"]
    cancelled = client.post(
        f"/api/v1/purchase-orders/{draft_id}/cancel",
        json={"reason": "作废草稿"},
        headers=header,
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["data"]["status"] == "CANCELLED"
    revive = client.post(f"/api/v1/purchase-orders/{draft_id}/approve", headers=header)
    assert revive.status_code == 400


def test_concurrent_approve_reject_does_not_overwrite(client: TestClient) -> None:
    owner, user_id = register_and_login(client, "po-race@example.com")
    tenant_id = _create_tenant(client, owner, "PoRace", "po-race")
    _, member_id = _member_id(client, owner, tenant_id)
    supplier = _create_supplier(client, owner, tenant_id, "竞态供应商")
    warehouse = _create_warehouse(client, owner, tenant_id, "深圳仓")
    product = _create_product(
        client,
        owner,
        tenant_id,
        "竞态货",
        [{"sku_code": "SKU-RACE-PO", "name": "R", "spec_values": {}}],
    )
    created = _create_po(
        client,
        owner,
        tenant_id,
        supplier_id=supplier["id"],
        warehouse_id=warehouse["id"],
        items=[{"sku_id": product["skus"][0]["id"], "quantity": 3}],
    )
    order_id = created.json()["data"]["id"]
    submitted = client.post(
        f"/api/v1/purchase-orders/{order_id}/submit",
        headers=auth_header(owner, tenant_id),
    )
    assert submitted.status_code == 200

    def _run(action: str) -> str:
        session = SessionLocal()
        try:
            context = TenantContext(
                user_id=user_id,
                tenant_id=tenant_id,
                member_id=member_id,
                is_owner=True,
                role=MemberRole.OWNER.value,
            )
            service = PurchaseOrderService(session, context)
            if action == "approve":
                service.approve_order(order_id)
            else:
                service.reject_order(order_id, PurchaseOrderReject(reason="并发驳回"))
            return "ok"
        except AppError as exc:
            data = exc.data or {}
            return str(data.get("error", exc.code))
        finally:
            session.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(_run, ["approve", "reject"]))
    assert results.count("ok") == 1
    assert all(
        item in {"ok", "PURCHASE_ORDER_STATE_CONFLICT", "INVALID_PURCHASE_ORDER_TRANSITION"}
        for item in results
    )
    current = client.get(
        f"/api/v1/purchase-orders/{order_id}",
        headers=auth_header(owner, tenant_id),
    )
    status = current.json()["data"]["status"]
    assert status in {"WAITING_RECEIPT", "REJECTED"}
    if status == "WAITING_RECEIPT":
        assert current.json()["data"]["reject_reason"] is None
    else:
        assert current.json()["data"]["approved_at"] is None

    session = SessionLocal()
    try:
        late = PurchaseOrderRepository(session, tenant_id).transition_if_status(
            order_id=order_id,
            expected_status="PENDING_APPROVAL",
            values={
                "status": "REJECTED",
                "reject_reason": "should-not-write",
                "updated_at": func.now(),
                "rejected_at": datetime.now(),
            },
        )
        session.commit()
        assert late == 0
    finally:
        session.close()
    unchanged = client.get(
        f"/api/v1/purchase-orders/{order_id}",
        headers=auth_header(owner, tenant_id),
    )
    assert unchanged.json()["data"]["status"] == status
    assert unchanged.json()["data"]["reject_reason"] != "should-not-write"


def test_purchase_does_not_change_inventory(client: TestClient) -> None:
    owner, _ = register_and_login(client, "po-inv@example.com")
    tenant_id = _create_tenant(client, owner, "PoInv", "po-inv")
    header = auth_header(owner, tenant_id)
    supplier = _create_supplier(client, owner, tenant_id, "库存供应商")
    warehouse = _create_warehouse(client, owner, tenant_id, "深圳仓")
    product = _create_product(
        client,
        owner,
        tenant_id,
        "库存货",
        [{"sku_code": "SKU-INV-PO", "name": "I", "spec_values": {}}],
    )
    sku_id = product["skus"][0]["id"]
    initialized = client.post(
        "/api/v1/inventory/initialize",
        json={"warehouse_id": warehouse["id"], "sku_id": sku_id, "quantity": 40},
        headers=header,
    )
    assert initialized.status_code == 200, initialized.text
    inventory_id = initialized.json()["data"]["id"]
    created = _create_po(
        client,
        owner,
        tenant_id,
        supplier_id=supplier["id"],
        warehouse_id=warehouse["id"],
        items=[{"sku_id": sku_id, "quantity": 100}],
    )
    assert created.status_code == 200
    order_id = created.json()["data"]["id"]
    client.post(f"/api/v1/purchase-orders/{order_id}/submit", headers=header)
    client.post(f"/api/v1/purchase-orders/{order_id}/approve", headers=header)
    current = client.get(f"/api/v1/inventory/{inventory_id}", headers=header)
    assert current.json()["data"]["quantity"] == 40
    assert current.json()["data"]["available_quantity"] == 40
    tx = client.get(f"/api/v1/inventory/{inventory_id}/transactions", headers=header)
    types = {item["type"] for item in tx.json()["data"]["items"]}
    assert "INBOUND" not in types
    extra_sku = client.post(
        f"/api/v1/products/{product['id']}/skus",
        json={"sku_code": "SKU-INV-PO-2", "name": "备用", "spec_values": {}},
        headers=header,
    )
    assert extra_sku.status_code == 200
    blocked_sku = client.delete(
        f"/api/v1/products/{product['id']}/skus/{sku_id}",
        headers=header,
    )
    assert blocked_sku.status_code == 400
    blocked_wh = client.delete(f"/api/v1/warehouses/{warehouse['id']}", headers=header)
    assert blocked_wh.status_code == 400
    assert blocked_wh.json()["data"]["error"] == "WAREHOUSE_IN_USE"


def test_purchase_and_supplier_permissions(client: TestClient) -> None:
    owner, _ = register_and_login(client, "po-perm-owner@example.com")
    tenant_id = _create_tenant(client, owner, "PoPerm", "po-perm")
    catalog = _catalog(client, owner, tenant_id)
    roles = _roles(client, owner, tenant_id)
    supplier = _create_supplier(client, owner, tenant_id, "权限供应商")
    warehouse = _create_warehouse(client, owner, tenant_id, "深圳仓")
    product = _create_product(
        client,
        owner,
        tenant_id,
        "权限货",
        [{"sku_code": "SKU-PERM-PO", "name": "P", "spec_values": {}}],
    )
    created = _create_po(
        client,
        owner,
        tenant_id,
        supplier_id=supplier["id"],
        warehouse_id=warehouse["id"],
        items=[{"sku_id": product["skus"][0]["id"], "quantity": 2}],
    )
    order_id = created.json()["data"]["id"]

    def _role(code: str, *perm_codes: str) -> int:
        created_role = client.post(
            "/api/v1/roles",
            json={
                "name": code,
                "code": code,
                "permission_ids": [catalog[item] for item in perm_codes],
            },
            headers=auth_header(owner, tenant_id),
        )
        assert created_role.status_code == 200, created_role.text
        return int(created_role.json()["data"]["id"])

    reader = _add_member(
        client,
        owner,
        tenant_id,
        "po-perm-read@example.com",
        [_role("POREAD", PermissionCode.PURCHASE_READ, PermissionCode.SUPPLIER_READ)],
    )
    creator = _add_member(
        client,
        owner,
        tenant_id,
        "po-perm-create@example.com",
        [
            _role(
                "POCREATE",
                PermissionCode.PURCHASE_READ,
                PermissionCode.PURCHASE_CREATE,
                PermissionCode.SUPPLIER_READ,
            )
        ],
    )
    updater = _add_member(
        client,
        owner,
        tenant_id,
        "po-perm-update@example.com",
        [_role("POUPDATE", PermissionCode.PURCHASE_READ, PermissionCode.PURCHASE_UPDATE)],
    )
    submitter = _add_member(
        client,
        owner,
        tenant_id,
        "po-perm-submit@example.com",
        [_role("POSUBMIT", PermissionCode.PURCHASE_READ, PermissionCode.PURCHASE_SUBMIT)],
    )
    auditor = _add_member(
        client,
        owner,
        tenant_id,
        "po-perm-audit@example.com",
        [_role("POAUDIT", PermissionCode.PURCHASE_READ, PermissionCode.PURCHASE_AUDIT)],
    )
    canceller = _add_member(
        client,
        owner,
        tenant_id,
        "po-perm-cancel@example.com",
        [_role("POCANCEL", PermissionCode.PURCHASE_READ, PermissionCode.PURCHASE_CANCEL)],
    )
    operator = _add_member(
        client,
        owner,
        tenant_id,
        "po-perm-op@example.com",
        [roles["OPERATOR"]["id"]],
    )

    denied_list = client.get("/api/v1/purchase-orders", headers=auth_header(creator, tenant_id))
    # creator has purchase:read
    assert denied_list.status_code == 200
    no_create = _create_po(
        client,
        reader,
        tenant_id,
        supplier_id=supplier["id"],
        warehouse_id=warehouse["id"],
        items=[{"sku_id": product["skus"][0]["id"], "quantity": 1}],
    )
    assert no_create.status_code == 403
    allowed_create = _create_po(
        client,
        creator,
        tenant_id,
        supplier_id=supplier["id"],
        warehouse_id=warehouse["id"],
        items=[{"sku_id": product["skus"][0]["id"], "quantity": 1}],
    )
    assert allowed_create.status_code == 200, allowed_create.text
    no_update = client.patch(
        f"/api/v1/purchase-orders/{order_id}",
        json={"remark": "无编辑权"},
        headers=auth_header(reader, tenant_id),
    )
    assert no_update.status_code == 403
    allowed_update = client.patch(
        f"/api/v1/purchase-orders/{order_id}",
        json={"remark": "有编辑权"},
        headers=auth_header(updater, tenant_id),
    )
    assert allowed_update.status_code == 200, allowed_update.text
    no_submit = client.post(
        f"/api/v1/purchase-orders/{order_id}/submit",
        headers=auth_header(reader, tenant_id),
    )
    assert no_submit.status_code == 403
    submitted = client.post(
        f"/api/v1/purchase-orders/{order_id}/submit",
        headers=auth_header(submitter, tenant_id),
    )
    assert submitted.status_code == 200, submitted.text
    no_approve = client.post(
        f"/api/v1/purchase-orders/{order_id}/approve",
        headers=auth_header(operator, tenant_id),
    )
    assert no_approve.status_code == 403
    no_cancel_pending = client.post(
        f"/api/v1/purchase-orders/{order_id}/cancel",
        json={},
        headers=auth_header(reader, tenant_id),
    )
    assert no_cancel_pending.status_code == 403
    rejected = client.post(
        f"/api/v1/purchase-orders/{order_id}/reject",
        json={"reason": "权限测试驳回"},
        headers=auth_header(auditor, tenant_id),
    )
    assert rejected.status_code == 200, rejected.text
    cancelled = client.post(
        f"/api/v1/purchase-orders/{order_id}/cancel",
        json={"reason": "权限测试取消"},
        headers=auth_header(canceller, tenant_id),
    )
    assert cancelled.status_code == 200, cancelled.text

    no_supplier_create = client.post(
        "/api/v1/suppliers",
        json={"name": "运营不能建供应商"},
        headers=auth_header(operator, tenant_id),
    )
    assert no_supplier_create.status_code == 403
    supplier_list = client.get("/api/v1/suppliers", headers=auth_header(operator, tenant_id))
    assert supplier_list.status_code == 200
    tree = client.get("/api/v1/permissions/tree", headers=auth_header(owner, tenant_id))
    titles: list[str] = []

    def _walk(nodes: list[dict]) -> None:
        for node in nodes:
            titles.append(node["title"])
            _walk(node.get("children") or [])

    _walk(tree.json()["data"])
    assert "采购管理" in titles
    assert "供应商管理" in titles
    assert "提交审核" in titles

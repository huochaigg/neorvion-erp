from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from app.core.exceptions import AppError
from app.core.permissions import PermissionCode
from app.core.tenant import TenantContext
from app.db.session import SessionLocal
from app.models.tenant import MemberRole
from app.services.stock_transfer import StockTransferService
from fastapi.testclient import TestClient

from tests.helpers.auth_api import auth_header, register_and_login


def _create_tenant(client: TestClient, token: str, name: str, code: str) -> int:
    response = client.post(
        "/api/v1/tenants",
        json={"name": name, "code": code},
        headers=auth_header(token),
    )
    assert response.status_code == 200, response.text
    return int(response.json()["data"]["id"])


def _member_id(client: TestClient, token: str, tenant_id: int) -> tuple[int, int]:
    response = client.get("/api/v1/tenants/current", headers=auth_header(token, tenant_id))
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    return int(data["user_id"]), int(data["member_id"])


def _catalog(client: TestClient, token: str, tenant_id: int) -> dict[str, int]:
    response = client.get("/api/v1/permissions", headers=auth_header(token, tenant_id))
    assert response.status_code == 200, response.text
    return {item["code"]: item["id"] for item in response.json()["data"]}


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
    client: TestClient, token: str, tenant_id: int, name: str, sku_code: str
) -> dict:
    category = client.post(
        "/api/v1/product-categories",
        json={"name": f"{name}-类目"},
        headers=auth_header(token, tenant_id),
    )
    assert category.status_code == 200, category.text
    created = client.post(
        "/api/v1/products",
        json={
            "name": name,
            "category_id": category.json()["data"]["id"],
            "skus": [{"sku_code": sku_code, "name": f"{name}-SKU"}],
        },
        headers=auth_header(token, tenant_id),
    )
    assert created.status_code == 200, created.text
    return created.json()["data"]


def _initialize(
    client: TestClient,
    token: str,
    tenant_id: int,
    warehouse_id: int,
    sku_id: int,
    quantity: int,
):
    return client.post(
        "/api/v1/inventory/initialize",
        json={"warehouse_id": warehouse_id, "sku_id": sku_id, "quantity": quantity},
        headers=auth_header(token, tenant_id),
    )


def _headers(token: str, tenant_id: int) -> dict[str, str]:
    return auth_header(token, tenant_id)


def _create_draft(
    client: TestClient,
    token: str,
    tenant_id: int,
    source_id: int,
    target_id: int,
    items: list[dict],
):
    return client.post(
        "/api/v1/stock-transfers",
        json={
            "source_warehouse_id": source_id,
            "target_warehouse_id": target_id,
            "items": items,
        },
        headers=_headers(token, tenant_id),
    )


def test_create_draft_rejects_same_warehouse_and_does_not_change_stock(client: TestClient) -> None:
    owner, _ = register_and_login(client, "tr-draft@example.com")
    tenant_id = _create_tenant(client, owner, "TrDraft", "tr-draft")
    source = _create_warehouse(client, owner, tenant_id, "深圳仓")
    target = _create_warehouse(client, owner, tenant_id, "广州仓")
    product = _create_product(client, owner, tenant_id, "手机", "SKU-T1")
    sku_id = product["skus"][0]["id"]
    inv = _initialize(client, owner, tenant_id, source["id"], sku_id, 100).json()["data"]
    same = _create_draft(
        client,
        owner,
        tenant_id,
        source["id"],
        source["id"],
        [{"sku_id": sku_id, "quantity": 20}],
    )
    assert same.status_code == 400
    assert same.json()["data"]["error"] == "STOCK_TRANSFER_SAME_WAREHOUSE"
    created = _create_draft(
        client,
        owner,
        tenant_id,
        source["id"],
        target["id"],
        [{"sku_id": sku_id, "quantity": 20}],
    )
    assert created.status_code == 200, created.text
    assert created.json()["data"]["status"] == "DRAFT"
    assert created.json()["data"]["transfer_no"].startswith("TR")
    current = client.get(f"/api/v1/inventory/{inv['id']}", headers=_headers(owner, tenant_id))
    assert current.json()["data"]["quantity"] == 100
    submitted = client.post(
        f"/api/v1/stock-transfers/{created.json()['data']['id']}/submit",
        headers=_headers(owner, tenant_id),
    )
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["data"]["status"] == "PENDING_OUTBOUND"
    still = client.get(f"/api/v1/inventory/{inv['id']}", headers=_headers(owner, tenant_id))
    assert still.json()["data"]["quantity"] == 100


def test_outbound_then_receive_and_transactions(client: TestClient) -> None:
    owner, _ = register_and_login(client, "tr-flow@example.com")
    tenant_id = _create_tenant(client, owner, "TrFlow", "tr-flow")
    source = _create_warehouse(client, owner, tenant_id, "深圳仓")
    target = _create_warehouse(client, owner, tenant_id, "广州仓")
    product = _create_product(client, owner, tenant_id, "手机", "SKU-T2")
    sku_id = product["skus"][0]["id"]
    source_inv = _initialize(client, owner, tenant_id, source["id"], sku_id, 100).json()["data"]
    reserved = client.post(
        f"/api/v1/inventory/{source_inv['id']}/reserve",
        json={"quantity": 30},
        headers=_headers(owner, tenant_id),
    )
    assert reserved.status_code == 200, reserved.text
    created = _create_draft(
        client,
        owner,
        tenant_id,
        source["id"],
        target["id"],
        [{"sku_id": sku_id, "quantity": 20}],
    ).json()["data"]
    transfer_id = created["id"]
    client.post(f"/api/v1/stock-transfers/{transfer_id}/submit", headers=_headers(owner, tenant_id))
    outbound = client.post(
        f"/api/v1/stock-transfers/{transfer_id}/confirm-outbound",
        headers=_headers(owner, tenant_id),
    )
    assert outbound.status_code == 200, outbound.text
    assert outbound.json()["data"]["status"] == "IN_TRANSIT"
    after_out = client.get(
        f"/api/v1/inventory/{source_inv['id']}",
        headers=_headers(owner, tenant_id),
    ).json()["data"]
    assert after_out["quantity"] == 80
    assert after_out["reserved_quantity"] == 30
    assert after_out["available_quantity"] == 50
    listed_target = client.get(
        "/api/v1/inventory",
        params={"warehouse_id": target["id"], "page": 1, "page_size": 20},
        headers=_headers(owner, tenant_id),
    )
    assert listed_target.json()["data"]["total"] == 0
    tx = client.get(
        f"/api/v1/inventory/{source_inv['id']}/transactions",
        headers=_headers(owner, tenant_id),
    )
    types = [row["type"] for row in tx.json()["data"]["items"]]
    assert "TRANSFER_OUT" in types
    cancelled = client.post(
        f"/api/v1/stock-transfers/{transfer_id}/cancel",
        headers=_headers(owner, tenant_id),
    )
    assert cancelled.status_code == 400
    assert cancelled.json()["data"]["error"] == "STOCK_TRANSFER_CANNOT_CANCEL"
    received = client.post(
        f"/api/v1/stock-transfers/{transfer_id}/confirm-receive",
        headers=_headers(owner, tenant_id),
    )
    assert received.status_code == 200, received.text
    assert received.json()["data"]["status"] == "COMPLETED"
    target_list = client.get(
        "/api/v1/inventory",
        params={"warehouse_id": target["id"], "page": 1, "page_size": 20},
        headers=_headers(owner, tenant_id),
    )
    assert target_list.json()["data"]["total"] == 1
    target_inv = target_list.json()["data"]["items"][0]
    assert target_inv["quantity"] == 20
    assert target_inv["reserved_quantity"] == 0
    target_tx = client.get(
        f"/api/v1/inventory/{target_inv['id']}/transactions",
        headers=_headers(owner, tenant_id),
    )
    assert any(row["type"] == "TRANSFER_IN" for row in target_tx.json()["data"]["items"])


def test_repeat_outbound_receive_and_insufficient_available(client: TestClient) -> None:
    owner, _ = register_and_login(client, "tr-idemp@example.com")
    tenant_id = _create_tenant(client, owner, "TrIdemp", "tr-idemp")
    source = _create_warehouse(client, owner, tenant_id, "深圳仓")
    target = _create_warehouse(client, owner, tenant_id, "广州仓")
    product_a = _create_product(client, owner, tenant_id, "A货", "SKU-T3")
    product_b = _create_product(client, owner, tenant_id, "B货", "SKU-T4")
    sku_a = product_a["skus"][0]["id"]
    sku_b = product_b["skus"][0]["id"]
    inv_a = _initialize(client, owner, tenant_id, source["id"], sku_a, 100).json()["data"]
    inv_b = _initialize(client, owner, tenant_id, source["id"], sku_b, 10).json()["data"]
    over = _create_draft(
        client,
        owner,
        tenant_id,
        source["id"],
        target["id"],
        [{"sku_id": sku_a, "quantity": 50}, {"sku_id": sku_b, "quantity": 20}],
    ).json()["data"]
    client.post(f"/api/v1/stock-transfers/{over['id']}/submit", headers=_headers(owner, tenant_id))
    failed = client.post(
        f"/api/v1/stock-transfers/{over['id']}/confirm-outbound",
        headers=_headers(owner, tenant_id),
    )
    assert failed.status_code == 400
    assert failed.json()["data"]["error"] == "INSUFFICIENT_AVAILABLE_INVENTORY"
    qty_a = client.get(
        f"/api/v1/inventory/{inv_a['id']}",
        headers=_headers(owner, tenant_id),
    ).json()["data"]["quantity"]
    qty_b = client.get(
        f"/api/v1/inventory/{inv_b['id']}",
        headers=_headers(owner, tenant_id),
    ).json()["data"]["quantity"]
    assert qty_a == 100
    assert qty_b == 10

    ok_transfer = _create_draft(
        client,
        owner,
        tenant_id,
        source["id"],
        target["id"],
        [{"sku_id": sku_a, "quantity": 20}],
    ).json()["data"]
    client.post(
        f"/api/v1/stock-transfers/{ok_transfer['id']}/submit",
        headers=_headers(owner, tenant_id),
    )
    first_out = client.post(
        f"/api/v1/stock-transfers/{ok_transfer['id']}/confirm-outbound",
        headers=_headers(owner, tenant_id),
    )
    assert first_out.status_code == 200, first_out.text
    second_out = client.post(
        f"/api/v1/stock-transfers/{ok_transfer['id']}/confirm-outbound",
        headers=_headers(owner, tenant_id),
    )
    assert second_out.status_code == 400
    assert second_out.json()["data"]["error"] == "STOCK_TRANSFER_ALREADY_OUTBOUND"
    after_qty = client.get(
        f"/api/v1/inventory/{inv_a['id']}",
        headers=_headers(owner, tenant_id),
    ).json()["data"]["quantity"]
    assert after_qty == 80
    first_in = client.post(
        f"/api/v1/stock-transfers/{ok_transfer['id']}/confirm-receive",
        headers=_headers(owner, tenant_id),
    )
    assert first_in.status_code == 200, first_in.text
    second_in = client.post(
        f"/api/v1/stock-transfers/{ok_transfer['id']}/confirm-receive",
        headers=_headers(owner, tenant_id),
    )
    assert second_in.status_code == 400
    assert second_in.json()["data"]["error"] == "STOCK_TRANSFER_ALREADY_RECEIVED"


def test_two_transfers_cannot_over_deduct(client: TestClient) -> None:
    owner, user_id = register_and_login(client, "tr-race@example.com")
    tenant_id = _create_tenant(client, owner, "TrRace", "tr-race")
    _, member_id = _member_id(client, owner, tenant_id)
    source = _create_warehouse(client, owner, tenant_id, "深圳仓")
    target = _create_warehouse(client, owner, tenant_id, "广州仓")
    product = _create_product(client, owner, tenant_id, "手机", "SKU-T5")
    sku_id = product["skus"][0]["id"]
    inv = _initialize(client, owner, tenant_id, source["id"], sku_id, 100).json()["data"]
    first = _create_draft(
        client,
        owner,
        tenant_id,
        source["id"],
        target["id"],
        [{"sku_id": sku_id, "quantity": 80}],
    ).json()["data"]
    second = _create_draft(
        client,
        owner,
        tenant_id,
        source["id"],
        target["id"],
        [{"sku_id": sku_id, "quantity": 80}],
    ).json()["data"]
    client.post(
        f"/api/v1/stock-transfers/{first['id']}/submit",
        headers=_headers(owner, tenant_id),
    )
    client.post(
        f"/api/v1/stock-transfers/{second['id']}/submit",
        headers=_headers(owner, tenant_id),
    )

    def _outbound(transfer_id: int) -> str:
        session = SessionLocal()
        try:
            context = TenantContext(
                user_id=user_id,
                tenant_id=tenant_id,
                member_id=member_id,
                is_owner=True,
                role=MemberRole.OWNER.value,
            )
            StockTransferService(session, context).confirm_outbound(transfer_id)
            return "ok"
        except AppError as exc:
            error = exc.data.get("error") if isinstance(exc.data, dict) else None
            return error or "err"
        except Exception:
            return "err"
        finally:
            session.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(_outbound, [first["id"], second["id"]]))
    assert results.count("ok") == 1
    assert "INSUFFICIENT_AVAILABLE_INVENTORY" in results
    current = client.get(
        f"/api/v1/inventory/{inv['id']}",
        headers=_headers(owner, tenant_id),
    ).json()["data"]
    assert current["quantity"] == 20
    assert current["reserved_quantity"] == 0
    assert current["quantity"] >= current["reserved_quantity"]


def test_transfer_cross_tenant_and_permissions(client: TestClient) -> None:
    owner_a, _ = register_and_login(client, "tr-a@example.com")
    owner_b, _ = register_and_login(client, "tr-b@example.com")
    tenant_a = _create_tenant(client, owner_a, "TrA", "tr-a")
    tenant_b = _create_tenant(client, owner_b, "TrB", "tr-b")
    source = _create_warehouse(client, owner_a, tenant_a, "深圳仓")
    target = _create_warehouse(client, owner_a, tenant_a, "广州仓")
    other_wh = _create_warehouse(client, owner_b, tenant_b, "外仓")
    product = _create_product(client, owner_a, tenant_a, "手机", "SKU-T6")
    sku_id = product["skus"][0]["id"]
    _initialize(client, owner_a, tenant_a, source["id"], sku_id, 40)
    cross = _create_draft(
        client,
        owner_a,
        tenant_a,
        source["id"],
        other_wh["id"],
        [{"sku_id": sku_id, "quantity": 5}],
    )
    assert cross.status_code == 404
    created = _create_draft(
        client,
        owner_a,
        tenant_a,
        source["id"],
        target["id"],
        [{"sku_id": sku_id, "quantity": 5}],
    )
    assert created.status_code == 200, created.text
    transfer_id = created.json()["data"]["id"]
    hidden = client.get(
        f"/api/v1/stock-transfers/{transfer_id}",
        headers=_headers(owner_b, tenant_b),
    )
    assert hidden.status_code == 404
    catalog = _catalog(client, owner_a, tenant_a)
    created_role = client.post(
        "/api/v1/roles",
        json={
            "name": "TRREAD",
            "code": "TRREAD",
            "permission_ids": [catalog[PermissionCode.STOCK_TRANSFER_READ]],
        },
        headers=_headers(owner_a, tenant_a),
    )
    reader = _add_member(
        client,
        owner_a,
        tenant_a,
        "tr-reader@example.com",
        [created_role.json()["data"]["id"]],
    )
    listed = client.get("/api/v1/stock-transfers", headers=_headers(reader, tenant_a))
    assert listed.status_code == 200
    create_blocked = _create_draft(
        client,
        reader,
        tenant_a,
        source["id"],
        target["id"],
        [{"sku_id": sku_id, "quantity": 1}],
    )
    assert create_blocked.status_code == 403
    outbound_blocked = client.post(
        f"/api/v1/stock-transfers/{transfer_id}/confirm-outbound",
        headers=_headers(reader, tenant_a),
    )
    assert outbound_blocked.status_code == 403
    receive_blocked = client.post(
        f"/api/v1/stock-transfers/{transfer_id}/confirm-receive",
        headers=_headers(reader, tenant_a),
    )
    assert receive_blocked.status_code == 403

"""物流商、物流单、确认发货、轨迹、签收。发货不得再改库存。"""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from app.core.exceptions import AppError
from app.core.tenant import TenantContext
from app.db.session import SessionLocal
from app.models.tenant import MemberRole
from app.services.shipment import ShipmentService
from fastapi.testclient import TestClient

from tests.helpers.auth_api import auth_header, register_and_login
from tests.test_sales_orders import (
    _add_member,
    _catalog,
    _create_tenant,
    _customer,
    _initialize,
    _member_id,
    _order,
    _product,
    _roles,
    _warehouse,
)


def _header(token: str, tenant_id: int) -> dict[str, str]:
    return auth_header(token, tenant_id)


def _confirmed_outbound(
    client: TestClient,
    token: str,
    tenant_id: int,
    qty: int = 10,
    stock: int = 100,
) -> dict:
    customer = _customer(client, token, tenant_id, "物流客户")
    warehouse = _warehouse(client, token, tenant_id, "物流仓")
    product = _product(
        client,
        token,
        tenant_id,
        "物流货",
        [{"sku_code": "SHP-A", "name": "A", "spec_values": {}}],
    )
    sku_id = product["skus"][0]["id"]
    inventory = _initialize(client, token, tenant_id, warehouse["id"], sku_id, stock)
    header = _header(token, tenant_id)
    created = _order(
        client,
        token,
        tenant_id,
        customer_id=customer["id"],
        warehouse_id=warehouse["id"],
        items=[{"sku_id": sku_id, "quantity": qty}],
    )
    order_id = created.json()["data"]["id"]
    client.post(f"/api/v1/sales-orders/{order_id}/submit", headers=header)
    client.post(f"/api/v1/sales-orders/{order_id}/confirm", headers=header)
    outbound = client.get(
        "/api/v1/outbound-orders",
        params={"sales_order_id": order_id},
        headers=header,
    ).json()["data"]["items"][0]
    detail = client.get(f"/api/v1/outbound-orders/{outbound['id']}", headers=header).json()["data"]
    client.post(
        f"/api/v1/outbound-orders/{outbound['id']}/pick",
        json={"items": [{"id": detail["items"][0]["id"], "picked_quantity": qty}]},
        headers=header,
    )
    confirmed = client.post(f"/api/v1/outbound-orders/{outbound['id']}/confirm", headers=header)
    assert confirmed.status_code == 200, confirmed.text
    return {
        "header": header,
        "order_id": order_id,
        "outbound": confirmed.json()["data"],
        "inventory_id": inventory.json()["data"]["id"],
        "sku_id": sku_id,
        "warehouse_id": warehouse["id"],
    }


def _carrier(
    client: TestClient,
    token: str,
    tenant_id: int,
    name: str,
    extra: dict | None = None,
) -> dict:
    payload = {
        "name": name,
        "carrier_type": "DOMESTIC_EXPRESS",
        **(extra or {}),
    }
    response = client.post("/api/v1/carriers", json=payload, headers=_header(token, tenant_id))
    assert response.status_code == 200, response.text
    return response.json()["data"]


def _shipment(
    client: TestClient,
    token: str,
    tenant_id: int,
    outbound: dict,
    carrier_id: int,
    qty: int | None = None,
    tracking_no: str | None = "SF123",
) -> dict:
    item = outbound["items"][0]
    payload = {
        "outbound_order_id": outbound["id"],
        "carrier_id": carrier_id,
        "tracking_no": tracking_no,
        "items": [
            {
                "outbound_order_item_id": item["id"],
                "quantity": item["outbound_quantity"] if qty is None else qty,
            }
        ],
    }
    response = client.post("/api/v1/shipments", json=payload, headers=_header(token, tenant_id))
    return response


def _stock(client: TestClient, token: str, tenant_id: int, inventory_id: int) -> dict:
    return client.get(
        f"/api/v1/inventory/{inventory_id}",
        headers=_header(token, tenant_id),
    ).json()["data"]


def test_carrier_code_unique_per_tenant_and_isolation(client: TestClient) -> None:
    owner, _ = register_and_login(client, "car-code@example.com")
    tenant_id = _create_tenant(client, owner, "CarCode", "car-code")
    created = _carrier(client, owner, tenant_id, "顺丰")
    assert created["code"].startswith("CAR")
    assert len(created["code"]) == 13
    custom = _carrier(client, owner, tenant_id, "DHL", {"code": "DHL-SZ"})
    assert custom["code"] == "DHL-SZ"
    dup = client.post(
        "/api/v1/carriers",
        json={"name": "重复", "carrier_type": "OTHER", "code": "DHL-SZ"},
        headers=_header(owner, tenant_id),
    )
    assert dup.status_code == 409
    other, _ = register_and_login(client, "car-code-b@example.com")
    other_tenant = _create_tenant(client, other, "CarCodeB", "car-code-b")
    other_row = _carrier(client, other, other_tenant, "DHL", {"code": "DHL-SZ"})
    assert other_row["code"] == "DHL-SZ"
    hidden = client.get(f"/api/v1/carriers/{created['id']}", headers=_header(other, other_tenant))
    assert hidden.status_code == 404


def test_disabled_carrier_cannot_create_shipment_and_used_cannot_delete(client: TestClient) -> None:
    owner, _ = register_and_login(client, "car-use@example.com")
    tenant_id = _create_tenant(client, owner, "CarUse", "car-use")
    data = _confirmed_outbound(client, owner, tenant_id, 4)
    carrier = _carrier(client, owner, tenant_id, "停用商")
    client.patch(
        f"/api/v1/carriers/{carrier['id']}/status",
        json={"status": "DISABLED"},
        headers=data["header"],
    )
    blocked = _shipment(client, owner, tenant_id, data["outbound"], carrier["id"], qty=4)
    assert blocked.status_code == 400
    assert blocked.json()["data"]["error"] == "CARRIER_DISABLED"
    active = _carrier(client, owner, tenant_id, "在用商")
    created = _shipment(client, owner, tenant_id, data["outbound"], active["id"], qty=4)
    assert created.status_code == 200, created.text
    deleted = client.delete(f"/api/v1/carriers/{active['id']}", headers=data["header"])
    assert deleted.status_code == 400
    unused = _carrier(client, owner, tenant_id, "可删商")
    gone = client.delete(f"/api/v1/carriers/{unused['id']}", headers=data["header"])
    assert gone.status_code == 200


def test_create_shipment_from_confirmed_outbound_only(client: TestClient) -> None:
    owner, _ = register_and_login(client, "shp-create@example.com")
    tenant_id = _create_tenant(client, owner, "ShpCreate", "shp-create")
    data = _confirmed_outbound(client, owner, tenant_id, 10)
    carrier = _carrier(client, owner, tenant_id, "顺丰")
    before = _stock(client, owner, tenant_id, data["inventory_id"])
    first = _shipment(client, owner, tenant_id, data["outbound"], carrier["id"], qty=6)
    assert first.status_code == 200, first.text
    body = first.json()["data"]
    assert body["status"] == "DRAFT"
    assert body["shipment_no"].startswith("SHP")
    sales = client.get(
        f"/api/v1/sales-orders/{data['order_id']}",
        headers=data["header"],
    ).json()["data"]
    assert sales["status"] == "OUTBOUNDED"
    assert sales["items"][0]["shipped_quantity"] == 0
    after = _stock(client, owner, tenant_id, data["inventory_id"])
    assert after["quantity"] == before["quantity"]
    assert after["reserved_quantity"] == before["reserved_quantity"]
    over = _shipment(
        client,
        owner,
        tenant_id,
        data["outbound"],
        carrier["id"],
        qty=5,
        tracking_no="SF-OVER",
    )
    assert over.status_code == 400
    second = _shipment(
        client,
        owner,
        tenant_id,
        data["outbound"],
        carrier["id"],
        qty=4,
        tracking_no="SF124",
    )
    assert second.status_code == 200, second.text
    waiting = client.get(
        "/api/v1/outbound-orders",
        params={"sales_order_id": data["order_id"]},
        headers=data["header"],
    ).json()["data"]["items"][0]
    assert waiting["status"] == "CONFIRMED"
    pending = client.post(
        "/api/v1/outbound-orders",
        json={"sales_order_id": data["order_id"]},
        headers=data["header"],
    )
    assert pending.status_code == 400


def test_unconfirmed_outbound_cannot_create_shipment(client: TestClient) -> None:
    owner, _ = register_and_login(client, "shp-raw@example.com")
    tenant_id = _create_tenant(client, owner, "ShpRaw", "shp-raw")
    customer = _customer(client, owner, tenant_id, "未出库客户")
    warehouse = _warehouse(client, owner, tenant_id, "未出库仓")
    product = _product(
        client,
        owner,
        tenant_id,
        "未出库货",
        [{"sku_code": "RAW-A", "name": "A", "spec_values": {}}],
    )
    sku_id = product["skus"][0]["id"]
    _initialize(client, owner, tenant_id, warehouse["id"], sku_id, 10)
    header = _header(owner, tenant_id)
    created = _order(
        client,
        owner,
        tenant_id,
        customer_id=customer["id"],
        warehouse_id=warehouse["id"],
        items=[{"sku_id": sku_id, "quantity": 3}],
    )
    order_id = created.json()["data"]["id"]
    client.post(f"/api/v1/sales-orders/{order_id}/submit", headers=header)
    client.post(f"/api/v1/sales-orders/{order_id}/confirm", headers=header)
    outbound = client.get(
        "/api/v1/outbound-orders",
        params={"sales_order_id": order_id},
        headers=header,
    ).json()["data"]["items"][0]
    carrier = _carrier(client, owner, tenant_id, "未出库商")
    blocked = client.post(
        "/api/v1/shipments",
        json={"outbound_order_id": outbound["id"], "carrier_id": carrier["id"]},
        headers=header,
    )
    assert blocked.status_code == 400


def test_confirm_shipment_partial_and_full_without_inventory_change(client: TestClient) -> None:
    owner, _ = register_and_login(client, "shp-cfm@example.com")
    tenant_id = _create_tenant(client, owner, "ShpCfm", "shp-cfm")
    data = _confirmed_outbound(client, owner, tenant_id, 10)
    carrier = _carrier(client, owner, tenant_id, "发货商")
    header = data["header"]
    before = _stock(client, owner, tenant_id, data["inventory_id"])
    first = _shipment(client, owner, tenant_id, data["outbound"], carrier["id"], qty=6).json()[
        "data"
    ]
    no_track = client.patch(
        f"/api/v1/shipments/{first['id']}",
        json={"tracking_no": None},
        headers=header,
    )
    assert no_track.status_code == 200
    missing = client.post(f"/api/v1/shipments/{first['id']}/confirm", headers=header)
    assert missing.status_code == 400
    assert missing.json()["data"]["error"] == "SHIPMENT_TRACKING_REQUIRED"
    client.patch(
        f"/api/v1/shipments/{first['id']}",
        json={"tracking_no": "SF600"},
        headers=header,
    )
    confirmed = client.post(f"/api/v1/shipments/{first['id']}/confirm", headers=header)
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["data"]["status"] == "SHIPPED"
    again = client.post(f"/api/v1/shipments/{first['id']}/confirm", headers=header)
    assert again.status_code == 400
    assert again.json()["data"]["error"] == "SHIPMENT_ALREADY_CONFIRMED"
    sales = client.get(f"/api/v1/sales-orders/{data['order_id']}", headers=header).json()["data"]
    assert sales["status"] == "PARTIALLY_SHIPPED"
    assert sales["items"][0]["shipped_quantity"] == 6
    assert sales["items"][0]["outbound_quantity"] == 10
    after = _stock(client, owner, tenant_id, data["inventory_id"])
    assert after["quantity"] == before["quantity"]
    assert after["reserved_quantity"] == before["reserved_quantity"]
    second = _shipment(
        client, owner, tenant_id, data["outbound"], carrier["id"], qty=4, tracking_no="SF601"
    ).json()["data"]
    done = client.post(f"/api/v1/shipments/{second['id']}/confirm", headers=header)
    assert done.status_code == 200, done.text
    finished = client.get(f"/api/v1/sales-orders/{data['order_id']}", headers=header).json()["data"]
    assert finished["status"] == "SHIPPED"
    assert finished["items"][0]["shipped_quantity"] == 10
    final_stock = _stock(client, owner, tenant_id, data["inventory_id"])
    assert final_stock["quantity"] == before["quantity"]


def test_disabled_carrier_cannot_confirm(client: TestClient) -> None:
    owner, _ = register_and_login(client, "shp-dis@example.com")
    tenant_id = _create_tenant(client, owner, "ShpDis", "shp-dis")
    data = _confirmed_outbound(client, owner, tenant_id, 3)
    carrier = _carrier(client, owner, tenant_id, "稍后停用")
    draft = _shipment(client, owner, tenant_id, data["outbound"], carrier["id"], qty=3).json()[
        "data"
    ]
    client.patch(
        f"/api/v1/carriers/{carrier['id']}/status",
        json={"status": "DISABLED"},
        headers=data["header"],
    )
    blocked = client.post(f"/api/v1/shipments/{draft['id']}/confirm", headers=data["header"])
    assert blocked.status_code == 400
    assert blocked.json()["data"]["error"] == "CARRIER_DISABLED"


def test_same_shipment_confirm_only_succeeds_once(client: TestClient) -> None:
    owner, user_id = register_and_login(client, "shp-race@example.com")
    tenant_id = _create_tenant(client, owner, "ShpRace", "shp-race")
    _, member_id = _member_id(client, owner, tenant_id)
    data = _confirmed_outbound(client, owner, tenant_id, 4)
    carrier = _carrier(client, owner, tenant_id, "并发商")
    draft = _shipment(client, owner, tenant_id, data["outbound"], carrier["id"], qty=4).json()[
        "data"
    ]

    def _confirm(_: int) -> str:
        session = SessionLocal()
        try:
            ShipmentService(
                session,
                TenantContext(
                    user_id=user_id,
                    tenant_id=tenant_id,
                    member_id=member_id,
                    is_owner=True,
                    role=MemberRole.OWNER.value,
                ),
            ).confirm_shipment(draft["id"])
            return "ok"
        except AppError as exc:
            return str(exc.data.get("error", exc.code) if exc.data else exc.code)
        finally:
            session.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(_confirm, [1, 2]))
    assert results.count("ok") == 1
    sales = client.get(
        f"/api/v1/sales-orders/{data['order_id']}",
        headers=data["header"],
    ).json()["data"]
    assert sales["items"][0]["shipped_quantity"] == 4


def test_two_shipments_cannot_exceed_outbound_quantity(client: TestClient) -> None:
    owner, _ = register_and_login(client, "shp-over@example.com")
    tenant_id = _create_tenant(client, owner, "ShpOver", "shp-over")
    data = _confirmed_outbound(client, owner, tenant_id, 10)
    carrier = _carrier(client, owner, tenant_id, "超发商")
    first = _shipment(client, owner, tenant_id, data["outbound"], carrier["id"], qty=6)
    assert first.status_code == 200
    second = _shipment(
        client, owner, tenant_id, data["outbound"], carrier["id"], qty=6, tracking_no="SF-OVER"
    )
    assert second.status_code == 400
    assert second.json()["data"]["error"] == "SHIPMENT_EXCEEDS_OUTBOUND"


def test_tracking_deliver_and_order_completed(client: TestClient) -> None:
    owner, _ = register_and_login(client, "shp-dlv@example.com")
    tenant_id = _create_tenant(client, owner, "ShpDlv", "shp-dlv")
    data = _confirmed_outbound(client, owner, tenant_id, 10)
    carrier = _carrier(client, owner, tenant_id, "轨迹商")
    header = data["header"]
    before = _stock(client, owner, tenant_id, data["inventory_id"])
    first = _shipment(client, owner, tenant_id, data["outbound"], carrier["id"], qty=6).json()[
        "data"
    ]
    client.post(f"/api/v1/shipments/{first['id']}/confirm", headers=header)
    event = client.post(
        f"/api/v1/shipments/{first['id']}/tracking-events",
        json={
            "status": "IN_TRANSIT",
            "description": "到达深圳转运中心",
            "location": "深圳",
            "occurred_at": datetime.now().isoformat(),
        },
        headers=header,
    )
    assert event.status_code == 200, event.text
    assert event.json()["data"]["status"] == "IN_TRANSIT"
    tracked = client.get(f"/api/v1/shipments/{first['id']}/tracking-events", headers=header)
    assert tracked.status_code == 200
    assert tracked.json()["data"][0]["status"] == "IN_TRANSIT"
    first_delivered = client.post(
        f"/api/v1/shipments/{first['id']}/deliver",
        json={"remark": "本人签收"},
        headers=header,
    )
    assert first_delivered.status_code == 200, first_delivered.text
    assert first_delivered.json()["data"]["status"] == "DELIVERED"
    events = first_delivered.json()["data"]["tracking_events"]
    assert any(row["status"] == "DELIVERED" for row in events)
    again = client.post(f"/api/v1/shipments/{first['id']}/deliver", json={}, headers=header)
    assert again.status_code == 400
    sales = client.get(f"/api/v1/sales-orders/{data['order_id']}", headers=header).json()["data"]
    assert sales["status"] == "PARTIALLY_SHIPPED"
    second = _shipment(
        client, owner, tenant_id, data["outbound"], carrier["id"], qty=4, tracking_no="SF-2"
    ).json()["data"]
    client.post(f"/api/v1/shipments/{second['id']}/confirm", headers=header)
    client.post(f"/api/v1/shipments/{second['id']}/deliver", json={}, headers=header)
    finished = client.get(f"/api/v1/sales-orders/{data['order_id']}", headers=header).json()["data"]
    assert finished["status"] == "COMPLETED"
    after = _stock(client, owner, tenant_id, data["inventory_id"])
    assert after["quantity"] == before["quantity"]
    assert after["reserved_quantity"] == before["reserved_quantity"]


def test_draft_can_cancel_shipped_cannot(client: TestClient) -> None:
    owner, _ = register_and_login(client, "shp-can@example.com")
    tenant_id = _create_tenant(client, owner, "ShpCan", "shp-can")
    data = _confirmed_outbound(client, owner, tenant_id, 5)
    carrier = _carrier(client, owner, tenant_id, "取消商")
    draft = _shipment(client, owner, tenant_id, data["outbound"], carrier["id"], qty=2).json()[
        "data"
    ]
    cancelled = client.post(f"/api/v1/shipments/{draft['id']}/cancel", headers=data["header"])
    assert cancelled.status_code == 200
    assert cancelled.json()["data"]["status"] == "CANCELLED"
    blocked_confirm = client.post(
        f"/api/v1/shipments/{draft['id']}/confirm",
        headers=data["header"],
    )
    assert blocked_confirm.status_code == 400
    live = _shipment(
        client, owner, tenant_id, data["outbound"], carrier["id"], qty=5, tracking_no="SF-LIVE"
    ).json()["data"]
    client.post(f"/api/v1/shipments/{live['id']}/confirm", headers=data["header"])
    blocked = client.post(f"/api/v1/shipments/{live['id']}/cancel", headers=data["header"])
    assert blocked.status_code == 400
    assert blocked.json()["data"]["error"] == "SHIPMENT_NOT_CANCELLABLE"


def test_shipment_tenant_isolation(client: TestClient) -> None:
    owner, _ = register_and_login(client, "shp-iso@example.com")
    tenant_id = _create_tenant(client, owner, "ShpIso", "shp-iso")
    data = _confirmed_outbound(client, owner, tenant_id, 2)
    carrier = _carrier(client, owner, tenant_id, "隔离商")
    created = _shipment(client, owner, tenant_id, data["outbound"], carrier["id"], qty=2).json()[
        "data"
    ]
    other, _ = register_and_login(client, "shp-iso-b@example.com")
    other_tenant = _create_tenant(client, other, "ShpIsoB", "shp-iso-b")
    hidden = client.get(f"/api/v1/shipments/{created['id']}", headers=_header(other, other_tenant))
    assert hidden.status_code == 404
    foreign = client.post(
        "/api/v1/shipments",
        json={"outbound_order_id": data["outbound"]["id"], "carrier_id": carrier["id"]},
        headers=_header(other, other_tenant),
    )
    assert foreign.status_code == 404


def test_viewer_cannot_mutate_shipping(client: TestClient) -> None:
    owner, _ = register_and_login(client, "shp-perm@example.com")
    tenant_id = _create_tenant(client, owner, "ShpPerm", "shp-perm")
    roles = _roles(client, owner, tenant_id)
    viewer = _add_member(client, owner, tenant_id, "shp-view@example.com", [roles["VIEWER"]["id"]])
    data = _confirmed_outbound(client, owner, tenant_id, 2)
    carrier = _carrier(client, owner, tenant_id, "权限商")
    draft = _shipment(client, owner, tenant_id, data["outbound"], carrier["id"], qty=2).json()[
        "data"
    ]
    listed = client.get("/api/v1/shipments", headers=_header(viewer, tenant_id))
    assert listed.status_code == 200
    created = client.post(
        "/api/v1/shipments",
        json={"outbound_order_id": data["outbound"]["id"], "carrier_id": carrier["id"]},
        headers=_header(viewer, tenant_id),
    )
    assert created.status_code == 403
    confirmed = client.post(
        f"/api/v1/shipments/{draft['id']}/confirm",
        headers=_header(viewer, tenant_id),
    )
    assert confirmed.status_code == 403
    catalog = _catalog(client, owner, tenant_id)
    assert "shipment:confirm" in catalog
    assert "carrier:read" in catalog

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from app.core.events import AggregateType, EventType
from app.core.sanitize import public_error_message, sanitize_payload
from app.db.session import SessionLocal
from app.models.system_event import SystemEvent
from app.services.event_publisher import EventPublisher
from app.tasks.worker import execute_task, run_once
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from tests.helpers.auth_api import auth_header, register_and_login


def _tenant(client: TestClient, token: str, name: str, code: str) -> int:
    response = client.post(
        "/api/v1/tenants", json={"name": name, "code": code}, headers=auth_header(token)
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


def _warehouse(client: TestClient, token: str, tenant_id: int) -> dict:
    response = client.post(
        "/api/v1/warehouses",
        json={"name": "主仓", "type": "DOMESTIC"},
        headers=auth_header(token, tenant_id),
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


def _product_sku(client: TestClient, token: str, tenant_id: int) -> int:
    category = client.post(
        "/api/v1/product-categories",
        json={"name": "事件类目"},
        headers=auth_header(token, tenant_id),
    )
    created = client.post(
        "/api/v1/products",
        json={
            "name": "事件商品",
            "category_id": category.json()["data"]["id"],
            "skus": [{"sku_code": "EVT-SKU", "name": "默认"}],
        },
        headers=auth_header(token, tenant_id),
    )
    assert created.status_code == 200, created.text
    return int(created.json()["data"]["skus"][0]["id"])


def _customer(client: TestClient, token: str, tenant_id: int) -> dict:
    response = client.post(
        "/api/v1/customers",
        json={"name": "事件客户", "country_code": "CN", "city": "深圳", "address": "科技园 1 号"},
        headers=auth_header(token, tenant_id),
    )
    return response.json()["data"]


def _init_stock(
    client: TestClient, token: str, tenant_id: int, warehouse_id: int, sku_id: int
) -> None:
    response = client.post(
        "/api/v1/inventory/initialize",
        json={"warehouse_id": warehouse_id, "sku_id": sku_id, "quantity": 20},
        headers=auth_header(token, tenant_id),
    )
    assert response.status_code == 200, response.text


def test_sanitize_payload_strips_secrets() -> None:
    cleaned = sanitize_payload(
        {"order_no": "SO1", "password": "secret", "token": "abc", "nested": {"access_token": "x"}}
    )
    assert cleaned["order_no"] == "SO1"
    assert "password" not in cleaned
    assert "token" not in cleaned
    assert "access_token" not in cleaned["nested"]
    assert public_error_message(RuntimeError("token=abc password=x")) == (
        "任务执行失败，请查看任务日志"
    )


def test_event_rolls_back_with_business_transaction() -> None:
    session = SessionLocal()
    try:
        publisher = EventPublisher(session, None)
        event = publisher.record(
            event_type=EventType.TASK_FAILED,
            aggregate_type=AggregateType.TASK,
            aggregate_id=1,
            payload={"password": "nope"},
        )
        session.flush()
        event_id = event.event_id
        assert "password" not in (event.payload or {})
        session.rollback()
        remaining = session.execute(
            select(func.count()).select_from(SystemEvent).where(SystemEvent.event_id == event_id)
        ).scalar_one()
        assert remaining == 0
    finally:
        session.close()


def test_order_confirm_event_log_and_tenant_isolation(client: TestClient) -> None:
    owner_a, _ = register_and_login(client, "evt-a@example.com")
    owner_b, _ = register_and_login(client, "evt-b@example.com")
    tenant_a = _tenant(client, owner_a, "事件A", "EVT-A")
    tenant_b = _tenant(client, owner_b, "事件B", "EVT-B")
    warehouse = _warehouse(client, owner_a, tenant_a)
    sku_id = _product_sku(client, owner_a, tenant_a)
    _init_stock(client, owner_a, tenant_a, warehouse["id"], sku_id)
    customer = _customer(client, owner_a, tenant_a)
    order = client.post(
        "/api/v1/sales-orders",
        json={
            "customer_id": customer["id"],
            "warehouse_id": warehouse["id"],
            "recipient_name": "John",
            "address": "科技园 1 号",
            "items": [{"sku_id": sku_id, "quantity": 2, "unit_price": 10}],
        },
        headers=auth_header(owner_a, tenant_a),
    ).json()["data"]
    header = {**auth_header(owner_a, tenant_a), "X-Request-ID": "req-event-confirm-001"}
    submitted = client.post(f"/api/v1/sales-orders/{order['id']}/submit", headers=header)
    assert submitted.status_code == 200
    confirmed = client.post(f"/api/v1/sales-orders/{order['id']}/confirm", headers=header)
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.headers.get("x-request-id") == "req-event-confirm-001"

    events = client.get(
        "/api/v1/events",
        params={"event_type": "SALES_ORDER_CONFIRMED", "aggregate_id": order["id"]},
        headers=auth_header(owner_a, tenant_a),
    )
    assert events.status_code == 200, events.text
    items = events.json()["data"]["items"]
    assert len(items) == 1
    assert items[0]["event_id"].startswith("evt_")
    assert items[0]["aggregate_type"] == "SALES_ORDER"
    assert items[0]["payload"]["order_no"]
    assert "password" not in (items[0]["payload"] or {})

    logs = client.get(
        "/api/v1/operation-logs",
        params={"action": "CONFIRM", "module": "order"},
        headers=auth_header(owner_a, tenant_a),
    )
    assert logs.status_code == 200
    log_items = logs.json()["data"]["items"]
    assert log_items
    assert log_items[0]["result"] == "SUCCESS"
    assert log_items[0]["request_id"] == "req-event-confirm-001"
    assert log_items[0]["operator_user_id"]

    other = client.get("/api/v1/events", headers=auth_header(owner_b, tenant_b))
    assert other.status_code == 200
    assert other.json()["data"]["total"] == 0
    other_logs = client.get("/api/v1/operation-logs", headers=auth_header(owner_b, tenant_b))
    assert other_logs.json()["data"]["total"] == 0

    detail = client.get(
        f"/api/v1/events/{items[0]['event_id']}", headers=auth_header(owner_b, tenant_b)
    )
    assert detail.status_code == 404
    deleted = client.delete(f"/api/v1/operation-logs/{log_items[0]['id']}", headers=header)
    assert deleted.status_code in {
        404,
        405,
        422,
    }

    failed = client.post("/api/v1/sales-orders/999999/confirm", headers=header)
    assert failed.status_code in {400, 404}
    failed_logs = client.get(
        "/api/v1/operation-logs",
        params={"action": "CONFIRM", "result": "FAILED"},
        headers=auth_header(owner_a, tenant_a),
    )
    assert failed_logs.json()["data"]["total"] >= 1

    inventory = client.get(
        "/api/v1/inventory", headers=auth_header(owner_a, tenant_a)
    ).json()["data"]["items"][0]
    adjusted = client.post(
        f"/api/v1/inventory/{inventory['id']}/adjust",
        json={"type": "ADJUST_OUT", "quantity": 1, "remark": "事件调整"},
        headers=auth_header(owner_a, tenant_a),
    )
    assert adjusted.status_code == 200, adjusted.text
    adjusted_events = client.get(
        "/api/v1/events",
        params={"event_type": "INVENTORY_ADJUSTED"},
        headers=auth_header(owner_a, tenant_a),
    )
    assert adjusted_events.json()["data"]["total"] >= 1

    roles = _roles(client, owner_a, tenant_a)
    viewer = _add_member(
        client, owner_a, tenant_a, "evt-viewer@example.com", [roles["VIEWER"]["id"]]
    )
    none_role = client.post(
        "/api/v1/roles",
        json={"code": "NO_EVT", "name": "无事件", "permission_ids": []},
        headers=auth_header(owner_a, tenant_a),
    )
    member = _add_member(
        client, owner_a, tenant_a, "evt-none@example.com", [none_role.json()["data"]["id"]]
    )
    assert client.get("/api/v1/events", headers=auth_header(viewer, tenant_a)).status_code == 200
    viewer_logs = client.get("/api/v1/operation-logs", headers=auth_header(viewer, tenant_a))
    assert viewer_logs.status_code == 403
    assert client.get("/api/v1/events", headers=auth_header(member, tenant_a)).status_code == 403


def test_report_export_task_retry_and_download_isolation(client: TestClient) -> None:
    owner_a, _ = register_and_login(client, "task-a@example.com")
    owner_b, _ = register_and_login(client, "task-b@example.com")
    tenant_a = _tenant(client, owner_a, "任务A", "TSK-A")
    tenant_b = _tenant(client, owner_b, "任务B", "TSK-B")
    created = client.post(
        "/api/v1/analytics/sales/export-tasks",
        params={"start_date": "2026-10-01", "end_date": "2026-10-12"},
        headers=auth_header(owner_a, tenant_a),
    )
    assert created.status_code == 200, created.text
    task = created.json()["data"]
    assert task["task_type"] == "REPORT_EXPORT"
    assert task["progress"] == 0
    assert task["status"] in {"PENDING", "QUEUED"}
    execute_task(task["task_id"])
    run_once(block_seconds=0)
    detail = client.get(f"/api/v1/tasks/{task['task_id']}", headers=auth_header(owner_a, tenant_a))
    assert detail.status_code == 200
    body = detail.json()["data"]
    assert body["status"] == "SUCCESS"
    assert body["progress"] == 100
    assert body["result"]["row_count"] >= 0
    logs = client.get(
        f"/api/v1/tasks/{task['task_id']}/logs", headers=auth_header(owner_a, tenant_a)
    )
    assert logs.json()["data"]
    download = client.get(
        f"/api/v1/tasks/{task['task_id']}/download", headers=auth_header(owner_a, tenant_a)
    )
    assert download.status_code == 200
    assert download.content.startswith(b"\xef\xbb\xbf") or b"date" in download.content.lower()
    assert len(download.content) > 0
    forbidden = client.get(
        f"/api/v1/tasks/{task['task_id']}/download", headers=auth_header(owner_b, tenant_b)
    )
    assert forbidden.status_code == 404
    retry_ok = client.post(
        f"/api/v1/tasks/{task['task_id']}/retry", headers=auth_header(owner_a, tenant_a)
    )
    assert retry_ok.status_code == 400

    session = SessionLocal()
    try:
        from app.models.async_task import AsyncTask

        row = session.execute(
            select(AsyncTask).where(AsyncTask.task_id == task["task_id"])
        ).scalar_one()
        row.status = "FAILED"
        row.error_message = "password=super-secret simulated"
        session.commit()
    finally:
        session.close()

    def _retry() -> int:
        return client.post(
            f"/api/v1/tasks/{task['task_id']}/retry", headers=auth_header(owner_a, tenant_a)
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        codes = list(pool.map(lambda _: _retry(), range(2)))
    assert codes.count(200) == 1
    assert 400 in codes or codes.count(200) == 1

    failed_create = client.post(
        "/api/v1/analytics/sales/export-tasks",
        json={"kind": "sales_trend"},
        headers=auth_header(owner_a, tenant_a),
    )
    assert failed_create.status_code == 200
    bogus = client.post(
        "/api/v1/analytics/sales/export-tasks",
        params={"start_date": "2026-10-01", "end_date": "2026-10-12"},
        headers=auth_header(owner_a, tenant_a),
    ).json()["data"]
    session = SessionLocal()
    try:
        from app.models.async_task import AsyncTask

        row = session.execute(
            select(AsyncTask).where(AsyncTask.task_id == bogus["task_id"])
        ).scalar_one()
        row.payload = {"kind": "unknown"}
        row.status = "QUEUED"
        session.commit()
    finally:
        session.close()
    status = execute_task(bogus["task_id"])
    assert status == "FAILED"
    failed_detail = client.get(
        f"/api/v1/tasks/{bogus['task_id']}", headers=auth_header(owner_a, tenant_a)
    ).json()["data"]
    assert failed_detail["status"] == "FAILED"
    assert "password" not in (failed_detail["error_message"] or "").lower()
    assert "super-secret" not in (failed_detail["error_message"] or "")

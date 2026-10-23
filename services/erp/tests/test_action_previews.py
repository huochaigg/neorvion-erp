from app.db.session import SessionLocal
from app.models.async_task import AsyncTask
from app.models.inventory import Inventory
from app.models.operation_log import OperationLog
from app.models.purchase import PurchaseOrder
from app.models.sales_order import SalesOrder
from app.models.stock_transfer import StockTransfer
from app.models.system_event import SystemEvent
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from tests.helpers.auth_api import auth_header, register_and_login
from tests.test_purchase import _create_supplier
from tests.test_sales_orders import _create_tenant, _customer, _initialize, _product, _warehouse


def _business_snapshot(tenant_id: int, inventory_id: int) -> tuple:
    session = SessionLocal()
    try:
        inventory = session.get(Inventory, inventory_id)
        assert inventory is not None
        models = (PurchaseOrder, SalesOrder, StockTransfer, SystemEvent, OperationLog, AsyncTask)
        counts = tuple(
            int(
                session.scalar(
                    select(func.count()).select_from(model).where(model.tenant_id == tenant_id)
                )
                or 0
            )
            for model in models
        )
        return (*counts, inventory.quantity, inventory.reserved_quantity, inventory.version)
    finally:
        session.close()


def test_all_action_previews_are_side_effect_free(client: TestClient) -> None:
    owner, _ = register_and_login(client, "preview-all@example.com")
    tenant_id = _create_tenant(client, owner, "Preview", "preview-all")
    headers = auth_header(owner, tenant_id)
    source = _warehouse(client, owner, tenant_id, "源仓")
    target = _warehouse(client, owner, tenant_id, "目标仓")
    supplier = _create_supplier(client, owner, tenant_id, "预检供应商")
    customer = _customer(client, owner, tenant_id, "预检客户")
    product = _product(
        client,
        owner,
        tenant_id,
        "预检商品",
        [{"sku_code": "SKU-PREVIEW", "name": "默认", "spec_values": {}}],
    )
    sku_id = product["skus"][0]["id"]
    inventory = _initialize(client, owner, tenant_id, source["id"], sku_id, 100).json()["data"]
    before = _business_snapshot(tenant_id, inventory["id"])

    purchase = client.post(
        "/api/v1/action-previews/purchase-order",
        json={
            "supplier_id": supplier["id"],
            "warehouse_id": source["id"],
            "items": [{"sku_id": sku_id, "quantity": 10}],
        },
        headers=headers,
    )
    sales = client.post(
        "/api/v1/action-previews/sales-order",
        json={
            "customer_id": customer["id"],
            "warehouse_id": source["id"],
            "items": [{"sku_id": sku_id, "quantity": 5, "unit_price": 20}],
        },
        headers=headers,
    )
    transfer = client.post(
        "/api/v1/action-previews/inventory-transfer",
        json={
            "source_warehouse_id": source["id"],
            "target_warehouse_id": target["id"],
            "items": [{"sku_id": sku_id, "quantity": 20}],
        },
        headers=headers,
    )

    assert purchase.status_code == sales.status_code == transfer.status_code == 200
    assert purchase.json()["data"]["valid"] is True
    assert sales.json()["data"]["valid"] is True
    assert transfer.json()["data"]["valid"] is True
    assert _business_snapshot(tenant_id, inventory["id"]) == before


def test_transfer_preview_blocks_insufficient_inventory_without_writing(client: TestClient) -> None:
    owner, _ = register_and_login(client, "preview-stock@example.com")
    tenant_id = _create_tenant(client, owner, "PreviewStock", "preview-stock")
    source = _warehouse(client, owner, tenant_id, "源仓")
    target = _warehouse(client, owner, tenant_id, "目标仓")
    product = _product(
        client, owner, tenant_id, "库存商品", [{"sku_code": "SKU-LOW", "name": "默认"}]
    )
    sku_id = product["skus"][0]["id"]
    inventory = _initialize(client, owner, tenant_id, source["id"], sku_id, 3).json()["data"]
    before = _business_snapshot(tenant_id, inventory["id"])

    response = client.post(
        "/api/v1/action-previews/inventory-transfer",
        json={
            "source_warehouse_id": source["id"],
            "target_warehouse_id": target["id"],
            "items": [{"sku_id": sku_id, "quantity": 4}],
        },
        headers=auth_header(owner, tenant_id),
    )
    assert response.status_code == 200
    assert response.json()["data"]["valid"] is False
    assert (
        response.json()["data"]["blocking_errors"][0]["code"] == "INSUFFICIENT_AVAILABLE_INVENTORY"
    )
    assert _business_snapshot(tenant_id, inventory["id"]) == before

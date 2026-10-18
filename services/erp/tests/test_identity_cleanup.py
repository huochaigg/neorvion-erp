"""确认 ERP 已去掉身份表，单据姓名来自本地快照而不是 users。"""

from app.db.session import engine
from sqlalchemy import inspect, text

from tests.helpers.auth_api import register_and_login
from tests.test_sales_orders import _create_tenant, _customer, _order, _product, _warehouse

_DROPPED = (
    "users",
    "tenants",
    "tenant_members",
    "roles",
    "permissions",
    "member_roles",
    "role_permissions",
)


def test_erp_database_has_no_legacy_identity_tables() -> None:
    tables = set(inspect(engine).get_table_names())
    for name in _DROPPED:
        assert name not in tables
    assert "identity_name_snapshots" in tables
    assert "sales_orders" in tables


def test_sales_order_list_uses_identity_name_snapshot(client) -> None:
    token, _ = register_and_login(client, "snapshot-owner@example.com", display_name="快照操作人")
    tenant_id = _create_tenant(client, token, "快照企业", "snapshot-co")
    header = {"Authorization": f"Bearer {token}", "X-Tenant-ID": str(tenant_id)}
    warehouse = _warehouse(client, token, tenant_id, "快照仓")
    product = _product(
        client,
        token,
        tenant_id,
        "快照商品",
        [{"sku_code": "SNAP-A", "name": "A", "spec_values": {}}],
    )
    customer = _customer(client, token, tenant_id, "快照客户")
    created = _order(
        client,
        token,
        tenant_id,
        customer_id=customer["id"],
        warehouse_id=warehouse["id"],
        items=[{"sku_id": product["skus"][0]["id"], "quantity": 1, "unit_price": 10}],
    )
    assert created.status_code == 200, created.text

    listed = client.get("/api/v1/sales-orders", headers=header)
    assert listed.status_code == 200, listed.text
    item = listed.json()["data"]["items"][0]
    assert item["created_by_name"] == "快照操作人"

    with engine.connect() as connection:
        row = connection.execute(
            text("SELECT display_name FROM identity_name_snapshots WHERE user_id = :uid"),
            {"uid": item["created_by"]},
        ).mappings().one()
    assert row["display_name"] == "快照操作人"

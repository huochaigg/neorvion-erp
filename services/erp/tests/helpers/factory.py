"""高频测试 setup。不重写全部历史测试，只给跨领域集成测试复用。"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi.testclient import TestClient

from tests.helpers.auth_api import auth_header, register_and_login
from tests.test_sales_orders import (
    _create_tenant,
    _customer,
    _initialize,
    _order,
    _product,
    _warehouse,
)
from tests.test_shipping import _carrier


@dataclass
class TenantFixture:
    client: TestClient
    token: str
    tenant_id: int
    header: dict[str, str]

    def warehouse(self, name: str = "核心仓") -> dict:
        return _warehouse(self.client, self.token, self.tenant_id, name)

    def product(self, name: str, sku_code: str = "CORE-A") -> dict:
        return _product(
            self.client,
            self.token,
            self.tenant_id,
            name,
            [{"sku_code": sku_code, "name": "A", "spec_values": {}}],
        )

    def customer(self, name: str = "核心客户") -> dict:
        return _customer(self.client, self.token, self.tenant_id, name)

    def carrier(self, name: str = "核心快递") -> dict:
        return _carrier(self.client, self.token, self.tenant_id, name)

    def initialize(self, warehouse_id: int, sku_id: int, quantity: int) -> dict:
        response = _initialize(
            self.client, self.token, self.tenant_id, warehouse_id, sku_id, quantity
        )
        assert response.status_code == 200, response.text
        return response.json()["data"]

    def create_sales_order(
        self, customer_id: int, warehouse_id: int, sku_id: int, qty: int
    ) -> dict:
        response = _order(
            self.client,
            self.token,
            self.tenant_id,
            customer_id=customer_id,
            warehouse_id=warehouse_id,
            items=[{"sku_id": sku_id, "quantity": qty, "unit_price": 10}],
        )
        assert response.status_code == 200, response.text
        return response.json()["data"]

    def get_inventory(self, inventory_id: int) -> dict:
        response = self.client.get(f"/api/v1/inventory/{inventory_id}", headers=self.header)
        assert response.status_code == 200, response.text
        return response.json()["data"]

    def get_order(self, order_id: int) -> dict:
        response = self.client.get(f"/api/v1/sales-orders/{order_id}", headers=self.header)
        assert response.status_code == 200, response.text
        return response.json()["data"]


def bootstrap(client: TestClient, email: str, name: str, code: str) -> TenantFixture:
    token, _ = register_and_login(client, email)
    tenant_id = _create_tenant(client, token, name, code)
    return TenantFixture(
        client=client,
        token=token,
        tenant_id=tenant_id,
        header=auth_header(token, tenant_id),
    )

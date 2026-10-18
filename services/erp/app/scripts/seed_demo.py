"""幂等写入演示业务单。不会创建用户或租户。

身份必须已经存在于 IAM。用法：

    uv run --directory services/iam python -m app.scripts.seed_permissions
    # 在 IAM 创建演示用户/租户后：
    DEMO_TENANT_ID=1 DEMO_USER_ID=1 DEMO_MEMBER_ID=1 DEMO_DISPLAY_NAME='Demo Owner' \\
      uv run --directory services/erp python -m app.scripts.seed_demo

已存在「深圳一号仓」时直接退出，不重复插入业务单。
数据为 synthetic / demo，不是真实客户或 GMV。
"""

from __future__ import annotations

import os
from decimal import Decimal

from sqlalchemy import select

from app.core.identity_projection import project_display_user
from app.core.permissions import known_permission_codes
from app.core.tenant import TenantContext
from app.db.session import SessionLocal
from app.models.warehouse import Warehouse
from app.schemas.carrier import CarrierCreate
from app.schemas.customer import CustomerCreate
from app.schemas.inventory import InventoryInitialize
from app.schemas.outbound import OutboundPick, OutboundPickItem
from app.schemas.product import CategoryCreate, ProductCreate, SkuInput
from app.schemas.purchase import PurchaseOrderCreate, PurchaseOrderItemIn
from app.schemas.purchase_receipt import PurchaseReceiptCreate, PurchaseReceiptItemIn
from app.schemas.sales_order import SalesOrderCreate, SalesOrderItemIn
from app.schemas.shipment import ShipmentCreate, ShipmentDeliver, ShipmentItemIn
from app.schemas.supplier import SupplierCreate
from app.schemas.warehouse import WarehouseCreate
from app.services.carrier import CarrierService
from app.services.catalog import CatalogService
from app.services.customer import CustomerService
from app.services.inventory import InventoryService
from app.services.outbound import OutboundOrderService
from app.services.product import ProductService
from app.services.purchase import PurchaseOrderService
from app.services.purchase_receipt import PurchaseReceiptService
from app.services.sales_order import SalesOrderService
from app.services.shipment import ShipmentService
from app.services.supplier import SupplierService
from app.services.warehouse import WarehouseService

DEMO_WAREHOUSE_NAME = "深圳一号仓"

_PRODUCTS = [
    ("蓝牙耳机", "黑"),
    ("机械键盘", "青轴"),
    ("显示器支架", "铝"),
    ("桌面灯", "白"),
    ("无线鼠标", "灰"),
    ("摄像头", "4K"),
    ("拓展坞", "USB4"),
    ("笔记本支架", "灰"),
    ("收纳盒", "中"),
    ("电源适配器", "65W"),
]


def _env_identity() -> tuple[int, int, int, str]:
    """读取 IAM 已有身份 ID。ERP 禁止自己建 users / tenants。"""
    try:
        tenant_id = int((os.environ.get("DEMO_TENANT_ID") or "").strip())
        user_id = int((os.environ.get("DEMO_USER_ID") or "").strip())
        member_id = int((os.environ.get("DEMO_MEMBER_ID") or "").strip())
    except ValueError as exc:
        raise SystemExit("DEMO_TENANT_ID / DEMO_USER_ID / DEMO_MEMBER_ID 必须是正整数") from exc
    if tenant_id <= 0 or user_id <= 0 or member_id <= 0:
        raise SystemExit(
            "请设置 DEMO_TENANT_ID、DEMO_USER_ID、DEMO_MEMBER_ID（来自 IAM，不要在 ERP 建用户）"
        )
    display_name = (os.environ.get("DEMO_DISPLAY_NAME") or "Demo Owner").strip() or "Demo Owner"
    return tenant_id, user_id, member_id, display_name[:64]


def _context(user_id: int, tenant_id: int, member_id: int, display_name: str) -> TenantContext:
    return TenantContext(
        user_id=user_id,
        tenant_id=tenant_id,
        member_id=member_id,
        is_owner=True,
        role="OWNER",
        permission_codes=frozenset(known_permission_codes()),
        role_codes=("OWNER",),
        display_name=display_name,
    )


def main() -> None:
    tenant_id, user_id, member_id, display_name = _env_identity()
    session = SessionLocal()
    try:
        existing = session.scalar(
            select(Warehouse.id).where(
                Warehouse.tenant_id == tenant_id,
                Warehouse.name == DEMO_WAREHOUSE_NAME,
            )
        )
        if existing is not None:
            print(f"demo warehouse already exists tenant_id={tenant_id}, skip business seed")
            return

        ctx = _context(user_id, tenant_id, member_id, display_name)
        project_display_user(session, ctx)

        warehouses = [
            WarehouseService(session, ctx).create_warehouse(
                WarehouseCreate(name=name, type="DOMESTIC", city="深圳")
            )
            for name in (DEMO_WAREHOUSE_NAME, "广州仓", "美西海外仓")
        ]
        main_wh = warehouses[0]
        category = CatalogService(session, ctx).create_category(CategoryCreate(name="3C配件"))
        sku_ids: list[int] = []
        products = ProductService(session, ctx)
        inventory = InventoryService(session, ctx)
        for index, (name, spec) in enumerate(_PRODUCTS, start=1):
            created = products.create_product(
                ProductCreate(
                    name=f"Demo {name}",
                    category_id=category.id,
                    skus=[
                        SkuInput(sku_code=f"DEMO-{index:02d}A", name=f"{name}-{spec}"),
                        SkuInput(sku_code=f"DEMO-{index:02d}B", name=f"{name}-备选"),
                    ],
                )
            )
            for sku in created.skus:
                sku_ids.append(sku.id)
                inventory.initialize_inventory(
                    InventoryInitialize(
                        warehouse_id=main_wh.id,
                        sku_id=sku.id,
                        quantity=100,
                        remark="demo seed",
                    )
                )

        supplier = SupplierService(session, ctx).create_supplier(
            SupplierCreate(name="Demo 供应商", country_code="CN", city="深圳")
        )
        customer = CustomerService(session, ctx).create_customer(
            CustomerCreate(
                name="Demo 客户",
                country_code="CN",
                city="深圳",
                address="科技园演示路 1 号",
            )
        )
        carrier = CarrierService(session, ctx).create_carrier(
            CarrierCreate(name="Demo 快递", carrier_type="DOMESTIC_EXPRESS")
        )

        purchase = PurchaseOrderService(session, ctx)
        po = purchase.create_order(
            PurchaseOrderCreate(
                supplier_id=supplier.id,
                warehouse_id=main_wh.id,
                items=[
                    PurchaseOrderItemIn(
                        sku_id=sku_ids[0], quantity=50, unit_price=Decimal("20")
                    )
                ],
            )
        )
        purchase.submit_order(po.id)
        purchase.approve_order(po.id)
        receipt = PurchaseReceiptService(session, ctx)
        draft = receipt.create_receipt(
            PurchaseReceiptCreate(
                purchase_order_id=po.id,
                items=[
                    PurchaseReceiptItemIn(
                        purchase_order_item_id=po.items[0].id, received_quantity=50
                    )
                ],
            )
        )
        receipt.confirm_receipt(draft.id)

        sales = SalesOrderService(session, ctx)
        order = sales.create_order(
            SalesOrderCreate(
                customer_id=customer.id,
                warehouse_id=main_wh.id,
                recipient_name="演示收件人",
                address="科技园演示路 1 号",
                items=[SalesOrderItemIn(sku_id=sku_ids[0], quantity=80, unit_price=Decimal("99"))],
            )
        )
        sales.submit_order(order.id)
        sales.confirm_order(order.id)

        outbound_svc = OutboundOrderService(session, ctx)
        outbound_list = outbound_svc.list_outbounds(
            q=None,
            sales_order_id=order.id,
            warehouse_id=None,
            status=None,
            created_from=None,
            created_to=None,
            page=1,
            page_size=20,
        )
        outbound = outbound_svc.get_outbound(outbound_list.items[0].id)
        outbound_svc.confirm_picking(
            outbound.id,
            OutboundPick(
                items=[
                    OutboundPickItem(id=item.id, picked_quantity=item.planned_quantity)
                    for item in outbound.items
                ],
                finish=True,
            ),
        )
        outbound_svc.confirm_outbound(outbound.id)
        refreshed = outbound_svc.get_outbound(outbound.id)

        shipments = ShipmentService(session, ctx)
        shipment = shipments.create_shipment(
            ShipmentCreate(
                outbound_order_id=refreshed.id,
                carrier_id=carrier.id,
                tracking_no="DEMO-SF-001",
                items=[
                    ShipmentItemIn(
                        outbound_order_item_id=item.id, quantity=item.outbound_quantity
                    )
                    for item in refreshed.items
                ],
            )
        )
        shipments.confirm_shipment(shipment.id)
        shipments.mark_delivered(shipment.id, ShipmentDeliver())
        print(f"demo business seed ready tenant_id={tenant_id}")
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()

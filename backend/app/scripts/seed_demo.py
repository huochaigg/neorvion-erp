"""幂等写入演示租户 Neorvion Demo。不会在 API 启动时自动执行。

用法（backend 目录，且已设置 DEMO_EMAIL / DEMO_PASSWORD）：

    uv run python -m app.scripts.seed_permissions
    uv run python -m app.scripts.seed_demo

已存在 code=neorvion-demo 的租户时直接退出，不重复插入业务单。
数据为 synthetic / demo，不是真实客户或 GMV。
"""

from __future__ import annotations

import os
from decimal import Decimal

from app.core.security import hash_password
from app.core.tenant import TenantContext
from app.db.session import SessionLocal
from app.models.user import User, UserStatus
from app.repositories.tenant import TenantMemberRepository, TenantRepository
from app.repositories.user import UserRepository
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
from app.services.rbac import RoleService
from app.services.sales_order import SalesOrderService
from app.services.shipment import ShipmentService
from app.services.supplier import SupplierService
from app.services.tenant import TenantService
from app.services.warehouse import WarehouseService

DEMO_TENANT_CODE = "neorvion-demo"
DEMO_TENANT_NAME = "Neorvion Demo"

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


def _env_credentials() -> tuple[str, str]:
    email = (os.environ.get("DEMO_EMAIL") or "").strip().lower()
    password = os.environ.get("DEMO_PASSWORD") or ""
    if not email or not password:
        raise SystemExit("请设置 DEMO_EMAIL 与 DEMO_PASSWORD 后再执行演示 seed。")
    has_letter = any(char.isalpha() for char in password)
    has_digit = any(char.isdigit() for char in password)
    if len(password) < 8 or not has_letter or not has_digit:
        raise SystemExit("DEMO_PASSWORD 至少 8 位，且同时包含字母和数字。")
    return email, password


def _context(user_id: int, tenant_id: int, member_id: int) -> TenantContext:
    return TenantContext(
        user_id=user_id,
        tenant_id=tenant_id,
        member_id=member_id,
        is_owner=True,
        role="OWNER",
    )


def main() -> None:
    email, password = _env_credentials()
    session = SessionLocal()
    try:
        RoleService(session).seed_permission_catalog()
        session.commit()

        users = UserRepository(session)
        user = users.get_by_email(email)
        if user is None:
            user = User(
                email=email,
                password_hash=hash_password(password),
                display_name="Demo Owner",
                status=UserStatus.ACTIVE.value,
                must_change_password=False,
            )
            users.add(user)
            session.commit()
            print(f"created demo user {email}")
        else:
            print(f"reuse demo user {email}")

        tenants = TenantRepository(session)
        existing = tenants.get_by_code(DEMO_TENANT_CODE)
        if existing is not None:
            print(f"demo tenant already exists id={existing.id}, skip business seed")
            return

        tenant = TenantService(session).create_tenant(
            user=user, name=DEMO_TENANT_NAME, code=DEMO_TENANT_CODE
        )
        member = TenantMemberRepository(session).get_by_tenant_user(tenant.id, user.id)
        if member is None:
            raise RuntimeError("demo tenant owner membership missing")
        ctx = _context(user.id, tenant.id, member.id)

        warehouses = [
            WarehouseService(session, ctx).create_warehouse(
                WarehouseCreate(name=name, type="DOMESTIC", city="深圳")
            )
            for name in ("深圳一号仓", "广州仓", "美西海外仓")
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
        print(f"demo tenant ready id={tenant.id} code={DEMO_TENANT_CODE}")
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()

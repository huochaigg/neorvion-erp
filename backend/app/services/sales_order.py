"""销售订单。确认预占和取消释放必须与订单状态放在同一个事务里。"""

from __future__ import annotations

import re
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.core.permissions import PermissionCode
from app.core.tenant import TenantContext
from app.models.customer import Customer, CustomerStatus
from app.models.inventory import Inventory
from app.models.product import ProductSku, SkuStatus
from app.models.sales_order import (
    SALES_ORDER_REFERENCE,
    SalesOrder,
    SalesOrderItem,
    SalesOrderSource,
    SalesOrderStatus,
)
from app.models.user import User
from app.models.warehouse import WarehouseStatus
from app.repositories.customer import CustomerRepository
from app.repositories.inventory import InventoryRepository
from app.repositories.product import ProductSkuRepository
from app.repositories.sales_order import SalesOrderRepository
from app.repositories.warehouse import WarehouseRepository
from app.schemas.sales_order import (
    SalesOrderCancel,
    SalesOrderCreate,
    SalesOrderDetailOut,
    SalesOrderItemIn,
    SalesOrderItemOut,
    SalesOrderListItemOut,
    SalesOrderListOut,
    SalesOrderUpdate,
)
from app.services.authorization import AuthorizationService
from app.services.inventory import InventoryService
from app.services.sales_order_state import (
    CANCELLABLE_STATUSES,
    CANCELLED,
    PENDING_CONFIRMATION,
    WAITING_OUTBOUND,
    require_editable,
    require_transition,
)

_UNAVAILABLE = "销售订单不存在或不可访问"
_CURRENCY = re.compile(r"^[A-Z]{3}$")
_COUNTRY = re.compile(r"^[A-Z]{2}$")
_SNAPSHOT_FIELDS = (
    "recipient_name",
    "recipient_phone",
    "country_code",
    "province",
    "city",
    "address",
)


class SalesOrderService:
    def __init__(self, session: Session, context: TenantContext) -> None:
        self.session = session
        self.context = context
        self.auth = AuthorizationService(session)
        self.orders = SalesOrderRepository(session, context.tenant_id)
        self.customers = CustomerRepository(session, context.tenant_id)
        self.warehouses = WarehouseRepository(session, context.tenant_id)
        self.skus = ProductSkuRepository(session, context.tenant_id)
        self.inventories = InventoryRepository(session, context.tenant_id)
        # 与订单共用同一个 Session。预占方法自己不 commit，才能和订单一起提交或一起回滚。
        self.inventory = InventoryService(session, context)

    def list_orders(
        self,
        *,
        q: str | None,
        order_no: str | None,
        external_order_no: str | None,
        customer_id: int | None,
        warehouse_id: int | None,
        sku_code: str | None,
        product_name: str | None,
        status: str | None,
        source: str | None,
        created_from: datetime | None,
        created_to: datetime | None,
        page: int,
        page_size: int,
    ) -> SalesOrderListOut:
        self.auth.require_all(self.context, (PermissionCode.ORDER_READ,))
        if status and status not in {item.value for item in SalesOrderStatus}:
            raise AppError("销售订单状态不合法", code=40110, status_code=400)
        if source and source not in {item.value for item in SalesOrderSource}:
            raise AppError("订单来源不合法", code=40118, status_code=400)
        rows, total = self.orders.list_page(
            q=(q or "").strip() or None,
            order_no=(order_no or "").strip() or None,
            external_order_no=(external_order_no or "").strip() or None,
            customer_id=customer_id,
            warehouse_id=warehouse_id,
            sku_code=(sku_code or "").strip() or None,
            product_name=(product_name or "").strip() or None,
            status=status,
            source=source,
            created_from=created_from,
            created_to=created_to,
            page=page,
            page_size=page_size,
        )
        items = [
            self._list_item(
                order,
                customer_name=customer_name,
                warehouse_name=warehouse_name,
                creator_name=creator_name,
                sku_count=int(sku_count or 0),
                total_quantity=int(total_quantity or 0),
                total_amount=self._money(total_amount),
            )
            for (
                order,
                customer_name,
                warehouse_name,
                creator_name,
                sku_count,
                total_quantity,
                total_amount,
            ) in rows
        ]
        return SalesOrderListOut(items=items, total=total, page=page, page_size=page_size)

    def get_order(self, order_id: int) -> SalesOrderDetailOut:
        self.auth.require_all(self.context, (PermissionCode.ORDER_READ,))
        order = self.orders.get_in_tenant(order_id)
        if order is None:
            raise AppError(_UNAVAILABLE, code=40471, status_code=404)
        return self._detail_out(order)

    def create_order(self, payload: SalesOrderCreate) -> SalesOrderDetailOut:
        """创建草稿。主表和明细同一事务；任一行失败整单 rollback。

        功能：保存销售计划和收货快照，此时不检查、不预占库存。
        参数：客户、仓库、明细；收货字段可空，空则抄客户当前档案作为快照初值。
        返回：草稿详情。
        异常：客户/仓库/SKU 不属于本租户；客户已禁用；SKU 重复；平台单号冲突。
        为什么草稿不看库存：用户可能先下单再补货。真正的可用量校验发生在确认。
        """
        self.auth.require_all(self.context, (PermissionCode.ORDER_CREATE,))
        customer = self._require_active_customer(payload.customer_id)
        warehouse = self._require_active_warehouse(payload.warehouse_id)
        sku_map = self._require_active_skus([item.sku_id for item in payload.items])
        source = self._normalize_source(payload.source or SalesOrderSource.MANUAL.value)
        currency = self._normalize_currency(payload.currency_code or "CNY") # TODO 后期支持多币种
        snapshot = self._initial_snapshot(payload, customer)
        order = SalesOrder(
            tenant_id=self.context.tenant_id,
            customer_id=customer.id,
            warehouse_id=warehouse.id,
            status=SalesOrderStatus.DRAFT.value,
            source=source,
            external_order_no=payload.external_order_no,
            currency_code=currency,
            remark=payload.remark,
            created_by=self.context.user_id,
            **snapshot,
        )
        try:
            self.orders.add(order)
            # flush 拿到自增 id。单号用年 + id，不靠 MAX(order_no)+1。
            self.session.flush()
            order.order_no = self._auto_order_no(order.id)
            self._insert_items(order.id, payload.items, sku_map)
            self.session.commit()
        except AppError:
            self.session.rollback()
            raise
        except IntegrityError as exc:
            self.session.rollback()
            raise self._integrity_to_error(exc) from None
        except Exception:
            self.session.rollback()
            raise
        created = self.orders.get_in_tenant(order.id)
        if created is None:
            raise AppError(_UNAVAILABLE, code=40471, status_code=404)
        return self._detail_out(created)

    def update_order(self, order_id: int, payload: SalesOrderUpdate) -> SalesOrderDetailOut:
        """仅草稿可改核心内容。明细整体替换：先删旧行再插新行。

        草稿还没预占库存，所以替换明细不用动 Inventory。
        提交之后禁止修改，避免确认时预占的数量和页面上看到的不一致。
        """
        self.auth.require_all(self.context, (PermissionCode.ORDER_UPDATE,))
        try:
            order = self._lock(order_id)
            require_editable(order.status)
            if payload.customer_id is not None:
                customer = self._require_active_customer(payload.customer_id)
                order.customer_id = customer.id
            if payload.warehouse_id is not None:
                warehouse = self._require_active_warehouse(payload.warehouse_id)
                order.warehouse_id = warehouse.id
            if "source" in payload.model_fields_set and payload.source is not None:
                order.source = self._normalize_source(payload.source)
            if "external_order_no" in payload.model_fields_set:
                order.external_order_no = payload.external_order_no
            if "currency_code" in payload.model_fields_set and payload.currency_code is not None:
                order.currency_code = self._normalize_currency(payload.currency_code)
            if "remark" in payload.model_fields_set:
                order.remark = payload.remark
            for field in _SNAPSHOT_FIELDS:
                if field in payload.model_fields_set:
                    value = getattr(payload, field)
                    if field == "country_code":
                        value = self._normalize_country(value)
                    setattr(order, field, value)
            if payload.items is not None:
                sku_map = self._require_active_skus([item.sku_id for item in payload.items])
                self.orders.delete_items(order.id)
                self.session.expire(order, ["items"])
                self._insert_items(order.id, payload.items, sku_map)
            self.session.commit()
        except AppError:
            self.session.rollback()
            raise
        except IntegrityError as exc:
            self.session.rollback()
            raise self._integrity_to_error(exc) from None
        except Exception:
            self.session.rollback()
            raise
        updated = self.orders.get_in_tenant(order_id)
        if updated is None:
            raise AppError(_UNAVAILABLE, code=40471, status_code=404)
        return self._detail_out(updated)

    def submit_order(self, order_id: int) -> SalesOrderDetailOut:
        """草稿提交为待确认。这里仍不预占库存。

        提交只表示业务资料齐了，等有 order:audit 的人确认。
        确认时库存可能已经变了，所以提交通过不代表确认一定成功。
        """
        self.auth.require_all(self.context, (PermissionCode.ORDER_SUBMIT,))
        try:
            order = self._lock(order_id)
            if order.status not in {SalesOrderStatus.DRAFT.value}:
                require_transition(order.status, PENDING_CONFIRMATION)
            items = self.orders.list_items(order.id)
            if not items:
                raise AppError(
                    "提交前至少需要一条订单明细",
                    code=40113,
                    status_code=400,
                    data={"error": "SALES_ORDER_ITEMS_REQUIRED"},
                )
            self._require_active_customer(order.customer_id)
            self._require_active_warehouse(order.warehouse_id)
            self._require_active_skus([item.sku_id for item in items])
            self._require_address(order)
            order.status = PENDING_CONFIRMATION
            order.submitted_at = datetime.now()
            self.session.commit()
        except AppError:
            self.session.rollback()
            raise
        except Exception:
            self.session.rollback()
            raise
        updated = self.orders.get_in_tenant(order_id)
        if updated is None:
            raise AppError(_UNAVAILABLE, code=40471, status_code=404)
        return self._detail_out(updated)

    def confirm_order(self, order_id: int) -> SalesOrderDetailOut:
        """将待确认订单确认，并原子预占全部 SKU 库存。

        功能：订单进入待出库，同时把每个明细的购买数量预占到履约仓库。
        参数：订单 id。调用方需要 order:audit。
        返回：待出库详情，明细 reserved_quantity 等于购买数量。
        异常：
        - 订单不属于当前租户
        - 状态不是待确认（含已取消不能再确认）
        - 客户 / 仓库 / SKU 无效
        - 任一 SKU 库存不存在或可用量不足
        - 并发下第二个确认请求看到状态已变
        核心流程：
        1. SELECT FOR UPDATE 锁订单主行，让同一订单的确认和取消排队。
        2. 校验状态仍是待确认。
        3. 读取明细，按 sku_id 升序排列。
        4. 先收集全部库存不足的 SKU，避免只报第一个。
        5. 逐个调用 InventoryService.reserve_within_transaction。它复用 V5 条件 UPDATE，
           并且不自己 commit。
        6. 全部成功后把明细 reserved_quantity 写成购买数量，订单改为待出库。
        7. 一次 commit。任意失败 rollback，已经执行的预占和流水一起撤销。

        为什么按 sku_id 排序：订单 1 锁 A 再锁 B，订单 2 锁 B 再锁 A，两个事务会互相等待形成死锁。
        所有确认都按 sku_id 从小到大更新库存行，锁顺序一致，就不会环路等待。
        这里不引入分布式锁，数据库行锁足够。

        为什么预占不减少 quantity：货还在仓库里，只是被这张订单占住。
        实际出库留给后续版本，那时才同时减少 quantity 和 reserved。
        """
        self.auth.require_all(self.context, (PermissionCode.ORDER_AUDIT,))
        try:
            order = self._lock(order_id)
            if order.status == CANCELLED:
                require_transition(order.status, WAITING_OUTBOUND)
            if order.status != PENDING_CONFIRMATION:
                require_transition(order.status, WAITING_OUTBOUND)
            self._require_active_customer(order.customer_id)
            self._require_active_warehouse(order.warehouse_id)
            items = self.orders.list_items(order.id)
            if not items:
                raise AppError(
                    "确认前至少需要一条订单明细",
                    code=40113,
                    status_code=400,
                    data={"error": "SALES_ORDER_ITEMS_REQUIRED"},
                )
            sku_map = self._require_active_skus([item.sku_id for item in items])
            # 复制成普通数据。后面的条件 UPDATE 会 expire_all，不能依赖还没写盘的 ORM 改动。
            warehouse_id = order.warehouse_id
            order_no = order.order_no or str(order.id)
            plan = sorted(items, key=lambda row: (row.sku_id, row.id))
            shortages = self._collect_shortages(warehouse_id, plan, sku_map)
            if shortages:
                raise self._shortage_error(shortages)
            for item in plan:
                sku = sku_map[item.sku_id]
                self.inventory.reserve_within_transaction(
                    warehouse_id=warehouse_id,
                    sku_id=item.sku_id,
                    quantity=item.quantity,
                    sku_code=sku.sku_code or "",
                    reference_type=SALES_ORDER_REFERENCE,
                    reference_id=order.id,
                    remark=f"销售订单 {order_no} 预占",
                )
            # 预占内部的 expire_all 会清掉内存里的订单对象。重新锁一次，锁仍由本事务持有。
            locked = self._lock(order_id)
            if locked.status != PENDING_CONFIRMATION:
                raise AppError(
                    "销售订单状态已被其他人修改，请刷新后重试",
                    code=40115,
                    status_code=400,
                    data={"error": "SALES_ORDER_STATE_CONFLICT"},
                )
            for item in self.orders.list_items(order_id):
                item.reserved_quantity = item.quantity
            locked.status = WAITING_OUTBOUND
            locked.confirmed_at = datetime.now()
            locked.confirmed_by = self.context.user_id
            # 确认已经预占成功。同一事务生成第一张出库单，失败则预占一并撤销。
            from app.services.outbound import OutboundOrderService

            OutboundOrderService(self.session, self.context).attach_initial(order_id)
            self.session.commit()
        except AppError:
            self.session.rollback()
            raise
        except Exception:
            self.session.rollback()
            raise
        updated = self.orders.get_in_tenant(order_id)
        if updated is None:
            raise AppError(_UNAVAILABLE, code=40471, status_code=404)
        return self._detail_out(updated)

    def cancel_order(self, order_id: int, payload: SalesOrderCancel) -> SalesOrderDetailOut:
        """取消订单。待出库必须在同一事务里释放全部预占。

        功能：把订单改为已取消。草稿和待确认没有库存动作；待出库要释放 reserved。
        参数：订单 id、可选原因。
        返回：已取消的订单，明细 reserved_quantity 为 0。
        异常：已经取消返回 ORDER_ALREADY_CANCELLED，不再释放；释放失败则整单回滚。
        核心流程：
        1. SELECT FOR UPDATE 锁订单，和确认排队。
        2. 已取消直接拒绝，避免把 reserved 减成负数。
        3. 待出库时按 sku_id 升序调用 release_within_transaction。
        4. 明细 reserved 归零，写入取消人和原因。
        5. 一次 commit。不能先提交释放再单独改订单，否则中途失败会库存已放、订单仍待出库。
        """
        self.auth.require_all(self.context, (PermissionCode.ORDER_CANCEL,))
        try:
            order = self._lock(order_id)
            if order.status == CANCELLED:
                raise AppError(
                    "订单已经取消",
                    code=40117,
                    status_code=400,
                    data={"error": "ORDER_ALREADY_CANCELLED"},
                )
            if order.status not in CANCELLABLE_STATUSES:
                require_transition(order.status, CANCELLED)
            release_stock = order.status == WAITING_OUTBOUND
            order_no = order.order_no or str(order.id)
            warehouse_id = order.warehouse_id
            if release_stock:
                shipped = [
                    item
                    for item in self.orders.list_items(order.id)
                    if item.shipped_quantity > 0
                ]
                if shipped:
                    raise AppError(
                        "订单已经出库，不能整单取消",
                        code=40120,
                        status_code=400,
                        data={"error": "SALES_ORDER_HAS_SHIPMENTS"},
                    )
                from app.repositories.outbound import OutboundOrderRepository

                OutboundOrderRepository(
                    self.session,
                    self.context.tenant_id,
                ).cancel_open_for_sales_order(order.id)
                items = [
                    item
                    for item in self.orders.list_items(order.id)
                    if item.reserved_quantity > 0
                ]
                # 和确认使用同一把 sku_id 顺序，避免确认、取消交叉加锁。
                items.sort(key=lambda row: (row.sku_id, row.id))
                for item in items:
                    sku_code = item.sku.sku_code if item.sku is not None else ""
                    self.inventory.release_within_transaction(
                        warehouse_id=warehouse_id,
                        sku_id=item.sku_id,
                        quantity=item.reserved_quantity,
                        sku_code=sku_code or "",
                        reference_type=SALES_ORDER_REFERENCE,
                        reference_id=order.id,
                        remark=f"销售订单 {order_no} 取消释放",
                    )
                locked = self._lock(order_id)
            else:
                locked = order
            if locked.status == CANCELLED:
                raise AppError(
                    "订单已经取消",
                    code=40117,
                    status_code=400,
                    data={"error": "ORDER_ALREADY_CANCELLED"},
                )
            if release_stock:
                for item in self.orders.list_items(order_id):
                    item.reserved_quantity = 0
            locked.status = CANCELLED
            locked.cancelled_at = datetime.now()
            locked.cancelled_by = self.context.user_id
            locked.cancel_reason = payload.reason
            self.session.commit()
        except AppError:
            self.session.rollback()
            raise
        except Exception:
            self.session.rollback()
            raise
        updated = self.orders.get_in_tenant(order_id)
        if updated is None:
            raise AppError(_UNAVAILABLE, code=40471, status_code=404)
        return self._detail_out(updated)

    def _lock(self, order_id: int) -> SalesOrder:
        order = self.orders.get_for_update(order_id)
        if order is None:
            raise AppError(_UNAVAILABLE, code=40471, status_code=404)
        return order

    def _collect_shortages(
        self,
        warehouse_id: int,
        items: list[SalesOrderItem],
        sku_map: dict[int, ProductSku],
    ) -> list[dict[str, object]]:
        """确认前看一遍可用量，把不够的 SKU 一次返回。真正扣预占仍以条件 UPDATE 为准。"""
        sku_ids = [item.sku_id for item in items]
        stock = {
            row.sku_id: row
            for row in self.inventories.list_by_warehouse_skus(warehouse_id, sku_ids)
        }
        shortages: list[dict[str, object]] = []
        for item in items:
            inventory = stock.get(item.sku_id)
            available = 0 if inventory is None else inventory.quantity - inventory.reserved_quantity
            if inventory is None or available < item.quantity:
                sku = sku_map[item.sku_id]
                shortages.append(
                    {
                        "sku_id": item.sku_id,
                        "sku_code": sku.sku_code or "",
                        "requested_quantity": item.quantity,
                        "available_quantity": available,
                    }
                )
        return shortages

    @staticmethod
    def _shortage_error(items: list[dict[str, object]]) -> AppError:
        parts = []
        for item in items:
            code = item["sku_code"]
            available = item["available_quantity"]
            requested = item["requested_quantity"]
            parts.append(f"{code} 可用库存 {available}，订单需要 {requested}。")
        message = "".join(parts)
        return AppError(
            message or "可用库存不足",
            code=40070,
            status_code=400,
            data={"error": "INSUFFICIENT_AVAILABLE_INVENTORY", "items": items},
        )

    def _insert_items(
        self,
        order_id: int,
        items: list[SalesOrderItemIn],
        sku_map: dict[int, ProductSku],
    ) -> None:
        for item in items:
            sku_map[item.sku_id]
            self.orders.add_item(
                SalesOrderItem(
                    tenant_id=self.context.tenant_id,
                    sales_order_id=order_id,
                    sku_id=item.sku_id,
                    quantity=item.quantity,
                    unit_price=item.unit_price,
                    reserved_quantity=0,
                    shipped_quantity=0,
                    remark=item.remark,
                )
            )

    def _require_active_customer(self, customer_id: int) -> Customer:
        customer = self.customers.get_in_tenant(customer_id)
        if customer is None:
            raise AppError("客户不存在或不可访问", code=40461, status_code=404)
        if customer.status != CustomerStatus.ACTIVE.value:
            raise AppError(
                "禁用的客户不能用于新的销售订单",
                code=40119,
                status_code=400,
                data={"error": "CUSTOMER_DISABLED"},
            )
        return customer

    def _require_active_warehouse(self, warehouse_id: int):
        warehouse = self.warehouses.get_in_tenant(warehouse_id)
        if warehouse is None:
            raise AppError("仓库不存在或不可访问", code=40440, status_code=404)
        if warehouse.status != WarehouseStatus.ACTIVE.value:
            raise AppError(
                "只能使用启用中的仓库",
                code=40097,
                status_code=400,
                data={"error": "WAREHOUSE_DISABLED"},
            )
        return warehouse

    def _require_active_skus(self, sku_ids: list[int]) -> dict[int, ProductSku]:
        unique_ids = list(dict.fromkeys(sku_ids))
        if len(unique_ids) != len(sku_ids):
            raise AppError(
                "同一销售订单中同一个 SKU 只能出现一行",
                code=40111,
                status_code=400,
                data={"error": "DUPLICATE_SALES_ORDER_SKU"},
            )
        found: dict[int, ProductSku] = {}
        for sku_id in unique_ids:
            sku = self.skus.get_by_id_in_tenant(sku_id)
            if sku is None:
                raise AppError("SKU 不存在或不可访问", code=40433, status_code=404)
            if sku.status != SkuStatus.ACTIVE.value:
                raise AppError("只能销售启用中的 SKU", code=40121, status_code=400)
            found[sku_id] = sku
        return found

    def _require_address(self, order: SalesOrder) -> None:
        if not (order.recipient_name and order.recipient_name.strip()):
            raise AppError(
                "提交前请填写收件人",
                code=40116,
                status_code=400,
                data={"error": "SALES_ORDER_ADDRESS_INCOMPLETE"},
            )
        if not (order.address and order.address.strip()):
            raise AppError(
                "提交前请填写详细地址",
                code=40116,
                status_code=400,
                data={"error": "SALES_ORDER_ADDRESS_INCOMPLETE"},
            )

    def _initial_snapshot(
        self,
        payload: SalesOrderCreate,
        customer: Customer,
    ) -> dict[str, str | None]:
        """未传的收货字段用客户档案填一次，然后写在订单自己的列上。

        之后客户改地址不会回写这张订单。传了空字符串则保留空，不强制覆盖。
        """
        defaults = {
            "recipient_name": customer.name,
            "recipient_phone": customer.phone,
            "country_code": customer.country_code,
            "province": customer.province,
            "city": customer.city,
            "address": customer.address,
        }
        snapshot: dict[str, str | None] = {}
        for field, fallback in defaults.items():
            if field in payload.model_fields_set:
                value = getattr(payload, field)
                if field == "country_code":
                    value = self._normalize_country(value)
                snapshot[field] = value
            else:
                snapshot[field] = fallback
        return snapshot

    def _detail_out(self, order: SalesOrder) -> SalesOrderDetailOut:
        stock = self._stock_map(order.warehouse_id, [item.sku_id for item in order.items])
        item_outs = [self._item_out(row, stock.get(row.sku_id)) for row in order.items]
        total_qty = sum(row.quantity for row in order.items)
        amounts = [row.line_amount for row in item_outs if row.line_amount is not None]
        total_amount = round(sum(amounts), 2) if amounts else None
        list_item = self._list_item(
            order,
            customer_name=order.customer.name if order.customer else "",
            warehouse_name=order.warehouse.name if order.warehouse else "",
            creator_name=self._user_name(order.created_by),
            sku_count=len({row.sku_id for row in order.items}),
            total_quantity=total_qty,
            total_amount=total_amount,
        )
        return SalesOrderDetailOut(
            **list_item.model_dump(),
            recipient_name=order.recipient_name,
            recipient_phone=order.recipient_phone,
            country_code=order.country_code,
            province=order.province,
            city=order.city,
            address=order.address,
            remark=order.remark,
            submitted_at=order.submitted_at,
            confirmed_at=order.confirmed_at,
            confirmed_by=order.confirmed_by,
            confirmed_by_name=self._user_name(order.confirmed_by),
            cancelled_at=order.cancelled_at,
            cancelled_by=order.cancelled_by,
            cancelled_by_name=self._user_name(order.cancelled_by),
            cancel_reason=order.cancel_reason,
            items=item_outs,
            picks=self._order_picks(order.id),
        )

    def _order_picks(self, order_id: int):
        from app.services.outbound import OutboundOrderService

        return OutboundOrderService(self.session, self.context).list_order_picks(order_id)

    def _stock_map(self, warehouse_id: int, sku_ids: list[int]) -> dict[int, Inventory]:
        if not sku_ids:
            return {}
        rows = self.inventories.list_by_warehouse_skus(warehouse_id, sku_ids)
        return {row.sku_id: row for row in rows}

    def _user_name(self, user_id: int | None) -> str | None:
        if user_id is None:
            return None
        return self.session.scalar(select(User.display_name).where(User.id == user_id))

    @staticmethod
    def _list_item(
        order: SalesOrder,
        *,
        customer_name: str,
        warehouse_name: str,
        creator_name: str | None,
        sku_count: int,
        total_quantity: int,
        total_amount: float | None,
    ) -> SalesOrderListItemOut:
        return SalesOrderListItemOut(
            id=order.id,
            tenant_id=order.tenant_id,
            order_no=order.order_no or "",
            customer_id=order.customer_id,
            customer_name=customer_name,
            warehouse_id=order.warehouse_id,
            warehouse_name=warehouse_name,
            status=order.status,
            source=order.source,
            external_order_no=order.external_order_no,
            currency_code=order.currency_code,
            sku_count=sku_count,
            total_quantity=total_quantity,
            total_amount=total_amount,
            created_by=order.created_by,
            created_by_name=creator_name,
            created_at=order.created_at,
            updated_at=order.updated_at,
        )

    @staticmethod
    def _item_out(item: SalesOrderItem, inventory: Inventory | None) -> SalesOrderItemOut:
        sku = item.sku
        product = sku.product if sku is not None else None
        price = SalesOrderService._money(item.unit_price)
        line = None if price is None else round(price * item.quantity, 2)
        current_qty = None if inventory is None else inventory.quantity
        current_reserved = None if inventory is None else inventory.reserved_quantity
        current_available = (
            None if inventory is None else inventory.quantity - inventory.reserved_quantity
        )
        return SalesOrderItemOut(
            id=item.id,
            sku_id=item.sku_id,
            sku_code=(sku.sku_code or "") if sku is not None else "",
            sku_name=sku.name if sku is not None else "",
            product_id=sku.product_id if sku is not None else 0,
            product_name=product.name if product is not None else "",
            spec_values=sku.spec_values if sku is not None and sku.spec_values else {},
            quantity=item.quantity,
            unit_price=price,
            line_amount=line,
            reserved_quantity=item.reserved_quantity,
            shipped_quantity=item.shipped_quantity,
            remark=item.remark,
            current_quantity=current_qty,
            current_reserved_quantity=current_reserved,
            current_available_quantity=current_available,
        )

    @staticmethod
    def _money(value: object) -> float | None:
        if value is None:
            return None
        return round(float(str(value)), 2)

    @staticmethod
    def _auto_order_no(order_id: int) -> str:
        year = datetime.now().year
        return f"SO{year}{order_id:06d}"

    @staticmethod
    def _normalize_source(value: str) -> str:
        if value not in {item.value for item in SalesOrderSource}:
            raise AppError("订单来源不合法", code=40118, status_code=400)
        return value

    @staticmethod
    def _normalize_currency(value: str) -> str:
        if not _CURRENCY.fullmatch(value):
            raise AppError("币种必须是 3 位字母，例如 CNY", code=40122, status_code=400)
        return value

    @staticmethod
    def _normalize_country(value: str | None) -> str | None:
        if value is None:
            return None
        if not _COUNTRY.fullmatch(value):
            raise AppError("国家代码必须是 ISO 两位字母，例如 CN", code=40087, status_code=400)
        return value

    @staticmethod
    def _integrity_to_error(exc: IntegrityError) -> AppError:
        text = str(exc.orig).lower()
        if "uq_so_items_order_sku" in text:
            return AppError(
                "同一销售订单中同一个 SKU 只能出现一行",
                code=40111,
                status_code=400,
                data={"error": "DUPLICATE_SALES_ORDER_SKU"},
            )
        if "uq_sales_orders_tenant_source_external" in text:
            return AppError(
                "同一来源下平台订单号已存在",
                code=40962,
                status_code=409,
                data={"error": "DUPLICATE_EXTERNAL_ORDER_NO"},
            )
        return AppError(
            "销售订单保存失败",
            code=40962,
            status_code=409,
            data={"error": "SALES_ORDER_CONFLICT"},
        )

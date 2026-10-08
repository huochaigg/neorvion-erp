"""库存台账。Repository 不 commit；库存数字与流水必须由本层同一事务提交。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.core.permissions import PermissionCode
from app.core.tenant import TenantContext
from app.models.inventory import Inventory, InventoryTransaction, InventoryTransactionType
from app.models.product import Product, ProductSku
from app.models.warehouse import Warehouse, WarehouseStatus
from app.repositories.inventory import (
    InventoryRepository,
    InventoryTransactionRepository,
    search_skus,
)
from app.repositories.product import ProductSkuRepository
from app.repositories.warehouse import WarehouseRepository
from app.schemas.inventory import (
    InventoryAdjust,
    InventoryDetailOut,
    InventoryInitialize,
    InventoryItemOut,
    InventoryListOut,
    InventoryOptimisticAdjust,
    InventoryQtyChange,
    InventoryTransactionListOut,
    InventoryTransactionOut,
    SkuOptionListOut,
    SkuOptionOut,
)
from app.services.authorization import AuthorizationService

_UNAVAILABLE = "库存不存在或不可访问"
_SKU_UNAVAILABLE = "SKU 不存在或不可访问"
_WAREHOUSE_UNAVAILABLE = "仓库不存在或不可访问"
_ADJUST_TYPES = {
    InventoryTransactionType.ADJUST_IN.value,
    InventoryTransactionType.ADJUST_OUT.value,
}


class InventoryService:
    def __init__(self, session: Session, context: TenantContext) -> None:
        self.session = session
        self.context = context
        self.auth = AuthorizationService(session)
        self.inventories = InventoryRepository(session, context.tenant_id)
        self.transactions = InventoryTransactionRepository(session, context.tenant_id)
        self.warehouses = WarehouseRepository(session, context.tenant_id)
        self.skus = ProductSkuRepository(session, context.tenant_id)

    def list_inventory(
        self,
        *,
        q: str | None,
        sku_code: str | None,
        warehouse_id: int | None,
        category_id: int | None,
        brand_id: int | None,
        stock_status: str | None,
        threshold: int,
        page: int,
        page_size: int,
    ) -> InventoryListOut:
        self.auth.require_all(self.context, (PermissionCode.INVENTORY_READ,))
        if stock_status and stock_status not in {"IN_STOCK", "ZERO", "LOW"}:
            raise AppError("库存状态筛选不合法", code=40074, status_code=400)
        rows, total = self.inventories.list_page(
            q=(q or "").strip() or None,
            sku_code=(sku_code or "").strip() or None,
            warehouse_id=warehouse_id,
            category_id=category_id,
            brand_id=brand_id,
            stock_status=stock_status,
            threshold=threshold,
            page=page,
            page_size=page_size,
        )
        return InventoryListOut(
            items=[
                self._item_out(inv, sku, product, warehouse)
                for inv, sku, product, warehouse in rows
            ],
            total=total,
            page=page,
            page_size=page_size,
        )

    def get_inventory(self, inventory_id: int) -> InventoryDetailOut:
        self.auth.require_all(self.context, (PermissionCode.INVENTORY_READ,))
        inventory = self.inventories.get_in_tenant(inventory_id)
        if inventory is None or inventory.sku is None or inventory.warehouse is None:
            raise AppError(_UNAVAILABLE, code=40450, status_code=404)
        sku = inventory.sku
        product = sku.product
        if product is None:
            raise AppError(_UNAVAILABLE, code=40450, status_code=404)
        item = self._item_out(inventory, sku, product, inventory.warehouse)
        recent = self.transactions.list_for_inventory(inventory.id, limit=20)
        recent_out = [
            self._tx_out(
                row,
                warehouse_name=inventory.warehouse.name,
                sku_code=sku.sku_code or "",
                sku_name=sku.name,
                product_name=product.name,
                operator_name=operator_name,
            )
            for row, operator_name in recent
        ]
        return InventoryDetailOut(**item.model_dump(), recent_transactions=recent_out)

    def list_transactions(
        self,
        *,
        inventory_id: int | None,
        warehouse_id: int | None,
        sku_id: int | None,
        tx_type: str | None,
        created_from: datetime | None,
        created_to: datetime | None,
        page: int,
        page_size: int,
    ) -> InventoryTransactionListOut:
        self.auth.require_all(self.context, (PermissionCode.INVENTORY_TRANSACTION_READ,))
        if tx_type and tx_type not in {item.value for item in InventoryTransactionType}:
            raise AppError("流水类型不合法", code=40073, status_code=400)
        rows, total = self.transactions.list_page(
            inventory_id=inventory_id,
            warehouse_id=warehouse_id,
            sku_id=sku_id,
            tx_type=tx_type,
            created_from=created_from,
            created_to=created_to,
            page=page,
            page_size=page_size,
        )
        return InventoryTransactionListOut(
            items=[
                self._tx_out(
                    tx,
                    warehouse_name=warehouse.name,
                    sku_code=sku.sku_code or "",
                    sku_name=sku.name,
                    product_name=product.name,
                    operator_name=operator_name,
                )
                for tx, warehouse, sku, product, operator_name in rows
            ],
            total=total,
            page=page,
            page_size=page_size,
        )

    def search_sku_options(self, *, q: str | None, page: int, page_size: int) -> SkuOptionListOut:
        """初始化库存下拉。读商品权限，避免无 product:read 的人扫全量 SKU。"""
        self.auth.require_all(self.context, (PermissionCode.PRODUCT_READ,))
        rows, total = search_skus(
            self.skus,
            q=(q or "").strip() or None,
            page=page,
            page_size=page_size,
        )
        return SkuOptionListOut(
            items=[self._sku_option(row) for row in rows],
            total=total,
            page=page,
            page_size=page_size,
        )

    def initialize_inventory(self, payload: InventoryInitialize) -> InventoryItemOut:
        """给某个仓库 + SKU 写入第一条库存。

        参数：warehouse_id、sku_id、quantity（允许 0）、可选备注。
        返回：含 available_quantity 的库存行。
        异常：仓库/SKU 不属于本租户 404；已存在 INVENTORY_ALREADY_EXISTS；数量为负 400。
        事务：INSERT Inventory 与 INSERT INITIALIZE 流水同一事务。任一步失败 rollback，
        不能出现「库存有了但没有历史」或「流水有了库存没有」。
        并发：两个初始化撞 UNIQUE(tenant, warehouse, sku) 时 IntegrityError 转成已存在。
        为什么 available 不存库：它等于 quantity - reserved，存第三份会和前两份打架。
        """
        self.auth.require_all(self.context, (PermissionCode.INVENTORY_INITIALIZE,))
        warehouse = self._require_active_warehouse(payload.warehouse_id)
        sku = self._require_sku(payload.sku_id)
        if self.inventories.get_by_warehouse_and_sku(warehouse.id, sku.id) is not None:
            raise AppError(
                "该仓库下此 SKU 已有库存，请使用库存调整",
                code=40950,
                status_code=409,
                data={"error": "INVENTORY_ALREADY_EXISTS"},
            )
        inventory = Inventory(
            tenant_id=self.context.tenant_id,
            warehouse_id=warehouse.id,
            sku_id=sku.id,
            quantity=payload.quantity,
            reserved_quantity=0,
            version=0,
        )
        try:
            self.inventories.add(inventory)
            self.session.flush()
            self._add_tx(
                inventory,
                tx_type=InventoryTransactionType.INITIALIZE.value,
                change_quantity=payload.quantity,
                before_qty=0,
                after_qty=payload.quantity,
                before_reserved=0,
                after_reserved=0,
                remark=payload.remark,
            )
            self.session.commit()
            created = self.inventories.get_in_tenant(inventory.id)
        except IntegrityError:
            self.session.rollback()
            raise AppError(
                "该仓库下此 SKU 已有库存，请使用库存调整",
                code=40950,
                status_code=409,
                data={"error": "INVENTORY_ALREADY_EXISTS"},
            ) from None
        except Exception:
            self.session.rollback()
            raise
        if created is None or created.sku is None or created.warehouse is None:
            raise AppError(_UNAVAILABLE, code=40450, status_code=404)
        return self._item_out(created, created.sku, created.sku.product, created.warehouse)

    def adjust_inventory(self, inventory_id: int, payload: InventoryAdjust) -> InventoryItemOut:
        """手工盘点调整。走 SELECT FOR UPDATE，不和乐观锁混用。

        ADJUST_IN：quantity += n。
        ADJUST_OUT：必须 quantity - n >= reserved，否则可用不够，预占会比实际还多。
        锁：FOR UPDATE 锁本行。两个调整并发时串行，后到的请求看到前一次已经改过的数字。
        事务：改 Inventory 与写流水必须一起 commit。
        """
        self.auth.require_all(self.context, (PermissionCode.INVENTORY_ADJUST,))
        if payload.type not in _ADJUST_TYPES:
            raise AppError("调整类型不合法", code=40073, status_code=400)
        try:
            inventory = self.inventories.get_for_update(inventory_id)
            if inventory is None:
                raise AppError(_UNAVAILABLE, code=40450, status_code=404)
            before_qty = inventory.quantity
            before_reserved = inventory.reserved_quantity
            if payload.type == InventoryTransactionType.ADJUST_IN.value:
                inventory.quantity = before_qty + payload.quantity
                change = payload.quantity
            else:
                available = before_qty - before_reserved
                if payload.quantity > available:
                    raise AppError(
                        "可用库存不足，不能把已预占的数量减没",
                        code=40070,
                        status_code=400,
                        data={"error": "INSUFFICIENT_AVAILABLE_INVENTORY"},
                    )
                inventory.quantity = before_qty - payload.quantity
                change = -payload.quantity
            inventory.version = inventory.version + 1
            self._add_tx(
                inventory,
                tx_type=payload.type,
                change_quantity=change,
                before_qty=before_qty,
                after_qty=inventory.quantity,
                before_reserved=before_reserved,
                after_reserved=inventory.reserved_quantity,
                remark=payload.remark,
            )
            self.session.commit()
            updated = self.inventories.get_in_tenant(inventory.id)
        except AppError:
            self.session.rollback()
            raise
        except Exception:
            self.session.rollback()
            raise
        if updated is None or updated.sku is None or updated.warehouse is None:
            raise AppError(_UNAVAILABLE, code=40450, status_code=404)
        return self._item_out(updated, updated.sku, updated.sku.product, updated.warehouse)

    def lookup_availability(
        self,
        *,
        warehouse_id: int,
        sku_ids: list[int],
    ) -> list[dict[str, int | bool]]:
        """按仓库 + SKU 返回当前可用量，给订单页面提示。确认时仍以后端实时校验为准。"""
        self.auth.require_all(self.context, (PermissionCode.INVENTORY_READ,))
        unique_ids = list(dict.fromkeys(sku_ids))
        found = {
            row.sku_id: row
            for row in self.inventories.list_by_warehouse_skus(warehouse_id, unique_ids)
        }
        items: list[dict[str, int | bool]] = []
        for sku_id in unique_ids:
            row = found.get(sku_id)
            if row is None:
                items.append(
                    {
                        "warehouse_id": warehouse_id,
                        "sku_id": sku_id,
                        "quantity": 0,
                        "reserved_quantity": 0,
                        "available_quantity": 0,
                        "initialized": False,
                    }
                )
                continue
            items.append(
                {
                    "warehouse_id": warehouse_id,
                    "sku_id": sku_id,
                    "quantity": row.quantity,
                    "reserved_quantity": row.reserved_quantity,
                    "available_quantity": row.quantity - row.reserved_quantity,
                    "initialized": True,
                }
            )
        return items

    def reserve_within_transaction(
        self,
        *,
        warehouse_id: int,
        sku_id: int,
        quantity: int,
        sku_code: str | None = None,
        reference_type: str | None = None,
        reference_id: int | None = None,
        remark: str | None = None,
    ) -> Inventory:
        """在当前 Session 里预占，不 commit、不检查 inventory:adjust。

        功能：复用 V5 条件 UPDATE，只增加 reserved，不减少 quantity，并写 RESERVE 流水。
        参数：仓库、SKU、数量；销售订单可传入 reference_type=SALES_ORDER 和订单 id。
        返回：预占之后的库存行。
        异常：没有库存行，或可用量不够。本方法不 rollback，调用方要回滚整个事务。
        为什么不在这里 commit：一张订单有多个 SKU。如果每个 SKU 自己提交，
        后面的 SKU 失败时，前面的预占已经落库，无法撤销。
        """
        current = self.inventories.get_by_warehouse_and_sku(warehouse_id, sku_id)
        if current is None:
            raise AppError(
                f"{sku_code or sku_id} 可用库存 0，订单需要 {quantity}。",
                code=40070,
                status_code=400,
                data={
                    "error": "INSUFFICIENT_AVAILABLE_INVENTORY",
                    "items": [
                        {
                            "sku_id": sku_id,
                            "sku_code": sku_code or "",
                            "requested_quantity": quantity,
                            "available_quantity": 0,
                        }
                    ],
                },
            )
        affected = self.inventories.reserve_if_available(
            warehouse_id=warehouse_id,
            sku_id=sku_id,
            quantity=quantity,
        )
        if affected != 1:
            again = self.inventories.get_by_warehouse_and_sku(warehouse_id, sku_id)
            available = 0 if again is None else again.quantity - again.reserved_quantity
            raise AppError(
                f"{sku_code or sku_id} 可用库存 {available}，订单需要 {quantity}。",
                code=40070,
                status_code=400,
                data={
                    "error": "INSUFFICIENT_AVAILABLE_INVENTORY",
                    "items": [
                        {
                            "sku_id": sku_id,
                            "sku_code": sku_code or "",
                            "requested_quantity": quantity,
                            "available_quantity": available,
                        }
                    ],
                },
            )
        updated = self.inventories.get_by_warehouse_and_sku(warehouse_id, sku_id)
        if updated is None:
            raise AppError(_UNAVAILABLE, code=40450, status_code=404)
        self._add_tx(
            updated,
            tx_type=InventoryTransactionType.RESERVE.value,
            change_quantity=0,
            before_qty=updated.quantity,
            after_qty=updated.quantity,
            before_reserved=updated.reserved_quantity - quantity,
            after_reserved=updated.reserved_quantity,
            remark=remark,
            reference_type=reference_type,
            reference_id=reference_id,
        )
        return updated

    def release_within_transaction(
        self,
        *,
        warehouse_id: int,
        sku_id: int,
        quantity: int,
        sku_code: str | None = None,
        reference_type: str | None = None,
        reference_id: int | None = None,
        remark: str | None = None,
    ) -> Inventory:
        """在当前 Session 里释放预占，不 commit。

        功能：条件 UPDATE 减少 reserved，并写 RELEASE 流水。quantity 不变。
        参数：仓库、SKU、要释放的数量。数量必须大于 0，且不能超过当前预占。
        返回：释放之后的库存行。
        异常：库存不存在，或预占不够。不 rollback，避免拆开外层订单事务。
        为什么和取消放在同一事务：如果先提交释放再改订单，中途失败会出现
        库存已经放开、订单却还是待出库。
        """
        current = self.inventories.get_by_warehouse_and_sku(warehouse_id, sku_id)
        if current is None:
            raise AppError(_UNAVAILABLE, code=40450, status_code=404)
        affected = self.inventories.release_if_reserved(
            warehouse_id=warehouse_id,
            sku_id=sku_id,
            quantity=quantity,
        )
        if affected != 1:
            raise AppError(
                "预占数量不足，不能超额释放",
                code=40071,
                status_code=400,
                data={
                    "error": "INSUFFICIENT_RESERVED_INVENTORY",
                    "sku_id": sku_id,
                    "sku_code": sku_code or "",
                    "quantity": quantity,
                },
            )
        updated = self.inventories.get_by_warehouse_and_sku(warehouse_id, sku_id)
        if updated is None:
            raise AppError(_UNAVAILABLE, code=40450, status_code=404)
        self._add_tx(
            updated,
            tx_type=InventoryTransactionType.RELEASE.value,
            change_quantity=0,
            before_qty=updated.quantity,
            after_qty=updated.quantity,
            before_reserved=updated.reserved_quantity + quantity,
            after_reserved=updated.reserved_quantity,
            remark=remark,
            reference_type=reference_type,
            reference_id=reference_id,
        )
        return updated

    def inbound_within_transaction(
        self,
        *,
        warehouse_id: int,
        sku_id: int,
        quantity: int,
        reference_type: str | None = None,
        reference_id: int | None = None,
        remark: str | None = None,
    ) -> Inventory:
        """在当前事务里增加实际库存，不 commit，不改 reserved。

        功能：采购确认收货时调用。没有库存行就先插入 0，再加数量。
        参数：仓库、SKU、本次入库数量，以及收货单引用。
        返回：入库后的库存行。
        异常：插入后仍找不到行。本方法不 rollback。
        为什么用保存点：两个收货同时给同一仓库+SKU 建第一行时，后一个会撞
        UNIQUE(tenant_id, warehouse_id, sku_id)。如果直接让外层事务失败，
        整张收货单会回滚。保存点只撤销这次插入，然后改去更新已经存在的行。
        """
        current = self.inventories.get_by_warehouse_and_sku(warehouse_id, sku_id)
        if current is None:
            self._insert_inventory_row(warehouse_id, sku_id)
        before = self.inventories.get_by_warehouse_and_sku(warehouse_id, sku_id)
        if before is None:
            raise AppError("入库时未能创建库存", code=40450, status_code=404)
        before_qty = before.quantity
        before_reserved = before.reserved_quantity
        affected = self.inventories.add_quantity(
            warehouse_id=warehouse_id,
            sku_id=sku_id,
            quantity=quantity,
        )
        if affected != 1:
            raise AppError("入库失败", code=40450, status_code=404)
        updated = self.inventories.get_by_warehouse_and_sku(warehouse_id, sku_id)
        if updated is None:
            raise AppError(_UNAVAILABLE, code=40450, status_code=404)
        self._add_tx(
            updated,
            tx_type=InventoryTransactionType.INBOUND.value,
            change_quantity=quantity,
            before_qty=before_qty,
            after_qty=updated.quantity,
            before_reserved=before_reserved,
            after_reserved=updated.reserved_quantity,
            remark=remark,
            reference_type=reference_type,
            reference_id=reference_id,
        )
        return updated

    def _insert_inventory_row(self, warehouse_id: int, sku_id: int) -> None:
        """插入 quantity=0 的库存行。并发插入冲突时只回滚保存点。"""
        nested = self.session.begin_nested()
        try:
            self.inventories.add(
                Inventory(
                    tenant_id=self.context.tenant_id,
                    warehouse_id=warehouse_id,
                    sku_id=sku_id,
                    quantity=0,
                    reserved_quantity=0,
                    version=0,
                )
            )
            self.session.flush()
            nested.commit()
        except IntegrityError:
            nested.rollback()

    def deduct_within_transaction(
        self,
        *,
        warehouse_id: int,
        sku_id: int,
        quantity: int,
        reference_type: str | None = None,
        reference_id: int | None = None,
        remark: str | None = None,
    ) -> Inventory:
        """在当前事务里同时减少 quantity 和 reserved，不 commit。

        功能：确认出库时调用，复用 V5 deduct_if_reserved。
        为什么两个数一起减：这批货出库前已经从可用量里预占掉了。
        只减 quantity 会让 reserved 还占着已经离库的货；只减 reserved 会让账面还显示货在库。
        可用量 = quantity - reserved，两边减同一个数，可用量通常不变。
        """
        current = self.inventories.get_by_warehouse_and_sku(warehouse_id, sku_id)
        if current is None:
            raise AppError(
                "预占或实际库存不足，不能确认出库",
                code=40071,
                status_code=400,
                data={"error": "INSUFFICIENT_RESERVED_INVENTORY"},
            )
        before_qty = current.quantity
        before_reserved = current.reserved_quantity
        affected = self.inventories.deduct_if_reserved(
            warehouse_id=warehouse_id,
            sku_id=sku_id,
            quantity=quantity,
        )
        if affected != 1:
            raise AppError(
                "预占或实际库存不足，不能确认出库",
                code=40071,
                status_code=400,
                data={"error": "INSUFFICIENT_RESERVED_INVENTORY", "sku_id": sku_id},
            )
        updated = self.inventories.get_by_warehouse_and_sku(warehouse_id, sku_id)
        if updated is None:
            raise AppError(_UNAVAILABLE, code=40450, status_code=404)
        self._add_tx(
            updated,
            tx_type=InventoryTransactionType.OUTBOUND.value,
            change_quantity=-quantity,
            before_qty=before_qty,
            after_qty=updated.quantity,
            before_reserved=before_reserved,
            after_reserved=updated.reserved_quantity,
            remark=remark,
            reference_type=reference_type,
            reference_id=reference_id,
        )
        return updated

    def reserve_inventory(self, inventory_id: int, payload: InventoryQtyChange) -> InventoryItemOut:
        """预占：只增加 reserved，不减少 quantity。

        库存页面的内部接口仍由本方法提交。销售订单不要直接调用它，
        否则每个 SKU 都会自己 commit，多 SKU 失败时无法整单回滚。
        条件 UPDATE 的规则在 reserve_within_transaction。
        """
        self.auth.require_all(self.context, (PermissionCode.INVENTORY_ADJUST,))
        current = self.inventories.get_in_tenant(inventory_id)
        if current is None:
            raise AppError(_UNAVAILABLE, code=40450, status_code=404)
        try:
            self.reserve_within_transaction(
                warehouse_id=current.warehouse_id,
                sku_id=current.sku_id,
                quantity=payload.quantity,
                remark=payload.remark,
            )
            self.session.commit()
            updated = self.inventories.get_in_tenant(inventory_id)
        except AppError:
            self.session.rollback()
            raise
        except Exception:
            self.session.rollback()
            raise
        if updated is None or updated.sku is None or updated.warehouse is None:
            raise AppError(_UNAVAILABLE, code=40450, status_code=404)
        return self._item_out(updated, updated.sku, updated.sku.product, updated.warehouse)

    def release_inventory(self, inventory_id: int, payload: InventoryQtyChange) -> InventoryItemOut:
        """释放预占。reserved 不够时拒绝，不能减成负数。订单取消请用 release_within_transaction。"""
        self.auth.require_all(self.context, (PermissionCode.INVENTORY_ADJUST,))
        current = self.inventories.get_in_tenant(inventory_id)
        if current is None:
            raise AppError(_UNAVAILABLE, code=40450, status_code=404)
        try:
            self.release_within_transaction(
                warehouse_id=current.warehouse_id,
                sku_id=current.sku_id,
                quantity=payload.quantity,
                remark=payload.remark,
            )
            self.session.commit()
            updated = self.inventories.get_in_tenant(inventory_id)
        except AppError:
            self.session.rollback()
            raise
        except Exception:
            self.session.rollback()
            raise
        if updated is None or updated.sku is None or updated.warehouse is None:
            raise AppError(_UNAVAILABLE, code=40450, status_code=404)
        return self._item_out(updated, updated.sku, updated.sku.product, updated.warehouse)

    def deduct_reserved_inventory(
        self,
        inventory_id: int,
        payload: InventoryQtyChange,
    ) -> InventoryItemOut:
        """出库确认底层：quantity 和 reserved 同时减少。

        预占 10 再发货 10：应从 100/10 变成 90/0，而不是 90/10。
        V5 不提供发货页面，只把这个原语留给出库版本复用。流水类型记 OUTBOUND。
        """
        self.auth.require_all(self.context, (PermissionCode.INVENTORY_ADJUST,))
        current = self.inventories.get_in_tenant(inventory_id)
        if current is None:
            raise AppError(_UNAVAILABLE, code=40450, status_code=404)
        try:
            self.deduct_within_transaction(
                warehouse_id=current.warehouse_id,
                sku_id=current.sku_id,
                quantity=payload.quantity,
                remark=payload.remark,
            )
            self.session.commit()
            updated = self.inventories.get_in_tenant(inventory_id)
        except AppError:
            self.session.rollback()
            raise
        except Exception:
            self.session.rollback()
            raise
        if updated is None or updated.sku is None or updated.warehouse is None:
            raise AppError(_UNAVAILABLE, code=40450, status_code=404)
        return self._item_out(updated, updated.sku, updated.sku.product, updated.warehouse)

    def adjust_inventory_optimistic(
        self,
        inventory_id: int,
        payload: InventoryOptimisticAdjust,
    ) -> InventoryItemOut:
        """乐观锁演示：UPDATE ... WHERE version = expected_version。

        正式盘点请用 adjust_inventory() 的 FOR UPDATE。
        若期间别人改过同一行，rowcount=0，返回 INVENTORY_CONFLICT，调用方应重新读取。
        仍然把库存变更和流水放进同一事务。
        """
        self.auth.require_all(self.context, (PermissionCode.INVENTORY_ADJUST,))
        current = self.inventories.get_in_tenant(inventory_id)
        if current is None:
            raise AppError(_UNAVAILABLE, code=40450, status_code=404)
        if payload.type not in _ADJUST_TYPES:
            raise AppError("调整类型不合法", code=40073, status_code=400)
        before_qty = current.quantity
        before_reserved = current.reserved_quantity
        if payload.type == InventoryTransactionType.ADJUST_IN.value:
            new_qty = before_qty + payload.quantity
            change = payload.quantity
        else:
            available = before_qty - before_reserved
            if payload.quantity > available:
                raise AppError(
                    "可用库存不足，不能把已预占的数量减没",
                    code=40070,
                    status_code=400,
                    data={"error": "INSUFFICIENT_AVAILABLE_INVENTORY"},
                )
            new_qty = before_qty - payload.quantity
            change = -payload.quantity
        try:
            affected = self.inventories.update_quantity_if_version(
                inventory_id=inventory_id,
                expected_version=payload.expected_version,
                new_quantity=new_qty,
            )
            if affected != 1:
                self.session.rollback()
                raise AppError(
                    "库存已被其他人修改，请刷新后重试",
                    code=40072,
                    status_code=400,
                    data={"error": "INVENTORY_CONFLICT"},
                )
            updated = self.inventories.get_in_tenant(inventory_id)
            if updated is None:
                raise AppError(_UNAVAILABLE, code=40450, status_code=404)
            self._add_tx(
                updated,
                tx_type=payload.type,
                change_quantity=change,
                before_qty=before_qty,
                after_qty=updated.quantity,
                before_reserved=before_reserved,
                after_reserved=updated.reserved_quantity,
                remark=payload.remark,
            )
            self.session.commit()
            updated = self.inventories.get_in_tenant(inventory_id)
        except AppError:
            self.session.rollback()
            raise
        except Exception:
            self.session.rollback()
            raise
        if updated is None or updated.sku is None or updated.warehouse is None:
            raise AppError(_UNAVAILABLE, code=40450, status_code=404)
        return self._item_out(updated, updated.sku, updated.sku.product, updated.warehouse)

    def _require_active_warehouse(self, warehouse_id: int) -> Warehouse:
        warehouse = self.warehouses.get_in_tenant(warehouse_id)
        if warehouse is None:
            raise AppError(_WAREHOUSE_UNAVAILABLE, code=40440, status_code=404)
        if warehouse.status != WarehouseStatus.ACTIVE.value:
            raise AppError("只能对启用中的仓库初始化库存", code=40075, status_code=400)
        return warehouse

    def _require_sku(self, sku_id: int) -> ProductSku:
        sku = self.skus.get_by_id_in_tenant(sku_id)
        if sku is None:
            raise AppError(_SKU_UNAVAILABLE, code=40433, status_code=404)
        return sku

    def _add_tx(
        self,
        inventory: Inventory,
        *,
        tx_type: str,
        change_quantity: int,
        before_qty: int,
        after_qty: int,
        before_reserved: int,
        after_reserved: int,
        remark: str | None,
        reference_type: str | None = None,
        reference_id: int | None = None,
    ) -> InventoryTransaction:
        row = InventoryTransaction(
            tenant_id=self.context.tenant_id,
            warehouse_id=inventory.warehouse_id,
            sku_id=inventory.sku_id,
            inventory_id=inventory.id,
            type=tx_type,
            change_quantity=change_quantity,
            before_quantity=before_qty,
            after_quantity=after_qty,
            before_reserved_quantity=before_reserved,
            after_reserved_quantity=after_reserved,
            reference_type=reference_type,
            reference_id=reference_id,
            remark=remark,
            operator_user_id=self.context.user_id,
        )
        self.transactions.add(row)
        return row

    @staticmethod
    def _item_out(
        inventory: Inventory,
        sku: ProductSku,
        product: Product | None,
        warehouse: Warehouse,
    ) -> InventoryItemOut:
        return InventoryItemOut(
            id=inventory.id,
            tenant_id=inventory.tenant_id,
            warehouse_id=inventory.warehouse_id,
            warehouse_name=warehouse.name,
            sku_id=inventory.sku_id,
            sku_code=sku.sku_code or "",
            sku_name=sku.name,
            product_id=sku.product_id,
            product_name=product.name if product is not None else "",
            spec_values=sku.spec_values or {},
            quantity=inventory.quantity,
            reserved_quantity=inventory.reserved_quantity,
            available_quantity=inventory.quantity - inventory.reserved_quantity,
            version=inventory.version,
            created_at=inventory.created_at,
            updated_at=inventory.updated_at,
        )

    @staticmethod
    def _tx_out(
        row: InventoryTransaction,
        *,
        warehouse_name: str,
        sku_code: str,
        sku_name: str,
        product_name: str,
        operator_name: str | None,
    ) -> InventoryTransactionOut:
        return InventoryTransactionOut(
            id=row.id,
            tenant_id=row.tenant_id,
            inventory_id=row.inventory_id,
            warehouse_id=row.warehouse_id,
            warehouse_name=warehouse_name,
            sku_id=row.sku_id,
            sku_code=sku_code,
            sku_name=sku_name,
            product_name=product_name,
            type=row.type,
            change_quantity=row.change_quantity,
            before_quantity=row.before_quantity,
            after_quantity=row.after_quantity,
            before_reserved_quantity=row.before_reserved_quantity,
            after_reserved_quantity=row.after_reserved_quantity,
            reference_type=row.reference_type,
            reference_id=row.reference_id,
            remark=row.remark,
            operator_user_id=row.operator_user_id,
            operator_name=operator_name,
            created_at=row.created_at,
        )

    @staticmethod
    def _sku_option(sku: ProductSku) -> SkuOptionOut:
        product = sku.product
        return SkuOptionOut(
            id=sku.id,
            tenant_id=sku.tenant_id,
            product_id=sku.product_id,
            product_name=product.name if product is not None else "",
            sku_code=sku.sku_code or "",
            name=sku.name,
            spec_values=sku.spec_values or {},
            status=sku.status,
        )

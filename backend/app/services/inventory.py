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

    def reserve_inventory(self, inventory_id: int, payload: InventoryQtyChange) -> InventoryItemOut:
        """预占：只增加 reserved，不减少 quantity。

        后续订单占用库存时走这里。如果直接减 quantity，盘点会看到货已经没了，
        但货还在仓库里等发。所以预占只动 reserved。
        实现：WHERE quantity - reserved >= qty 的条件 UPDATE。rowcount=0 再查一次，
        区分「没有这条库存」和「可用不够」，避免两个并发都读到 available=10 各扣 8 超卖。
        """
        self.auth.require_all(self.context, (PermissionCode.INVENTORY_ADJUST,))
        current = self.inventories.get_in_tenant(inventory_id)
        if current is None:
            raise AppError(_UNAVAILABLE, code=40450, status_code=404)
        try:
            affected = self.inventories.reserve_if_available(
                warehouse_id=current.warehouse_id,
                sku_id=current.sku_id,
                quantity=payload.quantity,
            )
            if affected != 1:
                self.session.rollback()
                again = self.inventories.get_in_tenant(inventory_id)
                if again is None:
                    raise AppError(_UNAVAILABLE, code=40450, status_code=404)
                raise AppError(
                    "可用库存不足",
                    code=40070,
                    status_code=400,
                    data={"error": "INSUFFICIENT_AVAILABLE_INVENTORY"},
                )
            updated = self.inventories.get_in_tenant(inventory_id)
            if updated is None:
                raise AppError(_UNAVAILABLE, code=40450, status_code=404)
            self._add_tx(
                updated,
                tx_type=InventoryTransactionType.RESERVE.value,
                change_quantity=0,
                before_qty=updated.quantity,
                after_qty=updated.quantity,
                before_reserved=updated.reserved_quantity - payload.quantity,
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

    def release_inventory(self, inventory_id: int, payload: InventoryQtyChange) -> InventoryItemOut:
        """释放预占。reserved 不够时拒绝，不能减成负数。"""
        self.auth.require_all(self.context, (PermissionCode.INVENTORY_ADJUST,))
        current = self.inventories.get_in_tenant(inventory_id)
        if current is None:
            raise AppError(_UNAVAILABLE, code=40450, status_code=404)
        try:
            affected = self.inventories.release_if_reserved(
                warehouse_id=current.warehouse_id,
                sku_id=current.sku_id,
                quantity=payload.quantity,
            )
            if affected != 1:
                self.session.rollback()
                again = self.inventories.get_in_tenant(inventory_id)
                if again is None:
                    raise AppError(_UNAVAILABLE, code=40450, status_code=404)
                raise AppError(
                    "预占数量不足，不能超额释放",
                    code=40071,
                    status_code=400,
                    data={"error": "INSUFFICIENT_RESERVED_INVENTORY"},
                )
            updated = self.inventories.get_in_tenant(inventory_id)
            if updated is None:
                raise AppError(_UNAVAILABLE, code=40450, status_code=404)
            self._add_tx(
                updated,
                tx_type=InventoryTransactionType.RELEASE.value,
                change_quantity=0,
                before_qty=updated.quantity,
                after_qty=updated.quantity,
                before_reserved=updated.reserved_quantity + payload.quantity,
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
            affected = self.inventories.deduct_if_reserved(
                warehouse_id=current.warehouse_id,
                sku_id=current.sku_id,
                quantity=payload.quantity,
            )
            if affected != 1:
                self.session.rollback()
                again = self.inventories.get_in_tenant(inventory_id)
                if again is None:
                    raise AppError(_UNAVAILABLE, code=40450, status_code=404)
                raise AppError(
                    "预占或实际库存不足，不能确认出库",
                    code=40070,
                    status_code=400,
                    data={"error": "INSUFFICIENT_AVAILABLE_INVENTORY"},
                )
            updated = self.inventories.get_in_tenant(inventory_id)
            if updated is None:
                raise AppError(_UNAVAILABLE, code=40450, status_code=404)
            self._add_tx(
                updated,
                tx_type=InventoryTransactionType.OUTBOUND.value,
                change_quantity=-payload.quantity,
                before_qty=updated.quantity + payload.quantity,
                after_qty=updated.quantity,
                before_reserved=updated.reserved_quantity + payload.quantity,
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

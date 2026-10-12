"""库存报表聚合。台账快照与流水趋势都在 MySQL 完成。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import case, func, select, true
from sqlalchemy.orm import Session

from app.core.analytics import DEFAULT_LOW_STOCK_THRESHOLD, int_or_zero
from app.models.inventory import Inventory, InventoryTransaction, InventoryTransactionType
from app.models.product import Product, ProductSku, SkuStatus
from app.models.warehouse import Warehouse, WarehouseStatus
from app.repositories.base import BaseRepository

INBOUND_TYPES = (
    InventoryTransactionType.INBOUND.value,
    InventoryTransactionType.INITIALIZE.value,
    InventoryTransactionType.ADJUST_IN.value,
    InventoryTransactionType.RETURN_INBOUND.value,
)
OUTBOUND_TYPES = (
    InventoryTransactionType.OUTBOUND.value,
    InventoryTransactionType.ADJUST_OUT.value,
    InventoryTransactionType.PURCHASE_RETURN_OUTBOUND.value,
)
AVAILABLE = Inventory.quantity - Inventory.reserved_quantity


class InventoryAnalyticsRepository(BaseRepository):
    def __init__(self, session: Session, tenant_id: int) -> None:
        super().__init__(session, tenant_id)

    def _tenant(self):
        return Inventory.tenant_id == self.ensure_tenant()

    def _warehouse(self, warehouse_id: int | None, column=None):
        if warehouse_id is None:
            return true()
        target = column if column is not None else Inventory.warehouse_id
        return target == warehouse_id

    def _active_sku_warehouse(self):
        """低库存 / 零库存只统计有效 SKU 和启用仓库。"""
        return (
            ProductSku.status == SkuStatus.ACTIVE.value,
            Warehouse.status == WarehouseStatus.ACTIVE.value,
        )

    def snapshot(
        self,
        warehouse_id: int | None = None,
        low_stock_threshold: int = DEFAULT_LOW_STOCK_THRESHOLD,
    ) -> dict[str, int]:
        """
        库存总量口径：
        total_quantity = SUM(quantity)
        total_reserved_quantity = SUM(reserved_quantity)
        total_available_quantity = SUM(quantity - reserved_quantity)
        zero_stock：available_quantity == 0（账面有货但全部预占也算零可用）
        low_stock：available_quantity <= threshold
        """
        tenant_id = self.ensure_tenant()
        stmt = select(
            func.count(Inventory.id),
            func.count(func.distinct(Inventory.sku_id)),
            func.count(func.distinct(Inventory.warehouse_id)),
            func.coalesce(func.sum(Inventory.quantity), 0),
            func.coalesce(func.sum(Inventory.reserved_quantity), 0),
            func.coalesce(func.sum(AVAILABLE), 0),
        ).where(self._tenant(), self._warehouse(warehouse_id))
        records, skus, warehouses, qty, reserved, available = self.session.execute(stmt).one()

        zero_stmt = (
            select(func.count(Inventory.id))
            .select_from(Inventory)
            .join(
                ProductSku,
                (Inventory.tenant_id == ProductSku.tenant_id) & (Inventory.sku_id == ProductSku.id),
            )
            .join(
                Warehouse,
                (Inventory.tenant_id == Warehouse.tenant_id)
                & (Inventory.warehouse_id == Warehouse.id),
            )
            .where(
                Inventory.tenant_id == tenant_id,
                self._warehouse(warehouse_id),
                AVAILABLE == 0,
                *self._active_sku_warehouse(),
            )
        )
        low_stmt = (
            select(func.count(Inventory.id))
            .select_from(Inventory)
            .join(
                ProductSku,
                (Inventory.tenant_id == ProductSku.tenant_id) & (Inventory.sku_id == ProductSku.id),
            )
            .join(
                Warehouse,
                (Inventory.tenant_id == Warehouse.tenant_id)
                & (Inventory.warehouse_id == Warehouse.id),
            )
            .where(
                Inventory.tenant_id == tenant_id,
                self._warehouse(warehouse_id),
                AVAILABLE <= low_stock_threshold,
                *self._active_sku_warehouse(),
            )
        )
        return {
            "inventory_record_count": int_or_zero(records),
            "sku_count": int_or_zero(skus),
            "warehouse_count": int_or_zero(warehouses),
            "total_quantity": int_or_zero(qty),
            "total_reserved_quantity": int_or_zero(reserved),
            "total_available_quantity": int_or_zero(available),
            "zero_stock_sku_count": int_or_zero(self.session.execute(zero_stmt).scalar_one()),
            "low_stock_sku_count": int_or_zero(self.session.execute(low_stmt).scalar_one()),
            "low_stock_threshold": low_stock_threshold,
        }

    def by_warehouse(
        self,
        start: datetime,
        end_exclusive: datetime,
        warehouse_id: int | None = None,
    ) -> list[tuple]:
        """仓库分布：台账 JOIN 流水按仓聚合。一次查出库存与期内出入库，避免按仓循环。"""
        tenant_id = self.ensure_tenant()
        stock_stmt = (
            select(
                Warehouse.id,
                Warehouse.name,
                func.count(func.distinct(Inventory.sku_id)).label("sku_count"),
                func.coalesce(func.sum(Inventory.quantity), 0).label("quantity"),
                func.coalesce(func.sum(Inventory.reserved_quantity), 0).label("reserved"),
                func.coalesce(func.sum(AVAILABLE), 0).label("available"),
            )
            .select_from(Warehouse)
            .outerjoin(
                Inventory,
                (Inventory.tenant_id == Warehouse.tenant_id)
                & (Inventory.warehouse_id == Warehouse.id),
            )
            .where(
                Warehouse.tenant_id == tenant_id,
                self._warehouse(warehouse_id, Warehouse.id),
            )
            .group_by(Warehouse.id, Warehouse.name)
            .order_by(Warehouse.id)
        )
        stocks = list(self.session.execute(stock_stmt).all())

        tx_stmt = (
            select(
                InventoryTransaction.warehouse_id,
                func.coalesce(
                    func.sum(
                        case(
                            (
                                InventoryTransaction.type.in_(INBOUND_TYPES),
                                InventoryTransaction.change_quantity,
                            ),
                            else_=0,
                        )
                    ),
                    0,
                ).label("inbound_qty"),
                func.coalesce(
                    func.sum(
                        case(
                            (
                                InventoryTransaction.type.in_(OUTBOUND_TYPES),
                                func.abs(InventoryTransaction.change_quantity),
                            ),
                            else_=0,
                        )
                    ),
                    0,
                ).label("outbound_qty"),
                func.coalesce(
                    func.sum(
                        case(
                            (
                                InventoryTransaction.type
                                == InventoryTransactionType.TRANSFER_IN.value,
                                InventoryTransaction.change_quantity,
                            ),
                            else_=0,
                        )
                    ),
                    0,
                ).label("transfer_in"),
                func.coalesce(
                    func.sum(
                        case(
                            (
                                InventoryTransaction.type
                                == InventoryTransactionType.TRANSFER_OUT.value,
                                func.abs(InventoryTransaction.change_quantity),
                            ),
                            else_=0,
                        )
                    ),
                    0,
                ).label("transfer_out"),
                func.coalesce(
                    func.sum(
                        case(
                            (
                                InventoryTransaction.type
                                == InventoryTransactionType.STOCKTAKE_ADJUSTMENT.value,
                                InventoryTransaction.change_quantity,
                            ),
                            else_=0,
                        )
                    ),
                    0,
                ).label("stocktake"),
            )
            .where(
                InventoryTransaction.tenant_id == tenant_id,
                InventoryTransaction.created_at >= start,
                InventoryTransaction.created_at < end_exclusive,
                self._warehouse(warehouse_id, InventoryTransaction.warehouse_id),
            )
            .group_by(InventoryTransaction.warehouse_id)
        )
        tx_by_wh = {int(row.warehouse_id): row for row in self.session.execute(tx_stmt)}
        merged: list[tuple] = []
        for row in stocks:
            tx = tx_by_wh.get(int(row.id))
            merged.append(
                (
                    row.id,
                    row.name,
                    int_or_zero(row.sku_count),
                    int_or_zero(row.quantity),
                    int_or_zero(row.reserved),
                    int_or_zero(row.available),
                    int_or_zero(getattr(tx, "inbound_qty", 0) if tx else 0),
                    int_or_zero(getattr(tx, "outbound_qty", 0) if tx else 0),
                    int_or_zero(getattr(tx, "transfer_in", 0) if tx else 0),
                    int_or_zero(getattr(tx, "transfer_out", 0) if tx else 0),
                    int_or_zero(getattr(tx, "stocktake", 0) if tx else 0),
                )
            )
        return merged

    def top_skus(
        self,
        *,
        metric: str,
        limit: int,
        warehouse_id: int | None = None,
    ) -> list[tuple]:
        """
        metric=quantity 库存最高；reserved 预占最高；available 可用最低。
        JOIN sku / product / warehouse 一次返回名称。
        """
        tenant_id = self.ensure_tenant()
        order_expr = AVAILABLE.asc()
        if metric == "quantity":
            order_expr = Inventory.quantity.desc()
        elif metric == "reserved":
            order_expr = Inventory.reserved_quantity.desc()
        stmt = (
            select(
                ProductSku.id,
                ProductSku.sku_code,
                ProductSku.name,
                Product.name,
                Warehouse.id,
                Warehouse.name,
                Inventory.quantity,
                Inventory.reserved_quantity,
                AVAILABLE.label("available"),
            )
            .select_from(Inventory)
            .join(
                ProductSku,
                (Inventory.tenant_id == ProductSku.tenant_id) & (Inventory.sku_id == ProductSku.id),
            )
            .join(
                Product,
                (ProductSku.tenant_id == Product.tenant_id) & (ProductSku.product_id == Product.id),
            )
            .join(
                Warehouse,
                (Inventory.tenant_id == Warehouse.tenant_id)
                & (Inventory.warehouse_id == Warehouse.id),
            )
            .where(Inventory.tenant_id == tenant_id, self._warehouse(warehouse_id))
            .order_by(order_expr, Inventory.id.asc())
            .limit(limit)
        )
        return list(self.session.execute(stmt).all())

    def low_stock(
        self,
        threshold: int,
        limit: int,
        warehouse_id: int | None = None,
    ) -> list[tuple]:
        tenant_id = self.ensure_tenant()
        stmt = (
            select(
                ProductSku.id,
                ProductSku.sku_code,
                ProductSku.name,
                Product.name,
                Warehouse.id,
                Warehouse.name,
                Inventory.quantity,
                Inventory.reserved_quantity,
                AVAILABLE.label("available"),
            )
            .select_from(Inventory)
            .join(
                ProductSku,
                (Inventory.tenant_id == ProductSku.tenant_id) & (Inventory.sku_id == ProductSku.id),
            )
            .join(
                Product,
                (ProductSku.tenant_id == Product.tenant_id) & (ProductSku.product_id == Product.id),
            )
            .join(
                Warehouse,
                (Inventory.tenant_id == Warehouse.tenant_id)
                & (Inventory.warehouse_id == Warehouse.id),
            )
            .where(
                Inventory.tenant_id == tenant_id,
                self._warehouse(warehouse_id),
                AVAILABLE <= threshold,
                *self._active_sku_warehouse(),
            )
            .order_by(AVAILABLE.asc(), Inventory.id.asc())
            .limit(limit)
        )
        return list(self.session.execute(stmt).all())

    def daily_transaction_trend(
        self,
        start: datetime,
        end_exclusive: datetime,
        warehouse_id: int | None = None,
    ) -> list[tuple]:
        """
        按日聚合库存流水。
        inbound：INBOUND / INITIALIZE / ADJUST_IN / RETURN_INBOUND
        outbound：OUTBOUND / ADJUST_OUT / PURCHASE_RETURN_OUTBOUND 取绝对值
        adjustment：STOCKTAKE_ADJUSTMENT 可正可负
        """
        tenant_id = self.ensure_tenant()
        day = func.date(InventoryTransaction.created_at)
        stmt = (
            select(
                day.label("bucket"),
                func.coalesce(
                    func.sum(
                        case(
                            (
                                InventoryTransaction.type.in_(INBOUND_TYPES),
                                InventoryTransaction.change_quantity,
                            ),
                            else_=0,
                        )
                    ),
                    0,
                ),
                func.coalesce(
                    func.sum(
                        case(
                            (
                                InventoryTransaction.type.in_(OUTBOUND_TYPES),
                                func.abs(InventoryTransaction.change_quantity),
                            ),
                            else_=0,
                        )
                    ),
                    0,
                ),
                func.coalesce(
                    func.sum(
                        case(
                            (
                                InventoryTransaction.type
                                == InventoryTransactionType.STOCKTAKE_ADJUSTMENT.value,
                                InventoryTransaction.change_quantity,
                            ),
                            else_=0,
                        )
                    ),
                    0,
                ),
                func.coalesce(
                    func.sum(
                        case(
                            (
                                InventoryTransaction.type
                                == InventoryTransactionType.TRANSFER_IN.value,
                                InventoryTransaction.change_quantity,
                            ),
                            else_=0,
                        )
                    ),
                    0,
                ),
                func.coalesce(
                    func.sum(
                        case(
                            (
                                InventoryTransaction.type
                                == InventoryTransactionType.TRANSFER_OUT.value,
                                func.abs(InventoryTransaction.change_quantity),
                            ),
                            else_=0,
                        )
                    ),
                    0,
                ),
            )
            .where(
                InventoryTransaction.tenant_id == tenant_id,
                InventoryTransaction.created_at >= start,
                InventoryTransaction.created_at < end_exclusive,
                self._warehouse(warehouse_id, InventoryTransaction.warehouse_id),
            )
            .group_by(day)
            .order_by(day)
        )
        return list(self.session.execute(stmt).all())

    def transaction_by_type(
        self,
        start: datetime,
        end_exclusive: datetime,
        warehouse_id: int | None = None,
    ) -> list[tuple]:
        tenant_id = self.ensure_tenant()
        stmt = (
            select(
                InventoryTransaction.type,
                func.coalesce(func.sum(InventoryTransaction.change_quantity), 0),
            )
            .where(
                InventoryTransaction.tenant_id == tenant_id,
                InventoryTransaction.created_at >= start,
                InventoryTransaction.created_at < end_exclusive,
                self._warehouse(warehouse_id, InventoryTransaction.warehouse_id),
            )
            .group_by(InventoryTransaction.type)
            .order_by(InventoryTransaction.type)
        )
        by_type = {row[0]: int_or_zero(row[1]) for row in self.session.execute(stmt)}
        return [(item.value, by_type.get(item.value, 0)) for item in InventoryTransactionType]

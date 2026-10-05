from datetime import date, datetime
from typing import Any

from sqlalchemy import and_, delete, func, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session, selectinload

from app.models.product import ProductSku
from app.models.purchase import PurchaseOrder, PurchaseOrderItem
from app.models.supplier import Supplier
from app.models.user import User
from app.models.warehouse import Warehouse
from app.repositories.base import BaseRepository


class PurchaseOrderRepository(BaseRepository):
    def __init__(self, session: Session, tenant_id: int) -> None:
        super().__init__(session, tenant_id)

    def get_in_tenant(self, order_id: int) -> PurchaseOrder | None:
        """详情一次 selectinload 明细 + SKU + 商品，避免循环查库。"""
        tenant_id = self.ensure_tenant()
        stmt = (
            select(PurchaseOrder)
            .options(
                selectinload(PurchaseOrder.supplier),
                selectinload(PurchaseOrder.warehouse),
                selectinload(PurchaseOrder.items).selectinload(PurchaseOrderItem.sku).selectinload(
                    ProductSku.product,
                ),
            )
            .where(PurchaseOrder.tenant_id == tenant_id, PurchaseOrder.id == order_id)
        )
        return self.session.scalars(stmt).first()

    def get_for_update(self, order_id: int) -> PurchaseOrder | None:
        """编辑明细时锁主表，避免两个草稿保存互相覆盖。"""
        tenant_id = self.ensure_tenant()
        stmt = (
            select(PurchaseOrder)
            .where(PurchaseOrder.tenant_id == tenant_id, PurchaseOrder.id == order_id)
            .with_for_update()
        )
        return self.session.scalars(stmt).first()

    def list_page(
        self,
        *,
        q: str | None,
        supplier_id: int | None,
        warehouse_id: int | None,
        sku_id: int | None,
        status: str | None,
        created_from: datetime | None,
        created_to: datetime | None,
        expected_from: date | None,
        expected_to: date | None,
        created_by: int | None,
        page: int,
        page_size: int,
    ) -> tuple[list[tuple], int]:
        """列表 JOIN 供应商/仓库/创建人，聚合 SKU 数和采购数量，不要 Python 再 sum。"""
        tenant_id = self.ensure_tenant()
        filters = [PurchaseOrder.tenant_id == tenant_id]
        if q:
            filters.append(PurchaseOrder.order_no.like(f"%{q}%"))
        if supplier_id:
            filters.append(PurchaseOrder.supplier_id == supplier_id)
        if warehouse_id:
            filters.append(PurchaseOrder.warehouse_id == warehouse_id)
        if status:
            filters.append(PurchaseOrder.status == status)
        if created_by:
            filters.append(PurchaseOrder.created_by == created_by)
        if created_from is not None:
            filters.append(PurchaseOrder.created_at >= created_from)
        if created_to is not None:
            filters.append(PurchaseOrder.created_at <= created_to)
        if expected_from is not None:
            filters.append(PurchaseOrder.expected_arrival_date >= expected_from)
        if expected_to is not None:
            filters.append(PurchaseOrder.expected_arrival_date <= expected_to)
        if sku_id:
            filters.append(
                PurchaseOrder.id.in_(
                    select(PurchaseOrderItem.purchase_order_id).where(
                        PurchaseOrderItem.tenant_id == tenant_id,
                        PurchaseOrderItem.sku_id == sku_id,
                    )
                )
            )

        count_stmt = select(func.count(PurchaseOrder.id)).where(*filters)
        total = int(self.session.scalar(count_stmt) or 0)
        sku_count = func.count(PurchaseOrderItem.id)
        total_qty = func.coalesce(func.sum(PurchaseOrderItem.quantity), 0)
        # 只合计有单价的行。全部没填价格时 total_amount 为 NULL，前端显示 '-'。
        priced = PurchaseOrderItem.quantity * PurchaseOrderItem.unit_price
        total_amount = func.sum(priced)
        stmt = (
            select(
                PurchaseOrder,
                Supplier.name,
                Warehouse.name,
                User.display_name,
                sku_count,
                total_qty,
                total_amount,
            )
            .join(
                Supplier,
                and_(
                    Supplier.tenant_id == PurchaseOrder.tenant_id,
                    Supplier.id == PurchaseOrder.supplier_id,
                ),
            )
            .join(
                Warehouse,
                and_(
                    Warehouse.tenant_id == PurchaseOrder.tenant_id,
                    Warehouse.id == PurchaseOrder.warehouse_id,
                ),
            )
            .outerjoin(User, User.id == PurchaseOrder.created_by)
            .outerjoin(
                PurchaseOrderItem,
                and_(
                    PurchaseOrderItem.tenant_id == PurchaseOrder.tenant_id,
                    PurchaseOrderItem.purchase_order_id == PurchaseOrder.id,
                ),
            )
            .where(*filters)
            .group_by(PurchaseOrder.id, Supplier.name, Warehouse.name, User.display_name)
            .order_by(PurchaseOrder.created_at.desc(), PurchaseOrder.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(self.session.execute(stmt).all()), total

    def count_by_supplier(self, supplier_id: int) -> int:
        tenant_id = self.ensure_tenant()
        stmt = select(func.count(PurchaseOrder.id)).where(
            PurchaseOrder.tenant_id == tenant_id,
            PurchaseOrder.supplier_id == supplier_id,
        )
        return int(self.session.scalar(stmt) or 0)

    def count_by_warehouse(self, warehouse_id: int) -> int:
        tenant_id = self.ensure_tenant()
        stmt = select(func.count(PurchaseOrder.id)).where(
            PurchaseOrder.tenant_id == tenant_id,
            PurchaseOrder.warehouse_id == warehouse_id,
        )
        return int(self.session.scalar(stmt) or 0)

    def count_by_sku(self, sku_id: int) -> int:
        tenant_id = self.ensure_tenant()
        stmt = select(func.count(PurchaseOrderItem.id)).where(
            PurchaseOrderItem.tenant_id == tenant_id,
            PurchaseOrderItem.sku_id == sku_id,
        )
        return int(self.session.scalar(stmt) or 0)

    def add(self, order: PurchaseOrder) -> PurchaseOrder:
        self.session.add(order)
        return order

    def add_item(self, item: PurchaseOrderItem) -> PurchaseOrderItem:
        self.session.add(item)
        return item

    def delete_items(self, order_id: int) -> None:
        tenant_id = self.ensure_tenant()
        stmt = delete(PurchaseOrderItem).where(
            PurchaseOrderItem.tenant_id == tenant_id,
            PurchaseOrderItem.purchase_order_id == order_id,
        )
        self.session.execute(stmt)

    def transition_if_status(
        self,
        *,
        order_id: int,
        expected_status: str,
        values: dict[str, Any],
    ) -> int:
        """条件 UPDATE 状态。rowcount=0 说明别人已经改过，不能覆盖。"""
        tenant_id = self.ensure_tenant()
        stmt = (
            update(PurchaseOrder)
            .where(
                PurchaseOrder.tenant_id == tenant_id,
                PurchaseOrder.id == order_id,
                PurchaseOrder.status == expected_status,
            )
            .values(**values)
        )
        result: CursorResult[Any] = self.session.execute(stmt)  # type: ignore[assignment]
        self.session.expire_all()
        return int(result.rowcount or 0)

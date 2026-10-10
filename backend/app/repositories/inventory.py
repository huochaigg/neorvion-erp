from datetime import datetime
from typing import cast

from sqlalchemy import Update, and_, func, or_, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session, selectinload

from app.models.inventory import Inventory, InventoryTransaction
from app.models.product import Product, ProductSku
from app.models.user import User
from app.models.warehouse import Warehouse
from app.repositories.base import BaseRepository
from app.repositories.product import ProductSkuRepository


class InventoryRepository(BaseRepository):
    def __init__(self, session: Session, tenant_id: int) -> None:
        super().__init__(session, tenant_id)

    def get_in_tenant(self, inventory_id: int) -> Inventory | None:
        tenant_id = self.ensure_tenant()
        stmt = (
            select(Inventory)
            .options(
                selectinload(Inventory.warehouse),
                selectinload(Inventory.sku).selectinload(ProductSku.product),
            )
            .where(Inventory.tenant_id == tenant_id, Inventory.id == inventory_id)
        )
        return self.session.scalars(stmt).first()

    def get_by_warehouse_and_sku(self, warehouse_id: int, sku_id: int) -> Inventory | None:
        tenant_id = self.ensure_tenant()
        stmt = select(Inventory).where(
            Inventory.tenant_id == tenant_id,
            Inventory.warehouse_id == warehouse_id,
            Inventory.sku_id == sku_id,
        )
        return self.session.scalars(stmt).first()

    def get_for_update(self, inventory_id: int) -> Inventory | None:
        """悲观锁：锁住本租户这一行库存，直到当前事务结束。

        两个管理员同时调整同一行时，后到的请求会等到前一个 commit/rollback，
        而不是各自按过期数字改，最后把 reserved > quantity。
        WHERE 必须带 tenant_id，不能只凭 id。
        """
        tenant_id = self.ensure_tenant()
        stmt = (
            select(Inventory)
            .where(Inventory.tenant_id == tenant_id, Inventory.id == inventory_id)
            .with_for_update()
        )
        return self.session.scalars(stmt).first()

    def get_by_warehouse_sku_for_update(
        self,
        warehouse_id: int,
        sku_id: int,
    ) -> Inventory | None:
        tenant_id = self.ensure_tenant()
        stmt = (
            select(Inventory)
            .where(
                Inventory.tenant_id == tenant_id,
                Inventory.warehouse_id == warehouse_id,
                Inventory.sku_id == sku_id,
            )
            .with_for_update()
        )
        return self.session.scalars(stmt).first()

    def list_page(
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
    ) -> tuple[list[tuple[Inventory, ProductSku, Product, Warehouse]], int]:
        """库存列表一次 JOIN 仓库/SKU/SPU，避免循环里再查名称（N+1）。

        execute().all() 得到元组；scalars() 只会丢掉后面的列，这里不能用。
        """
        tenant_id = self.ensure_tenant()
        filters = [Inventory.tenant_id == tenant_id]
        if warehouse_id:
            filters.append(Inventory.warehouse_id == warehouse_id)
        if sku_code:
            filters.append(ProductSku.sku_code.like(f"%{sku_code}%"))
        if category_id:
            filters.append(Product.category_id == category_id)
        if brand_id:
            filters.append(Product.brand_id == brand_id)
        if q:
            pattern = f"%{q}%"
            filters.append(
                or_(
                    Product.name.like(pattern),
                    ProductSku.name.like(pattern),
                    ProductSku.sku_code.like(pattern),
                )
            )
        if stock_status == "ZERO":
            filters.append(Inventory.quantity == 0)
        elif stock_status == "IN_STOCK":
            filters.append(Inventory.quantity > 0)
        elif stock_status == "LOW":
            # 低库存：还有可用量，但不超过阈值。零库存走 ZERO，不混在低库存里。
            available = Inventory.quantity - Inventory.reserved_quantity
            filters.append(available > 0)
            filters.append(available <= threshold)

        from_clause = (
            Inventory.__table__.join(
                ProductSku.__table__,
                and_(
                    ProductSku.tenant_id == Inventory.tenant_id,
                    ProductSku.id == Inventory.sku_id,
                ),
            )
            .join(
                Product.__table__,
                and_(
                    Product.tenant_id == Inventory.tenant_id,
                    Product.id == ProductSku.product_id,
                ),
            )
            .join(
                Warehouse.__table__,
                and_(
                    Warehouse.tenant_id == Inventory.tenant_id,
                    Warehouse.id == Inventory.warehouse_id,
                ),
            )
        )
        count_stmt = select(func.count(Inventory.id)).select_from(from_clause).where(*filters)
        total = int(self.session.scalar(count_stmt) or 0)
        stmt = (
            select(Inventory, ProductSku, Product, Warehouse)
            .join(
                ProductSku,
                and_(
                    ProductSku.tenant_id == Inventory.tenant_id,
                    ProductSku.id == Inventory.sku_id,
                ),
            )
            .join(
                Product,
                and_(
                    Product.tenant_id == Inventory.tenant_id,
                    Product.id == ProductSku.product_id,
                ),
            )
            .join(
                Warehouse,
                and_(
                    Warehouse.tenant_id == Inventory.tenant_id,
                    Warehouse.id == Inventory.warehouse_id,
                ),
            )
            .where(*filters)
            .order_by(Inventory.updated_at.desc(), Inventory.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        rows = list(self.session.execute(stmt).all())
        return [(row[0], row[1], row[2], row[3]) for row in rows], total

    def count_by_warehouse(self, warehouse_id: int) -> int:
        tenant_id = self.ensure_tenant()
        stmt = select(func.count(Inventory.id)).where(
            Inventory.tenant_id == tenant_id,
            Inventory.warehouse_id == warehouse_id,
        )
        return int(self.session.scalar(stmt) or 0)

    def list_by_warehouse_skus(self, warehouse_id: int, sku_ids: list[int]) -> list[Inventory]:
        """一次取出某仓库下多个 SKU 的库存，给订单确认前的可用量检查，避免逐行查询。"""
        if not sku_ids:
            return []
        tenant_id = self.ensure_tenant()
        stmt = select(Inventory).where(
            Inventory.tenant_id == tenant_id,
            Inventory.warehouse_id == warehouse_id,
            Inventory.sku_id.in_(list(dict.fromkeys(sku_ids))),
        )
        return list(self.session.scalars(stmt).all())

    def list_in_warehouse(
        self,
        warehouse_id: int,
        sku_ids: list[int] | None = None,
    ) -> list[Inventory]:
        """盘点创建时按仓库取库存行。只读快照，不加锁。"""
        tenant_id = self.ensure_tenant()
        filters = [
            Inventory.tenant_id == tenant_id,
            Inventory.warehouse_id == warehouse_id,
        ]
        if sku_ids is not None:
            unique_ids = list(dict.fromkeys(sku_ids))
            if not unique_ids:
                return []
            filters.append(Inventory.sku_id.in_(unique_ids))
        stmt = (
            select(Inventory)
            .options(selectinload(Inventory.sku).selectinload(ProductSku.product))
            .where(*filters)
            .order_by(Inventory.sku_id.asc(), Inventory.id.asc())
        )
        return list(self.session.scalars(stmt).all())

    def count_by_sku(self, sku_id: int) -> int:
        tenant_id = self.ensure_tenant()
        stmt = select(func.count(Inventory.id)).where(
            Inventory.tenant_id == tenant_id,
            Inventory.sku_id == sku_id,
        )
        return int(self.session.scalar(stmt) or 0)

    def add(self, inventory: Inventory) -> Inventory:
        self.session.add(inventory)
        return inventory

    def _execute_update(self, stmt: Update) -> int:
        """执行 Core UPDATE 并返回影响行数。

        Session.execute 静态类型是 Result，没有 rowcount；UPDATE 实际是 CursorResult。
        tuple[()] 表示不取行，只用 rowcount。expire 是因为 Core UPDATE 不刷新 identity map。
        """
        result = cast(CursorResult[tuple[()]], self.session.execute(stmt))
        self.session.expire_all()
        return int(result.rowcount or 0)

    def reserve_if_available(self, *, warehouse_id: int, sku_id: int, quantity: int) -> int:
        """条件 UPDATE 预占。数据库在 SET 时用当前行的 quantity/reserved 判断可用量。

        两个请求同时预占时，不会都先读到 available=10 再各自加 reserved。
        只有满足 quantity - reserved >= qty 的那次 UPDATE 能改到 1 行。
        返回 rowcount：1 成功，0 表示没有行或不满足可用量。
        """
        tenant_id = self.ensure_tenant()
        stmt = (
            update(Inventory)
            .where(
                Inventory.tenant_id == tenant_id,
                Inventory.warehouse_id == warehouse_id,
                Inventory.sku_id == sku_id,
                Inventory.quantity - Inventory.reserved_quantity >= quantity,
            )
            .values(
                reserved_quantity=Inventory.reserved_quantity + quantity,
                version=Inventory.version + 1,
                updated_at=func.now(),
            )
        )
        return self._execute_update(stmt)

    def release_if_reserved(self, *, warehouse_id: int, sku_id: int, quantity: int) -> int:
        """条件释放：reserved 不够时 rowcount=0，不会减成负数。"""
        tenant_id = self.ensure_tenant()
        stmt = (
            update(Inventory)
            .where(
                Inventory.tenant_id == tenant_id,
                Inventory.warehouse_id == warehouse_id,
                Inventory.sku_id == sku_id,
                Inventory.reserved_quantity >= quantity,
            )
            .values(
                reserved_quantity=Inventory.reserved_quantity - quantity,
                version=Inventory.version + 1,
                updated_at=func.now(),
            )
        )
        return self._execute_update(stmt)

    def deduct_if_reserved(self, *, warehouse_id: int, sku_id: int, quantity: int) -> int:
        """出库确认：实际库存和预占同时减少。不能只减 quantity 留下 reserved。"""
        tenant_id = self.ensure_tenant()
        stmt = (
            update(Inventory)
            .where(
                Inventory.tenant_id == tenant_id,
                Inventory.warehouse_id == warehouse_id,
                Inventory.sku_id == sku_id,
                Inventory.reserved_quantity >= quantity,
                Inventory.quantity >= quantity,
            )
            .values(
                quantity=Inventory.quantity - quantity,
                reserved_quantity=Inventory.reserved_quantity - quantity,
                version=Inventory.version + 1,
                updated_at=func.now(),
            )
        )
        return self._execute_update(stmt)

    def subtract_available_if_enough(
        self,
        *,
        warehouse_id: int,
        sku_id: int,
        quantity: int,
    ) -> int:
        """调拨调出：只减 quantity，不改 reserved。

        WHERE 用当前行的 available = quantity - reserved 判断。两个调拨单
        同时从同一仓扣同一 SKU 时，不会都先读到 available=100 再各自减 80。
        reserved 不动：销售订单预占不属于调拨领域。
        """
        tenant_id = self.ensure_tenant()
        stmt = (
            update(Inventory)
            .where(
                Inventory.tenant_id == tenant_id,
                Inventory.warehouse_id == warehouse_id,
                Inventory.sku_id == sku_id,
                Inventory.quantity - Inventory.reserved_quantity >= quantity,
            )
            .values(
                quantity=Inventory.quantity - quantity,
                version=Inventory.version + 1,
                updated_at=func.now(),
            )
        )
        return self._execute_update(stmt)

    def add_quantity(self, *, warehouse_id: int, sku_id: int, quantity: int) -> int:
        """采购入库 / 调拨调入：只增加 quantity，不改 reserved。

        入库的货还没被订单占住，所以可用量跟着实际库存一起增加。
        """
        tenant_id = self.ensure_tenant()
        stmt = (
            update(Inventory)
            .where(
                Inventory.tenant_id == tenant_id,
                Inventory.warehouse_id == warehouse_id,
                Inventory.sku_id == sku_id,
            )
            .values(
                quantity=Inventory.quantity + quantity,
                version=Inventory.version + 1,
                updated_at=func.now(),
            )
        )
        return self._execute_update(stmt)

    def update_quantity_if_version(
        self,
        *,
        inventory_id: int,
        expected_version: int,
        new_quantity: int,
    ) -> int:
        """乐观锁：WHERE version = 旧值。期间被别人改过则 rowcount=0。

        不和 SELECT FOR UPDATE 混用。正式调整走悲观锁；本方法只演示冲突。
        """
        tenant_id = self.ensure_tenant()
        stmt = (
            update(Inventory)
            .where(
                Inventory.tenant_id == tenant_id,
                Inventory.id == inventory_id,
                Inventory.version == expected_version,
            )
            .values(
                quantity=new_quantity,
                version=Inventory.version + 1,
                updated_at=func.now(),
            )
        )
        return self._execute_update(stmt)


class InventoryTransactionRepository(BaseRepository):
    def __init__(self, session: Session, tenant_id: int) -> None:
        super().__init__(session, tenant_id)

    def add(self, row: InventoryTransaction) -> InventoryTransaction:
        self.session.add(row)
        return row

    def list_for_inventory(
        self,
        inventory_id: int,
        *,
        limit: int = 20,
    ) -> list[tuple[InventoryTransaction, str | None]]:
        """详情最近流水。OUTER JOIN 操作人姓名，避免详情页操作人一直为空。"""
        tenant_id = self.ensure_tenant()
        stmt = (
            select(InventoryTransaction, User.display_name)
            .outerjoin(User, User.id == InventoryTransaction.operator_user_id)
            .where(
                InventoryTransaction.tenant_id == tenant_id,
                InventoryTransaction.inventory_id == inventory_id,
            )
            .order_by(InventoryTransaction.created_at.desc(), InventoryTransaction.id.desc())
            .limit(limit)
        )
        return [(row[0], row[1]) for row in self.session.execute(stmt).all()]

    def list_page(
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
    ) -> tuple[list[tuple[InventoryTransaction, Warehouse, ProductSku, Product, str | None]], int]:
        """流水列表 JOIN 仓库/SKU/商品/操作人姓名，避免循环查库。"""
        tenant_id = self.ensure_tenant()
        filters = [InventoryTransaction.tenant_id == tenant_id]
        if inventory_id:
            filters.append(InventoryTransaction.inventory_id == inventory_id)
        if warehouse_id:
            filters.append(InventoryTransaction.warehouse_id == warehouse_id)
        if sku_id:
            filters.append(InventoryTransaction.sku_id == sku_id)
        if tx_type:
            filters.append(InventoryTransaction.type == tx_type)
        if created_from is not None:
            filters.append(InventoryTransaction.created_at >= created_from)
        if created_to is not None:
            filters.append(InventoryTransaction.created_at <= created_to)

        count_stmt = select(func.count(InventoryTransaction.id)).where(*filters)
        total = int(self.session.scalar(count_stmt) or 0)
        stmt = (
            select(InventoryTransaction, Warehouse, ProductSku, Product, User.display_name)
            .join(
                Warehouse,
                and_(
                    Warehouse.tenant_id == InventoryTransaction.tenant_id,
                    Warehouse.id == InventoryTransaction.warehouse_id,
                ),
            )
            .join(
                ProductSku,
                and_(
                    ProductSku.tenant_id == InventoryTransaction.tenant_id,
                    ProductSku.id == InventoryTransaction.sku_id,
                ),
            )
            .join(
                Product,
                and_(
                    Product.tenant_id == InventoryTransaction.tenant_id,
                    Product.id == ProductSku.product_id,
                ),
            )
            .outerjoin(User, User.id == InventoryTransaction.operator_user_id)
            .where(*filters)
            .order_by(
                InventoryTransaction.created_at.desc(),
                InventoryTransaction.id.desc(),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        rows = list(self.session.execute(stmt).all())
        return [(row[0], row[1], row[2], row[3], row[4]) for row in rows], total


def search_skus(
    repo: ProductSkuRepository,
    *,
    q: str | None,
    page: int,
    page_size: int,
) -> tuple[list[ProductSku], int]:
    """SKU 远程搜索。不要一次拉全表，初始化库存下拉用。"""
    tenant_id = repo.ensure_tenant()
    filters = [ProductSku.tenant_id == tenant_id]
    if q:
        pattern = f"%{q}%"
        filters.append(
            or_(
                ProductSku.sku_code.like(pattern),
                ProductSku.name.like(pattern),
                Product.name.like(pattern),
            )
        )
    count_stmt = (
        select(func.count(ProductSku.id))
        .select_from(ProductSku)
        .join(
            Product,
            and_(Product.tenant_id == ProductSku.tenant_id, Product.id == ProductSku.product_id),
        )
        .where(*filters)
    )
    total = int(repo.session.scalar(count_stmt) or 0)
    stmt = (
        select(ProductSku)
        .options(selectinload(ProductSku.product))
        .join(
            Product,
            and_(Product.tenant_id == ProductSku.tenant_id, Product.id == ProductSku.product_id),
        )
        .where(*filters)
        .order_by(ProductSku.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return list(repo.session.scalars(stmt).all()), total

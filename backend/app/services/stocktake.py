"""库存盘点。创建只拍账面快照；确认时按差异调整当前库存，并与流水同一事务。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.core.permissions import PermissionCode
from app.core.tenant import TenantContext
from app.models.inventory import InventoryTransactionType
from app.models.stocktake import (
    STOCKTAKE_REFERENCE,
    StocktakeItem,
    StocktakeOrder,
    StocktakeOrderStatus,
    StocktakeScope,
)
from app.models.user import User
from app.models.warehouse import Warehouse, WarehouseStatus
from app.repositories.inventory import InventoryRepository
from app.repositories.product import ProductSkuRepository
from app.repositories.stocktake import StocktakeRepository
from app.repositories.warehouse import WarehouseRepository
from app.schemas.stocktake import (
    StocktakeCreate,
    StocktakeItemBatchIn,
    StocktakeItemOut,
    StocktakeItemPatch,
    StocktakeItemsSave,
    StocktakeListItem,
    StocktakeListOut,
    StocktakeOut,
    StocktakeUpdate,
)
from app.services.authorization import AuthorizationService
from app.services.inventory import InventoryService

_UNAVAILABLE = "盘点单不存在或不可访问"
_COUNTING = StocktakeOrderStatus.COUNTING.value
_PENDING = StocktakeOrderStatus.PENDING_CONFIRMATION.value
_CONFIRMED = StocktakeOrderStatus.CONFIRMED.value
_CANCELLED = StocktakeOrderStatus.CANCELLED.value
_DRAFT = StocktakeOrderStatus.DRAFT.value
_EDITABLE = {_DRAFT, _COUNTING}
_CANCELLABLE = {_DRAFT, _COUNTING, _PENDING}


class StocktakeService:
    def __init__(self, session: Session, context: TenantContext) -> None:
        self.session = session
        self.context = context
        self.auth = AuthorizationService(session)
        self.stocktakes = StocktakeRepository(session, context.tenant_id)
        self.inventories = InventoryRepository(session, context.tenant_id)
        self.warehouses = WarehouseRepository(session, context.tenant_id)
        self.skus = ProductSkuRepository(session, context.tenant_id)
        self.inventory = InventoryService(session, context)

    def list_stocktakes(
        self,
        *,
        q: str | None,
        warehouse_id: int | None,
        status: str | None,
        created_from: datetime | None,
        created_to: datetime | None,
        page: int,
        page_size: int,
    ) -> StocktakeListOut:
        self.auth.require_all(self.context, (PermissionCode.STOCKTAKE_READ,))
        if status and status not in {item.value for item in StocktakeOrderStatus}:
            raise AppError("盘点状态不合法", code=40200, status_code=400)
        rows, total = self.stocktakes.list_page(
            q=(q or "").strip() or None,
            warehouse_id=warehouse_id,
            status=status,
            created_from=created_from,
            created_to=created_to,
            page=page,
            page_size=page_size,
        )
        return StocktakeListOut(
            items=[
                StocktakeListItem(
                    id=order.id,
                    stocktake_no=order.stocktake_no or "",
                    warehouse_id=order.warehouse_id,
                    warehouse_name=warehouse_name,
                    scope=order.scope,
                    status=order.status,
                    sku_count=int(sku_count),
                    difference_sku_count=int(diff_count),
                    created_by_name=creator_name,
                    created_at=order.created_at,
                )
                for order, warehouse_name, creator_name, sku_count, diff_count in rows
            ],
            total=total,
            page=page,
            page_size=page_size,
        )

    def get_stocktake(self, stocktake_id: int) -> StocktakeOut:
        self.auth.require_all(self.context, (PermissionCode.STOCKTAKE_READ,))
        order = self.stocktakes.get_in_tenant(stocktake_id)
        if order is None:
            raise AppError(_UNAVAILABLE, code=40492, status_code=404)
        return self._out(order)

    def create_stocktake(self, payload: StocktakeCreate) -> StocktakeOut:
        """创建盘点任务。只保存当时账面快照，不锁库存、不改 Inventory。

        创建后直接进入 COUNTING。盘点可能持续几小时，不能用 SELECT FOR UPDATE
        一直占着库存行等人填数。确认时才短事务加锁。
        """
        self.auth.require_all(self.context, (PermissionCode.STOCKTAKE_CREATE,))
        try:
            warehouse = self._require_active_warehouse(payload.warehouse_id)
            scope = self._normalize_scope(payload.scope)
            inventories = self._target_inventories(warehouse.id, scope, payload.sku_ids)
            order = StocktakeOrder(
                tenant_id=self.context.tenant_id,
                warehouse_id=warehouse.id,
                status=_COUNTING,
                scope=scope,
                remark=payload.remark,
                created_by=self.context.user_id,
            )
            self.stocktakes.add(order)
            self.session.flush()
            order.stocktake_no = f"ST{datetime.now().year}{order.id:06d}"
            for inventory in inventories:
                self.stocktakes.add_item(
                    StocktakeItem(
                        tenant_id=self.context.tenant_id,
                        stocktake_order_id=order.id,
                        inventory_id=inventory.id,
                        sku_id=inventory.sku_id,
                        system_quantity=inventory.quantity,
                        system_reserved_quantity=inventory.reserved_quantity,
                    )
                )
            self.session.commit()
        except AppError:
            self.session.rollback()
            raise
        except Exception:
            self.session.rollback()
            raise
        created = self.stocktakes.get_in_tenant(order.id)
        if created is None:
            raise AppError(_UNAVAILABLE, code=40492, status_code=404)
        return self._out(created)

    def update_stocktake(self, stocktake_id: int, payload: StocktakeUpdate) -> StocktakeOut:
        self.auth.require_all(self.context, (PermissionCode.STOCKTAKE_UPDATE,))
        try:
            order = self.stocktakes.get_for_update(stocktake_id)
            if order is None:
                raise AppError(_UNAVAILABLE, code=40492, status_code=404)
            if order.status not in _EDITABLE:
                raise AppError(
                    "当前状态不能修改盘点任务",
                    code=40201,
                    status_code=400,
                    data={"error": "STOCKTAKE_NOT_EDITABLE"},
                )
            order.remark = payload.remark
            self.session.commit()
        except AppError:
            self.session.rollback()
            raise
        except Exception:
            self.session.rollback()
            raise
        return self.get_stocktake(stocktake_id)

    def update_item(
        self,
        stocktake_id: int,
        item_id: int,
        payload: StocktakeItemPatch,
    ) -> StocktakeOut:
        self.auth.require_all(self.context, (PermissionCode.STOCKTAKE_UPDATE,))
        try:
            order = self.stocktakes.get_for_update(stocktake_id)
            if order is None:
                raise AppError(_UNAVAILABLE, code=40492, status_code=404)
            if order.status != _COUNTING:
                raise AppError(
                    "只有盘点中的任务可以填写实盘数量",
                    code=40201,
                    status_code=400,
                    data={"error": "STOCKTAKE_NOT_EDITABLE"},
                )
            item = self.stocktakes.get_item(stocktake_id, item_id)
            if item is None:
                raise AppError("盘点明细不存在或不可访问", code=40492, status_code=404)
            item.counted_quantity = payload.counted_quantity
            item.difference_quantity = payload.counted_quantity - item.system_quantity
            item.remark = payload.remark
            self.session.commit()
        except AppError:
            self.session.rollback()
            raise
        except Exception:
            self.session.rollback()
            raise
        return self.get_stocktake(stocktake_id)

    def save_items(self, stocktake_id: int, payload: StocktakeItemsSave) -> StocktakeOut:
        """批量保存实盘数量。一次事务写完，页面一次提交几十行时用这个接口。"""
        self.auth.require_all(self.context, (PermissionCode.STOCKTAKE_UPDATE,))
        try:
            order = self.stocktakes.get_for_update(stocktake_id)
            if order is None:
                raise AppError(_UNAVAILABLE, code=40492, status_code=404)
            if order.status != _COUNTING:
                raise AppError(
                    "只有盘点中的任务可以填写实盘数量",
                    code=40201,
                    status_code=400,
                    data={"error": "STOCKTAKE_NOT_EDITABLE"},
                )
            items = {row.id: row for row in self.stocktakes.list_items(stocktake_id)}
            self._apply_counts(items, payload.items)
            self.session.commit()
        except AppError:
            self.session.rollback()
            raise
        except Exception:
            self.session.rollback()
            raise
        return self.get_stocktake(stocktake_id)

    def submit_stocktake(self, stocktake_id: int) -> StocktakeOut:
        self.auth.require_all(self.context, (PermissionCode.STOCKTAKE_SUBMIT,))
        try:
            order = self.stocktakes.get_for_update(stocktake_id)
            if order is None:
                raise AppError(_UNAVAILABLE, code=40492, status_code=404)
            if order.status == _PENDING:
                raise AppError(
                    "盘点单已经提交",
                    code=40200,
                    status_code=400,
                    data={"error": "STOCKTAKE_ALREADY_SUBMITTED"},
                )
            if order.status != _COUNTING:
                raise AppError(
                    "只有盘点中的任务可以提交",
                    code=40200,
                    status_code=400,
                    data={"error": "INVALID_STOCKTAKE_STATUS"},
                )
            items = self.stocktakes.list_items(stocktake_id)
            missing = [row.id for row in items if row.counted_quantity is None]
            if missing:
                raise AppError(
                    "还有盘点明细未填写实盘数量，不能提交",
                    code=40202,
                    status_code=400,
                    data={"error": "STOCKTAKE_ITEMS_INCOMPLETE", "item_ids": missing},
                )
            order.status = _PENDING
            order.submitted_at = datetime.now()
            self.session.commit()
        except AppError:
            self.session.rollback()
            raise
        except Exception:
            self.session.rollback()
            raise
        return self.get_stocktake(stocktake_id)

    def confirm_stocktake(self, stocktake_id: int) -> StocktakeOut:
        """确认盘点：按差异调整当前库存，而不是把库存覆盖成实盘数。

        功能：PENDING_CONFIRMATION → CONFIRMED，写 STOCKTAKE_ADJUSTMENT 流水。
        参数：盘点单 id。调用方需要 stocktake:confirm。
        返回：已确认的盘点单。
        异常：
        - 已经确认：拒绝，不再次调整（幂等）
        - 任一条调整后低于 reserved：整单回滚
        核心流程：
        1. SELECT FOR UPDATE 锁盘点单。
        2. 明细按 sku_id / inventory_id 稳定排序后再锁库存，降低死锁概率。
        3. 当前 quantity + difference_quantity。盘点期间的入库/出库会保留。
        4. 改库存、写流水、改盘点状态在同一事务。任一失败全部 rollback。
        为什么不能 Inventory.quantity = counted：创建时账面 100，期间采购入库 20，
        实盘 98。覆盖成 98 会把正常入库抹掉；应按差异 -2，得到 118。
        为什么确认前不能一直锁库存：仓库人员可能盘几小时。数据库行锁只能用于短事务。
        """
        self.auth.require_all(self.context, (PermissionCode.STOCKTAKE_CONFIRM,))
        try:
            order = self.stocktakes.get_for_update(stocktake_id)
            if order is None:
                raise AppError(_UNAVAILABLE, code=40492, status_code=404)
            if order.status == _CONFIRMED:
                raise AppError(
                    "盘点单已经确认，不能重复调整库存",
                    code=40203,
                    status_code=400,
                    data={"error": "STOCKTAKE_ALREADY_CONFIRMED"},
                )
            if order.status != _PENDING:
                raise AppError(
                    "只有待确认的盘点单可以审核",
                    code=40200,
                    status_code=400,
                    data={"error": "INVALID_STOCKTAKE_STATUS"},
                )
            self._require_active_warehouse(order.warehouse_id)
            items = self.stocktakes.list_items(stocktake_id)
            if not items:
                raise AppError("盘点单没有明细", code=40207, status_code=400)
            # 统一加锁顺序可以降低多个事务互相等待形成死锁的概率。
            items = sorted(items, key=lambda row: (row.sku_id, row.inventory_id, row.id))
            stocktake_no = order.stocktake_no or str(order.id)
            for item in items:
                if item.counted_quantity is None or item.difference_quantity is None:
                    raise AppError(
                        "还有盘点明细未填写实盘数量，不能确认",
                        code=40202,
                        status_code=400,
                        data={"error": "STOCKTAKE_ITEMS_INCOMPLETE"},
                    )
                self.inventory.apply_delta_within_transaction(
                    inventory_id=item.inventory_id,
                    change_quantity=item.difference_quantity,
                    tx_type=InventoryTransactionType.STOCKTAKE_ADJUSTMENT.value,
                    reference_type=STOCKTAKE_REFERENCE,
                    reference_id=stocktake_id,
                    remark=f"盘点 {stocktake_no} 差异调整",
                )
            locked = self.stocktakes.get_for_update(stocktake_id)
            if locked is None or locked.status != _PENDING:
                raise AppError(
                    "盘点单状态已变化，请刷新后重试",
                    code=40200,
                    status_code=400,
                    data={"error": "INVALID_STOCKTAKE_STATUS"},
                )
            locked.status = _CONFIRMED
            locked.confirmed_at = datetime.now()
            locked.confirmed_by = self.context.user_id
            self.session.commit()
        except AppError:
            self.session.rollback()
            raise
        except Exception:
            self.session.rollback()
            raise
        return self.get_stocktake(stocktake_id)

    def cancel_stocktake(self, stocktake_id: int) -> StocktakeOut:
        self.auth.require_all(self.context, (PermissionCode.STOCKTAKE_CANCEL,))
        try:
            order = self.stocktakes.get_for_update(stocktake_id)
            if order is None:
                raise AppError(_UNAVAILABLE, code=40492, status_code=404)
            if order.status == _CONFIRMED:
                raise AppError(
                    "已确认的盘点单不能取消",
                    code=40206,
                    status_code=400,
                    data={"error": "STOCKTAKE_CANNOT_CANCEL"},
                )
            if order.status == _CANCELLED:
                raise AppError(
                    "盘点单已经取消",
                    code=40206,
                    status_code=400,
                    data={"error": "STOCKTAKE_ALREADY_CANCELLED"},
                )
            if order.status not in _CANCELLABLE:
                raise AppError(
                    "当前状态不能取消盘点",
                    code=40206,
                    status_code=400,
                    data={"error": "STOCKTAKE_CANNOT_CANCEL"},
                )
            order.status = _CANCELLED
            order.cancelled_at = datetime.now()
            order.cancelled_by = self.context.user_id
            self.session.commit()
        except AppError:
            self.session.rollback()
            raise
        except Exception:
            self.session.rollback()
            raise
        return self.get_stocktake(stocktake_id)

    def _target_inventories(
        self,
        warehouse_id: int,
        scope: str,
        sku_ids: list[int],
    ) -> list:
        if scope == StocktakeScope.ALL.value:
            rows = self.inventories.list_in_warehouse(warehouse_id)
            if not rows:
                raise AppError(
                    "该仓库没有可盘点库存",
                    code=40207,
                    status_code=400,
                    data={"error": "STOCKTAKE_EMPTY"},
                )
            return rows
        if not sku_ids:
            raise AppError(
                "指定 SKU 盘点必须选择至少一个 SKU",
                code=40208,
                status_code=400,
                data={"error": "STOCKTAKE_SKU_REQUIRED"},
            )
        for sku_id in sku_ids:
            sku = self.skus.get_by_id_in_tenant(sku_id)
            if sku is None:
                raise AppError("SKU 不存在或不可访问", code=40433, status_code=404)
        rows = self.inventories.list_in_warehouse(warehouse_id, sku_ids)
        found = {row.sku_id for row in rows}
        missing = [sku_id for sku_id in sku_ids if sku_id not in found]
        if missing:
            raise AppError(
                "指定 SKU 在该仓库没有库存，无法盘点",
                code=40209,
                status_code=400,
                data={"error": "STOCKTAKE_SKU_NOT_INITIALIZED", "sku_ids": missing},
            )
        return rows

    def _require_active_warehouse(self, warehouse_id: int) -> Warehouse:
        warehouse = self.warehouses.get_in_tenant(warehouse_id)
        if warehouse is None:
            raise AppError("仓库不存在或不可访问", code=40440, status_code=404)
        if warehouse.status != WarehouseStatus.ACTIVE.value:
            raise AppError("只能对启用中的仓库做盘点", code=40097, status_code=400)
        return warehouse

    @staticmethod
    def _normalize_scope(value: str) -> str:
        if value not in {item.value for item in StocktakeScope}:
            raise AppError("盘点范围不合法", code=40208, status_code=400)
        return value

    def _apply_counts(
        self,
        items: dict[int, StocktakeItem],
        payload: list[StocktakeItemBatchIn],
    ) -> None:
        for row in payload:
            item = items.get(row.item_id)
            if item is None:
                raise AppError("盘点明细不存在或不可访问", code=40492, status_code=404)
            item.counted_quantity = row.counted_quantity
            item.difference_quantity = row.counted_quantity - item.system_quantity
            item.remark = row.remark

    def _user_name(self, user_id: int | None) -> str | None:
        if user_id is None:
            return None
        return self.session.scalar(select(User.display_name).where(User.id == user_id))

    def _out(self, order: StocktakeOrder) -> StocktakeOut:
        items = sorted(order.items, key=lambda row: (row.sku_id, row.id))
        counted = sum(1 for row in items if row.counted_quantity is not None)
        diff = sum(
            1
            for row in items
            if row.counted_quantity is not None and row.difference_quantity not in (None, 0)
        )
        warehouse_name = order.warehouse.name if order.warehouse is not None else ""
        return StocktakeOut(
            id=order.id,
            stocktake_no=order.stocktake_no or "",
            warehouse_id=order.warehouse_id,
            warehouse_name=warehouse_name,
            status=order.status,
            scope=order.scope,
            remark=order.remark,
            sku_count=len(items),
            counted_sku_count=counted,
            difference_sku_count=diff,
            created_by=order.created_by,
            created_by_name=self._user_name(order.created_by),
            submitted_at=order.submitted_at,
            confirmed_at=order.confirmed_at,
            confirmed_by=order.confirmed_by,
            confirmed_by_name=self._user_name(order.confirmed_by),
            cancelled_at=order.cancelled_at,
            cancelled_by=order.cancelled_by,
            created_at=order.created_at,
            updated_at=order.updated_at,
            items=[self._item_out(row) for row in items],
        )

    @staticmethod
    def _item_out(item: StocktakeItem) -> StocktakeItemOut:
        sku = item.sku
        product = sku.product if sku is not None else None
        spec = sku.spec_values if sku is not None and sku.spec_values else {}
        return StocktakeItemOut(
            id=item.id,
            inventory_id=item.inventory_id,
            sku_id=item.sku_id,
            sku_code=(sku.sku_code or "") if sku is not None else "",
            sku_name=sku.name if sku is not None else "",
            product_name=product.name if product is not None else "",
            spec_values=spec if isinstance(spec, dict) else {},
            system_quantity=item.system_quantity,
            system_reserved_quantity=item.system_reserved_quantity,
            system_available_quantity=item.system_quantity - item.system_reserved_quantity,
            counted_quantity=item.counted_quantity,
            difference_quantity=item.difference_quantity,
            remark=item.remark,
        )

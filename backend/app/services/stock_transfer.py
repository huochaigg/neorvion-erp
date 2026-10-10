"""库存调拨。草稿和提交不改库存；调出扣源仓，调入加目标仓，中间是在途。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.core.permissions import PermissionCode
from app.core.tenant import TenantContext
from app.models.inventory import InventoryTransactionType
from app.models.stock_transfer import (
    STOCK_TRANSFER_REFERENCE,
    StockTransfer,
    StockTransferItem,
    StockTransferStatus,
)
from app.models.user import User
from app.models.warehouse import Warehouse, WarehouseStatus
from app.repositories.inventory import InventoryRepository
from app.repositories.product import ProductSkuRepository
from app.repositories.stock_transfer import StockTransferRepository
from app.repositories.warehouse import WarehouseRepository
from app.schemas.stock_transfer import (
    StockTransferCreate,
    StockTransferItemIn,
    StockTransferItemOut,
    StockTransferListItem,
    StockTransferListOut,
    StockTransferOut,
    StockTransferUpdate,
)
from app.services.authorization import AuthorizationService
from app.services.inventory import InventoryService

_UNAVAILABLE = "调拨单不存在或不可访问"
_DRAFT = StockTransferStatus.DRAFT.value
_PENDING = StockTransferStatus.PENDING_OUTBOUND.value
_IN_TRANSIT = StockTransferStatus.IN_TRANSIT.value
_COMPLETED = StockTransferStatus.COMPLETED.value
_CANCELLED = StockTransferStatus.CANCELLED.value
_CANCELLABLE = {_DRAFT, _PENDING}


class StockTransferService:
    def __init__(self, session: Session, context: TenantContext) -> None:
        self.session = session
        self.context = context
        self.auth = AuthorizationService(session)
        self.transfers = StockTransferRepository(session, context.tenant_id)
        self.inventories = InventoryRepository(session, context.tenant_id)
        self.warehouses = WarehouseRepository(session, context.tenant_id)
        self.skus = ProductSkuRepository(session, context.tenant_id)
        self.inventory = InventoryService(session, context)

    def list_transfers(
        self,
        *,
        q: str | None,
        source_warehouse_id: int | None,
        target_warehouse_id: int | None,
        status: str | None,
        created_from: datetime | None,
        created_to: datetime | None,
        page: int,
        page_size: int,
    ) -> StockTransferListOut:
        self.auth.require_all(self.context, (PermissionCode.STOCK_TRANSFER_READ,))
        if status and status not in {item.value for item in StockTransferStatus}:
            raise AppError("调拨状态不合法", code=40227, status_code=400)
        rows, total = self.transfers.list_page(
            q=(q or "").strip() or None,
            source_warehouse_id=source_warehouse_id,
            target_warehouse_id=target_warehouse_id,
            status=status,
            created_from=created_from,
            created_to=created_to,
            page=page,
            page_size=page_size,
        )
        return StockTransferListOut(
            items=[
                StockTransferListItem(
                    id=transfer.id,
                    transfer_no=transfer.transfer_no or "",
                    source_warehouse_id=transfer.source_warehouse_id,
                    source_warehouse_name=source_name,
                    target_warehouse_id=transfer.target_warehouse_id,
                    target_warehouse_name=target_name,
                    status=transfer.status,
                    sku_count=int(sku_count),
                    total_quantity=int(total_qty),
                    created_by_name=creator_name,
                    created_at=transfer.created_at,
                )
                for (
                    transfer,
                    source_name,
                    target_name,
                    creator_name,
                    sku_count,
                    total_qty,
                ) in rows
            ],
            total=total,
            page=page,
            page_size=page_size,
        )

    def get_transfer(self, transfer_id: int) -> StockTransferOut:
        self.auth.require_all(self.context, (PermissionCode.STOCK_TRANSFER_READ,))
        transfer = self.transfers.get_in_tenant(transfer_id)
        if transfer is None:
            raise AppError(_UNAVAILABLE, code=40493, status_code=404)
        return self._out(transfer)

    def create_transfer(self, payload: StockTransferCreate) -> StockTransferOut:
        """创建调拨草稿。不改库存。库存不足也可以先保存，真正校验在确认调出。"""
        self.auth.require_all(self.context, (PermissionCode.STOCK_TRANSFER_CREATE,))
        try:
            source, target = self._require_warehouses(
                payload.source_warehouse_id,
                payload.target_warehouse_id,
            )
            lines = self._plan_lines(payload.items)
            transfer = StockTransfer(
                tenant_id=self.context.tenant_id,
                source_warehouse_id=source.id,
                target_warehouse_id=target.id,
                status=_DRAFT,
                remark=payload.remark,
                created_by=self.context.user_id,
            )
            self.transfers.add(transfer)
            self.session.flush()
            transfer.transfer_no = f"TR{datetime.now().year}{transfer.id:06d}"
            self._insert_items(transfer.id, lines)
            self.session.commit()
        except AppError:
            self.session.rollback()
            raise
        except Exception:
            self.session.rollback()
            raise
        created = self.transfers.get_in_tenant(transfer.id)
        if created is None:
            raise AppError(_UNAVAILABLE, code=40493, status_code=404)
        return self._out(created)

    def update_transfer(self, transfer_id: int, payload: StockTransferUpdate) -> StockTransferOut:
        self.auth.require_all(self.context, (PermissionCode.STOCK_TRANSFER_UPDATE,))
        try:
            transfer = self.transfers.get_for_update(transfer_id)
            if transfer is None:
                raise AppError(_UNAVAILABLE, code=40493, status_code=404)
            if transfer.status != _DRAFT:
                raise AppError(
                    "只有草稿调拨单可以修改仓库和明细",
                    code=40221,
                    status_code=400,
                    data={"error": "STOCK_TRANSFER_NOT_EDITABLE"},
                )
            source, target = self._require_warehouses(
                payload.source_warehouse_id,
                payload.target_warehouse_id,
            )
            lines = self._plan_lines(payload.items)
            self.transfers.delete_items(transfer.id)
            self.session.flush()
            transfer.source_warehouse_id = source.id
            transfer.target_warehouse_id = target.id
            transfer.remark = payload.remark
            self._insert_items(transfer.id, lines)
            self.session.commit()
        except AppError:
            self.session.rollback()
            raise
        except Exception:
            self.session.rollback()
            raise
        return self.get_transfer(transfer_id)

    def submit_transfer(self, transfer_id: int) -> StockTransferOut:
        """提交调拨：DRAFT → PENDING_OUTBOUND。仍然不改库存。"""
        self.auth.require_all(self.context, (PermissionCode.STOCK_TRANSFER_SUBMIT,))
        try:
            transfer = self.transfers.get_for_update(transfer_id)
            if transfer is None:
                raise AppError(_UNAVAILABLE, code=40493, status_code=404)
            if transfer.status == _PENDING:
                raise AppError(
                    "调拨单已经提交",
                    code=40227,
                    status_code=400,
                    data={"error": "STOCK_TRANSFER_ALREADY_SUBMITTED"},
                )
            if transfer.status != _DRAFT:
                raise AppError(
                    "只有草稿调拨单可以提交",
                    code=40227,
                    status_code=400,
                    data={"error": "INVALID_STOCK_TRANSFER_STATUS"},
                )
            self._require_warehouses(transfer.source_warehouse_id, transfer.target_warehouse_id)
            items = self.transfers.list_items(transfer_id)
            if not items:
                raise AppError(
                    "提交前至少需要一条调拨明细",
                    code=40222,
                    status_code=400,
                    data={"error": "STOCK_TRANSFER_EMPTY"},
                )
            for item in items:
                sku = self.skus.get_by_id_in_tenant(item.sku_id)
                if sku is None:
                    raise AppError("SKU 不存在或不可访问", code=40433, status_code=404)
            transfer.status = _PENDING
            transfer.submitted_at = datetime.now()
            self.session.commit()
        except AppError:
            self.session.rollback()
            raise
        except Exception:
            self.session.rollback()
            raise
        return self.get_transfer(transfer_id)

    def confirm_outbound(self, transfer_id: int) -> StockTransferOut:
        """确认调出：从源仓扣减 available，目标仓此时不增加。

        功能：PENDING_OUTBOUND → IN_TRANSIT，写 TRANSFER_OUT 流水。
        参数：调拨单 id。调用方需要 stock_transfer:outbound。
        返回：在途调拨单。
        异常：
        - 已经调出：拒绝，不再次扣减（幂等）
        - 任一 SKU 可用不足：整单 rollback
        核心流程：
        1. 锁调拨单。
        2. 明细按 sku_id 稳定排序后再扣库存，降低死锁概率。
        3. 调用 InventoryService.deduct_available_within_transaction。
           它只减 quantity，不改 reserved。
        4. 源仓库存、流水、调拨状态同一事务提交。
        为什么调出和调入拆开：深圳仓今天发货，广州仓可能明天才收到。
        调出后货物在途，不属于任一仓库存。第一版用 IN_TRANSIT + outbound_quantity
        表示在途，不另建 inventory_in_transit 表。
        为什么只能扣 available：账面 100、预占 80 时，那 80 已经卖给销售订单。
        """
        self.auth.require_all(self.context, (PermissionCode.STOCK_TRANSFER_OUTBOUND,))
        try:
            transfer = self.transfers.get_for_update(transfer_id)
            if transfer is None:
                raise AppError(_UNAVAILABLE, code=40493, status_code=404)
            if transfer.status == _IN_TRANSIT or transfer.status == _COMPLETED:
                raise AppError(
                    "调拨单已经调出，不能重复扣减源仓库存",
                    code=40224,
                    status_code=400,
                    data={"error": "STOCK_TRANSFER_ALREADY_OUTBOUND"},
                )
            if transfer.status != _PENDING:
                raise AppError(
                    "只有待调出的调拨单可以确认调出",
                    code=40227,
                    status_code=400,
                    data={"error": "INVALID_STOCK_TRANSFER_STATUS"},
                )
            self._require_warehouses(transfer.source_warehouse_id, transfer.target_warehouse_id)
            items = self.transfers.list_items(transfer_id)
            if not items:
                raise AppError("调拨单没有明细", code=40222, status_code=400)
            # 先抄成普通数据。库存条件 UPDATE 会 expire_all，不能靠未提交的 ORM 对象继续改。
            # 统一按 sku_id 排序后再扣库存，降低多个事务互相等待形成死锁的概率。
            plan = sorted(
                [
                    (
                        item.id,
                        item.sku_id,
                        item.quantity,
                        item.sku.sku_code if item.sku is not None else None,
                    )
                    for item in items
                ],
                key=lambda row: (row[1], row[0]),
            )
            transfer_no = transfer.transfer_no or str(transfer.id)
            source_id = transfer.source_warehouse_id
            for _item_id, sku_id, qty, sku_code in plan:
                self.inventory.deduct_available_within_transaction(
                    warehouse_id=source_id,
                    sku_id=sku_id,
                    quantity=qty,
                    sku_code=sku_code,
                    reference_type=STOCK_TRANSFER_REFERENCE,
                    reference_id=transfer_id,
                    remark=f"调拨 {transfer_no} 调出",
                    tx_type=InventoryTransactionType.TRANSFER_OUT.value,
                )
            locked = self.transfers.get_for_update(transfer_id)
            if locked is None or locked.status != _PENDING:
                raise AppError(
                    "调拨单状态已变化，请刷新后重试",
                    code=40227,
                    status_code=400,
                    data={"error": "INVALID_STOCK_TRANSFER_STATUS"},
                )
            qty_by_id = {item_id: qty for item_id, _sku_id, qty, _code in plan}
            for item in self.transfers.list_items(transfer_id):
                item.outbound_quantity = qty_by_id[item.id]
            locked.status = _IN_TRANSIT
            locked.outbound_at = datetime.now()
            locked.outbound_by = self.context.user_id
            self.session.commit()
        except AppError:
            self.session.rollback()
            raise
        except Exception:
            self.session.rollback()
            raise
        return self.get_transfer(transfer_id)

    def confirm_receive(self, transfer_id: int) -> StockTransferOut:
        """确认调入：把在途数量加到目标仓。目标仓没有该 SKU 时安全创建库存行。

        功能：IN_TRANSIT → COMPLETED，写 TRANSFER_IN 流水。
        参数：调拨单 id。调用方需要 stock_transfer:receive。
        返回：已完成的调拨单。
        异常：已经收货则拒绝，不再次增加（幂等）。
        核心流程：
        1. 锁调拨单。
        2. 明细按 sku_id 稳定排序。
        3. 复用 inbound_within_transaction：目标仓没有行就先插入 0 再加数量。
           并发首次创建撞 UNIQUE 时只回滚保存点。
        4. reserved 不变。调拨不能给目标仓增加销售预占。
        第一版 received_quantity 等于 outbound_quantity，暂不处理运输损耗。
        """
        self.auth.require_all(self.context, (PermissionCode.STOCK_TRANSFER_RECEIVE,))
        try:
            transfer = self.transfers.get_for_update(transfer_id)
            if transfer is None:
                raise AppError(_UNAVAILABLE, code=40493, status_code=404)
            if transfer.status == _COMPLETED:
                raise AppError(
                    "调拨单已经收货，不能重复增加目标仓库存",
                    code=40225,
                    status_code=400,
                    data={"error": "STOCK_TRANSFER_ALREADY_RECEIVED"},
                )
            if transfer.status != _IN_TRANSIT:
                raise AppError(
                    "只有在途调拨单可以确认调入",
                    code=40227,
                    status_code=400,
                    data={"error": "INVALID_STOCK_TRANSFER_STATUS"},
                )
            self._require_warehouses(transfer.source_warehouse_id, transfer.target_warehouse_id)
            items = self.transfers.list_items(transfer_id)
            if not items:
                raise AppError("调拨单没有明细", code=40222, status_code=400)
            plan = sorted(
                [(item.id, item.sku_id, item.outbound_quantity) for item in items],
                key=lambda row: (row[1], row[0]),
            )
            transfer_no = transfer.transfer_no or str(transfer.id)
            target_id = transfer.target_warehouse_id
            for _item_id, sku_id, qty in plan:
                if qty <= 0:
                    raise AppError("在途数量无效，不能确认调入", code=40227, status_code=400)
                self.inventory.inbound_within_transaction(
                    warehouse_id=target_id,
                    sku_id=sku_id,
                    quantity=qty,
                    reference_type=STOCK_TRANSFER_REFERENCE,
                    reference_id=transfer_id,
                    remark=f"调拨 {transfer_no} 调入",
                    tx_type=InventoryTransactionType.TRANSFER_IN.value,
                )
            locked = self.transfers.get_for_update(transfer_id)
            if locked is None or locked.status != _IN_TRANSIT:
                raise AppError(
                    "调拨单状态已变化，请刷新后重试",
                    code=40227,
                    status_code=400,
                    data={"error": "INVALID_STOCK_TRANSFER_STATUS"},
                )
            qty_by_id = {item_id: qty for item_id, _sku_id, qty in plan}
            for item in self.transfers.list_items(transfer_id):
                item.received_quantity = qty_by_id[item.id]
            locked.status = _COMPLETED
            locked.received_at = datetime.now()
            locked.received_by = self.context.user_id
            self.session.commit()
        except AppError:
            self.session.rollback()
            raise
        except Exception:
            self.session.rollback()
            raise
        return self.get_transfer(transfer_id)

    def cancel_transfer(self, transfer_id: int) -> StockTransferOut:
        self.auth.require_all(self.context, (PermissionCode.STOCK_TRANSFER_CANCEL,))
        try:
            transfer = self.transfers.get_for_update(transfer_id)
            if transfer is None:
                raise AppError(_UNAVAILABLE, code=40493, status_code=404)
            if transfer.status == _IN_TRANSIT:
                raise AppError(
                    "在途调拨单不能普通取消，货物已离开源仓。如需撤回请创建反向调拨",
                    code=40226,
                    status_code=400,
                    data={"error": "STOCK_TRANSFER_CANNOT_CANCEL"},
                )
            if transfer.status == _COMPLETED:
                raise AppError(
                    "已完成的调拨单不能取消",
                    code=40226,
                    status_code=400,
                    data={"error": "STOCK_TRANSFER_CANNOT_CANCEL"},
                )
            if transfer.status == _CANCELLED:
                raise AppError(
                    "调拨单已经取消",
                    code=40226,
                    status_code=400,
                    data={"error": "STOCK_TRANSFER_ALREADY_CANCELLED"},
                )
            if transfer.status not in _CANCELLABLE:
                raise AppError(
                    "当前状态不能取消调拨",
                    code=40226,
                    status_code=400,
                    data={"error": "STOCK_TRANSFER_CANNOT_CANCEL"},
                )
            transfer.status = _CANCELLED
            transfer.cancelled_at = datetime.now()
            transfer.cancelled_by = self.context.user_id
            self.session.commit()
        except AppError:
            self.session.rollback()
            raise
        except Exception:
            self.session.rollback()
            raise
        return self.get_transfer(transfer_id)

    def _require_warehouses(self, source_id: int, target_id: int) -> tuple[Warehouse, Warehouse]:
        if source_id == target_id:
            raise AppError(
                "调出仓和调入仓不能相同",
                code=40220,
                status_code=400,
                data={"error": "STOCK_TRANSFER_SAME_WAREHOUSE"},
            )
        source = self._require_active_warehouse(source_id)
        target = self._require_active_warehouse(target_id)
        return source, target

    def _require_active_warehouse(self, warehouse_id: int) -> Warehouse:
        warehouse = self.warehouses.get_in_tenant(warehouse_id)
        if warehouse is None:
            raise AppError("仓库不存在或不可访问", code=40440, status_code=404)
        if warehouse.status != WarehouseStatus.ACTIVE.value:
            raise AppError("只能使用启用中的仓库调拨", code=40097, status_code=400)
        return warehouse

    def _plan_lines(self, items: list[StockTransferItemIn]) -> list[tuple[int, int]]:
        lines: list[tuple[int, int]] = []
        for row in items:
            sku = self.skus.get_by_id_in_tenant(row.sku_id)
            if sku is None:
                raise AppError("SKU 不存在或不可访问", code=40433, status_code=404)
            lines.append((sku.id, row.quantity))
        return lines

    def _insert_items(self, transfer_id: int, lines: list[tuple[int, int]]) -> None:
        for sku_id, quantity in lines:
            self.transfers.add_item(
                StockTransferItem(
                    tenant_id=self.context.tenant_id,
                    stock_transfer_id=transfer_id,
                    sku_id=sku_id,
                    quantity=quantity,
                    outbound_quantity=0,
                    received_quantity=0,
                )
            )

    def _user_name(self, user_id: int | None) -> str | None:
        if user_id is None:
            return None
        return self.session.scalar(select(User.display_name).where(User.id == user_id))

    def _out(self, transfer: StockTransfer) -> StockTransferOut:
        items = sorted(transfer.items, key=lambda row: (row.sku_id, row.id))
        source_name = (
            transfer.source_warehouse.name if transfer.source_warehouse is not None else ""
        )
        target_name = (
            transfer.target_warehouse.name if transfer.target_warehouse is not None else ""
        )
        stock_map = {
            row.sku_id: row
            for row in self.inventories.list_by_warehouse_skus(
                transfer.source_warehouse_id,
                [item.sku_id for item in items],
            )
        }
        return StockTransferOut(
            id=transfer.id,
            transfer_no=transfer.transfer_no or "",
            source_warehouse_id=transfer.source_warehouse_id,
            source_warehouse_name=source_name,
            target_warehouse_id=transfer.target_warehouse_id,
            target_warehouse_name=target_name,
            status=transfer.status,
            remark=transfer.remark,
            sku_count=len(items),
            total_quantity=sum(item.quantity for item in items),
            created_by=transfer.created_by,
            created_by_name=self._user_name(transfer.created_by),
            submitted_at=transfer.submitted_at,
            outbound_at=transfer.outbound_at,
            outbound_by=transfer.outbound_by,
            outbound_by_name=self._user_name(transfer.outbound_by),
            received_at=transfer.received_at,
            received_by=transfer.received_by,
            received_by_name=self._user_name(transfer.received_by),
            cancelled_at=transfer.cancelled_at,
            cancelled_by=transfer.cancelled_by,
            created_at=transfer.created_at,
            updated_at=transfer.updated_at,
            items=[self._item_out(item, stock_map.get(item.sku_id)) for item in items],
        )

    @staticmethod
    def _item_out(item: StockTransferItem, inventory) -> StockTransferItemOut:
        sku = item.sku
        product = sku.product if sku is not None else None
        spec = sku.spec_values if sku is not None and sku.spec_values else {}
        qty = inventory.quantity if inventory is not None else None
        reserved = inventory.reserved_quantity if inventory is not None else None
        available = (qty - reserved) if qty is not None and reserved is not None else None
        return StockTransferItemOut(
            id=item.id,
            sku_id=item.sku_id,
            sku_code=(sku.sku_code or "") if sku is not None else "",
            sku_name=sku.name if sku is not None else "",
            product_name=product.name if product is not None else "",
            spec_values=spec if isinstance(spec, dict) else {},
            quantity=item.quantity,
            outbound_quantity=item.outbound_quantity,
            received_quantity=item.received_quantity,
            source_quantity=qty,
            source_reserved_quantity=reserved,
            source_available_quantity=available,
        )

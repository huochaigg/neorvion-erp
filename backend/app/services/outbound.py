"""销售出库。拣货不扣库存；确认出库才同时减少 quantity 和 reserved。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.core.permissions import PermissionCode
from app.core.tenant import TenantContext
from app.models.outbound import (
    OUTBOUND_ORDER_REFERENCE,
    OutboundOrder,
    OutboundOrderItem,
    OutboundOrderStatus,
    OutboundPick,
    OutboundPickLine,
)
from app.models.sales_order import SalesOrderItem
from app.models.user import User
from app.repositories.outbound import OutboundOrderRepository
from app.repositories.sales_order import SalesOrderRepository
from app.repositories.shipment import ShipmentRepository
from app.schemas.outbound import (
    OutboundCreate,
    OutboundItemIn,
    OutboundItemOut,
    OutboundListItem,
    OutboundListOut,
    OutboundOrderOut,
    OutboundPickLineOut,
    OutboundPickOut,
)
from app.schemas.outbound import (
    OutboundPick as OutboundPickPayload,
)
from app.services.authorization import AuthorizationService
from app.services.inventory import InventoryService
from app.services.sales_order_state import (
    OUTBOUNDABLE_STATUSES,
    apply_fulfillment_status,
)

_UNAVAILABLE = "出库单不存在或不可访问"
_PENDING = OutboundOrderStatus.PENDING_PICKING.value
_FULFILLABLE = OUTBOUNDABLE_STATUSES
_PICKED = OutboundOrderStatus.PICKED.value
_CONFIRMED = OutboundOrderStatus.CONFIRMED.value
_CANCELLED = OutboundOrderStatus.CANCELLED.value


class OutboundOrderService:
    def __init__(self, session: Session, context: TenantContext) -> None:
        self.session = session
        self.context = context
        self.auth = AuthorizationService(session)
        self.outbounds = OutboundOrderRepository(session, context.tenant_id)
        self.orders = SalesOrderRepository(session, context.tenant_id)
        self.shipments = ShipmentRepository(session, context.tenant_id)
        self.inventory = InventoryService(session, context)

    def list_outbounds(
        self,
        *,
        q: str | None,
        sales_order_id: int | None,
        warehouse_id: int | None,
        status: str | None,
        created_from: datetime | None,
        created_to: datetime | None,
        page: int,
        page_size: int,
    ) -> OutboundListOut:
        self.auth.require_all(self.context, (PermissionCode.OUTBOUND_READ,))
        rows, total = self.outbounds.list_page(
            q=q,
            sales_order_id=sales_order_id,
            warehouse_id=warehouse_id,
            status=status,
            created_from=created_from,
            created_to=created_to,
            page=page,
            page_size=page_size,
        )
        items = [
            OutboundListItem(
                id=order.id,
                outbound_no=order.outbound_no or "",
                sales_order_id=order.sales_order_id,
                sales_order_no=order_no or "",
                customer_name=customer_name,
                warehouse_name=warehouse_name,
                status=order.status,
                sku_count=int(sku_count),
                planned_quantity=int(planned),
                picked_quantity=int(picked),
                outbound_quantity=int(shipped),
                created_at=order.created_at,
            )
            for (
                order,
                order_no,
                customer_name,
                warehouse_name,
                sku_count,
                planned,
                picked,
                shipped,
            ) in rows
        ]
        return OutboundListOut(items=items, total=total, page=page, page_size=page_size)

    def get_outbound(self, outbound_id: int) -> OutboundOrderOut:
        self.auth.require_all(self.context, (PermissionCode.OUTBOUND_READ,))
        order = self.outbounds.get_in_tenant(outbound_id)
        if order is None:
            raise AppError(_UNAVAILABLE, code=40481, status_code=404)
        return self._out(order)

    def create_outbound(self, payload: OutboundCreate) -> OutboundOrderOut:
        """按剩余预占生成出库任务。不修改库存。"""
        self.auth.require_all(self.context, (PermissionCode.OUTBOUND_CREATE,))
        try:
            created_id = self._create_for_order(
                payload.sales_order_id,
                payload.remark,
                payload.items,
            )
            self.session.commit()
        except AppError:
            self.session.rollback()
            raise
        except Exception:
            self.session.rollback()
            raise
        created = self.outbounds.get_in_tenant(created_id)
        if created is None:
            raise AppError(_UNAVAILABLE, code=40481, status_code=404)
        return self._out(created)

    def attach_initial(self, sales_order_id: int) -> None:
        """订单确认成功后自动生成第一张出库单。调用方已经持有事务，这里不 commit。

        历史待出库订单如果没有出库单，走 create_outbound，不在迁移里批量生成。
        """
        if self.outbounds.has_active(sales_order_id):
            return
        self._create_for_order(sales_order_id, None, None)

    def confirm_picking(self, outbound_id: int, payload: OutboundPickPayload) -> OutboundOrderOut:
        """记录一次拣货。库存不变，累计数量留给确认出库使用。

        功能：把本次拣到的数量追加到出库明细，并写一条不能改的拣货记录。
        参数：出库单 id；items 里的 picked_quantity 是本次增量，不是新的累计总数；
        finish 为真时结束拣货。不传 finish 时默认结束，和原来点一次「确认拣货」一致。
        返回：带拣货记录的出库单。
        异常：不是待拣货；本次超过剩余计划；结束时仍有明细一次都没拣。
        核心流程：
        1. 锁出库单。已拣货、已出库、已取消都不能再拣，避免把历史累计改掉。
        2. 按本次数量增加 picked_quantity，同时记下拣前、本次、拣后。
        3. 每一行都拣满，或调用方明确结束，状态才变成 PICKED。
        4. 否则保持待拣货，所以可以先拣 3 再拣 2，两次都留在记录里。

        为什么不把累计直接改成最后一次的数字：计划 5、先拣 3 再拣 2 时，
        明细上最终仍是 5，但 3 和 2 分别是两次仓库动作。确认出库继续读累计，不读记录。
        """
        self.auth.require_all(self.context, (PermissionCode.OUTBOUND_PICK,))
        try:
            order = self.outbounds.get_for_update(outbound_id)
            if order is None:
                raise AppError(_UNAVAILABLE, code=40481, status_code=404)
            if order.status != _PENDING:
                raise AppError(
                    "只有待拣货的出库单可以继续拣货",
                    code=40143,
                    status_code=400,
                    data={"error": "OUTBOUND_NOT_PICKABLE"},
                )
            rows = {row.id: row for row in self.outbounds.list_items(outbound_id)}
            seen: set[int] = set()
            changes: list[tuple[OutboundOrderItem, int]] = []
            for item in payload.items:
                if item.id in seen:
                    raise AppError("拣货明细重复", code=40148, status_code=400)
                seen.add(item.id)
                row = rows.get(item.id)
                if row is None:
                    raise AppError("拣货明细不存在", code=40148, status_code=400)
                remaining = row.planned_quantity - row.picked_quantity
                if item.picked_quantity > remaining:
                    raise AppError(
                        "本次拣货不能超过剩余计划数量",
                        code=40148,
                        status_code=400,
                        data={"error": "OUTBOUND_PICK_EXCEEDS_PLAN"},
                    )
                changes.append((row, item.picked_quantity))
            if not changes and not payload.finish:
                raise AppError("请填写本次拣货数量", code=40148, status_code=400)
            now = datetime.now()
            if changes:
                pick = OutboundPick(
                    tenant_id=self.context.tenant_id,
                    outbound_order_id=order.id,
                    picked_at=now,
                    picked_by=self.context.user_id,
                )
                self.session.add(pick)
                self.session.flush()
                for row, qty in changes:
                    before = row.picked_quantity
                    after = before + qty
                    row.picked_quantity = after
                    self.session.add(
                        OutboundPickLine(
                            tenant_id=self.context.tenant_id,
                            pick_id=pick.id,
                            outbound_order_item_id=row.id,
                            sku_id=row.sku_id,
                            quantity=qty,
                            picked_before=before,
                            picked_after=after,
                        )
                    )
                order.picked_at = now
                order.picked_by = self.context.user_id
            filled = all(row.picked_quantity == row.planned_quantity for row in rows.values())
            ready = all(row.picked_quantity > 0 for row in rows.values())
            if payload.finish and not ready:
                raise AppError(
                    "结束拣货前，每条明细至少要拣过一次",
                    code=40148,
                    status_code=400,
                )
            if filled or payload.finish:
                order.status = _PICKED
                order.picked_at = order.picked_at or now
                order.picked_by = order.picked_by or self.context.user_id
            self.session.commit()
        except AppError:
            self.session.rollback()
            raise
        except Exception:
            self.session.rollback()
            raise
        updated = self.outbounds.get_in_tenant(outbound_id)
        if updated is None:
            raise AppError(_UNAVAILABLE, code=40481, status_code=404)
        return self._out(updated)

    def confirm_outbound(self, outbound_id: int) -> OutboundOrderOut:
        """确认出库：quantity 和 reserved 同时减少，并推进销售订单状态。

        功能：已拣货的出库单正式离库。
        参数：出库单 id。权限 outbound:confirm。
        返回：已确认的出库单。
        异常：重复确认不再扣库存；预占不够；销售明细剩余预占不够。任一 SKU 失败整单回滚。
        核心流程：
        1. SELECT FOR UPDATE 锁出库单。已确认直接拒绝。
        2. 锁销售订单和明细，明细按 sku_id 升序。
        3. 确认每个 SKU 的订单预占不少于本次出库数量。
        4. 按同一顺序调用 deduct_within_transaction。它复用 V5 条件 UPDATE，
           同时减少 quantity 和 reserved，不自己 commit。
        5. 增加 shipped，减少订单 reserved，更新订单状态。
        6. 一次 commit。

        为什么可用量通常不变：出库前 available = quantity - reserved。
        两边减去同一个数，差值不变。这批货出库前已经被预占，不算可售。
        为什么按 sku_id 排序：两张出库单交叉锁 SKU-A / SKU-B 会死锁。
        """
        self.auth.require_all(self.context, (PermissionCode.OUTBOUND_CONFIRM,))
        try:
            order = self.outbounds.get_for_update(outbound_id)
            if order is None:
                raise AppError(_UNAVAILABLE, code=40481, status_code=404)
            if order.status == _CONFIRMED:
                raise AppError(
                    "出库单已经确认，不能重复扣减库存",
                    code=40141,
                    status_code=400,
                    data={"error": "OUTBOUND_ALREADY_CONFIRMED"},
                )
            if order.status != _PICKED:
                raise AppError(
                    "请先确认拣货，再确认出库",
                    code=40140,
                    status_code=400,
                    data={"error": "INVALID_OUTBOUND_STATUS"},
                )
            sales = self.orders.get_for_update(order.sales_order_id)
            if sales is None or sales.status not in _FULFILLABLE:
                raise AppError(
                    "销售订单当前不能出库",
                    code=40144,
                    status_code=400,
                    data={"error": "SALES_ORDER_NOT_OUTBOUNDABLE"},
                )
            sales_items = {
                row.id: row for row in self.outbounds.list_sales_items_for_update(sales.id)
            }
            rows = self.outbounds.list_items(outbound_id)
            plan = sorted(
                [
                    (row.sku_id, row.sales_order_item_id, row.picked_quantity, row.id)
                    for row in rows
                ],
                key=lambda item: (item[0], item[3]),
            )
            outbound_no = order.outbound_no or str(order.id)
            warehouse_id = order.warehouse_id
            for sku_id, sales_item_id, qty, _item_id in plan:
                sales_item = sales_items.get(sales_item_id)
                if sales_item is None or qty > sales_item.reserved_quantity:
                    raise AppError(
                        "出库数量超过订单剩余预占",
                        code=40142,
                        status_code=400,
                        data={"error": "OUTBOUND_EXCEEDS_RESERVED", "sku_id": sku_id},
                    )
                held = sales_item.reserved_quantity + sales_item.outbound_quantity
                if held > sales_item.quantity:
                    raise AppError("订单数量关系不合法", code=40142, status_code=400)
            for sku_id, _sales_item_id, qty, _item_id in plan:
                self.inventory.deduct_within_transaction(
                    warehouse_id=warehouse_id,
                    sku_id=sku_id,
                    quantity=qty,
                    reference_type=OUTBOUND_ORDER_REFERENCE,
                    reference_id=outbound_id,
                    remark=f"销售出库 {outbound_no}",
                )
            locked = self.outbounds.get_for_update(outbound_id)
            if locked is None or locked.status != _PICKED:
                raise AppError(
                    "出库单状态已被其他人修改，请刷新后重试",
                    code=40141,
                    status_code=400,
                    data={"error": "OUTBOUND_ALREADY_CONFIRMED"},
                )
            fresh_sales_items = {
                row.id: row for row in self.outbounds.list_sales_items_for_update(sales.id)
            }
            item_rows = {row.id: row for row in self.outbounds.list_items(outbound_id)}
            for _sku_id, sales_item_id, qty, item_id in plan:
                sales_item = fresh_sales_items[sales_item_id]
                if qty > sales_item.reserved_quantity:
                    raise AppError(
                        "出库数量超过订单剩余预占",
                        code=40142,
                        status_code=400,
                        data={"error": "OUTBOUND_EXCEEDS_RESERVED"},
                    )
                sales_item.reserved_quantity -= qty
                sales_item.outbound_quantity += qty
                item_rows[item_id].outbound_quantity = qty
            locked.status = _CONFIRMED
            locked.confirmed_at = datetime.now()
            locked.confirmed_by = self.context.user_id
            fresh_sales = self.orders.get_for_update(sales.id)
            if fresh_sales is None:
                raise AppError("销售订单不存在或不可访问", code=40471, status_code=404)
            self._sync_sales_status(fresh_sales, list(fresh_sales_items.values()))
            self.session.commit()
        except AppError:
            self.session.rollback()
            raise
        except Exception:
            self.session.rollback()
            raise
        updated = self.outbounds.get_in_tenant(outbound_id)
        if updated is None:
            raise AppError(_UNAVAILABLE, code=40481, status_code=404)
        return self._out(updated)

    def cancel_outbound(self, outbound_id: int) -> OutboundOrderOut:
        """取消未出库的任务。已确认的不能取消，库存已经扣过。"""
        self.auth.require_all(self.context, (PermissionCode.OUTBOUND_CANCEL,))
        try:
            order = self.outbounds.get_for_update(outbound_id)
            if order is None:
                raise AppError(_UNAVAILABLE, code=40481, status_code=404)
            if order.status == _CANCELLED:
                raise AppError(
                    "出库单已经取消",
                    code=40146,
                    status_code=400,
                    data={"error": "OUTBOUND_ALREADY_CANCELLED"},
                )
            if order.status == _CONFIRMED:
                raise AppError(
                    "已出库的单据不能取消",
                    code=40146,
                    status_code=400,
                    data={"error": "OUTBOUND_ALREADY_CONFIRMED"},
                )
            order.status = _CANCELLED
            self.session.commit()
        except AppError:
            self.session.rollback()
            raise
        except Exception:
            self.session.rollback()
            raise
        updated = self.outbounds.get_in_tenant(outbound_id)
        if updated is None:
            raise AppError(_UNAVAILABLE, code=40481, status_code=404)
        return self._out(updated)

    def _create_for_order(
        self,
        sales_order_id: int,
        remark: str | None,
        items: list[OutboundItemIn] | None,
    ) -> int:
        sales = self.orders.get_for_update(sales_order_id)
        if sales is None:
            raise AppError("销售订单不存在或不可访问", code=40471, status_code=404)
        if sales.status not in _FULFILLABLE:
            raise AppError(
                "只有待出库或部分出库的订单可以生成出库单",
                code=40144,
                status_code=400,
                data={"error": "SALES_ORDER_NOT_OUTBOUNDABLE"},
            )
        sales_items = self.outbounds.list_sales_items_for_update(sales.id)
        occupied = self.outbounds.open_planned_by_item(sales.id)
        available = {
            item.id: item.reserved_quantity - occupied.get(item.id, 0) for item in sales_items
        }
        chosen = self._choose_lines(sales_items, available, items)
        outbound = OutboundOrder(
            tenant_id=self.context.tenant_id,
            sales_order_id=sales.id,
            warehouse_id=sales.warehouse_id,
            status=_PENDING,
            remark=remark,
            created_by=self.context.user_id,
        )
        self.outbounds.add(outbound)
        self.session.flush()
        outbound.outbound_no = f"OUT{datetime.now().year}{outbound.id:06d}"
        for sales_item, qty in chosen:
            self.session.add(
                OutboundOrderItem(
                    tenant_id=self.context.tenant_id,
                    outbound_order_id=outbound.id,
                    sales_order_item_id=sales_item.id,
                    sku_id=sales_item.sku_id,
                    planned_quantity=qty,
                    picked_quantity=0,
                    outbound_quantity=0,
                )
            )
        return outbound.id

    def _choose_lines(
        self,
        sales_items: list[SalesOrderItem],
        available: dict[int, int],
        items: list[OutboundItemIn] | None,
    ) -> list[tuple[SalesOrderItem, int]]:
        by_id = {item.id: item for item in sales_items}
        if items is None:
            chosen = [(item, available[item.id]) for item in sales_items if available[item.id] > 0]
        else:
            seen: set[int] = set()
            chosen = []
            for incoming in items:
                if incoming.sales_order_item_id in seen:
                    raise AppError("同一订单明细不能重复", code=40148, status_code=400)
                seen.add(incoming.sales_order_item_id)
                sales_item = by_id.get(incoming.sales_order_item_id)
                if sales_item is None:
                    raise AppError("销售明细不存在", code=40471, status_code=404)
                remain = available.get(sales_item.id, 0)
                if incoming.planned_quantity > remain:
                    raise AppError(
                        "计划出库超过剩余预占",
                        code=40142,
                        status_code=400,
                        data={"error": "OUTBOUND_EXCEEDS_RESERVED"},
                    )
                chosen.append((sales_item, incoming.planned_quantity))
        if not chosen:
            raise AppError(
                "没有剩余可出库数量",
                code=40144,
                status_code=400,
                data={"error": "SALES_ORDER_NOTHING_TO_SHIP"},
            )
        return chosen

    def _sync_sales_status(self, order, items: list[SalesOrderItem]) -> None:
        order.status = apply_fulfillment_status(order.status, items)

    def _out(self, order: OutboundOrder) -> OutboundOrderOut:
        sales = order.sales_order
        customer_name = ""
        if sales is not None and sales.customer is not None:
            customer_name = sales.customer.name
        warehouse_name = ""
        if sales is not None and sales.warehouse is not None:
            warehouse_name = sales.warehouse.name
        confirmed = self.shipments.allocated_by_outbound_item(order.id, confirmed_only=True)
        allocated = self.shipments.allocated_by_outbound_item(order.id, confirmed_only=False)
        return OutboundOrderOut(
            id=order.id,
            outbound_no=order.outbound_no or "",
            sales_order_id=order.sales_order_id,
            sales_order_no="" if sales is None or sales.order_no is None else sales.order_no,
            customer_name=customer_name,
            warehouse_id=order.warehouse_id,
            warehouse_name=warehouse_name,
            status=order.status,
            remark=order.remark,
            recipient_name=None if sales is None else sales.recipient_name,
            address=None if sales is None else sales.address,
            picked_at=order.picked_at,
            picked_by=order.picked_by,
            confirmed_at=order.confirmed_at,
            confirmed_by=order.confirmed_by,
            created_at=order.created_at,
            items=[
                self._item_out(
                    item,
                    shipped_quantity=confirmed.get(item.id, 0),
                    remaining_shippable_quantity=max(
                        item.outbound_quantity - allocated.get(item.id, 0),
                        0,
                    ),
                )
                for item in order.items
            ],
            picks=self.pick_outs(self.outbounds.list_picks(order.id)),
        )

    @staticmethod
    def _item_out(
        item: OutboundOrderItem,
        *,
        shipped_quantity: int = 0,
        remaining_shippable_quantity: int = 0,
    ) -> OutboundItemOut:
        sku = item.sku
        spec = {} if sku is None or sku.spec_values is None else sku.spec_values
        return OutboundItemOut(
            id=item.id,
            sales_order_item_id=item.sales_order_item_id,
            sku_id=item.sku_id,
            sku_code="" if sku is None or sku.sku_code is None else sku.sku_code,
            sku_name="" if sku is None else sku.name,
            product_name="" if sku is None or sku.product is None else sku.product.name,
            spec_values=spec if isinstance(spec, dict) else {},
            planned_quantity=item.planned_quantity,
            picked_quantity=item.picked_quantity,
            outbound_quantity=item.outbound_quantity,
            shipped_quantity=shipped_quantity,
            remaining_shippable_quantity=remaining_shippable_quantity,
        )

    def list_order_picks(self, sales_order_id: int) -> list[OutboundPickOut]:
        """订单详情读取拣货过程。调用方已经检查了订单读取权限。"""
        return self.pick_outs(self.outbounds.list_picks_for_sales_order(sales_order_id))

    def pick_outs(self, picks: list[OutboundPick]) -> list[OutboundPickOut]:
        user_ids = {pick.picked_by for pick in picks if pick.picked_by is not None}
        names: dict[int, str] = {}
        if user_ids:
            rows = self.session.execute(
                select(User.id, User.display_name).where(User.id.in_(user_ids))
            ).all()
            names = {row.id: row.display_name for row in rows}
        result: list[OutboundPickOut] = []
        for pick in picks:
            outbound = pick.outbound_order
            result.append(
                OutboundPickOut(
                    id=pick.id,
                    outbound_order_id=pick.outbound_order_id,
                    outbound_no=(
                        ""
                        if outbound is None or outbound.outbound_no is None
                        else outbound.outbound_no
                    ),
                    outbound_status="" if outbound is None else outbound.status,
                    picked_at=pick.picked_at,
                    picked_by=pick.picked_by,
                    picked_by_name=None if pick.picked_by is None else names.get(pick.picked_by),
                    lines=[self._pick_line_out(line) for line in pick.lines],
                )
            )
        return result

    @staticmethod
    def _pick_line_out(line: OutboundPickLine) -> OutboundPickLineOut:
        sku = line.sku
        return OutboundPickLineOut(
            id=line.id,
            outbound_order_item_id=line.outbound_order_item_id,
            sku_id=line.sku_id,
            sku_code="" if sku is None or sku.sku_code is None else sku.sku_code,
            sku_name="" if sku is None else sku.name,
            product_name="" if sku is None or sku.product is None else sku.product.name,
            quantity=line.quantity,
            picked_before=line.picked_before,
            picked_after=line.picked_after,
        )

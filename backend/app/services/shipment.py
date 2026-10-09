"""销售物流。确认发货不再扣库存，因为 V8 出库时已经扣过。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.core.permissions import PermissionCode
from app.core.tenant import TenantContext
from app.models.carrier import CarrierStatus
from app.models.outbound import OutboundOrderItem, OutboundOrderStatus
from app.models.sales_order import SalesOrderItem
from app.models.shipment import (
    Shipment,
    ShipmentItem,
    ShipmentStatus,
    ShipmentTrackingEvent,
    TrackingEventStatus,
)
from app.models.user import User
from app.repositories.carrier import CarrierRepository
from app.repositories.outbound import OutboundOrderRepository
from app.repositories.sales_order import SalesOrderRepository
from app.repositories.shipment import ShipmentRepository
from app.schemas.shipment import (
    ShipmentCreate,
    ShipmentDeliver,
    ShipmentItemIn,
    ShipmentItemOut,
    ShipmentListItem,
    ShipmentListOut,
    ShipmentOut,
    ShipmentUpdate,
    TrackingEventCreate,
    TrackingEventOut,
)
from app.services.authorization import AuthorizationService
from app.services.sales_order_state import apply_fulfillment_status

_UNAVAILABLE = "物流单不存在或不可访问"
_DRAFT = ShipmentStatus.DRAFT.value
_SHIPPED = ShipmentStatus.SHIPPED.value
_IN_TRANSIT = ShipmentStatus.IN_TRANSIT.value
_DELIVERED = ShipmentStatus.DELIVERED.value
_CANCELLED = ShipmentStatus.CANCELLED.value
_OUTBOUND_CONFIRMED = OutboundOrderStatus.CONFIRMED.value
_IN_TRANSIT_EVENTS = {
    TrackingEventStatus.PICKED_UP.value,
    TrackingEventStatus.IN_TRANSIT.value,
    TrackingEventStatus.ARRIVED_AT_HUB.value,
    TrackingEventStatus.OUT_FOR_DELIVERY.value,
}


class ShipmentService:
    def __init__(self, session: Session, context: TenantContext) -> None:
        self.session = session
        self.context = context
        self.auth = AuthorizationService(session)
        self.shipments = ShipmentRepository(session, context.tenant_id)
        self.outbounds = OutboundOrderRepository(session, context.tenant_id)
        self.orders = SalesOrderRepository(session, context.tenant_id)
        self.carriers = CarrierRepository(session, context.tenant_id)

    def list_shipments(self, **kwargs) -> ShipmentListOut:
        self.auth.require_all(self.context, (PermissionCode.SHIPMENT_READ,))
        rows, total = self.shipments.list_page(**kwargs)
        items = [
            ShipmentListItem(
                id=row.id,
                shipment_no=row.shipment_no or "",
                sales_order_id=row.sales_order_id,
                sales_order_no=order_no or "",
                outbound_order_id=row.outbound_order_id,
                outbound_no=outbound_no or "",
                customer_name=customer_name or "",
                carrier_name=carrier_name or "",
                tracking_no=row.tracking_no,
                status=row.status,
                sku_count=int(sku_count),
                total_quantity=int(total_qty),
                shipped_at=row.shipped_at,
                delivered_at=row.delivered_at,
                created_at=row.created_at,
            )
            for (
                row,
                order_no,
                outbound_no,
                customer_name,
                carrier_name,
                sku_count,
                total_qty,
            ) in rows
        ]
        return ShipmentListOut(
            items=items,
            total=total,
            page=kwargs["page"],
            page_size=kwargs["page_size"],
        )

    def get_shipment(self, shipment_id: int) -> ShipmentOut:
        self.auth.require_all(self.context, (PermissionCode.SHIPMENT_READ,))
        shipment = self.shipments.get_in_tenant(shipment_id)
        if shipment is None:
            raise AppError(_UNAVAILABLE, code=40491, status_code=404)
        return self._out(shipment)

    def create_shipment(self, payload: ShipmentCreate) -> ShipmentOut:
        """基于已确认出库单创建草稿物流单。此时不改库存、不推进销售发货状态。"""
        self.auth.require_all(self.context, (PermissionCode.SHIPMENT_CREATE,))
        try:
            created_id = self._create(payload)
            self.session.commit()
        except AppError:
            self.session.rollback()
            raise
        except IntegrityError:
            self.session.rollback()
            raise AppError(
                "运单号已存在",
                code=40971,
                status_code=409,
                data={"error": "TRACKING_NO_CONFLICT"},
            ) from None
        except Exception:
            self.session.rollback()
            raise
        return self.get_shipment(created_id)

    def update_shipment(self, shipment_id: int, payload: ShipmentUpdate) -> ShipmentOut:
        self.auth.require_all(self.context, (PermissionCode.SHIPMENT_UPDATE,))
        try:
            shipment = self.shipments.get_for_update(shipment_id)
            if shipment is None:
                raise AppError(_UNAVAILABLE, code=40491, status_code=404)
            if shipment.status != _DRAFT:
                raise AppError(
                    "只有草稿物流单可以修改",
                    code=40156,
                    status_code=400,
                    data={"error": "SHIPMENT_NOT_EDITABLE"},
                )
            if payload.carrier_id is not None:
                self._require_active_carrier(payload.carrier_id)
                shipment.carrier_id = payload.carrier_id
            if "tracking_no" in payload.model_fields_set:
                shipment.tracking_no = payload.tracking_no
            if "remark" in payload.model_fields_set:
                shipment.remark = payload.remark
            if payload.items is not None:
                self.shipments.delete_items(shipment.id)
                self._add_items(shipment, payload.items)
            self.session.commit()
        except AppError:
            self.session.rollback()
            raise
        except IntegrityError:
            self.session.rollback()
            raise AppError(
                "运单号已存在",
                code=40971,
                status_code=409,
                data={"error": "TRACKING_NO_CONFLICT"},
            ) from None
        except Exception:
            self.session.rollback()
            raise
        return self.get_shipment(shipment_id)

    def confirm_shipment(self, shipment_id: int) -> ShipmentOut:
        """确认发货：把已出库的货交给承运商。

        功能：草稿物流单变成已发货，累加销售明细 shipped_quantity。
        参数：物流单 id。权限 shipment:confirm。
        返回：已发货的物流单。
        异常：重复确认不再累计；没有运单号；物流商已禁用；超过出库剩余可发。
        核心流程：
        1. SELECT FOR UPDATE 锁物流单，避免同一张单确认两次。
        2. 必须仍是 DRAFT，且 tracking_no、启用中的承运商、至少一条明细都在。
        3. 锁出库明细，按 sku_id 升序，和别的物流单使用同一把顺序。
        4. 重新计算已经 SHIPPED / IN_TRANSIT / DELIVERED 的数量，再判断本次会不会超发。
        5. 增加 SalesOrderItem.shipped_quantity，更新销售订单发货状态。
        6. 一次 commit。不调用 InventoryService。

        为什么发货不再扣库存：出库确认时 quantity 和 reserved 已经一起减少。
        如果这里再减一次，账面会少一倍。发货只表示货交给了快递员。
        """
        self.auth.require_all(self.context, (PermissionCode.SHIPMENT_CONFIRM,))
        try:
            shipment = self.shipments.get_for_update(shipment_id)
            if shipment is None:
                raise AppError(_UNAVAILABLE, code=40491, status_code=404)
            if shipment.status == _SHIPPED or shipment.status == _IN_TRANSIT:
                raise AppError(
                    "物流单已经发货，不能重复确认",
                    code=40151,
                    status_code=400,
                    data={"error": "SHIPMENT_ALREADY_CONFIRMED"},
                )
            if shipment.status == _DELIVERED:
                raise AppError(
                    "物流单已经签收",
                    code=40155,
                    status_code=400,
                    data={"error": "SHIPMENT_ALREADY_DELIVERED"},
                )
            if shipment.status != _DRAFT:
                raise AppError(
                    "只有草稿物流单可以确认发货",
                    code=40150,
                    status_code=400,
                    data={"error": "INVALID_SHIPMENT_STATUS"},
                )
            if not (shipment.tracking_no or "").strip():
                raise AppError(
                    "确认发货前必须填写运单号",
                    code=40153,
                    status_code=400,
                    data={"error": "SHIPMENT_TRACKING_REQUIRED"},
                )
            self._require_active_carrier(shipment.carrier_id)
            lines = self.shipments.list_items(shipment.id)
            if not lines:
                raise AppError("物流单没有发货明细", code=40150, status_code=400)
            outbound = self.outbounds.get_for_update(shipment.outbound_order_id)
            if outbound is None or outbound.status != _OUTBOUND_CONFIRMED:
                raise AppError("出库单当前不能发货", code=40150, status_code=400)
            ob_items = {
                row.id: row for row in self.shipments.list_outbound_items_for_update(outbound.id)
            }
            # 只统计已经正式发货的数量。草稿占用在创建时拦过，确认时以锁后的实发为准。
            confirmed = self.shipments.allocated_by_outbound_item(
                outbound.id,
                confirmed_only=True,
                exclude_shipment_id=shipment.id,
            )
            plan = sorted(
                [
                    (
                        line.sku_id,
                        line.outbound_order_item_id,
                        line.sales_order_item_id,
                        line.quantity,
                    )
                    for line in lines
                ],
                key=lambda item: (item[0], item[1]),
            )
            for sku_id, ob_item_id, _sales_item_id, qty in plan:
                ob_item = ob_items.get(ob_item_id)
                already = confirmed.get(ob_item_id, 0)
                remain = 0 if ob_item is None else ob_item.outbound_quantity - already
                if ob_item is None or qty > remain:
                    raise AppError(
                        "本次发货超过出库剩余数量",
                        code=40152,
                        status_code=400,
                        data={
                            "error": "SHIPMENT_EXCEEDS_OUTBOUND",
                            "sku_id": sku_id,
                            "requested_quantity": qty,
                            "remaining_quantity": remain,
                        },
                    )
            sales = self.orders.get_for_update(shipment.sales_order_id)
            if sales is None:
                raise AppError("销售订单不存在或不可访问", code=40471, status_code=404)
            sales_items = {
                row.id: row for row in self.outbounds.list_sales_items_for_update(sales.id)
            }
            for _sku_id, _ob_item_id, sales_item_id, qty in plan:
                sales_item = sales_items.get(sales_item_id)
                if sales_item is None:
                    raise AppError("销售明细不存在", code=40152, status_code=400)
                if sales_item.shipped_quantity + qty > sales_item.outbound_quantity:
                    raise AppError(
                        "发货数量不能超过已出库数量",
                        code=40152,
                        status_code=400,
                        data={"error": "SHIPMENT_EXCEEDS_OUTBOUND"},
                    )
                sales_item.shipped_quantity += qty
            locked = self.shipments.get_for_update(shipment_id)
            if locked is None or locked.status != _DRAFT:
                raise AppError(
                    "物流单状态已被其他人修改，请刷新后重试",
                    code=40151,
                    status_code=400,
                    data={"error": "SHIPMENT_ALREADY_CONFIRMED"},
                )
            locked.status = _SHIPPED
            locked.shipped_at = datetime.now()
            locked.shipped_by = self.context.user_id
            self._sync_sales(sales, list(sales_items.values()), all_delivered=False)
            self.session.commit()
        except AppError:
            self.session.rollback()
            raise
        except Exception:
            self.session.rollback()
            raise
        return self.get_shipment(shipment_id)

    def cancel_shipment(self, shipment_id: int) -> ShipmentOut:
        self.auth.require_all(self.context, (PermissionCode.SHIPMENT_CANCEL,))
        try:
            shipment = self.shipments.get_for_update(shipment_id)
            if shipment is None:
                raise AppError(_UNAVAILABLE, code=40491, status_code=404)
            if shipment.status == _CANCELLED:
                raise AppError(
                    "物流单已经取消",
                    code=40154,
                    status_code=400,
                    data={"error": "SHIPMENT_ALREADY_CANCELLED"},
                )
            if shipment.status != _DRAFT:
                raise AppError(
                    "已经发货的物流单不能取消",
                    code=40157,
                    status_code=400,
                    data={"error": "SHIPMENT_NOT_CANCELLABLE"},
                )
            shipment.status = _CANCELLED
            self.session.commit()
        except AppError:
            self.session.rollback()
            raise
        except Exception:
            self.session.rollback()
            raise
        return self.get_shipment(shipment_id)

    def add_tracking_event(
        self,
        shipment_id: int,
        payload: TrackingEventCreate,
    ) -> ShipmentOut:
        self.auth.require_all(self.context, (PermissionCode.SHIPMENT_TRACKING_UPDATE,))
        if payload.status not in {item.value for item in TrackingEventStatus}:
            raise AppError("轨迹状态不合法", code=40158, status_code=400)
        if payload.status == TrackingEventStatus.DELIVERED.value:
            raise AppError("签收请使用确认签收接口", code=40158, status_code=400)
        try:
            shipment = self.shipments.get_for_update(shipment_id)
            if shipment is None:
                raise AppError(_UNAVAILABLE, code=40491, status_code=404)
            if shipment.status not in {_SHIPPED, _IN_TRANSIT}:
                raise AppError(
                    "只有已发货或运输中的物流单可以添加轨迹",
                    code=40158,
                    status_code=400,
                    data={"error": "SHIPMENT_TRACKING_NOT_ALLOWED"},
                )
            self.session.add(
                ShipmentTrackingEvent(
                    tenant_id=self.context.tenant_id,
                    shipment_id=shipment.id,
                    status=payload.status,
                    description=payload.description or payload.status,
                    location=payload.location,
                    occurred_at=payload.occurred_at,
                    created_by=self.context.user_id,
                )
            )
            if shipment.status == _SHIPPED and payload.status in _IN_TRANSIT_EVENTS:
                shipment.status = _IN_TRANSIT
            self.session.commit()
        except AppError:
            self.session.rollback()
            raise
        except Exception:
            self.session.rollback()
            raise
        return self.get_shipment(shipment_id)

    def mark_delivered(self, shipment_id: int, payload: ShipmentDeliver) -> ShipmentOut:
        """确认签收。整张物流单签收，不做某个 SKU 部分签收。

        功能：SHIPPED / IN_TRANSIT 变成 DELIVERED，并写一条签收轨迹。
        参数：物流单 id；可选签收时间和备注。
        返回：已签收的物流单。
        异常：重复签收；草稿或已取消不能签收。
        核心流程：
        1. 锁物流单。
        2. 写成 DELIVERED，记下 delivered_at。
        3. 自动追加 DELIVERED 轨迹，避免详情时间线缺签收。
        4. 如果销售订单所有数量都已发货且所有物流单都已签收，订单进入 COMPLETED。
        5. 不修改 Inventory。货在出库时已经离开仓库。
        """
        self.auth.require_all(self.context, (PermissionCode.SHIPMENT_DELIVER,))
        try:
            shipment = self.shipments.get_for_update(shipment_id)
            if shipment is None:
                raise AppError(_UNAVAILABLE, code=40491, status_code=404)
            if shipment.status == _DELIVERED:
                raise AppError(
                    "物流单已经签收",
                    code=40155,
                    status_code=400,
                    data={"error": "SHIPMENT_ALREADY_DELIVERED"},
                )
            if shipment.status not in {_SHIPPED, _IN_TRANSIT}:
                raise AppError(
                    "只有已发货或运输中的物流单可以签收",
                    code=40150,
                    status_code=400,
                    data={"error": "INVALID_SHIPMENT_STATUS"},
                )
            now = payload.delivered_at or datetime.now()
            shipment.status = _DELIVERED
            shipment.delivered_at = now
            description = payload.remark or "已签收"
            self.session.add(
                ShipmentTrackingEvent(
                    tenant_id=self.context.tenant_id,
                    shipment_id=shipment.id,
                    status=TrackingEventStatus.DELIVERED.value,
                    description=description,
                    location=None,
                    occurred_at=now,
                    created_by=self.context.user_id,
                )
            )
            sales = self.orders.get_for_update(shipment.sales_order_id)
            if sales is None:
                raise AppError("销售订单不存在或不可访问", code=40471, status_code=404)
            sales_items = self.outbounds.list_sales_items_for_update(sales.id)
            related = self.shipments.list_for_sales_order(sales.id)
            confirmed = [
                row
                for row in related
                if row.status in {_SHIPPED, _IN_TRANSIT, _DELIVERED} or row.id == shipment.id
            ]
            all_delivered = bool(confirmed) and all(
                row.status == _DELIVERED or row.id == shipment.id for row in confirmed
            )
            self._sync_sales(sales, sales_items, all_delivered=all_delivered)
            self.session.commit()
        except AppError:
            self.session.rollback()
            raise
        except Exception:
            self.session.rollback()
            raise
        return self.get_shipment(shipment_id)

    def list_tracking_events(self, shipment_id: int) -> list[TrackingEventOut]:
        return self.get_shipment(shipment_id).tracking_events

    def list_order_shipments(self, sales_order_id: int) -> list[ShipmentOut]:
        return [self._out(row) for row in self.shipments.list_for_sales_order(sales_order_id)]

    def shipped_by_outbound_item(self, outbound_id: int) -> dict[int, int]:
        return self.shipments.allocated_by_outbound_item(outbound_id, confirmed_only=False)

    def _create(self, payload: ShipmentCreate) -> int:
        outbound = self.outbounds.get_for_update(payload.outbound_order_id)
        if outbound is None:
            raise AppError("出库单不存在或不可访问", code=40481, status_code=404)
        if outbound.status != _OUTBOUND_CONFIRMED:
            raise AppError(
                "只有已确认出库的单据可以创建物流单",
                code=40150,
                status_code=400,
                data={"error": "OUTBOUND_NOT_SHIPPABLE"},
            )
        self._require_active_carrier(payload.carrier_id)
        shipment = Shipment(
            tenant_id=self.context.tenant_id,
            sales_order_id=outbound.sales_order_id,
            outbound_order_id=outbound.id,
            carrier_id=payload.carrier_id,
            tracking_no=payload.tracking_no,
            status=_DRAFT,
            remark=payload.remark,
            created_by=self.context.user_id,
        )
        self.shipments.add(shipment)
        self.session.flush()
        shipment.shipment_no = f"SHP{datetime.now().year}{shipment.id:06d}"
        self._add_items(shipment, payload.items)
        return shipment.id

    def _add_items(
        self,
        shipment: Shipment,
        items: list[ShipmentItemIn] | None,
    ) -> None:
        ob_items = {
            row.id: row
            for row in self.shipments.list_outbound_items_for_update(shipment.outbound_order_id)
        }
        allocated = self.shipments.allocated_by_outbound_item(
            shipment.outbound_order_id,
            exclude_shipment_id=shipment.id,
        )
        chosen: list[tuple[OutboundOrderItem, int]] = []
        if items:
            seen: set[int] = set()
            for incoming in items:
                if incoming.outbound_order_item_id in seen:
                    raise AppError("发货明细重复", code=40152, status_code=400)
                seen.add(incoming.outbound_order_item_id)
                ob_item = ob_items.get(incoming.outbound_order_item_id)
                if ob_item is None:
                    raise AppError("出库明细不存在", code=40152, status_code=400)
                remain = ob_item.outbound_quantity - allocated.get(ob_item.id, 0)
                if incoming.quantity > remain:
                    raise AppError(
                        "本次发货超过出库剩余数量",
                        code=40152,
                        status_code=400,
                        data={"error": "SHIPMENT_EXCEEDS_OUTBOUND"},
                    )
                chosen.append((ob_item, incoming.quantity))
        else:
            for ob_item in sorted(ob_items.values(), key=lambda row: (row.sku_id, row.id)):
                remain = ob_item.outbound_quantity - allocated.get(ob_item.id, 0)
                if remain > 0:
                    chosen.append((ob_item, remain))
        if not chosen:
            raise AppError(
                "没有剩余可发货数量",
                code=40152,
                status_code=400,
                data={"error": "SHIPMENT_NOTHING_TO_SHIP"},
            )
        for ob_item, qty in chosen:
            self.session.add(
                ShipmentItem(
                    tenant_id=self.context.tenant_id,
                    shipment_id=shipment.id,
                    outbound_order_item_id=ob_item.id,
                    sales_order_item_id=ob_item.sales_order_item_id,
                    sku_id=ob_item.sku_id,
                    quantity=qty,
                )
            )

    def _require_active_carrier(self, carrier_id: int):
        carrier = self.carriers.get_in_tenant(carrier_id)
        if carrier is None:
            raise AppError("物流商不存在或不可访问", code=40490, status_code=404)
        if carrier.status != CarrierStatus.ACTIVE.value:
            raise AppError(
                "停用的物流商不能用于发货",
                code=40096,
                status_code=400,
                data={"error": "CARRIER_DISABLED"},
            )
        return carrier

    def _sync_sales(
        self,
        order,
        items: list[SalesOrderItem],
        *,
        all_delivered: bool,
    ) -> None:
        order.status = apply_fulfillment_status(
            order.status,
            items,
            all_delivered=all_delivered,
        )

    def _out(self, shipment: Shipment) -> ShipmentOut:
        sales = shipment.sales_order
        outbound = shipment.outbound_order
        carrier = shipment.carrier
        customer_name = ""
        if sales is not None and sales.customer is not None:
            customer_name = sales.customer.name
        allocated = self.shipments.allocated_by_outbound_item(
            shipment.outbound_order_id,
            confirmed_only=True,
            exclude_shipment_id=shipment.id,
        )
        ob_qty = {
            row.id: row.outbound_quantity
            for row in self.outbounds.list_items(shipment.outbound_order_id)
        }
        return ShipmentOut(
            id=shipment.id,
            shipment_no=shipment.shipment_no or "",
            sales_order_id=shipment.sales_order_id,
            sales_order_no="" if sales is None or sales.order_no is None else sales.order_no,
            outbound_order_id=shipment.outbound_order_id,
            outbound_no=(
                "" if outbound is None or outbound.outbound_no is None else outbound.outbound_no
            ),
            customer_name=customer_name,
            recipient_name=None if sales is None else sales.recipient_name,
            address=None if sales is None else sales.address,
            carrier_id=shipment.carrier_id,
            carrier_name="" if carrier is None else carrier.name,
            tracking_no=shipment.tracking_no,
            status=shipment.status,
            remark=shipment.remark,
            shipped_at=shipment.shipped_at,
            shipped_by=shipment.shipped_by,
            shipped_by_name=self._user_name(shipment.shipped_by),
            delivered_at=shipment.delivered_at,
            created_by=shipment.created_by,
            created_at=shipment.created_at,
            sku_count=len(shipment.items),
            total_quantity=sum(item.quantity for item in shipment.items),
            items=[
                self._item_out(item, ob_qty.get(item.outbound_order_item_id, 0), allocated)
                for item in shipment.items
            ],
            tracking_events=[self._event_out(event) for event in shipment.tracking_events],
        )

    @staticmethod
    def _item_out(
        item: ShipmentItem,
        outbound_quantity: int,
        allocated: dict[int, int],
    ) -> ShipmentItemOut:
        sku = item.sku
        return ShipmentItemOut(
            id=item.id,
            outbound_order_item_id=item.outbound_order_item_id,
            sales_order_item_id=item.sales_order_item_id,
            sku_id=item.sku_id,
            sku_code="" if sku is None or sku.sku_code is None else sku.sku_code,
            sku_name="" if sku is None else sku.name,
            product_name="" if sku is None or sku.product is None else sku.product.name,
            quantity=item.quantity,
            outbound_quantity=outbound_quantity,
            shipped_before=allocated.get(item.outbound_order_item_id, 0),
        )

    @staticmethod
    def _event_out(event: ShipmentTrackingEvent) -> TrackingEventOut:
        return TrackingEventOut(
            id=event.id,
            status=event.status,
            description=event.description,
            location=event.location,
            occurred_at=event.occurred_at,
            created_by=event.created_by,
            created_at=event.created_at,
        )

    def _user_name(self, user_id: int | None) -> str | None:
        if user_id is None:
            return None
        return self.session.scalar(select(User.display_name).where(User.id == user_id))

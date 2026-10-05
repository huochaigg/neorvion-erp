"""采购单。创建/审核绝不改 Inventory；收货版本才增加 quantity。"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.core.permissions import PermissionCode
from app.core.tenant import TenantContext
from app.models.product import ProductSku, SkuStatus
from app.models.purchase import PurchaseOrder, PurchaseOrderItem, PurchaseOrderStatus
from app.models.supplier import SupplierStatus
from app.models.user import User
from app.models.warehouse import WarehouseStatus
from app.repositories.product import ProductSkuRepository
from app.repositories.purchase import PurchaseOrderRepository
from app.repositories.supplier import SupplierRepository
from app.repositories.warehouse import WarehouseRepository
from app.schemas.purchase import (
    PurchaseOrderCancel,
    PurchaseOrderCreate,
    PurchaseOrderDetailOut,
    PurchaseOrderItemIn,
    PurchaseOrderItemOut,
    PurchaseOrderListItemOut,
    PurchaseOrderListOut,
    PurchaseOrderReject,
    PurchaseOrderUpdate,
)
from app.services.authorization import AuthorizationService
from app.services.purchase_state import (
    CANCELLABLE_STATUSES,
    PENDING_APPROVAL,
    REJECTED,
    SUBMITTABLE_STATUSES,
    WAITING_RECEIPT,
    require_editable,
    require_transition,
)

_UNAVAILABLE = "采购单不存在或不可访问"


class PurchaseOrderService:
    def __init__(self, session: Session, context: TenantContext) -> None:
        self.session = session
        self.context = context
        self.auth = AuthorizationService(session)
        self.orders = PurchaseOrderRepository(session, context.tenant_id)
        self.suppliers = SupplierRepository(session, context.tenant_id)
        self.warehouses = WarehouseRepository(session, context.tenant_id)
        self.skus = ProductSkuRepository(session, context.tenant_id)

    def list_orders(
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
    ) -> PurchaseOrderListOut:
        self.auth.require_all(self.context, (PermissionCode.PURCHASE_READ,))
        if status and status not in {item.value for item in PurchaseOrderStatus}:
            raise AppError("采购单状态不合法", code=40092, status_code=400)
        rows, total = self.orders.list_page(
            q=(q or "").strip() or None,
            supplier_id=supplier_id,
            warehouse_id=warehouse_id,
            sku_id=sku_id,
            status=status,
            created_from=created_from,
            created_to=created_to,
            expected_from=expected_from,
            expected_to=expected_to,
            created_by=created_by,
            page=page,
            page_size=page_size,
        )
        items = [
            self._list_item(
                order,
                supplier_name=supplier_name,
                warehouse_name=warehouse_name,
                creator_name=creator_name,
                sku_count=int(sku_count or 0),
                total_quantity=int(total_quantity or 0),
                total_amount=self._money(total_amount),
            )
            for (
                order,
                supplier_name,
                warehouse_name,
                creator_name,
                sku_count,
                total_quantity,
                total_amount,
            ) in rows
        ]
        return PurchaseOrderListOut(items=items, total=total, page=page, page_size=page_size)

    def get_order(self, order_id: int) -> PurchaseOrderDetailOut:
        self.auth.require_all(self.context, (PermissionCode.PURCHASE_READ,))
        order = self.orders.get_in_tenant(order_id)
        if order is None:
            raise AppError(_UNAVAILABLE, code=40470, status_code=404)
        return self._detail_out(order)

    def create_order(self, payload: PurchaseOrderCreate) -> PurchaseOrderDetailOut:
        """创建采购单主表 + 明细，同一事务。任一行失败整单 rollback。

        审核通过也不改库存：采购只是计划数量，货可能少到。收货版本才动 Inventory。
        """
        self.auth.require_all(self.context, (PermissionCode.PURCHASE_CREATE,))
        supplier = self._require_active_supplier(payload.supplier_id)
        warehouse = self._require_active_warehouse(payload.warehouse_id)
        sku_map = self._require_active_skus([item.sku_id for item in payload.items])
        order = PurchaseOrder(
            tenant_id=self.context.tenant_id,
            supplier_id=supplier.id,
            warehouse_id=warehouse.id,
            status=PurchaseOrderStatus.DRAFT.value,
            expected_arrival_date=payload.expected_arrival_date,
            remark=payload.remark,
            created_by=self.context.user_id,
        )
        try:
            self.orders.add(order)
            # flush 拿到自增 id，按年+id 生成单号，不靠 MAX(order_no)+1。
            self.session.flush()
            order.order_no = self._auto_order_no(order.id)
            self._insert_items(order.id, payload.items, sku_map)
            self.session.commit()
        except AppError:
            self.session.rollback()
            raise
        except IntegrityError:
            self.session.rollback()
            raise AppError(
                "同一采购单中同一个 SKU 只能出现一行",
                code=40093,
                status_code=400,
                data={"error": "DUPLICATE_PURCHASE_ORDER_SKU"},
            ) from None
        except Exception:
            self.session.rollback()
            raise
        created = self.orders.get_in_tenant(order.id)
        if created is None:
            raise AppError(_UNAVAILABLE, code=40470, status_code=404)
        return self._detail_out(created)

    def update_order(self, order_id: int, payload: PurchaseOrderUpdate) -> PurchaseOrderDetailOut:
        """仅 DRAFT / REJECTED 可改核心字段。提交审核后改 SKU 会使审核失去意义。

        明细采用整体替换：删旧行再建新行，比一堆增删改接口更不容易漏。
        """
        self.auth.require_all(self.context, (PermissionCode.PURCHASE_UPDATE,))
        try:
            order = self.orders.get_for_update(order_id)
            if order is None:
                raise AppError(_UNAVAILABLE, code=40470, status_code=404)
            require_editable(order.status)
            if payload.supplier_id is not None:
                supplier = self._require_active_supplier(payload.supplier_id)
                order.supplier_id = supplier.id
            if payload.warehouse_id is not None:
                warehouse = self._require_active_warehouse(payload.warehouse_id)
                order.warehouse_id = warehouse.id
            if "expected_arrival_date" in payload.model_fields_set:
                order.expected_arrival_date = payload.expected_arrival_date
            if "remark" in payload.model_fields_set:
                order.remark = payload.remark
            if payload.items is not None:
                sku_map = self._require_active_skus([item.sku_id for item in payload.items])
                self.orders.delete_items(order.id)
                # SQL 删行后 ORM 集合仍可能缓存旧明细，过期后再插入，避免脏对象混进同一事务。
                self.session.expire(order, ["items"])
                self._insert_items(order.id, payload.items, sku_map)
            self.session.commit()
        except AppError:
            self.session.rollback()
            raise
        except IntegrityError:
            self.session.rollback()
            raise AppError(
                "同一采购单中同一个 SKU 只能出现一行",
                code=40093,
                status_code=400,
                data={"error": "DUPLICATE_PURCHASE_ORDER_SKU"},
            ) from None
        except Exception:
            self.session.rollback()
            raise
        updated = self.orders.get_in_tenant(order_id)
        if updated is None:
            raise AppError(_UNAVAILABLE, code=40470, status_code=404)
        return self._detail_out(updated)

    def submit_order(self, order_id: int) -> PurchaseOrderDetailOut:
        """DRAFT / REJECTED → PENDING_APPROVAL。提交前再校验供应商、仓库、SKU、明细。"""
        self.auth.require_all(self.context, (PermissionCode.PURCHASE_SUBMIT,))
        order = self._require(order_id)
        if order.status not in SUBMITTABLE_STATUSES:
            require_transition(order.status, PENDING_APPROVAL)
        items = list(order.items)
        if not items:
            raise AppError("提交审核前至少需要一条采购明细", code=40094, status_code=400)
        self._require_active_supplier(order.supplier_id)
        self._require_active_warehouse(order.warehouse_id)
        self._require_active_skus([item.sku_id for item in items])
        now = datetime.now()
        return self._apply_transition(
            order_id,
            expected=order.status,
            target=PENDING_APPROVAL,
            values={
                "status": PENDING_APPROVAL,
                "submitted_at": now,
                "reject_reason": None,
                "rejected_at": None,
                "rejected_by": None,
                "updated_at": func.now(),
            },
        )

    def approve_order(self, order_id: int) -> PurchaseOrderDetailOut:
        """PENDING_APPROVAL → WAITING_RECEIPT。条件 UPDATE，避免一人通过一人驳回互相覆盖。

        不改库存。待收货只表示审核已通过、等后续收货版本入库。
        """
        self.auth.require_all(self.context, (PermissionCode.PURCHASE_AUDIT,))
        order = self._require(order_id)
        require_transition(order.status, WAITING_RECEIPT)
        now = datetime.now()
        return self._apply_transition(
            order_id,
            expected=PENDING_APPROVAL,
            target=WAITING_RECEIPT,
            values={
                "status": WAITING_RECEIPT,
                "approved_at": now,
                "approved_by": self.context.user_id,
                "updated_at": func.now(),
            },
        )

    def reject_order(self, order_id: int, payload: PurchaseOrderReject) -> PurchaseOrderDetailOut:
        self.auth.require_all(self.context, (PermissionCode.PURCHASE_AUDIT,))
        order = self._require(order_id)
        require_transition(order.status, REJECTED)
        now = datetime.now()
        return self._apply_transition(
            order_id,
            expected=PENDING_APPROVAL,
            target=REJECTED,
            values={
                "status": REJECTED,
                "rejected_at": now,
                "rejected_by": self.context.user_id,
                "reject_reason": payload.reason,
                "updated_at": func.now(),
            },
        )

    def cancel_order(self, order_id: int, payload: PurchaseOrderCancel) -> PurchaseOrderDetailOut:
        """WAITING_RECEIPT 禁止取消：审核通过可能已通知供应商。后续再做关闭/作废。"""
        self.auth.require_all(self.context, (PermissionCode.PURCHASE_CANCEL,))
        order = self._require(order_id)
        if order.status not in CANCELLABLE_STATUSES:
            require_transition(order.status, PurchaseOrderStatus.CANCELLED.value)
        now = datetime.now()
        return self._apply_transition(
            order_id,
            expected=order.status,
            target=PurchaseOrderStatus.CANCELLED.value,
            values={
                "status": PurchaseOrderStatus.CANCELLED.value,
                "cancelled_at": now,
                "cancelled_by": self.context.user_id,
                "cancel_reason": payload.reason,
                "updated_at": func.now(),
            },
        )

    def _apply_transition(
        self,
        order_id: int,
        *,
        expected: str,
        target: str,
        values: dict,
    ) -> PurchaseOrderDetailOut:
        require_transition(expected, target)
        try:
            affected = self.orders.transition_if_status(
                order_id=order_id,
                expected_status=expected,
                values=values,
            )
            if affected != 1:
                self.session.rollback()
                raise AppError(
                    "采购单状态已被其他人修改，请刷新后重试",
                    code=40095,
                    status_code=400,
                    data={"error": "PURCHASE_ORDER_STATE_CONFLICT"},
                )
            self.session.commit()
        except AppError:
            self.session.rollback()
            raise
        except Exception:
            self.session.rollback()
            raise
        updated = self.orders.get_in_tenant(order_id)
        if updated is None:
            raise AppError(_UNAVAILABLE, code=40470, status_code=404)
        return self._detail_out(updated)

    def _insert_items(
        self,
        order_id: int,
        items: list[PurchaseOrderItemIn],
        sku_map: dict[int, ProductSku],
    ) -> None:
        # TODO: 这里可以优化，一次性插入多行，避免循环里多次查询数据库
        for item in items:
            sku_map[item.sku_id]
            self.orders.add_item(
                PurchaseOrderItem(
                    tenant_id=self.context.tenant_id,
                    purchase_order_id=order_id,
                    sku_id=item.sku_id,
                    quantity=item.quantity,
                    unit_price=item.unit_price,
                    received_quantity=0,
                    remark=item.remark,
                )
            )

    def _require(self, order_id: int) -> PurchaseOrder:
        order = self.orders.get_in_tenant(order_id)
        if order is None:
            raise AppError(_UNAVAILABLE, code=40470, status_code=404)
        return order

    def _require_active_supplier(self, supplier_id: int):
        supplier = self.suppliers.get_in_tenant(supplier_id)
        if supplier is None:
            raise AppError("供应商不存在或不可访问", code=40460, status_code=404)
        if supplier.status != SupplierStatus.ACTIVE.value:
            raise AppError(
                "禁用的供应商不能用于新的采购单",
                code=40096,
                status_code=400,
                data={"error": "SUPPLIER_DISABLED"},
            )
        return supplier

    def _require_active_warehouse(self, warehouse_id: int):
        warehouse = self.warehouses.get_in_tenant(warehouse_id)
        if warehouse is None:
            raise AppError("仓库不存在或不可访问", code=40440, status_code=404)
        if warehouse.status != WarehouseStatus.ACTIVE.value:
            raise AppError("只能使用启用中的仓库", code=40097, status_code=400)
        return warehouse

    def _require_active_skus(self, sku_ids: list[int]) -> dict[int, ProductSku]:
        """一次性校验全部 SKU 属于本租户且有效，避免循环里各查一次还漏重复。"""
        unique_ids = list(dict.fromkeys(sku_ids))
        if len(unique_ids) != len(sku_ids):
            raise AppError(
                "同一采购单中同一个 SKU 只能出现一行",
                code=40093,
                status_code=400,
                data={"error": "DUPLICATE_PURCHASE_ORDER_SKU"},
            )
        found: dict[int, ProductSku] = {}
        for sku_id in unique_ids:
            sku = self.skus.get_by_id_in_tenant(sku_id)
            if sku is None:
                raise AppError("SKU 不存在或不可访问", code=40433, status_code=404)
            if sku.status != SkuStatus.ACTIVE.value:
                raise AppError("只能采购启用中的 SKU", code=40098, status_code=400)
            found[sku_id] = sku
        return found

    def _user_name(self, user_id: int | None) -> str | None:
        if user_id is None:
            return None
        return self.session.scalar(select(User.display_name).where(User.id == user_id))

    def _detail_out(self, order: PurchaseOrder) -> PurchaseOrderDetailOut:
        item_outs = [self._item_out(row) for row in order.items]
        total_qty = sum(row.quantity for row in order.items)
        amounts = [row.line_amount for row in item_outs if row.line_amount is not None]
        total_amount = round(sum(amounts), 2) if amounts else None
        list_item = self._list_item(
            order,
            supplier_name=order.supplier.name if order.supplier else "",
            warehouse_name=order.warehouse.name if order.warehouse else "",
            creator_name=self._user_name(order.created_by),
            sku_count=len(order.items),
            total_quantity=total_qty,
            total_amount=total_amount,
        )
        return PurchaseOrderDetailOut(
            **list_item.model_dump(),
            remark=order.remark,
            submitted_at=order.submitted_at,
            approved_at=order.approved_at,
            approved_by=order.approved_by,
            approved_by_name=self._user_name(order.approved_by),
            rejected_at=order.rejected_at,
            rejected_by=order.rejected_by,
            rejected_by_name=self._user_name(order.rejected_by),
            reject_reason=order.reject_reason,
            cancelled_at=order.cancelled_at,
            cancelled_by=order.cancelled_by,
            cancelled_by_name=self._user_name(order.cancelled_by),
            cancel_reason=order.cancel_reason,
            items=item_outs,
        )

    @staticmethod
    def _list_item(
        order: PurchaseOrder,
        *,
        supplier_name: str,
        warehouse_name: str,
        creator_name: str | None,
        sku_count: int,
        total_quantity: int,
        total_amount: float | None,
    ) -> PurchaseOrderListItemOut:
        return PurchaseOrderListItemOut(
            id=order.id,
            tenant_id=order.tenant_id,
            order_no=order.order_no or "",
            supplier_id=order.supplier_id,
            supplier_name=supplier_name,
            warehouse_id=order.warehouse_id,
            warehouse_name=warehouse_name,
            status=order.status,
            sku_count=sku_count,
            total_quantity=total_quantity,
            total_amount=total_amount,
            expected_arrival_date=order.expected_arrival_date,
            created_by=order.created_by,
            created_by_name=creator_name,
            created_at=order.created_at,
            updated_at=order.updated_at,
        )

    @staticmethod
    def _item_out(item: PurchaseOrderItem) -> PurchaseOrderItemOut:
        sku = item.sku
        product = sku.product if sku is not None else None
        price = PurchaseOrderService._money(item.unit_price)
        line = None if price is None else round(price * item.quantity, 2)
        return PurchaseOrderItemOut(
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
            received_quantity=item.received_quantity,
            remark=item.remark,
        )

    @staticmethod
    def _money(value: object) -> float | None:
        if value is None:
            return None
        return round(float(str(value)), 2)

    @staticmethod
    def _auto_order_no(order_id: int) -> str:
        year = datetime.now().year
        return f"PO{year}{order_id:06d}"

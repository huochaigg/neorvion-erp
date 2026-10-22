"""供应商退款记录持久化。不在这里 commit。"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.models.identity import IdentityNameSnapshot
from app.models.purchase import PurchaseOrder
from app.models.purchase_return import PurchaseReturn
from app.models.supplier import Supplier
from app.models.supplier_refund import SupplierRefundRecord, SupplierRefundRecordStatus
from app.repositories.base import BaseRepository


class SupplierRefundRepository(BaseRepository):
    def __init__(self, session: Session, tenant_id: int) -> None:
        super().__init__(session, tenant_id)

    def get_in_tenant(self, refund_id: int) -> SupplierRefundRecord | None:
        tenant_id = self.ensure_tenant()
        stmt = (
            select(SupplierRefundRecord)
            .options(
                selectinload(SupplierRefundRecord.purchase_return).selectinload(PurchaseReturn.purchase_order),
                selectinload(SupplierRefundRecord.purchase_return).selectinload(PurchaseReturn.supplier),
            )
            .where(
                SupplierRefundRecord.tenant_id == tenant_id,
                SupplierRefundRecord.id == refund_id,
            )
        )
        return self.session.scalars(stmt).first()

    def get_for_update(self, refund_id: int) -> SupplierRefundRecord | None:
        tenant_id = self.ensure_tenant()
        stmt = (
            select(SupplierRefundRecord)
            .where(
                SupplierRefundRecord.tenant_id == tenant_id,
                SupplierRefundRecord.id == refund_id,
            )
            .with_for_update()
        )
        return self.session.scalars(stmt).first()

    def list_by_return(self, purchase_return_id: int) -> list[SupplierRefundRecord]:
        tenant_id = self.ensure_tenant()
        stmt = (
            select(SupplierRefundRecord)
            .where(
                SupplierRefundRecord.tenant_id == tenant_id,
                SupplierRefundRecord.purchase_return_id == purchase_return_id,
            )
            .order_by(SupplierRefundRecord.created_at.desc(), SupplierRefundRecord.id.desc())
        )
        return list(self.session.scalars(stmt).all())

    def has_pending(self, purchase_return_id: int, *, exclude_id: int | None = None) -> bool:
        tenant_id = self.ensure_tenant()
        filters = [
            SupplierRefundRecord.tenant_id == tenant_id,
            SupplierRefundRecord.purchase_return_id == purchase_return_id,
            SupplierRefundRecord.status == SupplierRefundRecordStatus.PENDING.value,
        ]
        if exclude_id is not None:
            filters.append(SupplierRefundRecord.id != exclude_id)
        stmt = select(SupplierRefundRecord.id).where(*filters).limit(1)
        return self.session.scalar(stmt) is not None

    def success_amount(self, purchase_return_id: int) -> Decimal:
        tenant_id = self.ensure_tenant()
        stmt = select(func.coalesce(func.sum(SupplierRefundRecord.amount), 0)).where(
            SupplierRefundRecord.tenant_id == tenant_id,
            SupplierRefundRecord.purchase_return_id == purchase_return_id,
            SupplierRefundRecord.status == SupplierRefundRecordStatus.SUCCESS.value,
        )
        return Decimal(str(self.session.scalar(stmt) or 0))

    def pending_amount(self, purchase_return_id: int) -> Decimal:
        tenant_id = self.ensure_tenant()
        stmt = select(func.coalesce(func.sum(SupplierRefundRecord.amount), 0)).where(
            SupplierRefundRecord.tenant_id == tenant_id,
            SupplierRefundRecord.purchase_return_id == purchase_return_id,
            SupplierRefundRecord.status == SupplierRefundRecordStatus.PENDING.value,
        )
        return Decimal(str(self.session.scalar(stmt) or 0))

    def add(self, record: SupplierRefundRecord) -> SupplierRefundRecord:
        self.session.add(record)
        return record

    def list_page(
        self,
        *,
        q: str | None,
        purchase_return_id: int | None,
        status: str | None,
        created_from: datetime | None,
        created_to: datetime | None,
        page: int,
        page_size: int,
    ) -> tuple[list[tuple], int]:
        tenant_id = self.ensure_tenant()
        filters = [SupplierRefundRecord.tenant_id == tenant_id]
        if q:
            like = f"%{q}%"
            filters.append(
                or_(
                    SupplierRefundRecord.refund_no.like(like),
                    PurchaseReturn.purchase_return_no.like(like),
                    PurchaseOrder.order_no.like(like),
                    Supplier.name.like(like),
                )
            )
        if purchase_return_id:
            filters.append(SupplierRefundRecord.purchase_return_id == purchase_return_id)
        if status:
            filters.append(SupplierRefundRecord.status == status)
        if created_from:
            filters.append(SupplierRefundRecord.created_at >= created_from)
        if created_to:
            filters.append(SupplierRefundRecord.created_at <= created_to)

        base = (
            select(SupplierRefundRecord)
            .join(PurchaseReturn, and_(PurchaseReturn.tenant_id == SupplierRefundRecord.tenant_id,
                PurchaseReturn.id == SupplierRefundRecord.purchase_return_id))
            .join(PurchaseOrder, and_(PurchaseOrder.tenant_id == PurchaseReturn.tenant_id,
                PurchaseOrder.id == PurchaseReturn.purchase_order_id))
            .join(Supplier, and_(Supplier.tenant_id == PurchaseReturn.tenant_id,
                Supplier.id == PurchaseReturn.supplier_id))
            .outerjoin(
                IdentityNameSnapshot,
                IdentityNameSnapshot.user_id == SupplierRefundRecord.created_by,
            )
            .where(*filters)
        )
        total = int(self.session.scalar(select(func.count()).select_from(base.subquery())) or 0)
        stmt = (
            select(
                SupplierRefundRecord,
                PurchaseReturn.purchase_return_no,
                PurchaseReturn.purchase_order_id,
                PurchaseOrder.order_no,
                PurchaseReturn.supplier_id,
                Supplier.name,
                IdentityNameSnapshot.display_name,
            )
            .join(PurchaseReturn, and_(PurchaseReturn.tenant_id == SupplierRefundRecord.tenant_id,
                PurchaseReturn.id == SupplierRefundRecord.purchase_return_id))
            .join(PurchaseOrder, and_(PurchaseOrder.tenant_id == PurchaseReturn.tenant_id,
                PurchaseOrder.id == PurchaseReturn.purchase_order_id))
            .join(Supplier, and_(Supplier.tenant_id == PurchaseReturn.tenant_id,
                Supplier.id == PurchaseReturn.supplier_id))
            .outerjoin(
                IdentityNameSnapshot,
                IdentityNameSnapshot.user_id == SupplierRefundRecord.created_by,
            )
            .where(*filters)
            .order_by(SupplierRefundRecord.created_at.desc(), SupplierRefundRecord.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(self.session.execute(stmt).all()), total

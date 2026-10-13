"""退款记录持久化。不在这里 commit。"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.models.after_sale import AfterSaleOrder
from app.models.customer import Customer
from app.models.refund import RefundRecord, RefundRecordStatus
from app.models.sales_order import SalesOrder
from app.models.user import User
from app.repositories.base import BaseRepository


class RefundRepository(BaseRepository):
    def __init__(self, session: Session, tenant_id: int) -> None:
        super().__init__(session, tenant_id)

    def get_in_tenant(self, refund_id: int) -> RefundRecord | None:
        tenant_id = self.ensure_tenant()
        stmt = (
            select(RefundRecord)
            .options(selectinload(RefundRecord.after_sale_order))
            .where(RefundRecord.tenant_id == tenant_id, RefundRecord.id == refund_id)
        )
        return self.session.scalars(stmt).first()

    def get_for_update(self, refund_id: int) -> RefundRecord | None:
        tenant_id = self.ensure_tenant()
        stmt = (
            select(RefundRecord)
            .where(RefundRecord.tenant_id == tenant_id, RefundRecord.id == refund_id)
            .with_for_update()
        )
        return self.session.scalars(stmt).first()

    def add(self, record: RefundRecord) -> RefundRecord:
        self.session.add(record)
        return record

    def list_by_after_sale(self, after_sale_id: int) -> list[RefundRecord]:
        tenant_id = self.ensure_tenant()
        stmt = (
            select(RefundRecord)
            .where(
                RefundRecord.tenant_id == tenant_id,
                RefundRecord.after_sale_order_id == after_sale_id,
            )
            .order_by(RefundRecord.id.asc())
        )
        return list(self.session.scalars(stmt).all())

    def has_pending(self, after_sale_id: int, *, exclude_id: int | None = None) -> bool:
        tenant_id = self.ensure_tenant()
        stmt = select(func.count(RefundRecord.id)).where(
            RefundRecord.tenant_id == tenant_id,
            RefundRecord.after_sale_order_id == after_sale_id,
            RefundRecord.status == RefundRecordStatus.PENDING.value,
        )
        if exclude_id is not None:
            stmt = stmt.where(RefundRecord.id != exclude_id)
        return int(self.session.scalar(stmt) or 0) > 0

    def success_amount(self, after_sale_id: int) -> Decimal:
        tenant_id = self.ensure_tenant()
        stmt = select(func.coalesce(func.sum(RefundRecord.amount), 0)).where(
            RefundRecord.tenant_id == tenant_id,
            RefundRecord.after_sale_order_id == after_sale_id,
            RefundRecord.status == RefundRecordStatus.SUCCESS.value,
        )
        return Decimal(str(self.session.scalar(stmt) or 0))

    def pending_amount(self, after_sale_id: int) -> Decimal:
        tenant_id = self.ensure_tenant()
        stmt = select(func.coalesce(func.sum(RefundRecord.amount), 0)).where(
            RefundRecord.tenant_id == tenant_id,
            RefundRecord.after_sale_order_id == after_sale_id,
            RefundRecord.status == RefundRecordStatus.PENDING.value,
        )
        return Decimal(str(self.session.scalar(stmt) or 0))

    def list_page(
        self,
        *,
        q: str | None,
        after_sale_id: int | None,
        status: str | None,
        created_from: datetime | None,
        created_to: datetime | None,
        page: int,
        page_size: int,
    ) -> tuple[list[tuple], int]:
        tenant_id = self.ensure_tenant()
        filters = [RefundRecord.tenant_id == tenant_id]
        if q:
            like = f"%{q}%"
            filters.append(
                or_(
                    RefundRecord.refund_no.like(like),
                    AfterSaleOrder.after_sale_no.like(like),
                    SalesOrder.order_no.like(like),
                    Customer.name.like(like),
                )
            )
        if after_sale_id:
            filters.append(RefundRecord.after_sale_order_id == after_sale_id)
        if status:
            filters.append(RefundRecord.status == status)
        if created_from:
            filters.append(RefundRecord.created_at >= created_from)
        if created_to:
            filters.append(RefundRecord.created_at <= created_to)

        base = (
            select(RefundRecord.id)
            .join(AfterSaleOrder, AfterSaleOrder.id == RefundRecord.after_sale_order_id)
            .join(SalesOrder, SalesOrder.id == AfterSaleOrder.sales_order_id)
            .join(Customer, Customer.id == AfterSaleOrder.customer_id)
            .where(*filters)
        )
        total = int(self.session.scalar(select(func.count()).select_from(base.subquery())) or 0)
        stmt = (
            select(
                RefundRecord,
                AfterSaleOrder.after_sale_no,
                AfterSaleOrder.sales_order_id,
                SalesOrder.order_no,
                AfterSaleOrder.customer_id,
                Customer.name,
                User.display_name,
            )
            .join(AfterSaleOrder, AfterSaleOrder.id == RefundRecord.after_sale_order_id)
            .join(SalesOrder, SalesOrder.id == AfterSaleOrder.sales_order_id)
            .join(Customer, Customer.id == AfterSaleOrder.customer_id)
            .outerjoin(User, User.id == RefundRecord.created_by)
            .where(*filters)
            .order_by(RefundRecord.created_at.desc(), RefundRecord.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(self.session.execute(stmt).all()), total

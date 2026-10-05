from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.supplier import Supplier
from app.repositories.base import BaseRepository


class SupplierRepository(BaseRepository):
    def __init__(self, session: Session, tenant_id: int) -> None:
        super().__init__(session, tenant_id)

    def list_page(
        self,
        *,
        q: str | None,
        status: str | None,
        country_code: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[Supplier], int]:
        tenant_id = self.ensure_tenant()
        filters = [Supplier.tenant_id == tenant_id]
        if status:
            filters.append(Supplier.status == status)
        if country_code:
            filters.append(Supplier.country_code == country_code)
        if q:
            pattern = f"%{q}%"
            filters.append(or_(Supplier.name.like(pattern), Supplier.code.like(pattern)))
        total = int(self.session.scalar(select(func.count(Supplier.id)).where(*filters)) or 0)
        stmt = (
            select(Supplier)
            .where(*filters)
            .order_by(Supplier.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(self.session.scalars(stmt).all()), total

    def get_in_tenant(self, supplier_id: int) -> Supplier | None:
        tenant_id = self.ensure_tenant()
        stmt = select(Supplier).where(
            Supplier.tenant_id == tenant_id,
            Supplier.id == supplier_id,
        )
        return self.session.scalars(stmt).first()

    def get_by_code(self, code: str) -> Supplier | None:
        tenant_id = self.ensure_tenant()
        stmt = select(Supplier).where(Supplier.tenant_id == tenant_id, Supplier.code == code)
        return self.session.scalars(stmt).first()

    def add(self, supplier: Supplier) -> Supplier:
        self.session.add(supplier)
        return supplier

    def delete(self, supplier: Supplier) -> None:
        self.session.delete(supplier)

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.customer import Customer
from app.repositories.base import BaseRepository


class CustomerRepository(BaseRepository):
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
    ) -> tuple[list[Customer], int]:
        tenant_id = self.ensure_tenant()
        filters = [Customer.tenant_id == tenant_id]
        if status:
            filters.append(Customer.status == status)
        if country_code:
            filters.append(Customer.country_code == country_code)
        if q:
            pattern = f"%{q}%"
            filters.append(
                or_(
                    Customer.name.like(pattern),
                    Customer.code.like(pattern),
                    Customer.email.like(pattern),
                    Customer.phone.like(pattern),
                )
            )
        total = int(self.session.scalar(select(func.count(Customer.id)).where(*filters)) or 0)
        stmt = (
            select(Customer)
            .where(*filters)
            .order_by(Customer.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(self.session.scalars(stmt).all()), total

    def get_in_tenant(self, customer_id: int) -> Customer | None:
        tenant_id = self.ensure_tenant()
        stmt = select(Customer).where(Customer.tenant_id == tenant_id, Customer.id == customer_id)
        return self.session.scalars(stmt).first()

    def get_by_code(self, code: str) -> Customer | None:
        tenant_id = self.ensure_tenant()
        stmt = select(Customer).where(Customer.tenant_id == tenant_id, Customer.code == code)
        return self.session.scalars(stmt).first()

    def add(self, customer: Customer) -> Customer:
        self.session.add(customer)
        return customer

    def delete(self, customer: Customer) -> None:
        self.session.delete(customer)

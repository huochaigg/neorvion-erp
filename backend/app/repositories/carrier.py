from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.carrier import Carrier
from app.models.shipment import Shipment
from app.repositories.base import BaseRepository


class CarrierRepository(BaseRepository):
    def __init__(self, session: Session, tenant_id: int) -> None:
        super().__init__(session, tenant_id)

    def list_page(
        self,
        *,
        q: str | None,
        status: str | None,
        carrier_type: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[Carrier], int]:
        tenant_id = self.ensure_tenant()
        filters = [Carrier.tenant_id == tenant_id]
        if status:
            filters.append(Carrier.status == status)
        if carrier_type:
            filters.append(Carrier.carrier_type == carrier_type)
        if q:
            pattern = f"%{q}%"
            filters.append(or_(Carrier.name.like(pattern), Carrier.code.like(pattern)))
        total = int(self.session.scalar(select(func.count(Carrier.id)).where(*filters)) or 0)
        stmt = (
            select(Carrier)
            .where(*filters)
            .order_by(Carrier.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(self.session.scalars(stmt).all()), total

    def get_in_tenant(self, carrier_id: int) -> Carrier | None:
        tenant_id = self.ensure_tenant()
        stmt = select(Carrier).where(Carrier.tenant_id == tenant_id, Carrier.id == carrier_id)
        return self.session.scalars(stmt).first()

    def get_by_code(self, code: str) -> Carrier | None:
        tenant_id = self.ensure_tenant()
        stmt = select(Carrier).where(Carrier.tenant_id == tenant_id, Carrier.code == code)
        return self.session.scalars(stmt).first()

    def add(self, carrier: Carrier) -> Carrier:
        self.session.add(carrier)
        return carrier

    def delete(self, carrier: Carrier) -> None:
        self.session.delete(carrier)

    def count_shipments(self, carrier_id: int) -> int:
        tenant_id = self.ensure_tenant()
        return int(
            self.session.scalar(
                select(func.count(Shipment.id)).where(
                    Shipment.tenant_id == tenant_id,
                    Shipment.carrier_id == carrier_id,
                )
            )
            or 0
        )

"""物流商档案。被物流单引用后不能删除，只能禁用。"""

from __future__ import annotations

import re

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.core.permissions import PermissionCode
from app.core.tenant import TenantContext
from app.models.carrier import Carrier, CarrierStatus, CarrierType
from app.repositories.carrier import CarrierRepository
from app.schemas.carrier import (
    CarrierCreate,
    CarrierListOut,
    CarrierOut,
    CarrierStatusUpdate,
    CarrierUpdate,
)
from app.services.authorization import AuthorizationService

_UNAVAILABLE = "物流商不存在或不可访问"
_AUTO_PREFIX = "CAR"
_AUTO_WIDTH = 10
_CARRIER_CODE = re.compile(r"^[A-Z0-9_-]{2,32}$")


class CarrierService:
    def __init__(self, session: Session, context: TenantContext) -> None:
        self.session = session
        self.context = context
        self.auth = AuthorizationService(session)
        self.carriers = CarrierRepository(session, context.tenant_id)

    def list_carriers(
        self,
        *,
        q: str | None,
        status: str | None,
        carrier_type: str | None,
        page: int,
        page_size: int,
    ) -> CarrierListOut:
        self.auth.require_all(self.context, (PermissionCode.CARRIER_READ,))
        rows, total = self.carriers.list_page(
            q=(q or "").strip() or None,
            status=status,
            carrier_type=carrier_type,
            page=page,
            page_size=page_size,
        )
        return CarrierListOut(
            items=[self._out(row) for row in rows],
            total=total,
            page=page,
            page_size=page_size,
        )

    def get_carrier(self, carrier_id: int) -> CarrierOut:
        self.auth.require_all(self.context, (PermissionCode.CARRIER_READ,))
        return self._out(self._require(carrier_id))

    def create_carrier(self, payload: CarrierCreate) -> CarrierOut:
        """新增物流商。未填 code 时 flush 拿 id，再写成 CAR + 10 位数字。"""
        self.auth.require_all(self.context, (PermissionCode.CARRIER_CREATE,))
        custom_code = self._normalize_optional_code(payload.code)
        carrier_type = self._normalize_type(payload.carrier_type)
        if custom_code and self.carriers.get_by_code(custom_code) is not None:
            raise AppError(
                "物流商编码已存在",
                code=40970,
                status_code=409,
                data={"error": "CARRIER_CODE_CONFLICT"},
            )
        carrier = Carrier(
            tenant_id=self.context.tenant_id,
            name=payload.name,
            code=custom_code,
            carrier_type=carrier_type,
            contact_name=payload.contact_name,
            contact_phone=payload.contact_phone,
            website=payload.website,
            remark=payload.remark,
            status=CarrierStatus.ACTIVE.value,
        )
        try:
            self.carriers.add(carrier)
            self.session.flush()
            if carrier.code is None:
                carrier.code = self._auto_code(carrier.id)
            self.session.commit()
        except IntegrityError:
            self.session.rollback()
            raise AppError(
                "物流商编码已存在",
                code=40970,
                status_code=409,
                data={"error": "CARRIER_CODE_CONFLICT"},
            ) from None
        except Exception:
            self.session.rollback()
            raise
        return self._out(self._require(carrier.id))

    def update_carrier(self, carrier_id: int, payload: CarrierUpdate) -> CarrierOut:
        self.auth.require_all(self.context, (PermissionCode.CARRIER_UPDATE,))
        carrier = self._require(carrier_id)
        if payload.name is not None:
            carrier.name = payload.name
        if payload.carrier_type is not None:
            carrier.carrier_type = self._normalize_type(payload.carrier_type)
        if "contact_name" in payload.model_fields_set:
            carrier.contact_name = payload.contact_name
        if "contact_phone" in payload.model_fields_set:
            carrier.contact_phone = payload.contact_phone
        if "website" in payload.model_fields_set:
            carrier.website = payload.website
        if "remark" in payload.model_fields_set:
            carrier.remark = payload.remark
        try:
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        return self._out(self._require(carrier_id))

    def change_status(self, carrier_id: int, payload: CarrierStatusUpdate) -> CarrierOut:
        self.auth.require_all(self.context, (PermissionCode.CARRIER_DISABLE,))
        carrier = self._require(carrier_id)
        carrier.status = self._normalize_status(payload.status)
        try:
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        return self._out(self._require(carrier_id))

    def delete_carrier(self, carrier_id: int) -> None:
        self.auth.require_all(self.context, (PermissionCode.CARRIER_DELETE,))
        carrier = self._require(carrier_id)
        if self.carriers.count_shipments(carrier.id) > 0:
            raise AppError(
                "物流商已被物流单引用，不能删除。",
                code=40096,
                status_code=400,
                data={"error": "CARRIER_IN_USE"},
            )
        try:
            self.carriers.delete(carrier)
            self.session.commit()
        except IntegrityError:
            self.session.rollback()
            raise AppError(
                "物流商已被物流单引用，不能删除。",
                code=40096,
                status_code=400,
                data={"error": "CARRIER_IN_USE"},
            ) from None
        except Exception:
            self.session.rollback()
            raise

    def _require(self, carrier_id: int) -> Carrier:
        carrier = self.carriers.get_in_tenant(carrier_id)
        if carrier is None:
            raise AppError(_UNAVAILABLE, code=40490, status_code=404)
        return carrier

    @staticmethod
    def _auto_code(carrier_id: int) -> str:
        return f"{_AUTO_PREFIX}{carrier_id:0{_AUTO_WIDTH}d}"

    @staticmethod
    def _normalize_status(value: str) -> str:
        if value not in {item.value for item in CarrierStatus}:
            raise AppError("物流商状态不合法", code=40097, status_code=400)
        return value

    @staticmethod
    def _normalize_type(value: str) -> str:
        if value not in {item.value for item in CarrierType}:
            raise AppError("物流商类型不合法", code=40097, status_code=400)
        return value

    @staticmethod
    def _normalize_optional_code(value: str | None) -> str | None:
        if value is None:
            return None
        code = value.strip().upper()
        if not _CARRIER_CODE.fullmatch(code):
            raise AppError("物流商编码格式不合法", code=40098, status_code=400)
        return code

    @staticmethod
    def _out(carrier: Carrier) -> CarrierOut:
        return CarrierOut(
            id=carrier.id,
            tenant_id=carrier.tenant_id,
            name=carrier.name,
            code=carrier.code or "",
            carrier_type=carrier.carrier_type,
            contact_name=carrier.contact_name,
            contact_phone=carrier.contact_phone,
            website=carrier.website,
            status=carrier.status,
            remark=carrier.remark,
            created_at=carrier.created_at,
            updated_at=carrier.updated_at,
        )

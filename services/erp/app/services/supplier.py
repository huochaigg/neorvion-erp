"""供应商主数据。Repository 不 commit；写操作由本层提交。"""

from __future__ import annotations

import re

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.core.permissions import PermissionCode
from app.core.tenant import TenantContext
from app.models.supplier import Supplier, SupplierStatus
from app.repositories.purchase import PurchaseOrderRepository
from app.repositories.supplier import SupplierRepository
from app.schemas.supplier import (
    SupplierCreate,
    SupplierListOut,
    SupplierOut,
    SupplierStatusUpdate,
    SupplierUpdate,
)
from app.services.authorization import AuthorizationService

_UNAVAILABLE = "供应商不存在或不可访问"
_SUPPLIER_CODE = re.compile(r"^[A-Z0-9][A-Z0-9_-]{0,31}$")
_COUNTRY_CODE = re.compile(r"^[A-Z]{2}$")
_AUTO_PREFIX = "SUP"
_AUTO_WIDTH = 10
_OPTIONAL_TEXT_FIELDS = (
    "contact_name",
    "contact_phone",
    "contact_email",
    "country_code",
    "province",
    "city",
    "address",
    "remark",
)


class SupplierService:
    def __init__(self, session: Session, context: TenantContext) -> None:
        self.session = session
        self.context = context
        self.auth = AuthorizationService(session)
        self.suppliers = SupplierRepository(session, context.tenant_id)
        self.orders = PurchaseOrderRepository(session, context.tenant_id)

    def list_suppliers(
        self,
        *,
        q: str | None,
        status: str | None,
        country_code: str | None,
        page: int,
        page_size: int,
    ) -> SupplierListOut:
        self.auth.require_all(self.context, (PermissionCode.SUPPLIER_READ,))
        if status and status not in {item.value for item in SupplierStatus}:
            raise AppError("供应商状态不合法", code=40080, status_code=400)
        country = (country_code or "").strip().upper() or None
        rows, total = self.suppliers.list_page(
            q=(q or "").strip() or None,
            status=status,
            country_code=country,
            page=page,
            page_size=page_size,
        )
        return SupplierListOut(
            items=[self._to_out(row) for row in rows],
            total=total,
            page=page,
            page_size=page_size,
        )

    def get_supplier(self, supplier_id: int) -> SupplierOut:
        self.auth.require_all(self.context, (PermissionCode.SUPPLIER_READ,))
        return self._to_out(self._require(supplier_id))

    def create_supplier(self, payload: SupplierCreate) -> SupplierOut:
        """新增供应商。未填 code 时 flush 拿 id，再写成 SUP + 10 位数字。

        不要用 MAX(code)+1：删除后会复用号段，并发也不安全。
        """
        self.auth.require_all(self.context, (PermissionCode.SUPPLIER_CREATE,))
        status = self._normalize_status(payload.status or SupplierStatus.ACTIVE.value)
        custom_code = self._normalize_optional_code(payload.code)
        country_code = self._normalize_country(payload.country_code)
        try:
            if custom_code is not None and self.suppliers.get_by_code(custom_code) is not None:
                raise AppError("供应商编码已存在", code=40960, status_code=409)
            supplier = Supplier(
                tenant_id=self.context.tenant_id,
                name=payload.name,
                code=custom_code,
                contact_name=payload.contact_name,
                contact_phone=payload.contact_phone,
                contact_email=payload.contact_email,
                country_code=country_code,
                province=payload.province,
                city=payload.city,
                address=payload.address,
                status=status,
                remark=payload.remark,
            )
            self.suppliers.add(supplier)
            self.session.flush()
            if supplier.code is None:
                supplier.code = self._auto_code(supplier.id)
            if not supplier.code:
                raise AppError("供应商编码生成失败", code=50021, status_code=500)
            self.session.commit()
            self.session.refresh(supplier)
        except IntegrityError:
            self.session.rollback()
            raise AppError("供应商编码已存在", code=40960, status_code=409) from None
        except Exception:
            self.session.rollback()
            raise
        return self._to_out(supplier)

    def update_supplier(self, supplier_id: int, payload: SupplierUpdate) -> SupplierOut:
        """编辑档案。PATCH 不提交 code，创建后编码只读。"""
        self.auth.require_all(self.context, (PermissionCode.SUPPLIER_UPDATE,))
        supplier = self._require(supplier_id)
        if payload.name is not None:
            supplier.name = payload.name
        if "country_code" in payload.model_fields_set:
            supplier.country_code = self._normalize_country(payload.country_code)
        for field in _OPTIONAL_TEXT_FIELDS:
            if field == "country_code":
                continue
            if field in payload.model_fields_set:
                setattr(supplier, field, getattr(payload, field))
        try:
            self.session.commit()
            self.session.refresh(supplier)
        except Exception:
            self.session.rollback()
            raise
        return self._to_out(supplier)

    def change_status(self, supplier_id: int, payload: SupplierStatusUpdate) -> SupplierOut:
        self.auth.require_all(self.context, (PermissionCode.SUPPLIER_DISABLE,))
        supplier = self._require(supplier_id)
        status = self._normalize_status(payload.status)
        supplier.status = status
        try:
            self.session.commit()
            self.session.refresh(supplier)
        except Exception:
            self.session.rollback()
            raise
        return self._to_out(supplier)

    def delete_supplier(self, supplier_id: int) -> None:
        """已被采购单引用的供应商不能删，只能禁用。历史单据必须还能看到供应商名称。"""
        self.auth.require_all(self.context, (PermissionCode.SUPPLIER_DELETE,))
        supplier = self._require(supplier_id)
        if self.orders.count_by_supplier(supplier.id) > 0:
            raise AppError(
                "供应商已被采购单引用，不能删除。",
                code=40081,
                status_code=400,
                data={"error": "SUPPLIER_IN_USE"},
            )
        try:
            self.suppliers.delete(supplier)
            self.session.commit()
        except IntegrityError:
            self.session.rollback()
            raise AppError(
                "供应商已被采购单引用，不能删除。",
                code=40081,
                status_code=400,
                data={"error": "SUPPLIER_IN_USE"},
            ) from None
        except Exception:
            self.session.rollback()
            raise

    def _require(self, supplier_id: int) -> Supplier:
        supplier = self.suppliers.get_in_tenant(supplier_id)
        if supplier is None:
            raise AppError(_UNAVAILABLE, code=40460, status_code=404)
        return supplier

    @staticmethod
    def _auto_code(supplier_id: int) -> str:
        return f"{_AUTO_PREFIX}{supplier_id:0{_AUTO_WIDTH}d}"

    @staticmethod
    def _normalize_status(value: str) -> str:
        if value not in {item.value for item in SupplierStatus}:
            raise AppError("供应商状态不合法", code=40080, status_code=400)
        return value

    @staticmethod
    def _normalize_optional_code(value: str | None) -> str | None:
        if value is None:
            return None
        code = value.strip().upper()
        if not _SUPPLIER_CODE.fullmatch(code):
            raise AppError("供应商编码格式不合法", code=40082, status_code=400)
        return code

    @staticmethod
    def _normalize_country(value: str | None) -> str | None:
        if value is None:
            return None
        if not _COUNTRY_CODE.fullmatch(value):
            raise AppError("国家代码必须是 ISO 两位字母，例如 CN", code=40083, status_code=400)
        return value

    @staticmethod
    def _to_out(supplier: Supplier) -> SupplierOut:
        return SupplierOut(
            id=supplier.id,
            tenant_id=supplier.tenant_id,
            name=supplier.name,
            code=supplier.code or "",
            contact_name=supplier.contact_name,
            contact_phone=supplier.contact_phone,
            contact_email=supplier.contact_email,
            country_code=supplier.country_code,
            province=supplier.province,
            city=supplier.city,
            address=supplier.address,
            status=supplier.status,
            remark=supplier.remark,
            created_at=supplier.created_at,
            updated_at=supplier.updated_at,
        )

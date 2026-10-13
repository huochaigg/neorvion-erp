"""客户档案。Repository 不 commit；写操作由本层提交。"""

from __future__ import annotations

import re

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.core.permissions import PermissionCode
from app.core.tenant import TenantContext
from app.models.customer import Customer, CustomerStatus
from app.repositories.customer import CustomerRepository
from app.repositories.sales_order import SalesOrderRepository
from app.schemas.customer import (
    CustomerCreate,
    CustomerListOut,
    CustomerOut,
    CustomerStatusUpdate,
    CustomerUpdate,
)
from app.services.authorization import AuthorizationService

_UNAVAILABLE = "客户不存在或不可访问"
_CUSTOMER_CODE = re.compile(r"^[A-Z0-9][A-Z0-9_-]{0,31}$")
_COUNTRY_CODE = re.compile(r"^[A-Z]{2}$")
_AUTO_PREFIX = "CUS"
_AUTO_WIDTH = 10
_OPTIONAL_TEXT_FIELDS = (
    "email",
    "phone",
    "country_code",
    "province",
    "city",
    "address",
    "remark",
)


class CustomerService:
    def __init__(self, session: Session, context: TenantContext) -> None:
        self.session = session
        self.context = context
        self.auth = AuthorizationService(session)
        self.customers = CustomerRepository(session, context.tenant_id)
        self.orders = SalesOrderRepository(session, context.tenant_id)

    def list_customers(
        self,
        *,
        q: str | None,
        status: str | None,
        country_code: str | None,
        page: int,
        page_size: int,
    ) -> CustomerListOut:
        self.auth.require_all(self.context, (PermissionCode.CUSTOMER_READ,))
        if status and status not in {item.value for item in CustomerStatus}:
            raise AppError("客户状态不合法", code=40084, status_code=400)
        country = (country_code or "").strip().upper() or None
        rows, total = self.customers.list_page(
            q=(q or "").strip() or None,
            status=status,
            country_code=country,
            page=page,
            page_size=page_size,
        )
        return CustomerListOut(
            items=[self._to_out(row) for row in rows],
            total=total,
            page=page,
            page_size=page_size,
        )

    def get_customer(self, customer_id: int) -> CustomerOut:
        self.auth.require_all(self.context, (PermissionCode.CUSTOMER_READ,))
        return self._to_out(self._require(customer_id))

    def create_customer(self, payload: CustomerCreate) -> CustomerOut:
        """新增客户。未填 code 时 flush 拿 id，再写成 CUS + 10 位数字。

        功能：给当前租户建一条客户档案。
        参数：名称必填，编码可空。
        返回：带最终 code 的客户。
        异常：编码冲突 40961；格式不合法 40086。
        核心流程：先插入拿到数据库 id，再按 id 生成编码。不用 MAX(code)+1，
        否则删除后会复用号段，两个请求也会抢同一个号。
        """
        self.auth.require_all(self.context, (PermissionCode.CUSTOMER_CREATE,))
        status = self._normalize_status(payload.status or CustomerStatus.ACTIVE.value)
        custom_code = self._normalize_optional_code(payload.code)
        country_code = self._normalize_country(payload.country_code)
        try:
            if custom_code is not None and self.customers.get_by_code(custom_code) is not None:
                raise AppError("客户编码已存在", code=40961, status_code=409)
            customer = Customer(
                tenant_id=self.context.tenant_id,
                name=payload.name,
                code=custom_code,
                email=payload.email,
                phone=payload.phone,
                country_code=country_code,
                province=payload.province,
                city=payload.city,
                address=payload.address,
                status=status,
                remark=payload.remark,
            )
            self.customers.add(customer)
            self.session.flush()
            if customer.code is None:
                customer.code = self._auto_code(customer.id)
            if not customer.code:
                raise AppError("客户编码生成失败", code=50021, status_code=500)
            self.session.commit()
            self.session.refresh(customer)
        except IntegrityError:
            self.session.rollback()
            raise AppError("客户编码已存在", code=40961, status_code=409) from None
        except AppError:
            self.session.rollback()
            raise
        except Exception:
            self.session.rollback()
            raise
        return self._to_out(customer)

    def update_customer(self, customer_id: int, payload: CustomerUpdate) -> CustomerOut:
        """编辑档案。不接收 code：创建后编码只读，避免历史订单对不上客户编码。"""
        self.auth.require_all(self.context, (PermissionCode.CUSTOMER_UPDATE,))
        customer = self._require(customer_id)
        if payload.name is not None:
            customer.name = payload.name
        if "country_code" in payload.model_fields_set:
            customer.country_code = self._normalize_country(payload.country_code)
        for field in _OPTIONAL_TEXT_FIELDS:
            if field == "country_code":
                continue
            if field in payload.model_fields_set:
                setattr(customer, field, getattr(payload, field))
        try:
            self.session.commit()
            self.session.refresh(customer)
        except Exception:
            self.session.rollback()
            raise
        return self._to_out(customer)

    def change_status(self, customer_id: int, payload: CustomerStatusUpdate) -> CustomerOut:
        self.auth.require_all(self.context, (PermissionCode.CUSTOMER_DISABLE,))
        customer = self._require(customer_id)
        customer.status = self._normalize_status(payload.status)
        try:
            self.session.commit()
            self.session.refresh(customer)
        except Exception:
            self.session.rollback()
            raise
        return self._to_out(customer)

    def delete_customer(self, customer_id: int) -> None:
        """已被销售订单引用的客户不能删，只能禁用。历史订单还要显示客户名称。"""
        self.auth.require_all(self.context, (PermissionCode.CUSTOMER_DELETE,))
        customer = self._require(customer_id)
        if self.orders.count_by_customer(customer.id) > 0:
            raise AppError(
                "客户已被销售订单引用，不能删除。",
                code=40085,
                status_code=400,
                data={"error": "CUSTOMER_IN_USE"},
            )
        try:
            self.customers.delete(customer)
            self.session.commit()
        except IntegrityError:
            self.session.rollback()
            raise AppError(
                "客户已被销售订单引用，不能删除。",
                code=40085,
                status_code=400,
                data={"error": "CUSTOMER_IN_USE"},
            ) from None
        except Exception:
            self.session.rollback()
            raise

    def _require(self, customer_id: int) -> Customer:
        customer = self.customers.get_in_tenant(customer_id)
        if customer is None:
            raise AppError(_UNAVAILABLE, code=40461, status_code=404)
        return customer

    @staticmethod
    def _auto_code(customer_id: int) -> str:
        return f"{_AUTO_PREFIX}{customer_id:0{_AUTO_WIDTH}d}"

    @staticmethod
    def _normalize_status(value: str) -> str:
        if value not in {item.value for item in CustomerStatus}:
            raise AppError("客户状态不合法", code=40084, status_code=400)
        return value

    @staticmethod
    def _normalize_optional_code(value: str | None) -> str | None:
        if value is None:
            return None
        code = value.strip().upper()
        if not _CUSTOMER_CODE.fullmatch(code):
            raise AppError("客户编码格式不合法", code=40086, status_code=400)
        return code

    @staticmethod
    def _normalize_country(value: str | None) -> str | None:
        if value is None:
            return None
        if not _COUNTRY_CODE.fullmatch(value):
            raise AppError("国家代码必须是 ISO 两位字母，例如 CN", code=40087, status_code=400)
        return value

    @staticmethod
    def _to_out(customer: Customer) -> CustomerOut:
        return CustomerOut(
            id=customer.id,
            tenant_id=customer.tenant_id,
            name=customer.name,
            code=customer.code or "",
            email=customer.email,
            phone=customer.phone,
            country_code=customer.country_code,
            province=customer.province,
            city=customer.city,
            address=customer.address,
            status=customer.status,
            remark=customer.remark,
            created_at=customer.created_at,
            updated_at=customer.updated_at,
        )

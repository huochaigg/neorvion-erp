from fastapi import APIRouter, Query

from app.api.deps import DbSession
from app.api.rbac_deps import (
    CustomerCreateContext,
    CustomerDeleteContext,
    CustomerDisableContext,
    CustomerReadContext,
    CustomerUpdateContext,
)
from app.schemas.common import ApiResponse, ok
from app.schemas.customer import (
    CustomerCreate,
    CustomerListOut,
    CustomerOut,
    CustomerStatusUpdate,
    CustomerUpdate,
)
from app.services.customer import CustomerService

router = APIRouter(prefix="/customers", tags=["customers"])


@router.get("", response_model=ApiResponse[CustomerListOut], summary="客户列表")
def list_customers(
    context: CustomerReadContext,
    session: DbSession,
    q: str | None = Query(default=None, max_length=64),
    status: str | None = Query(default=None, max_length=16),
    country_code: str | None = Query(default=None, max_length=2),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> ApiResponse[CustomerListOut]:
    return ok(
        CustomerService(session, context).list_customers(
            q=q,
            status=status,
            country_code=country_code,
            page=page,
            page_size=page_size,
        )
    )


@router.get("/{customer_id}", response_model=ApiResponse[CustomerOut], summary="客户详情")
def get_customer(
    customer_id: int,
    context: CustomerReadContext,
    session: DbSession,
) -> ApiResponse[CustomerOut]:
    return ok(CustomerService(session, context).get_customer(customer_id))


@router.post("", response_model=ApiResponse[CustomerOut], summary="新增客户")
def create_customer(
    payload: CustomerCreate,
    context: CustomerCreateContext,
    session: DbSession,
) -> ApiResponse[CustomerOut]:
    return ok(CustomerService(session, context).create_customer(payload), "创建成功")


@router.patch("/{customer_id}", response_model=ApiResponse[CustomerOut], summary="编辑客户")
def update_customer(
    customer_id: int,
    payload: CustomerUpdate,
    context: CustomerUpdateContext,
    session: DbSession,
) -> ApiResponse[CustomerOut]:
    return ok(CustomerService(session, context).update_customer(customer_id, payload))


@router.patch(
    "/{customer_id}/status",
    response_model=ApiResponse[CustomerOut],
    summary="启用或禁用客户",
)
def change_customer_status(
    customer_id: int,
    payload: CustomerStatusUpdate,
    context: CustomerDisableContext,
    session: DbSession,
) -> ApiResponse[CustomerOut]:
    return ok(CustomerService(session, context).change_status(customer_id, payload))


@router.delete("/{customer_id}", response_model=ApiResponse[None], summary="删除客户")
def delete_customer(
    customer_id: int,
    context: CustomerDeleteContext,
    session: DbSession,
) -> ApiResponse[None]:
    CustomerService(session, context).delete_customer(customer_id)
    return ok(None, "已删除")

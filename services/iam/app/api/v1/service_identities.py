from fastapi import APIRouter

from app.api.deps import BootstrapDb, PlatformAdmin
from app.schemas.common import ApiResponse, ok
from app.schemas.service_identity import (
    ServiceIdentityCreate,
    ServiceIdentityCreated,
    ServiceIdentityOut,
    ServiceTokenOut,
    ServiceTokenRequest,
)
from app.services.service_identities import ServiceIdentityService

router = APIRouter(tags=["service-identities"])


@router.post("/service-tokens", response_model=ApiResponse[ServiceTokenOut])
def issue_service_token(payload: ServiceTokenRequest, session: BootstrapDb):
    token, ttl = ServiceIdentityService(session).issue(payload)
    return ok(
        ServiceTokenOut(
            access_token=token,
            expires_in=ttl,
            scope=" ".join(sorted(set(payload.scopes))),
        )
    )


@router.get("/service-identities", response_model=ApiResponse[list[ServiceIdentityOut]])
def list_service_identities(_admin: PlatformAdmin, session: BootstrapDb):
    rows = ServiceIdentityService(session).list()
    return ok([ServiceIdentityOut.model_validate(row) for row in rows])


@router.post("/service-identities", response_model=ApiResponse[ServiceIdentityCreated])
def create_service_identity(
    payload: ServiceIdentityCreate, admin: PlatformAdmin, session: BootstrapDb
):
    row, secret = ServiceIdentityService(session).create(payload, admin.id)
    return ok(
        ServiceIdentityCreated(
            identity=ServiceIdentityOut.model_validate(row), client_secret=secret
        ),
        "服务身份已创建，请立即安全保存一次性密钥",
    )


@router.post(
    "/service-identities/{service_id}/rotate",
    response_model=ApiResponse[ServiceIdentityCreated],
)
def rotate_service_identity(service_id: str, admin: PlatformAdmin, session: BootstrapDb):
    row, secret = ServiceIdentityService(session).rotate(service_id, admin.id)
    return ok(
        ServiceIdentityCreated(
            identity=ServiceIdentityOut.model_validate(row), client_secret=secret
        ),
        "服务凭据已轮换，旧 Token 立即失效",
    )


@router.post(
    "/service-identities/{service_id}/revoke",
    response_model=ApiResponse[ServiceIdentityOut],
)
def revoke_service_identity(service_id: str, admin: PlatformAdmin, session: BootstrapDb):
    row = ServiceIdentityService(session).revoke(service_id, admin.id)
    return ok(ServiceIdentityOut.model_validate(row), "服务身份已吊销")

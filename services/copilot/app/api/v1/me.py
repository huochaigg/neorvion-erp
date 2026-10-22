from fastapi import APIRouter

from app.api.deps import CopilotContext
from app.schemas.common import ApiResponse, ok
from app.schemas.identity import CurrentIdentityOut

router = APIRouter(prefix="/me", tags=["me"])


@router.get("", response_model=ApiResponse[CurrentIdentityOut], summary="当前 Copilot 身份")
async def current_identity(context: CopilotContext) -> ApiResponse[CurrentIdentityOut]:
    roles = set(context.role_codes)
    if context.role:
        roles.add(context.role)
    if context.is_owner:
        roles.add("OWNER")
    return ok(
        CurrentIdentityOut(
            user_id=context.user_id,
            tenant_id=context.tenant_id,
            member_id=context.member_id,
            is_owner=context.is_owner,
            roles=sorted(roles),
            permissions=sorted(context.permission_codes),
            authz_version=context.authz_version,
        )
    )


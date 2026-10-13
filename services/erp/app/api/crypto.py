from fastapi import APIRouter, Query

from app.schemas.auth import PublicKeyOut
from app.schemas.common import ApiResponse, ok
from app.services.crypto import issue_public_key

router = APIRouter(prefix="/api/crypto", tags=["crypto"])


@router.get(
    "/public-key",
    response_model=ApiResponse[PublicKeyOut],
    summary="获取 RSA 公钥",
)
def public_key(
    key_id: str | None = Query(default=None, min_length=1, max_length=64),
) -> ApiResponse[PublicKeyOut]:
    """完全公开。不需要 Access Token 或 Refresh Token。

    默认返回当前密钥。指定 key_id 时返回对应仍在服务端加载的公钥。
    未知或已停用的 key_id 返回 404。私钥永不返回。
    """
    return ok(issue_public_key(key_id))

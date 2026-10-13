"""独立校验 ERP 签发的 Access Token 签名。不把 token 当权限快照。"""

from typing import Any

import jwt

from app.core.config import settings
from app.core.exceptions import AppError


def decode_access_token(token: str) -> dict[str, Any]:
    """校验签名、过期时间和 type=access，返回 payload。

    功能：Knowledge 自己验证 JWT，避免只解码不验签。
    参数：浏览器转发的 Access Token。
    返回：含 sub / jti / exp 的 payload。
    异常：过期 40103，签名或类型错误 40102。
    说明：payload 只有 user_id，租户成员与权限必须再走 ERP 内省。
    """
    try:
        payload = jwt.decode(
            token,
            settings.erp_jwt_secret,
            algorithms=[settings.erp_jwt_algorithm],
        )
    except jwt.ExpiredSignatureError as exc:
        raise AppError("登录已过期，请重新登录", code=40103, status_code=401) from exc
    except jwt.InvalidTokenError as exc:
        raise AppError("无效的登录凭证", code=40102, status_code=401) from exc

    if payload.get("type") != "access":
        raise AppError("无效的登录凭证", code=40102, status_code=401)

    subject = payload.get("sub")
    jti = payload.get("jti")
    if not subject or not jti:
        raise AppError("无效的登录凭证", code=40102, status_code=401)
    return payload

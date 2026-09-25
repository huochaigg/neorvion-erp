"""公开接口白名单。只匹配「方法 + 完整路径」，禁止用前缀或模糊包含。"""

from __future__ import annotations

from fastapi import Request

# Refresh 只校验 Cookie 里的 Refresh Token，不能要求 Access Token。
PUBLIC_ROUTES: frozenset[tuple[str, str]] = frozenset(
    {
        ("POST", "/api/v1/auth/register"),
        ("POST", "/api/v1/auth/login"),
        ("GET", "/api/v1/auth/public-key"),
        ("POST", "/api/v1/auth/refresh"),
        ("POST", "/api/v1/auth/logout"),
        ("GET", "/api/v1/health"),
    }
)


def normalize_path(path: str) -> str:
    if path != "/" and path.endswith("/"):
        return path.rstrip("/")
    return path


def is_public_route(method: str, path: str) -> bool:
    return (method.upper(), normalize_path(path)) in PUBLIC_ROUTES


def is_public_request(request: Request) -> bool:
    return is_public_route(request.method, request.url.path)

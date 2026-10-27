"""公开接口白名单。只匹配方法 + 完整路径。"""

from __future__ import annotations

from fastapi import Request

PUBLIC_ROUTES: frozenset[tuple[str, str]] = frozenset(
    {
        ("POST", "/api/v1/auth/register"),
        ("POST", "/api/v1/auth/login"),
        ("GET", "/api/crypto/public-key"),
        ("POST", "/api/v1/auth/refresh"),
        ("POST", "/api/v1/auth/logout"),
        ("GET", "/api/v1/health"),
        ("GET", "/.well-known/jwks.json"),
        ("POST", "/api/v1/internal/permissions/sync"),
        ("POST", "/api/v1/internal/authorize"),
        ("POST", "/api/v1/service-tokens"),
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

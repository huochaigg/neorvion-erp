from __future__ import annotations

from fastapi import Request

PUBLIC_ROUTES: frozenset[tuple[str, str]] = frozenset(
    {
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

from __future__ import annotations

import httpx

from app.core.config import settings


async def model_runtime_status() -> dict[str, str | None]:
    """安全探测 OpenAI-compatible 模型端点，不返回密钥，也不静默切换到 Mock。"""
    provider = settings.model_provider.strip().lower()
    if provider == "mock":
        return {"state": "mock", "provider": "mock", "model": "mock", "detail": "显式开发测试模式"}
    if provider != "openai_compat":
        return {
            "state": "unconfigured",
            "provider": provider,
            "model": settings.chat_model,
            "detail": "Provider 不受支持",
        }
    api_key = settings.resolved_chat_api_key()
    if not api_key or not settings.chat_base_url.strip() or not settings.chat_model.strip():
        return {
            "state": "unconfigured",
            "provider": provider,
            "model": settings.chat_model or None,
            "detail": "模型配置或密钥缺失",
        }
    try:
        timeout = min(5.0, settings.chat_timeout_seconds)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(
                f"{settings.chat_base_url.rstrip('/')}/models",
                headers={"Authorization": f"Bearer {api_key}"},
            )
        if response.status_code < 400:
            return {
                "state": "available",
                "provider": provider,
                "model": settings.chat_model,
                "detail": "模型服务探测成功",
            }
        return {
            "state": "unavailable",
            "provider": provider,
            "model": settings.chat_model,
            "detail": f"模型服务返回 HTTP {response.status_code}",
        }
    except httpx.HTTPError:
        return {
            "state": "unavailable",
            "provider": provider,
            "model": settings.chat_model,
            "detail": "模型服务连接失败",
        }

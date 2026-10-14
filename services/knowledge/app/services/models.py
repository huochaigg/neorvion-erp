"""平台模型配置。密钥只来自环境变量，响应只返回是否已配置。"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.errors import redact_secrets
from app.ai.factory import get_chat_client, get_embedding_client, get_rerank_client
from app.core.config import settings
from app.core.exceptions import AppError
from app.models.rag import ModelKind, ModelProfile
from app.schemas.rag import ModelProfileOut


def _has_key(value: str) -> bool:
    return bool(value.strip())


class ModelService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_profiles(self) -> list[ModelProfileOut]:
        await self._sync_system_profiles()
        rows = list((await self.session.scalars(select(ModelProfile).order_by(ModelProfile.kind))).all())
        return [self._out(item) for item in rows]

    async def test(self, kind: str) -> ModelProfileOut:
        kind_value = kind.strip().upper()
        await self._sync_system_profiles()
        row = await self.session.scalar(
            select(ModelProfile).where(ModelProfile.kind == kind_value, ModelProfile.is_default.is_(True))
        )
        if row is None:
            raise AppError("未找到该类型的默认模型", code=40471, status_code=404)
        ok = False
        message = "ok"
        try:
            if kind_value == ModelKind.EMBEDDING.value:
                message = await self._test_embedding()
            elif kind_value == ModelKind.CHAT.value:
                message = await self._test_chat()
            elif kind_value == ModelKind.RERANK.value:
                message = await self._test_rerank()
            else:
                raise AppError("不支持的模型类型", code=40094, status_code=400)
            ok = True
        except AppError as exc:
            message = redact_secrets(exc.message)
            ok = False
        row.last_tested_at = datetime.now(UTC)
        row.last_test_ok = ok
        row.last_test_message = message
        await self.session.commit()
        await self.session.refresh(row)
        if not ok:
            raise AppError(message, code=50265, status_code=502)
        return self._out(row)

    async def _test_embedding(self) -> str:
        if not settings.resolved_embedding_base_url():
            raise AppError("未配置 Embedding Base URL", code=50360, status_code=503)
        if not settings.resolved_embedding_api_key() and settings.resolved_provider("embedding") != "mock":
            raise AppError("未配置 Embedding API Key", code=50360, status_code=503)
        vectors = await get_embedding_client().embed(["neorvion knowledge ping"])
        dim = len(vectors[0])
        preview = ", ".join(f"{value:.4f}" for value in vectors[0][:4])
        return f"{settings.embedding_model} 返回 {dim} 维，预览 [{preview}, ...]"

    async def _test_chat(self) -> str:
        if not settings.resolved_chat_api_key() and settings.resolved_provider("chat") != "mock":
            raise AppError("未配置 Chat API Key", code=50361, status_code=503)
        parts: list[str] = []
        async for delta in get_chat_client().stream([{"role": "user", "content": "只回复两个字母：ok"}]):
            if delta.text:
                parts.append(delta.text)
            if delta.finished:
                break
        preview = redact_secrets("".join(parts).strip())[:80] or "(空响应)"
        return f"{settings.chat_model} 已响应，预览：{preview}"

    async def _test_rerank(self) -> str:
        client = get_rerank_client()
        if client is None:
            raise AppError("未配置 Rerank 密钥或模型", code=50362, status_code=503)
        hits = await client.rerank(
            "库存预占",
            ["确认订单只增加 reserved_quantity，不扣 quantity。", "量子计算是前沿学科。"],
        )
        if not hits:
            raise AppError("Rerank 未返回结果", code=50266, status_code=502)
        top = hits[0]
        return f"{settings.rerank_model} 返回 {len(hits)} 条，最高分 {top.score:.4f}（index={top.index}）"

    async def _sync_system_profiles(self) -> None:
        specs = [
            (
                ModelKind.EMBEDDING.value,
                "默认 Embedding",
                settings.resolved_provider("embedding"),
                settings.resolved_embedding_base_url(),
                settings.embedding_model,
                settings.embedding_dimensions,
                settings.embedding_api_key_env(),
            ),
            (
                ModelKind.CHAT.value,
                "默认 Chat",
                settings.resolved_provider("chat"),
                settings.resolved_chat_base_url(),
                settings.chat_model,
                None,
                settings.chat_api_key_env(),
            ),
            (
                ModelKind.RERANK.value,
                "默认 Rerank",
                settings.resolved_provider("rerank"),
                settings.resolved_rerank_base_url(),
                settings.rerank_model or "-",
                None,
                settings.rerank_api_key_env(),
            ),
        ]
        for kind, name, provider, base_url, model_name, dimensions, env_name in specs:
            row = await self.session.scalar(
                select(ModelProfile).where(ModelProfile.kind == kind, ModelProfile.is_system.is_(True))
            )
            if row is None:
                self.session.add(
                    ModelProfile(
                        kind=kind,
                        name=name,
                        provider=provider,
                        base_url=base_url,
                        model_name=model_name,
                        dimensions=dimensions,
                        api_key_env=env_name,
                        is_default=True,
                        enabled=True,
                        is_system=True,
                    )
                )
            else:
                row.base_url = base_url
                row.model_name = model_name
                row.dimensions = dimensions
                row.provider = provider
                row.api_key_env = env_name
        await self.session.commit()

    @staticmethod
    def _out(row: ModelProfile) -> ModelProfileOut:
        has_key = False
        if row.kind == ModelKind.EMBEDDING.value:
            has_key = _has_key(settings.resolved_embedding_api_key()) or settings.resolved_provider("embedding") == "mock"
        elif row.kind == ModelKind.CHAT.value:
            has_key = _has_key(settings.resolved_chat_api_key()) or settings.resolved_provider("chat") == "mock"
        elif row.kind == ModelKind.RERANK.value:
            has_key = _has_key(settings.resolved_rerank_api_key()) or settings.resolved_provider("rerank") == "mock"
        return ModelProfileOut(
            id=row.id,
            kind=row.kind,
            name=row.name,
            provider=row.provider,
            base_url=row.base_url,
            model_name=row.model_name,
            dimensions=row.dimensions,
            api_key_env=row.api_key_env,
            has_api_key=has_key,
            is_default=row.is_default,
            enabled=row.enabled,
            is_system=row.is_system,
            last_tested_at=row.last_tested_at,
            last_test_ok=row.last_test_ok,
            last_test_message=row.last_test_message,
        )

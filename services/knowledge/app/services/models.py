"""平台模型配置。密钥只来自环境变量，响应只返回是否已配置。"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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
                vectors = await get_embedding_client().embed(["ping"])
                if len(vectors[0]) != settings.embedding_dimensions:
                    raise AppError("向量维度与配置不一致", code=40090, status_code=400)
            elif kind_value == ModelKind.CHAT.value:
                async for _delta in get_chat_client().stream(
                    [{"role": "user", "content": "只回复：ok"}]
                ):
                    break
            elif kind_value == ModelKind.RERANK.value:
                client = get_rerank_client()
                if client is None:
                    raise AppError("未配置 Rerank", code=50362, status_code=503)
                await client.rerank("ping", ["pong"])
            else:
                raise AppError("不支持的模型类型", code=40094, status_code=400)
            ok = True
        except AppError as exc:
            message = exc.message
            ok = False
        row.last_tested_at = datetime.now(UTC)
        row.last_test_ok = ok
        row.last_test_message = message
        await self.session.commit()
        await self.session.refresh(row)
        if not ok:
            raise AppError(message, code=50265, status_code=502)
        return self._out(row)

    async def _sync_system_profiles(self) -> None:
        specs = [
            (
                ModelKind.EMBEDDING.value,
                "默认 Embedding",
                settings.embedding_base_url,
                settings.embedding_model,
                settings.embedding_dimensions,
                "EMBEDDING_API_KEY",
            ),
            (
                ModelKind.CHAT.value,
                "默认 Chat",
                settings.chat_base_url,
                settings.chat_model,
                None,
                "CHAT_API_KEY",
            ),
            (
                ModelKind.RERANK.value,
                "默认 Rerank",
                settings.rerank_base_url or settings.chat_base_url,
                settings.rerank_model or "-",
                None,
                "RERANK_API_KEY",
            ),
        ]
        for kind, name, base_url, model_name, dimensions, env_name in specs:
            row = await self.session.scalar(
                select(ModelProfile).where(ModelProfile.kind == kind, ModelProfile.is_system.is_(True))
            )
            if row is None:
                self.session.add(
                    ModelProfile(
                        kind=kind,
                        name=name,
                        provider=settings.model_provider,
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
                row.provider = settings.model_provider
                row.api_key_env = env_name
        await self.session.commit()

    @staticmethod
    def _out(row: ModelProfile) -> ModelProfileOut:
        has_key = False
        if row.kind == ModelKind.EMBEDDING.value:
            has_key = _has_key(settings.embedding_api_key) or settings.model_provider == "mock"
        elif row.kind == ModelKind.CHAT.value:
            has_key = _has_key(settings.chat_api_key) or settings.model_provider == "mock"
        elif row.kind == ModelKind.RERANK.value:
            has_key = _has_key(settings.rerank_api_key) or settings.model_provider == "mock"
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

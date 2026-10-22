"""查询向量缓存。只保存成功且维度完整的结果，模型或配置变化后键不同。"""

from __future__ import annotations

import hashlib
import math
import re
import unicodedata
from dataclasses import dataclass

from neorvion_db import ReviewedSql, reviewed_sql_option
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.factory import get_embedding_client
from app.core.config import settings
from app.core.exceptions import AppError
from app.models.rag import QueryEmbeddingCache

_WHITESPACE = re.compile(r"\s+")


@dataclass(frozen=True)
class QueryEmbeddingResult:
    vector: list[float]
    cache_hit: bool
    api_calls: int
    prompt_tokens: int | None
    tokens_estimated: bool


def normalize_query_text(value: str) -> str:
    """折叠空白并做 NFKC。不改变大小写，避免中英文问题被错误合并。"""
    normalized = unicodedata.normalize("NFKC", value).replace("\u00a0", " ")
    return _WHITESPACE.sub(" ", normalized).strip()


def query_cache_key(normalized: str) -> str:
    identity = "\n".join(
        [
            settings.resolved_provider("embedding"),
            settings.resolved_embedding_base_url(),
            settings.embedding_model,
            str(settings.embedding_dimensions),
        ]
    )
    return hashlib.sha256(f"{identity}\n{normalized}".encode()).hexdigest()


def _lock_id(tenant_id: int, cache_key: str) -> int:
    digest = hashlib.sha256(f"{tenant_id}:{cache_key}".encode()).digest()
    return int.from_bytes(digest[:8], "big", signed=True)


def _valid_vector(vector: list[float]) -> bool:
    if len(vector) != settings.embedding_dimensions:
        return False
    return all(isinstance(item, (int, float)) and math.isfinite(float(item)) for item in vector)


def _prompt_tokens(usage: dict | None) -> int | None:
    if not usage:
        return None
    raw = usage.get("prompt_tokens")
    if raw is None:
        raw = usage.get("total_tokens")
    if raw is None:
        return None
    return int(raw)


async def _load(session: AsyncSession, tenant_id: int, cache_key: str) -> QueryEmbeddingCache | None:
    return await session.scalar(
        select(QueryEmbeddingCache).where(
            QueryEmbeddingCache.tenant_id == tenant_id,
            QueryEmbeddingCache.cache_key == cache_key,
        )
    )


def _from_row(row: QueryEmbeddingCache) -> QueryEmbeddingResult | None:
    vector = [float(item) for item in row.embedding or []]
    if not _valid_vector(vector):
        return None
    if row.model_name != settings.embedding_model or row.dimensions != settings.embedding_dimensions:
        return None
    if row.provider != settings.resolved_provider("embedding"):
        return None
    return QueryEmbeddingResult(
        vector=vector,
        cache_hit=True,
        api_calls=0,
        prompt_tokens=None,
        tokens_estimated=False,
    )


async def _embed(texts: list[str]) -> tuple[list[list[float]], dict | None]:
    client = get_embedding_client()
    detailed = getattr(client, "embed_with_usage", None)
    if detailed is not None:
        vectors, usage = await detailed(texts)
        return vectors, usage if isinstance(usage, dict) else None
    return await client.embed(texts), None


async def _read_hit(session: AsyncSession, tenant_id: int, cache_key: str) -> QueryEmbeddingResult | None:
    row = await _load(session, tenant_id, cache_key)
    if row is None:
        return None
    parsed = _from_row(row)
    if parsed is not None:
        return parsed
    await session.delete(row)
    await session.flush()
    return None


async def embed_query(session: AsyncSession, tenant_id: int, text_value: str) -> QueryEmbeddingResult:
    """相同租户、问题和模型配置复用成功向量。并发请求只生成一次。"""
    normalized = normalize_query_text(text_value)
    if not normalized:
        raise AppError("请输入检索内容", code=40091, status_code=400)
    key = query_cache_key(normalized)
    cached = await _read_hit(session, tenant_id, key)
    if cached is not None:
        return cached
    await session.execute(
        text("SELECT pg_advisory_xact_lock(:lock_id)").execution_options(
            **reviewed_sql_option(ReviewedSql.ADVISORY_LOCK)
        ),
        {"lock_id": _lock_id(tenant_id, key)},
    )
    cached = await _read_hit(session, tenant_id, key)
    if cached is not None:
        return cached
    vectors, usage = await _embed([normalized])
    vector = [float(item) for item in vectors[0]] if vectors else []
    if not _valid_vector(vector):
        raise AppError(
            f"查询向量无效或维度不一致：期望 {settings.embedding_dimensions}，实际 {len(vector)}",
            code=40090,
            status_code=400,
        )
    prompt_tokens = _prompt_tokens(usage)
    row = QueryEmbeddingCache(
        tenant_id=tenant_id,
        cache_key=key,
        provider=settings.resolved_provider("embedding"),
        model_name=settings.embedding_model,
        dimensions=settings.embedding_dimensions,
        embedding=vector,
        prompt_tokens=prompt_tokens,
    )
    try:
        async with session.begin_nested():
            session.add(row)
            await session.flush()
    except IntegrityError:
        stored = await _read_hit(session, tenant_id, key)
        if stored is not None:
            return stored
        raise
    return QueryEmbeddingResult(
        vector=vector,
        cache_hit=False,
        api_calls=1,
        prompt_tokens=prompt_tokens,
        tokens_estimated=False,
    )

"""查询向量缓存与传输错误分类。只使用 Mock，不调用收费 Embedding。"""

from __future__ import annotations

import asyncio

import httpx
import pytest
from app.ai.errors import describe_embedding_transport
from app.core.config import settings
from app.core.event_loop import selector_loop_factory
from app.core.exceptions import AppError
from app.core.tenant import TenantContext
from app.db.session import SessionLocal
from app.services.query_embedding_cache import embed_query, normalize_query_text, query_cache_key
from app.services.retrieval import RetrievalService


def _run(coro):
    return asyncio.run(coro, loop_factory=selector_loop_factory)


def _context() -> TenantContext:
    return TenantContext(
        user_id=1,
        tenant_id=1,
        member_id=1,
        is_owner=True,
        role="OWNER",
        permission_codes=frozenset(),
        token_jti="query-cache-test",
    )


def test_transport_errors_keep_their_kind() -> None:
    dns = describe_embedding_transport(httpx.ConnectError("getaddrinfo failed"))
    refused = describe_embedding_transport(httpx.ConnectError("Connection refused"))
    timeout = describe_embedding_transport(httpx.ReadTimeout("timed out"))
    reset = describe_embedding_transport(httpx.RemoteProtocolError("connection closed"))
    assert dns.code == 50262
    assert "域名无法解析" in dns.message
    assert "Base URL" not in dns.message
    assert refused.code == 50262
    assert "拒绝连接" in refused.message
    assert timeout.code == 50460
    assert reset.code == 50262
    assert "中断" in reset.message


def test_cache_key_changes_with_model_and_normalizes_space() -> None:
    assert normalize_query_text("  销售  订单\nDRAFT  ") == "销售 订单 DRAFT"
    left = query_cache_key(normalize_query_text("  销售订单 DRAFT "))
    right = query_cache_key(normalize_query_text("销售订单 DRAFT"))
    assert left == right


def test_query_embedding_cache_hit_isolation_and_failures(monkeypatch) -> None:
    _run(_query_embedding_cache_hit_isolation_and_failures(monkeypatch))


async def _query_embedding_cache_hit_isolation_and_failures(monkeypatch) -> None:
    calls = {"n": 0, "fail_left": 1}
    monkeypatch.setattr(settings, "embedding_model", "mock-embed")
    monkeypatch.setattr(settings, "embedding_dimensions", 8)

    class Client:
        async def embed_with_usage(self, texts: list[str]):
            calls["n"] += 1
            if texts == ["失败一次"] and calls["fail_left"] > 0:
                calls["fail_left"] -= 1
                raise AppError("无法建立到 Embedding 服务的连接（ConnectError）", code=50262, status_code=502)
            if texts == ["坏向量"]:
                return [[0.1, 0.2]], {"prompt_tokens": 9}
            return [[0.1] * settings.embedding_dimensions], {"prompt_tokens": 4}

    monkeypatch.setattr("app.services.query_embedding_cache.get_embedding_client", lambda: Client())

    async with SessionLocal() as session:
        first = await embed_query(session, 3, "  销售订单   DRAFT ")
        await session.commit()
    async with SessionLocal() as session:
        second = await embed_query(session, 3, "销售订单 DRAFT")
        await session.commit()
    assert calls["n"] == 1
    assert first.cache_hit is False
    assert first.api_calls == 1
    assert first.prompt_tokens == 4
    assert second.cache_hit is True
    assert second.api_calls == 0
    assert second.prompt_tokens is None
    assert second.vector == first.vector

    monkeypatch.setattr(settings, "embedding_model", "other-model")
    async with SessionLocal() as session:
        other_model = await embed_query(session, 3, "销售订单 DRAFT")
        await session.commit()
    assert calls["n"] == 2
    assert other_model.cache_hit is False

    monkeypatch.setattr(settings, "embedding_model", "mock-embed")
    async with SessionLocal() as session:
        other_tenant = await embed_query(session, 9, "销售订单 DRAFT")
        await session.commit()
    assert calls["n"] == 3
    assert other_tenant.cache_hit is False

    with pytest.raises(AppError) as failed:
        async with SessionLocal() as session:
            await embed_query(session, 3, "失败一次")
            await session.commit()
    assert failed.value.code == 50262
    async with SessionLocal() as session:
        recovered = await embed_query(session, 3, "失败一次")
        await session.commit()
    assert calls["n"] == 5
    assert recovered.cache_hit is False

    with pytest.raises(AppError) as invalid:
        async with SessionLocal() as session:
            await embed_query(session, 3, "坏向量")
    assert invalid.value.code == 40090
    async with SessionLocal() as session:
        class Good:
            async def embed_with_usage(self, texts: list[str]):
                calls["n"] += 1
                return [[0.2] * settings.embedding_dimensions], None

        monkeypatch.setattr("app.services.query_embedding_cache.get_embedding_client", lambda: Good())
        again = await embed_query(session, 3, "坏向量")
        await session.commit()
    assert again.cache_hit is False
    assert again.prompt_tokens is None
    assert calls["n"] == 7


def test_same_query_is_embedded_once_under_concurrency(monkeypatch) -> None:
    _run(_same_query_is_embedded_once_under_concurrency(monkeypatch))


async def _same_query_is_embedded_once_under_concurrency(monkeypatch) -> None:
    calls = {"n": 0}
    started = asyncio.Event()
    release = asyncio.Event()

    class Slow:
        async def embed(self, texts: list[str]):
            calls["n"] += 1
            started.set()
            await release.wait()
            return [[0.3] * settings.embedding_dimensions]

    monkeypatch.setattr("app.services.query_embedding_cache.get_embedding_client", lambda: Slow())

    async def once():
        async with SessionLocal() as session:
            result = await embed_query(session, 4, "并发问题")
            await session.commit()
            return result

    first = asyncio.create_task(once())
    await started.wait()
    second = asyncio.create_task(once())
    await asyncio.sleep(0.05)
    release.set()
    left, right = await asyncio.gather(first, second)
    assert calls["n"] == 1
    assert left.vector == right.vector
    assert {left.cache_hit, right.cache_hit} == {False, True}


def test_keyword_search_does_not_embed(monkeypatch) -> None:
    _run(_keyword_search_does_not_embed(monkeypatch))


async def _keyword_search_does_not_embed(monkeypatch) -> None:
    calls = {"n": 0}

    async def embed_query_stub(*_args, **_kwargs):
        calls["n"] += 1
        raise AppError("不应调用 Embedding", code=50000, status_code=500)

    monkeypatch.setattr("app.services.retrieval.embed_query", embed_query_stub)
    async with SessionLocal() as session:
        service = RetrievalService(session, _context())

        async def bases(_ids):
            return [1]

        async def keyword(*_args, **_kwargs):
            return []

        async def ready(_ids):
            return 1

        service._authorized_base_ids = bases  # type: ignore[method-assign]
        service._keyword_search = keyword  # type: ignore[method-assign]
        service._ready_vector_count = ready  # type: ignore[method-assign]
        result = await service.search(
            "销售订单",
            knowledge_base_ids=[1],
            strategy="KEYWORD",
            persist_log=False,
        )
        assert result.hits == []
        assert calls["n"] == 0
        assert result.stages["embedding_api_calls"] == 0
        with pytest.raises(AppError) as exc:
            await service.search(
                "销售订单",
                knowledge_base_ids=[1],
                strategy="VECTOR",
                persist_log=False,
            )
        assert exc.value.code == 50000
        assert calls["n"] == 1

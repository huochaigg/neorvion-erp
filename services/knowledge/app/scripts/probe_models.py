"""真实探测 Chat / Embedding / Rerank。不打印密钥。"""

from __future__ import annotations

import asyncio

from app.ai.dashscope import DashScopeRerankClient, dashscope_rerank_url
from app.ai.openai_compat import OpenAICompatChatClient, OpenAICompatEmbeddingClient
from app.core.config import Settings
from app.core.exceptions import AppError


def _mask_url(url: str) -> str:
    return url.replace("https://", "").split("/")[0]


async def _probe_chat(settings: Settings) -> str:
    client = OpenAICompatChatClient(
        base_url=settings.resolved_chat_base_url(),
        api_key=settings.resolved_chat_api_key(),
        model=settings.chat_model,
    )
    parts: list[str] = []
    async for delta in client.stream([{"role": "user", "content": "只回复两个字母：ok"}]):
        if delta.text:
            parts.append(delta.text)
        if delta.finished:
            break
    preview = "".join(parts).strip()[:80] or "(空)"
    return f"OK 预览={preview}"


async def _probe_embedding(settings: Settings) -> str:
    client = OpenAICompatEmbeddingClient(
        base_url=settings.resolved_embedding_base_url(),
        api_key=settings.resolved_embedding_api_key(),
        model=settings.embedding_model,
    )
    vectors = await client.embed(["neorvion knowledge ping"])
    return f"OK dim={len(vectors[0])}"


async def _probe_rerank(settings: Settings) -> str:
    client = DashScopeRerankClient(
        base_url=settings.resolved_rerank_base_url(),
        api_key=settings.resolved_rerank_api_key(),
        model=settings.rerank_model,
    )
    hits = await client.rerank("库存预占", ["确认订单只预占 reserved_quantity。", "量子计算。"])
    top = hits[0] if hits else None
    return f"OK count={len(hits)} top={top.score if top else None}"


async def main() -> int:
    settings = Settings()
    print(f"chat model={settings.chat_model} host={_mask_url(settings.resolved_chat_base_url())} key={bool(settings.resolved_chat_api_key())}")
    print(
        f"embedding model={settings.embedding_model} dim={settings.embedding_dimensions} "
        f"host={_mask_url(settings.resolved_embedding_base_url())} key={bool(settings.resolved_embedding_api_key())}"
    )
    rerank_url = ""
    try:
        rerank_url = dashscope_rerank_url(settings.resolved_rerank_base_url())
    except AppError as exc:
        rerank_url = exc.message
    print(f"rerank model={settings.rerank_model} url_ok={rerank_url.endswith('text-rerank')} key={bool(settings.resolved_rerank_api_key())}")
    code = 0
    for name, factory in (
        ("CHAT", _probe_chat),
        ("EMBEDDING", _probe_embedding),
        ("RERANK", _probe_rerank),
    ):
        try:
            detail = await factory(settings)
            print(f"{name}: {detail}")
        except AppError as exc:
            print(f"{name}: FAIL {exc.message}")
            code = 1
        except Exception as exc:  # noqa: BLE001
            print(f"{name}: FAIL {type(exc).__name__}")
            code = 1
    return code


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

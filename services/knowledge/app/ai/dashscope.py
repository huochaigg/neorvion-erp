"""阿里云百炼 DashScope 原生协议客户端。Rerank 不得走 Chat Completions。"""

from __future__ import annotations

import json
from urllib.parse import urlparse

import httpx

from app.ai.errors import classify_model_http_error
from app.ai.types import RerankHit
from app.core.config import settings
from app.core.exceptions import AppError

_RERANK_PATH = "/api/v1/services/rerank/text-rerank/text-rerank"


def dashscope_rerank_url(base_url: str) -> str:
    """从百炼工作空间 host 或完整地址推导原生 Rerank URL，不臆造地域。"""
    raw = (base_url or "").strip().rstrip("/")
    if not raw:
        raise AppError("未配置 Rerank Base URL，且无法从 Embedding 地址推导", code=50363, status_code=503)
    if raw.endswith(_RERANK_PATH):
        return raw
    parsed = urlparse(raw)
    origin = f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else raw
    path = parsed.path.rstrip("/")
    if path.endswith("/compatible-mode/v1"):
        return f"{origin}{_RERANK_PATH}"
    if path.endswith("/api/v1"):
        return f"{origin}/api/v1/services/rerank/text-rerank/text-rerank"
    if "maas.aliyuncs.com" in origin or "dashscope.aliyuncs.com" in origin:
        return f"{origin}{_RERANK_PATH}"
    raise AppError("无法从当前 Base URL 推导百炼 Rerank 地址，请显式配置 RERANK_BASE_URL", code=50364, status_code=503)


class DashScopeRerankClient:
    """POST .../services/rerank/text-rerank/text-rerank，body 为 model + input + parameters。"""

    def __init__(self, *, base_url: str, api_key: str, model: str) -> None:
        self.url = dashscope_rerank_url(base_url)
        self.api_key = api_key
        self.model = model

    async def rerank(self, query: str, documents: list[str]) -> list[RerankHit]:
        if not self.api_key:
            raise AppError("未配置 Rerank API Key", code=50362, status_code=503)
        if not self.model:
            raise AppError("未配置 Rerank 模型", code=50362, status_code=503)
        payload = {
            "model": self.model,
            "input": {"query": query, "documents": documents},
            "parameters": {"top_n": len(documents), "return_documents": False},
        }
        try:
            async with httpx.AsyncClient(timeout=settings.model_timeout_seconds) as client:
                response = await client.post(
                    self.url,
                    json=payload,
                    headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                )
        except httpx.TimeoutException as exc:
            raise AppError("Rerank 超时", code=50460, status_code=504) from exc
        except httpx.HTTPError as exc:
            raise AppError("无法连接 Rerank 服务，请检查 Base URL", code=50262, status_code=502) from exc
        if response.status_code >= 400:
            raise classify_model_http_error(response.status_code, response.text)
        data = response.json()
        if data.get("code"):
            raise classify_model_http_error(400, json.dumps(data, ensure_ascii=False))
        output = data.get("output") if isinstance(data.get("output"), dict) else data
        results = (output or {}).get("results") or []
        hits: list[RerankHit] = []
        for row in results:
            if not isinstance(row, dict):
                continue
            raw_index = row.get("index")
            raw_score = row.get("relevance_score")
            index = int(raw_index if raw_index is not None else 0)
            score = float(raw_score if raw_score is not None else 0)
            hits.append(RerankHit(index=index, score=score))
        hits.sort(key=lambda item: item.score, reverse=True)
        return hits

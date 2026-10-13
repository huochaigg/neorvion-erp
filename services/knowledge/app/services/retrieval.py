"""检索引擎。VECTOR / KEYWORD / HYBRID 共用同一实现；租户过滤在 SQL 内完成。"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.factory import get_embedding_client, get_rerank_client
from app.core.config import settings
from app.core.exceptions import AppError
from app.core.tenant import TenantContext
from app.models.knowledge import (
    ChunkStatus,
    DocumentChunk,
    KnowledgeBase,
    KnowledgeBaseStatus,
    KnowledgeDocument,
)
from app.models.rag import ChunkEmbedding, EmbeddingStatus, RetrievalLog, RetrievalStrategy
from app.repositories.knowledge import KnowledgeBaseRepository

logger = logging.getLogger(__name__)

_LATIN = re.compile(r"[A-Za-z0-9]+")


@dataclass
class RetrievedHit:
    chunk_id: int
    document_id: int
    knowledge_base_id: int
    filename: str
    content: str
    page_no: int | None
    heading: str | None
    chunk_index: int
    version: int
    vector_score: float | None = None
    keyword_score: float | None = None
    rrf_score: float | None = None
    rerank_score: float | None = None
    vector_rank: int | None = None
    keyword_rank: int | None = None
    final_rank: int = 0


@dataclass
class RetrievalResult:
    hits: list[RetrievedHit]
    strategy: str
    rerank_applied: bool
    rerank_degraded: bool
    stages: dict = field(default_factory=dict)
    latency_ms: int = 0
    knowledge_base_ids: list[int] = field(default_factory=list)


class RetrievalService:
    def __init__(self, session: AsyncSession, context: TenantContext) -> None:
        self.session = session
        self.context = context
        self.bases = KnowledgeBaseRepository(session, context.tenant_id)

    async def search(
        self,
        query: str,
        *,
        knowledge_base_ids: list[int] | None,
        strategy: str,
        top_k: int | None = None,
        candidate_k: int | None = None,
        similarity_threshold: float | None = None,
        rerank: bool = False,
        persist_log: bool = True,
        conversation_id: int | None = None,
        message_id: int | None = None,
    ) -> RetrievalResult:
        started = time.perf_counter()
        text_query = query.strip()
        if not text_query:
            raise AppError("请输入检索内容", code=40091, status_code=400)
        strategy_value = text_query and strategy.strip().upper()
        if strategy_value not in {
            RetrievalStrategy.VECTOR.value,
            RetrievalStrategy.KEYWORD.value,
            RetrievalStrategy.HYBRID.value,
        }:
            raise AppError("不支持的检索策略", code=40092, status_code=400)
        top_k = top_k or settings.default_top_k
        candidate_k = max(candidate_k or settings.default_candidate_k, top_k)
        allowed = await self._authorized_base_ids(knowledge_base_ids)
        if not allowed:
            latency_ms = int((time.perf_counter() - started) * 1000)
            return RetrievalResult(
                hits=[],
                strategy=strategy_value,
                rerank_applied=False,
                rerank_degraded=False,
                stages={"empty_bases": True},
                latency_ms=latency_ms,
                knowledge_base_ids=[],
            )

        vector_hits: list[RetrievedHit] = []
        keyword_hits: list[RetrievedHit] = []
        stages: dict = {}
        if strategy_value in {RetrievalStrategy.VECTOR.value, RetrievalStrategy.HYBRID.value}:
            t0 = time.perf_counter()
            vector_hits = await self._vector_search(
                text_query, allowed, candidate_k, similarity_threshold
            )
            stages["vector_ms"] = int((time.perf_counter() - t0) * 1000)
            stages["vector_ranks"] = [
                {"chunk_id": item.chunk_id, "rank": item.vector_rank, "similarity": item.vector_score}
                for item in vector_hits
            ]
        if strategy_value in {RetrievalStrategy.KEYWORD.value, RetrievalStrategy.HYBRID.value}:
            t0 = time.perf_counter()
            keyword_hits = await self._keyword_search(text_query, allowed, candidate_k)
            stages["keyword_ms"] = int((time.perf_counter() - t0) * 1000)
            stages["keyword_ranks"] = [
                {"chunk_id": item.chunk_id, "rank": item.keyword_rank, "score": item.keyword_score}
                for item in keyword_hits
            ]

        if strategy_value == RetrievalStrategy.VECTOR.value:
            fused = vector_hits
        elif strategy_value == RetrievalStrategy.KEYWORD.value:
            fused = keyword_hits
        else:
            fused = self._rrf(vector_hits, keyword_hits)
            stages["rrf_ranks"] = [
                {"chunk_id": item.chunk_id, "rrf": item.rrf_score} for item in fused
            ]

        rerank_applied = False
        rerank_degraded = False
        if rerank and fused:
            t0 = time.perf_counter()
            fused, rerank_applied, rerank_degraded = await self._maybe_rerank(text_query, fused)
            stages["rerank_ms"] = int((time.perf_counter() - t0) * 1000)
            stages["rerank_applied"] = rerank_applied
            stages["rerank_degraded"] = rerank_degraded

        hits = fused[:top_k]
        for index, hit in enumerate(hits, start=1):
            hit.final_rank = index
        latency_ms = int((time.perf_counter() - started) * 1000)
        result = RetrievalResult(
            hits=hits,
            strategy=strategy_value,
            rerank_applied=rerank_applied,
            rerank_degraded=rerank_degraded,
            stages=stages,
            latency_ms=latency_ms,
            knowledge_base_ids=allowed,
        )
        if persist_log:
            self.session.add(
                RetrievalLog(
                    tenant_id=self.context.tenant_id,
                    user_id=self.context.user_id,
                    conversation_id=conversation_id,
                    message_id=message_id,
                    query=text_query,
                    strategy=strategy_value,
                    knowledge_base_ids=allowed,
                    params={
                        "top_k": top_k,
                        "candidate_k": candidate_k,
                        "similarity_threshold": similarity_threshold,
                        "rerank": rerank,
                    },
                    stages=stages,
                    latency_ms=latency_ms,
                )
            )
            await self.session.commit()
        return result

    async def _authorized_base_ids(self, requested: list[int] | None) -> list[int]:
        rows, _ = await self.bases.list_page(q=None, status=KnowledgeBaseStatus.ACTIVE.value, page=1, page_size=100)
        allowed = {item.id for item in rows}
        if not requested:
            return sorted(allowed)
        unknown = [item for item in requested if item not in allowed]
        if unknown:
            raise AppError("包含无权访问或不存在的知识库", code=40450, status_code=404)
        return [item for item in requested if item in allowed]

    def _visible_chunk_filters(self, base_ids: list[int]):
        tenant_id = self.context.tenant_id
        return [
            DocumentChunk.tenant_id == tenant_id,
            DocumentChunk.status == ChunkStatus.ACTIVE.value,
            DocumentChunk.enabled.is_(True),
            DocumentChunk.knowledge_base_id.in_(base_ids),
            KnowledgeDocument.tenant_id == tenant_id,
            KnowledgeDocument.deleted_at.is_(None),
            KnowledgeDocument.id == DocumentChunk.document_id,
            KnowledgeDocument.active_chunk_version == DocumentChunk.version,
            KnowledgeBase.tenant_id == tenant_id,
            KnowledgeBase.id == DocumentChunk.knowledge_base_id,
            KnowledgeBase.deleted_at.is_(None),
            KnowledgeBase.status == KnowledgeBaseStatus.ACTIVE.value,
        ]

    async def _vector_search(
        self,
        query: str,
        base_ids: list[int],
        limit: int,
        similarity_threshold: float | None,
    ) -> list[RetrievedHit]:
        vectors = await get_embedding_client().embed([query])
        if not vectors or len(vectors[0]) != settings.embedding_dimensions:
            raise AppError("查询向量维度与索引不一致，请重建索引", code=40090, status_code=400)
        query_vector = vectors[0]
        distance = ChunkEmbedding.embedding.cosine_distance(query_vector)
        similarity = (1 - distance).label("similarity")
        stmt = (
            select(
                DocumentChunk,
                KnowledgeDocument.filename,
                similarity,
            )
            .join(
                ChunkEmbedding,
                and_(
                    ChunkEmbedding.tenant_id == DocumentChunk.tenant_id,
                    ChunkEmbedding.chunk_id == DocumentChunk.id,
                ),
            )
            .join(KnowledgeDocument, KnowledgeDocument.id == DocumentChunk.document_id)
            .join(KnowledgeBase, KnowledgeBase.id == DocumentChunk.knowledge_base_id)
            .where(
                *self._visible_chunk_filters(base_ids),
                ChunkEmbedding.tenant_id == self.context.tenant_id,
                ChunkEmbedding.status == EmbeddingStatus.READY.value,
                ChunkEmbedding.model_name == settings.embedding_model,
                ChunkEmbedding.dimensions == settings.embedding_dimensions,
            )
            .order_by(distance.asc())
            .limit(limit)
        )
        if similarity_threshold is not None:
            stmt = stmt.where(similarity >= similarity_threshold)
        rows = (await self.session.execute(stmt)).all()
        hits: list[RetrievedHit] = []
        for rank, (chunk, filename, score) in enumerate(rows, start=1):
            hits.append(
                self._hit_from_chunk(
                    chunk,
                    filename=filename,
                    vector_score=float(score) if score is not None else None,
                    vector_rank=rank,
                )
            )
        return hits

    async def _keyword_search(self, query: str, base_ids: list[int], limit: int) -> list[RetrievedHit]:
        """PostgreSQL simple FTS + trigram。这不是 BM25。"""
        latin = " & ".join(_LATIN.findall(query))
        tsquery = func.to_tsquery("simple", latin) if latin else None
        fts_rank = func.ts_rank_cd(DocumentChunk.search_tsv, tsquery) if tsquery is not None else 0
        trgm = func.similarity(DocumentChunk.content, query)
        combined = func.greatest(func.coalesce(fts_rank, 0), func.coalesce(trgm, 0)).label("keyword_score")
        conditions = list(self._visible_chunk_filters(base_ids))
        matchers = [
            DocumentChunk.content.ilike(f"%{query}%"),
            DocumentChunk.content.op("%")(query),
        ]
        if tsquery is not None:
            matchers.append(DocumentChunk.search_tsv.op("@@")(tsquery))
        conditions.append(or_(*matchers))
        stmt = (
            select(DocumentChunk, KnowledgeDocument.filename, combined)
            .join(KnowledgeDocument, KnowledgeDocument.id == DocumentChunk.document_id)
            .join(KnowledgeBase, KnowledgeBase.id == DocumentChunk.knowledge_base_id)
            .where(*conditions)
            .order_by(combined.desc())
            .limit(limit)
        )
        rows = (await self.session.execute(stmt)).all()
        hits: list[RetrievedHit] = []
        for rank, (chunk, filename, score) in enumerate(rows, start=1):
            hits.append(
                self._hit_from_chunk(
                    chunk,
                    filename=filename,
                    keyword_score=float(score) if score is not None else 0.0,
                    keyword_rank=rank,
                )
            )
        return hits

    def _rrf(self, vector_hits: list[RetrievedHit], keyword_hits: list[RetrievedHit]) -> list[RetrievedHit]:
        k = settings.rrf_k
        merged: dict[int, RetrievedHit] = {}
        for hit in vector_hits + keyword_hits:
            current = merged.get(hit.chunk_id)
            if current is None:
                merged[hit.chunk_id] = RetrievedHit(
                    chunk_id=hit.chunk_id,
                    document_id=hit.document_id,
                    knowledge_base_id=hit.knowledge_base_id,
                    filename=hit.filename,
                    content=hit.content,
                    page_no=hit.page_no,
                    heading=hit.heading,
                    chunk_index=hit.chunk_index,
                    version=hit.version,
                    vector_score=hit.vector_score,
                    keyword_score=hit.keyword_score,
                    vector_rank=hit.vector_rank,
                    keyword_rank=hit.keyword_rank,
                    rrf_score=0.0,
                )
                current = merged[hit.chunk_id]
            else:
                if hit.vector_score is not None:
                    current.vector_score = hit.vector_score
                    current.vector_rank = hit.vector_rank
                if hit.keyword_score is not None:
                    current.keyword_score = hit.keyword_score
                    current.keyword_rank = hit.keyword_rank
            rrf = current.rrf_score or 0.0
            if hit.vector_rank:
                rrf += 1.0 / (k + hit.vector_rank)
            if hit.keyword_rank:
                rrf += 1.0 / (k + hit.keyword_rank)
            current.rrf_score = rrf
        ranked = sorted(merged.values(), key=lambda item: item.rrf_score or 0.0, reverse=True)
        return ranked

    async def _maybe_rerank(
        self,
        query: str,
        hits: list[RetrievedHit],
    ) -> tuple[list[RetrievedHit], bool, bool]:
        client = get_rerank_client()
        if client is None:
            return hits, False, True
        try:
            ranked = await client.rerank(query, [item.content for item in hits])
        except Exception:
            logger.warning("rerank degraded tenant=%s", self.context.tenant_id)
            return hits, False, True
        by_index = {item.index: item.score for item in ranked}
        for index, hit in enumerate(hits):
            hit.rerank_score = by_index.get(index)
        hits.sort(key=lambda item: item.rerank_score if item.rerank_score is not None else -1.0, reverse=True)
        return hits, True, False

    @staticmethod
    def _hit_from_chunk(
        chunk: DocumentChunk,
        *,
        filename: str,
        vector_score: float | None = None,
        keyword_score: float | None = None,
        vector_rank: int | None = None,
        keyword_rank: int | None = None,
    ) -> RetrievedHit:
        return RetrievedHit(
            chunk_id=chunk.id,
            document_id=chunk.document_id,
            knowledge_base_id=chunk.knowledge_base_id,
            filename=filename,
            content=chunk.content,
            page_no=chunk.page_no,
            heading=chunk.heading,
            chunk_index=chunk.chunk_index,
            version=chunk.version,
            vector_score=vector_score,
            keyword_score=keyword_score,
            vector_rank=vector_rank,
            keyword_rank=keyword_rank,
        )

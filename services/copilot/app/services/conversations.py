from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import AppError
from app.core.tenant import TenantContext
from app.knowledge.client import KnowledgeApiClient
from app.models.conversation import Conversation
from app.repositories.conversations import ConversationRepository
from app.schemas.conversation import (
    ConversationDetailOut,
    ConversationListOut,
    ConversationOut,
    EvidenceOut,
    MessageOut,
    ToolRunOut,
)


class ConversationService:
    def __init__(
        self,
        session: AsyncSession,
        context: TenantContext,
        *,
        knowledge_client: KnowledgeApiClient | None = None,
        access_token: str = "",
        knowledge_audience_authorized: bool = False,
        request_id: str = "",
    ) -> None:
        self.session = session
        self.repo = ConversationRepository(session, context.tenant_id, context.user_id)
        self.context = context
        self.knowledge_client = knowledge_client
        self.access_token = access_token
        self.knowledge_audience_authorized = knowledge_audience_authorized
        self.request_id = request_id

    @staticmethod
    def _out(row: Conversation) -> ConversationOut:
        return ConversationOut.model_validate(row, from_attributes=True)

    async def create(self, title: str) -> ConversationOut:
        row = await self.repo.create(title.strip())
        await self.session.commit()
        return self._out(row)

    async def list(self, page: int, page_size: int) -> ConversationListOut:
        rows, total = await self.repo.list(page, page_size)
        return ConversationListOut(items=[self._out(row) for row in rows], total=total, page=page, page_size=page_size)

    async def get(self, conversation_id: int) -> ConversationDetailOut:
        row = await self.repo.get(conversation_id)
        if row is None:
            raise AppError("会话不存在", code=40480, status_code=404)
        messages = await self.repo.messages(conversation_id)
        runs = await self.repo.tool_runs(conversation_id)
        evidence_rows = await self.repo.evidences(conversation_id)
        by_message: dict[int, list[ToolRunOut]] = {}
        for run in runs:
            by_message.setdefault(run.message_id, []).append(ToolRunOut.model_validate(run, from_attributes=True))
        evidence_by_message: dict[int, list[EvidenceOut]] = {}
        try:
            outputs = await asyncio.wait_for(
                asyncio.gather(*(self._evidence_out(item) for item in evidence_rows)),
                timeout=settings.knowledge_history_revalidation_timeout_seconds,
            )
        except TimeoutError:
            outputs = [self._evidence_out_without_knowledge(item) for item in evidence_rows]
        for evidence, output in zip(evidence_rows, outputs, strict=True):
            evidence_by_message.setdefault(evidence.message_id, []).append(output)
        return ConversationDetailOut(
            **self._out(row).model_dump(),
            messages=[MessageOut(**{
                "id": item.id, "role": item.role, "content": item.content, "status": item.status,
                "request_id": item.request_id, "created_at": item.created_at, "updated_at": item.updated_at,
                "tool_runs": by_message.get(item.id, []),
                "evidences": evidence_by_message.get(item.id, []),
            }) for item in messages],
        )

    async def _evidence_out(self, row) -> EvidenceOut:
        """历史 Knowledge 证据展示前重新鉴权；失权或删除时不返回旧摘录。"""
        status = "ACTIVE"
        excerpt = row.excerpt
        if row.source_type == "KNOWLEDGE":
            if not self.knowledge_client or not self.access_token or not self.knowledge_audience_authorized:
                status, excerpt = "FORBIDDEN", None
            else:
                try:
                    current = await self.knowledge_client.get_chunk(
                        row.chunk_id,
                        access_token=self.access_token,
                        tenant_id=self.context.tenant_id,
                        request_id=self.request_id,
                    )
                except AppError as exc:
                    if exc.status_code == 404:
                        status = "MISSING"
                    elif exc.status_code == 403:
                        status = "FORBIDDEN"
                    else:
                        status = "UNAVAILABLE"
                    excerpt = None
                else:
                    if current.get("knowledge_base_id") != row.knowledge_base_id or current.get("document_id") != row.document_id:
                        status, excerpt = "MISSING", None
                    elif current.get("version") != row.source_version:
                        status = "STALE"
        return EvidenceOut(
            citation_id=row.citation_id,
            source_type=row.source_type,
            resource_type=row.resource_type,
            resource_id=row.resource_id,
            knowledge_base_id=row.knowledge_base_id,
            document_id=row.document_id,
            chunk_id=row.chunk_id,
            title=row.title,
            excerpt=excerpt,
            source_version=row.source_version,
            metadata=row.evidence_metadata,
            observed_at=row.observed_at,
            access_status=status,
        )

    @staticmethod
    def _evidence_out_without_knowledge(row) -> EvidenceOut:
        """整批来源复核超时时采用拒绝展示策略，ERP 本地快照仍可正常返回。"""
        knowledge = row.source_type == "KNOWLEDGE"
        return EvidenceOut(
            citation_id=row.citation_id,
            source_type=row.source_type,
            resource_type=row.resource_type,
            resource_id=row.resource_id,
            knowledge_base_id=row.knowledge_base_id,
            document_id=row.document_id,
            chunk_id=row.chunk_id,
            title=row.title,
            excerpt=None if knowledge else row.excerpt,
            source_version=row.source_version,
            metadata=row.evidence_metadata,
            observed_at=row.observed_at,
            access_status="UNAVAILABLE" if knowledge else "ACTIVE",
        )

    async def rename(self, conversation_id: int, title: str) -> ConversationOut:
        row = await self.repo.get(conversation_id, lock=True)
        if row is None:
            raise AppError("会话不存在", code=40480, status_code=404)
        row.title = title.strip()
        await self.session.commit()
        return self._out(row)

    async def delete(self, conversation_id: int) -> None:
        row = await self.repo.get(conversation_id, lock=True)
        if row is None:
            raise AppError("会话不存在", code=40480, status_code=404)
        row.status = "DELETED"
        row.deleted_at = datetime.now(UTC)
        await self.session.commit()

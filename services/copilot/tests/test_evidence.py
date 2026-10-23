from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, cast

import pytest
from app.core.exceptions import AppError
from app.services.conversations import ConversationService


def evidence_row(**overrides):
    values = {
        "citation_id": "K1",
        "source_type": "KNOWLEDGE",
        "resource_type": "knowledge_chunk",
        "resource_id": "31",
        "knowledge_base_id": 11,
        "document_id": 21,
        "chunk_id": 31,
        "title": "制度.md",
        "excerpt": "检索时的原文",
        "source_version": 4,
        "evidence_metadata": {"page_no": 2},
        "observed_at": datetime.now(UTC),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class ChunkClient:
    def __init__(self, result=None, error: AppError | None = None) -> None:
        self.result = result
        self.error = error

    async def get_chunk(self, *args, **kwargs):
        if self.error:
            raise self.error
        return self.result


def service(client) -> ConversationService:
    result = cast(Any, object.__new__(ConversationService))
    result.knowledge_client = client
    result.access_token = "user-token"
    result.knowledge_audience_authorized = True
    result.request_id = "request-1"
    result.context = SimpleNamespace(tenant_id=7)
    return result


@pytest.mark.asyncio
async def test_history_evidence_marks_updated_document_stale() -> None:
    output = await service(ChunkClient({
        "id": 31, "knowledge_base_id": 11, "document_id": 21, "version": 5,
    }))._evidence_out(evidence_row())
    assert output.access_status == "STALE"
    assert output.excerpt == "检索时的原文"


@pytest.mark.asyncio
async def test_history_evidence_hides_excerpt_after_access_revoked() -> None:
    output = await service(ChunkClient(error=AppError(
        "知识来源不存在或已无权访问", code=40474, status_code=404,
    )))._evidence_out(evidence_row())
    assert output.access_status == "MISSING"
    assert output.excerpt is None


@pytest.mark.asyncio
async def test_history_evidence_requires_knowledge_audience() -> None:
    instance = service(ChunkClient({}))
    instance.knowledge_audience_authorized = False
    output = await instance._evidence_out(evidence_row())
    assert output.access_status == "FORBIDDEN"
    assert output.excerpt is None

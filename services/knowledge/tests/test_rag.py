from __future__ import annotations

from app.ai.factory import get_embedding_client, get_rerank_client
from app.ai.mock import MockRerankClient
from fastapi.testclient import TestClient

from tests.conftest import ALL_KNOWLEDGE_PERMS, FakeIdentityClient, auth_header


def _create_base(client: TestClient, identity: FakeIdentityClient, tenant_id: int = 11, user_id: int = 1) -> int:
    identity.grant(user_id, tenant_id, permissions=ALL_KNOWLEDGE_PERMS)
    response = client.post(
        "/api/v1/knowledge-bases",
        json={"name": f"RAG库-{tenant_id}"},
        headers=auth_header(user_id, tenant_id),
    )
    assert response.status_code == 200, response.text
    return int(response.json()["data"]["id"])


def _upload_text(client: TestClient, base_id: int, filename: str, body: str, tenant_id: int = 11) -> int:
    uploaded = client.post(
        f"/api/v1/knowledge-bases/{base_id}/documents",
        files=[("files", (filename, body.encode("utf-8"), "text/plain"))],
        headers=auth_header(1, tenant_id),
    )
    assert uploaded.status_code == 200, uploaded.text
    assert uploaded.json()["data"]["succeeded"] == 1
    return int(uploaded.json()["data"]["items"][0]["document"]["id"])


def test_embed_search_hybrid_and_chat(client: TestClient, identity: FakeIdentityClient) -> None:
    get_embedding_client.cache_clear()
    get_rerank_client.cache_clear()
    base_id = _create_base(client, identity)
    headers = auth_header(1, 11)
    doc_id = _upload_text(
        client,
        base_id,
        "policy.txt",
        "Neorvion 七天无理由退货政策：签收后七日内可退货，商品需保持完好。" * 3,
    )
    detail = client.get(f"/api/v1/documents/{doc_id}", headers=headers)
    assert detail.json()["data"]["status"] == "COMPLETED"
    chunks = client.get("/api/v1/chunks", params={"document_id": doc_id}, headers=headers)
    assert chunks.json()["data"]["items"]
    status = client.get(f"/api/v1/knowledge-bases/{base_id}/index-status", headers=headers)
    assert status.status_code == 200
    assert status.json()["data"]["ready"] >= 1

    vector = client.post(
        "/api/v1/search",
        json={"query": "七天无理由退货政策", "strategy": "VECTOR", "knowledge_base_ids": [base_id]},
        headers=headers,
    )
    assert vector.status_code == 200, vector.text
    assert vector.json()["data"]["items"]
    assert vector.json()["data"]["items"][0]["document_id"] == doc_id

    keyword = client.post(
        "/api/v1/search",
        json={"query": "退货政策", "strategy": "KEYWORD", "knowledge_base_ids": [base_id]},
        headers=headers,
    )
    assert keyword.status_code == 200, keyword.text
    assert keyword.json()["data"]["items"]

    hybrid = client.post(
        "/api/v1/retrieval/test",
        json={"query": "七天退货", "strategy": "HYBRID", "knowledge_base_ids": [base_id], "rerank": True},
        headers=headers,
    )
    assert hybrid.status_code == 200
    body = hybrid.json()["data"]
    assert body["strategy"] == "HYBRID"
    ids = [item["chunk_id"] for item in body["items"]]
    assert len(ids) == len(set(ids))

    empty = client.post(
        "/api/v1/search",
        json={"query": "完全不相关的火星矿石采购流程XYZ", "strategy": "KEYWORD", "knowledge_base_ids": [base_id]},
        headers=headers,
    )
    assert empty.status_code == 200

    conversation = client.post(
        "/api/v1/conversations",
        json={"title": "退货咨询", "knowledge_base_ids": [base_id]},
        headers=headers,
    )
    assert conversation.status_code == 200
    cid = conversation.json()["data"]["id"]
    with client.stream(
        "POST",
        f"/api/v1/conversations/{cid}/messages",
        json={"content": "退货要几天？", "strategy": "HYBRID", "rerank": True},
        headers=headers,
    ) as stream:
        assert stream.status_code == 200
        payload = b"".join(stream.iter_bytes()).decode("utf-8")
    assert "event: token" in payload
    assert "event: done" in payload
    detail_conv = client.get(f"/api/v1/conversations/{cid}", headers=headers)
    assert detail_conv.status_code == 200
    messages = detail_conv.json()["data"]["messages"]
    assert any(item["role"] == "ASSISTANT" and item["status"] == "COMPLETED" for item in messages)


def test_keyword_terms_extracts_cjk_and_latin() -> None:
    from app.services.retrieval import keyword_terms

    latin, terms = keyword_terms("销售订单 DRAFT 状态会不会预占库存？")
    assert "DRAFT" in latin
    assert "销售订单" in terms
    assert "预占" in terms
    assert "库存" in terms


def test_keyword_search_matches_chinese_paraphrase(client: TestClient, identity: FakeIdentityClient) -> None:
    base_id = _create_base(client, identity)
    headers = auth_header(1, 11)
    _upload_text(
        client,
        base_id,
        "logistics.txt",
        "履约手册（模拟）：头程是工厂到海外仓，尾程是海外仓到消费者。在途不可售。",
    )
    searched = client.post(
        "/api/v1/search",
        json={
            "query": "模拟物流把头程和尾程分别定义成什么？",
            "strategy": "KEYWORD",
            "knowledge_base_ids": [base_id],
        },
        headers=headers,
    )
    assert searched.status_code == 200, searched.text
    assert searched.json()["data"]["items"]


def test_dimension_mismatch_and_chunk_update_reindex(client: TestClient, identity: FakeIdentityClient) -> None:
    get_embedding_client.cache_clear()
    base_id = _create_base(client, identity)
    headers = auth_header(1, 11)
    doc_id = _upload_text(client, base_id, "a.txt", "原始切片内容用于维度与更新测试。" * 4)
    chunks = client.get("/api/v1/chunks", params={"document_id": doc_id}, headers=headers).json()["data"]["items"]
    chunk_id = chunks[0]["id"]

    class BadClient:
        async def embed(self, texts: list[str]) -> list[list[float]]:
            return [[0.1, 0.2] for _ in texts]

    from app.services import embedding as embedding_mod

    original = embedding_mod.get_embedding_client
    embedding_mod.get_embedding_client = lambda: BadClient()  # type: ignore[assignment]
    try:
        rebuilt = client.post(f"/api/v1/knowledge-bases/{base_id}/reindex", headers=headers)
        assert rebuilt.status_code in {200, 400}
    finally:
        embedding_mod.get_embedding_client = original  # type: ignore[assignment]

    updated = client.patch(
        f"/api/v1/chunks/{chunk_id}",
        json={"content": "更新后的切片：七天退货仍然有效。" * 3},
        headers=headers,
    )
    assert updated.status_code == 200
    status = client.get(f"/api/v1/knowledge-bases/{base_id}/index-status", headers=headers)
    assert status.status_code == 200


def test_rerank_degrade_and_cross_tenant(client: TestClient, identity: FakeIdentityClient) -> None:
    get_rerank_client.cache_clear()
    base_a = _create_base(client, identity, tenant_id=11, user_id=1)
    headers_a = auth_header(1, 11)
    _upload_text(client, base_a, "a.txt", "租户甲的保密退货说明只属于甲。" * 4, tenant_id=11)

    identity.grant(2, 22, permissions=ALL_KNOWLEDGE_PERMS)
    stolen = client.post(
        "/api/v1/search",
        json={"query": "退货说明", "strategy": "HYBRID", "knowledge_base_ids": [base_a]},
        headers=auth_header(2, 22),
    )
    assert stolen.status_code in {404, 400}

    other_search = client.post(
        "/api/v1/search",
        json={"query": "退货说明", "strategy": "VECTOR"},
        headers=auth_header(2, 22),
    )
    assert other_search.status_code in {200, 400}
    if other_search.status_code == 200:
        assert other_search.json()["data"]["items"] == [] or all(
            item["knowledge_base_id"] != base_a for item in other_search.json()["data"]["items"]
        )

    conv = client.post("/api/v1/conversations", json={"title": "甲"}, headers=headers_a)
    cid = conv.json()["data"]["id"]
    stolen_conv = client.get(f"/api/v1/conversations/{cid}", headers=auth_header(2, 22))
    assert stolen_conv.status_code == 404

    from app.services import retrieval as retrieval_mod

    original = retrieval_mod.get_rerank_client
    retrieval_mod.get_rerank_client = lambda: MockRerankClient(fail=True)  # type: ignore[assignment]
    try:
        degraded = client.post(
            "/api/v1/retrieval/test",
            json={"query": "退货", "strategy": "HYBRID", "rerank": True, "knowledge_base_ids": [base_a]},
            headers=headers_a,
        )
        assert degraded.status_code == 200
        assert degraded.json()["data"]["rerank_degraded"] is True
    finally:
        retrieval_mod.get_rerank_client = original  # type: ignore[assignment]


def test_chat_can_rebind_knowledge_bases(client: TestClient, identity: FakeIdentityClient) -> None:
    identity.grant(1, 11, permissions=ALL_KNOWLEDGE_PERMS)
    headers = auth_header(1, 11)
    erp_id = _create_base(client, identity)
    other = client.post("/api/v1/knowledge-bases", json={"name": "产品手册"}, headers=headers)
    assert other.status_code == 200, other.text
    other_id = int(other.json()["data"]["id"])
    _upload_text(client, erp_id, "order.md", "销售订单 DRAFT 状态不会预占库存。确认才写 RESERVE。" * 3)
    created = client.post(
        "/api/v1/conversations",
        json={"title": "错库会话", "knowledge_base_ids": [other_id]},
        headers=headers,
    )
    cid = created.json()["data"]["id"]
    with client.stream(
        "POST",
        f"/api/v1/conversations/{cid}/messages",
        json={"content": "销售订单 DRAFT 状态会不会预占库存？", "strategy": "KEYWORD"},
        headers=headers,
    ) as stream:
        missed = b"".join(stream.iter_bytes()).decode("utf-8")
    assert "知识库中没有足够依据" in missed
    assert "产品手册" in missed
    patched = client.patch(
        f"/api/v1/conversations/{cid}",
        json={"knowledge_base_ids": [erp_id]},
        headers=headers,
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["data"]["knowledge_base_ids"] == [erp_id]
    with client.stream(
        "POST",
        f"/api/v1/conversations/{cid}/messages",
        json={"content": "销售订单 DRAFT 状态会不会预占库存？", "strategy": "KEYWORD"},
        headers=headers,
    ) as stream:
        hit = b"".join(stream.iter_bytes()).decode("utf-8")
    assert "event: citation" in hit


def test_no_result_chat_and_models(client: TestClient, identity: FakeIdentityClient) -> None:
    identity.grant(1, 11, permissions=ALL_KNOWLEDGE_PERMS)
    headers = auth_header(1, 11)
    models = client.get("/api/v1/models", headers=headers)
    assert models.status_code == 200
    kinds = {item["kind"] for item in models.json()["data"]}
    assert "CHAT" in kinds
    assert "EMBEDDING" in kinds
    for item in models.json()["data"]:
        assert "api_key" not in item or item.get("api_key") in {None, ""}
        assert "has_api_key" in item

    tested = client.post("/api/v1/models/test", json={"kind": "EMBEDDING"}, headers=headers)
    assert tested.status_code == 200

    conv = client.post("/api/v1/conversations", json={"title": "空库"}, headers=headers)
    cid = conv.json()["data"]["id"]
    with client.stream(
        "POST",
        f"/api/v1/conversations/{cid}/messages",
        json={"content": "完全没有资料的问题", "strategy": "KEYWORD"},
        headers=headers,
    ) as stream:
        payload = b"".join(stream.iter_bytes()).decode("utf-8")
    assert "event: done" in payload or "event: token" in payload
    deleted = client.delete(f"/api/v1/conversations/{cid}", headers=headers)
    assert deleted.status_code == 200


def test_rrf_dedup_and_chunk_isolation(client: TestClient, identity: FakeIdentityClient) -> None:
    from app.services.retrieval import RetrievalService, RetrievedHit

    service = RetrievalService.__new__(RetrievalService)
    vector = [
        RetrievedHit(
            chunk_id=1,
            document_id=1,
            knowledge_base_id=1,
            filename="a.txt",
            content="a",
            page_no=1,
            heading=None,
            chunk_index=0,
            version=1,
            vector_score=0.9,
            vector_rank=1,
        ),
        RetrievedHit(
            chunk_id=2,
            document_id=1,
            knowledge_base_id=1,
            filename="a.txt",
            content="b",
            page_no=1,
            heading=None,
            chunk_index=1,
            version=1,
            vector_score=0.5,
            vector_rank=2,
        ),
    ]
    keyword = [
        RetrievedHit(
            chunk_id=1,
            document_id=1,
            knowledge_base_id=1,
            filename="a.txt",
            content="a",
            page_no=1,
            heading=None,
            chunk_index=0,
            version=1,
            keyword_score=0.8,
            keyword_rank=1,
        )
    ]
    fused = RetrievalService._rrf(service, vector, keyword)
    assert [item.chunk_id for item in fused] == [1, 2]
    assert fused[0].rrf_score and fused[0].rrf_score > (fused[1].rrf_score or 0)

    base_id = _create_base(client, identity)
    headers = auth_header(1, 11)
    doc_id = _upload_text(client, base_id, "iso.txt", "引用原文隔离测试内容。" * 4)
    chunks = client.get("/api/v1/chunks", params={"document_id": doc_id}, headers=headers).json()["data"]["items"]
    chunk_id = chunks[0]["id"]
    own = client.get(f"/api/v1/chunks/{chunk_id}", headers=headers)
    assert own.status_code == 200
    identity.grant(2, 22, permissions=ALL_KNOWLEDGE_PERMS)
    stolen = client.get(f"/api/v1/chunks/{chunk_id}", headers=auth_header(2, 22))
    assert stolen.status_code == 404


def test_model_error_classification() -> None:
    from app.ai.openai_compat import _classify_http_error

    assert _classify_http_error(429, "rate").code == 42960
    assert _classify_http_error(401, "auth").code == 40160
    assert _classify_http_error(402, "quota").code == 40260
    assert _classify_http_error(504, "timeout").code == 50460

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import ALL_KNOWLEDGE_PERMS, READ_ONLY_PERMS, FakeIdentityClient, auth_header


def _create_base(client: TestClient, identity: FakeIdentityClient, *, tenant_id: int = 11, user_id: int = 1, name: str = "手册库") -> int:
    identity.grant(user_id, tenant_id, permissions=ALL_KNOWLEDGE_PERMS, is_owner=True)
    response = client.post(
        "/api/v1/knowledge-bases",
        json={"name": name},
        headers=auth_header(user_id, tenant_id),
    )
    assert response.status_code == 200, response.text
    return int(response.json()["data"]["id"])


def _upload(client: TestClient, base_id: int, filename: str, body: str, *, tenant_id: int = 11) -> int:
    uploaded = client.post(
        f"/api/v1/knowledge-bases/{base_id}/documents",
        files=[("files", (filename, body.encode("utf-8"), "text/plain"))],
        headers=auth_header(1, tenant_id),
    )
    assert uploaded.status_code == 200, uploaded.text
    assert uploaded.json()["data"]["succeeded"] == 1
    return int(uploaded.json()["data"]["items"][0]["document"]["id"])


def test_soft_delete_hides_chunks_and_search(client: TestClient, identity: FakeIdentityClient) -> None:
    base_id = _create_base(client, identity, name="产品手册")
    headers = auth_header(1, 11)
    doc_id = _upload(client, base_id, "policy.txt", "七天无理由退货政策：签收后七日内可退货。" * 8)
    assert client.get("/api/v1/chunks", params={"knowledge_base_id": base_id}, headers=headers).json()["data"]["items"]
    searched = client.post(
        "/api/v1/search",
        json={"query": "七天无理由退货", "strategy": "HYBRID", "knowledge_base_ids": [base_id]},
        headers=headers,
    )
    assert searched.status_code == 200
    assert searched.json()["data"]["items"]

    deleted = client.delete(f"/api/v1/documents/{doc_id}", headers=headers)
    assert deleted.status_code == 200
    assert client.get(f"/api/v1/documents/{doc_id}", headers=headers).status_code == 404
    chunks = client.get("/api/v1/chunks", params={"knowledge_base_id": base_id}, headers=headers)
    assert chunks.json()["data"]["items"] == []
    assert chunks.json()["data"]["total"] == 0
    hidden = client.post(
        "/api/v1/search",
        json={"query": "七天无理由退货", "strategy": "HYBRID", "knowledge_base_ids": [base_id]},
        headers=headers,
    )
    assert hidden.json()["data"]["items"] == []
    status = client.get(f"/api/v1/knowledge-bases/{base_id}/index-status", headers=headers)
    assert status.json()["data"]["total_active_chunks"] == 0
    assert status.json()["data"]["ready"] == 0
    recycle = client.get("/api/v1/recycle", headers=headers)
    assert "policy.txt" in [item["name"] for item in recycle.json()["data"]["items"]]

    restored = client.post(f"/api/v1/documents/{doc_id}/restore", headers=headers)
    assert restored.status_code == 200
    assert client.get("/api/v1/chunks", params={"document_id": doc_id}, headers=headers).json()["data"]["items"]
    again = client.post(
        "/api/v1/search",
        json={"query": "七天无理由退货", "strategy": "HYBRID", "knowledge_base_ids": [base_id]},
        headers=headers,
    )
    assert again.json()["data"]["items"]


def test_knowledge_base_restore_skips_independently_deleted_docs(
    client: TestClient, identity: FakeIdentityClient
) -> None:
    base_id = _create_base(client, identity, name="级联库")
    headers = auth_header(1, 11)
    keep_id = _upload(client, base_id, "keep.txt", "库存预占确认后发生，出库才扣减 quantity。" * 6)
    gone_id = _upload(client, base_id, "gone.txt", "单独删除的文档不应随知识库恢复。" * 6)
    assert client.delete(f"/api/v1/documents/{gone_id}", headers=headers).status_code == 200
    assert client.delete(f"/api/v1/knowledge-bases/{base_id}", headers=headers).status_code == 200

    recycle = client.get("/api/v1/recycle", headers=headers).json()["data"]["items"]
    names = {item["name"] for item in recycle}
    types = {item["resource_type"] for item in recycle}
    assert "级联库" in names
    assert "gone.txt" not in names
    assert "keep.txt" not in names
    assert types == {"knowledge_base"}

    restored = client.post(f"/api/v1/knowledge-bases/{base_id}/restore", headers=headers)
    assert restored.status_code == 200
    assert client.get(f"/api/v1/documents/{keep_id}", headers=headers).status_code == 200
    assert client.get(f"/api/v1/documents/{gone_id}", headers=headers).status_code == 404
    recycle_after = client.get("/api/v1/recycle", headers=headers).json()["data"]["items"]
    assert "gone.txt" in [item["name"] for item in recycle_after]


def test_recycle_batch_and_empty(client: TestClient, identity: FakeIdentityClient) -> None:
    base_id = _create_base(client, identity, name="批量库")
    headers = auth_header(1, 11)
    first = _upload(client, base_id, "a.txt", "第一条文档用于批量恢复。" * 6)
    second = _upload(client, base_id, "b.txt", "第二条文档用于批量彻底删除。" * 6)
    client.delete(f"/api/v1/documents/{first}", headers=headers)
    client.delete(f"/api/v1/documents/{second}", headers=headers)

    restored = client.post(
        "/api/v1/recycle/restore-batch",
        json={"items": [{"resource_type": "document", "id": first}, {"resource_type": "document", "id": first}]},
        headers=headers,
    )
    assert restored.status_code == 200, restored.text
    body = restored.json()["data"]
    assert body["succeeded"] == 1
    assert client.get(f"/api/v1/documents/{first}", headers=headers).status_code == 200

    client.delete(f"/api/v1/documents/{first}", headers=headers)
    listed = client.get("/api/v1/recycle", headers=headers).json()["data"]
    wrong = client.post(
        "/api/v1/recycle/empty",
        json={"confirm": True, "expected_count": listed["total"] + 1},
        headers=headers,
    )
    assert wrong.status_code == 409
    denied = client.post("/api/v1/recycle/empty", json={"confirm": False, "expected_count": listed["total"]}, headers=headers)
    assert denied.status_code == 400
    emptied = client.post(
        "/api/v1/recycle/empty",
        json={"confirm": True, "expected_count": listed["total"]},
        headers=headers,
    )
    assert emptied.status_code == 200, emptied.text
    assert client.get("/api/v1/recycle", headers=headers).json()["data"]["total"] == 0
    assert client.get(f"/api/v1/documents/{first}", headers=headers).status_code == 404


def test_deleted_document_parse_is_rejected_and_cross_tenant_hidden(
    client: TestClient, identity: FakeIdentityClient
) -> None:
    base_id = _create_base(client, identity, name="隔离库")
    headers = auth_header(1, 11)
    doc_id = _upload(client, base_id, "secret.txt", "租户隔离文档，删除后不可解析。" * 6)
    client.delete(f"/api/v1/documents/{doc_id}", headers=headers)
    parse = client.post(f"/api/v1/documents/{doc_id}/parse", headers=headers)
    assert parse.status_code == 404
    tasks = client.get("/api/v1/tasks", headers=headers)
    assert tasks.status_code == 200
    assert tasks.json()["data"]["items"]
    assert any(item["document_id"] == doc_id and item["document_available"] is False for item in tasks.json()["data"]["items"])

    identity.grant(2, 12, permissions=ALL_KNOWLEDGE_PERMS, is_owner=True)
    other = auth_header(2, 12)
    assert client.get("/api/v1/recycle", headers=other).json()["data"]["total"] == 0
    restore = client.post(f"/api/v1/documents/{doc_id}/restore", headers=other)
    assert restore.status_code == 404
    search = client.post(
        "/api/v1/search",
        json={"query": "租户隔离文档", "strategy": "KEYWORD"},
        headers=other,
    )
    assert search.status_code == 200
    assert search.json()["data"]["items"] == []


def test_read_only_cannot_purge_or_empty(client: TestClient, identity: FakeIdentityClient) -> None:
    identity.grant(3, 11, permissions=READ_ONLY_PERMS, is_owner=False, role="VIEWER")
    headers = auth_header(3, 11)
    emptied = client.post("/api/v1/recycle/empty", json={"confirm": True, "expected_count": 0}, headers=headers)
    assert emptied.status_code in {403, 401}


def test_retrieval_defaults_match_settings(client: TestClient, identity: FakeIdentityClient) -> None:
    identity.grant(1, 11, permissions=ALL_KNOWLEDGE_PERMS, is_owner=True)
    response = client.get("/api/v1/retrieval/defaults", headers=auth_header(1, 11))
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["default_top_k"] == 8
    assert data["default_candidate_k"] == 24
    assert data["rrf_k"] == 60
    assert data["similarity_threshold"] is None
    assert data["default_chunk_size"] == 800
    assert data["embedding_dimensions"] == 8

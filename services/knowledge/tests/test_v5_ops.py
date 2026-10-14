from __future__ import annotations

from app.core.permissions import PermissionCode
from app.scripts.eval_questions import all_questions
from fastapi.testclient import TestClient

from tests.conftest import ALL_KNOWLEDGE_PERMS, FakeIdentityClient, auth_header

READ_PERMS = frozenset({PermissionCode.KNOWLEDGE_READ.value})


def test_eval_catalog_has_100_questions() -> None:
    items = all_questions()
    assert len(items) == 100
    assert sum(1 for item in items if item["category"] == "erp") == 30
    assert sum(1 for item in items if item["category"] == "ecommerce") == 30
    assert sum(1 for item in items if item["category"] == "general") == 30
    assert sum(1 for item in items if item["category"] == "advanced") == 10
    assert all(item["needs_human_review"] for item in items)
    assert all(item["question_id"] for item in items)
    assert sum(1 for item in items if item["is_unanswerable"]) >= 3
    assert len({item["question_id"] for item in items}) == 100


def _create_base(client: TestClient, identity: FakeIdentityClient, *, user_id: int, tenant_id: int, name: str) -> int:
    identity.grant(user_id, tenant_id, permissions=ALL_KNOWLEDGE_PERMS, is_owner=True)
    response = client.post(
        "/api/v1/knowledge-bases",
        json={"name": name},
        headers=auth_header(user_id, tenant_id),
    )
    assert response.status_code == 200, response.text
    return int(response.json()["data"]["id"])


def test_recycle_restore_and_purge(client: TestClient, identity: FakeIdentityClient) -> None:
    base_id = _create_base(client, identity, user_id=1, tenant_id=11, name="可回收库")
    headers = auth_header(1, 11)
    uploaded = client.post(
        f"/api/v1/knowledge-bases/{base_id}/documents",
        files=[("files", ("a.txt", "库存预占确认后发生，出库才扣减 quantity。".encode(), "text/plain"))],
        headers=headers,
    )
    assert uploaded.status_code == 200, uploaded.text
    doc_id = uploaded.json()["data"]["items"][0]["document"]["id"]

    deleted = client.delete(f"/api/v1/documents/{doc_id}", headers=headers)
    assert deleted.status_code == 200
    missing = client.get(f"/api/v1/documents/{doc_id}", headers=headers)
    assert missing.status_code == 404
    recycle = client.get("/api/v1/recycle", headers=headers)
    assert recycle.status_code == 200
    names = [item["name"] for item in recycle.json()["data"]["items"]]
    assert "a.txt" in names

    restored = client.post(f"/api/v1/documents/{doc_id}/restore", headers=headers)
    assert restored.status_code == 200
    assert client.get(f"/api/v1/documents/{doc_id}", headers=headers).status_code == 200

    client.delete(f"/api/v1/documents/{doc_id}", headers=headers)
    purged = client.delete(f"/api/v1/documents/{doc_id}/purge", headers=headers)
    assert purged.status_code == 200
    recycle_after = client.get("/api/v1/recycle", headers=headers)
    assert "a.txt" not in [item["name"] for item in recycle_after.json()["data"]["items"]]


def test_document_replace_keeps_revision(client: TestClient, identity: FakeIdentityClient) -> None:
    base_id = _create_base(client, identity, user_id=1, tenant_id=11, name="版本库")
    headers = auth_header(1, 11)
    uploaded = client.post(
        f"/api/v1/knowledge-bases/{base_id}/documents",
        files=[("files", ("v1.txt", "第一版：确认订单会 RESERVE 预占，不扣 quantity。".encode(), "text/plain"))],
        headers=headers,
    )
    doc_id = uploaded.json()["data"]["items"][0]["document"]["id"]
    replaced = client.post(
        f"/api/v1/documents/{doc_id}/replace",
        files={"file": ("v2.txt", "第二版：出库同时扣减 quantity 与 reserved_quantity。".encode(), "text/plain")},
        data={"note": "业务勘误"},
        headers=headers,
    )
    assert replaced.status_code == 200, replaced.text
    revisions = client.get(f"/api/v1/documents/{doc_id}/revisions", headers=headers)
    assert revisions.status_code == 200
    items = revisions.json()["data"]["items"]
    assert items
    assert items[0]["filename"] == "v1.txt"
    logs = client.get("/api/v1/audit-logs", params={"action": "document.replace"}, headers=headers)
    assert logs.json()["data"]["total"] >= 1


def test_grants_restrict_non_owner(client: TestClient, identity: FakeIdentityClient) -> None:
    base_id = _create_base(client, identity, user_id=1, tenant_id=11, name="授权库")
    identity.grant(2, 11, permissions=ALL_KNOWLEDGE_PERMS, is_owner=False, role="MEMBER")
    identity.grant(3, 11, permissions=READ_PERMS, is_owner=False, role="MEMBER")
    granted = client.post(
        f"/api/v1/knowledge-bases/{base_id}/grants",
        json={"user_id": 2, "permission": "READ"},
        headers=auth_header(1, 11),
    )
    assert granted.status_code == 200, granted.text
    visible = client.get("/api/v1/knowledge-bases", headers=auth_header(2, 11))
    assert [item["name"] for item in visible.json()["data"]["items"]] == ["授权库"]
    hidden = client.get("/api/v1/knowledge-bases", headers=auth_header(3, 11))
    assert hidden.json()["data"]["items"] == []
    forbidden = client.get(f"/api/v1/knowledge-bases/{base_id}", headers=auth_header(3, 11))
    assert forbidden.status_code == 404


def test_api_key_search_revoke_and_tenant_bind(client: TestClient, identity: FakeIdentityClient) -> None:
    base_id = _create_base(client, identity, user_id=1, tenant_id=11, name="Key库")
    identity.grant(1, 22, permissions=ALL_KNOWLEDGE_PERMS, is_owner=True)
    headers = auth_header(1, 11)
    created = client.post(
        "/api/v1/api-keys",
        json={"name": "copilot", "scopes": ["search"], "knowledge_base_ids": [base_id]},
        headers=headers,
    )
    assert created.status_code == 200, created.text
    plaintext = created.json()["data"]["api_key"]
    assert plaintext.startswith("nk_")
    listed = client.get("/api/v1/api-keys", headers=headers)
    assert "api_key" not in listed.json()["data"]["items"][0]

    searched = client.post(
        "/api/v1/search",
        json={"query": "库存预占", "strategy": "KEYWORD", "knowledge_base_ids": [base_id]},
        headers={"Authorization": f"Bearer {plaintext}", "X-Tenant-ID": "11"},
    )
    assert searched.status_code == 200, searched.text

    crossed = client.post(
        "/api/v1/search",
        json={"query": "库存预占", "strategy": "KEYWORD"},
        headers={"Authorization": f"Bearer {plaintext}", "X-Tenant-ID": "22"},
    )
    assert crossed.status_code == 403

    key_id = created.json()["data"]["id"]
    revoked = client.post(f"/api/v1/api-keys/{key_id}/revoke", headers=headers)
    assert revoked.status_code == 200
    after = client.post(
        "/api/v1/search",
        json={"query": "库存预占", "strategy": "KEYWORD"},
        headers={"Authorization": f"Bearer {plaintext}"},
    )
    assert after.status_code == 401


def test_eval_upsert_idempotent(client: TestClient, identity: FakeIdentityClient) -> None:
    identity.grant(1, 11, permissions=ALL_KNOWLEDGE_PERMS)
    headers = auth_header(1, 11)
    dataset = client.post("/api/v1/evaluation/datasets", json={"name": "V5幂等"}, headers=headers)
    dataset_id = dataset.json()["data"]["id"]
    payload = {
        "items": [
            {
                "external_key": "erp-001",
                "question": "确认销售订单时会不会扣减账面库存 quantity？",
                "expected_answer": "不会。确认只做 RESERVE 预占。",
                "question_type": "FACTUAL",
                "difficulty": 2,
                "tags": ["erp", "inventory"],
                "is_unanswerable": False,
                "needs_human_review": True,
            }
        ]
    }
    first = client.post(f"/api/v1/evaluation/datasets/{dataset_id}/upsert-cases", json=payload, headers=headers)
    assert first.status_code == 200, first.text
    assert first.json()["data"]["created"] == 1
    second = client.post(f"/api/v1/evaluation/datasets/{dataset_id}/upsert-cases", json=payload, headers=headers)
    assert second.status_code == 200
    assert second.json()["data"]["created"] == 0
    assert second.json()["data"]["updated"] == 1
    listed = client.get(f"/api/v1/evaluation/datasets/{dataset_id}/cases", headers=headers)
    assert listed.json()["data"]["total"] == 1
    row = listed.json()["data"]["items"][0]
    assert row["external_key"] == "erp-001"
    assert row["needs_human_review"] is True

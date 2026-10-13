from __future__ import annotations

from app.core.config import settings
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from tests.conftest import (
    ALL_KNOWLEDGE_PERMS,
    READ_ONLY_PERMS,
    FakeIdentityClient,
    auth_header,
)


def _create(
    client: TestClient,
    identity: FakeIdentityClient,
    *,
    user_id: int,
    tenant_id: int,
    name: str,
    description: str | None = None,
    permissions: frozenset[str] = ALL_KNOWLEDGE_PERMS,
) -> dict:
    identity.grant(user_id, tenant_id, permissions=permissions)
    payload: dict[str, object] = {"name": name}
    if description is not None:
        payload["description"] = description
    response = client.post(
        "/api/v1/knowledge-bases",
        json=payload,
        headers=auth_header(user_id, tenant_id),
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


def test_create_knowledge_base_success(client: TestClient, identity: FakeIdentityClient) -> None:
    data = _create(client, identity, user_id=1, tenant_id=11, name="产品手册", description="跨境 FAQ")
    assert data["name"] == "产品手册"
    assert data["description"] == "跨境 FAQ"
    assert data["status"] == "ACTIVE"
    assert data["tenant_id"] == 11
    assert data["created_by"] == 1
    assert data["document_count"] == 0
    forbidden_fields = client.post(
        "/api/v1/knowledge-bases",
        json={"name": "忽略字段", "tenant_id": 99, "created_by": 88},
        headers=auth_header(1, 11),
    )
    assert forbidden_fields.status_code == 422


def test_duplicate_name_same_tenant_conflict(client: TestClient, identity: FakeIdentityClient) -> None:
    _create(client, identity, user_id=1, tenant_id=11, name="同名库")
    dup = client.post(
        "/api/v1/knowledge-bases",
        json={"name": "同名库"},
        headers=auth_header(1, 11),
    )
    assert dup.status_code == 409
    assert dup.json()["code"] == 40950


def test_same_name_allowed_across_tenants(client: TestClient, identity: FakeIdentityClient) -> None:
    _create(client, identity, user_id=1, tenant_id=11, name="共享名")
    other = _create(client, identity, user_id=2, tenant_id=22, name="共享名")
    assert other["tenant_id"] == 22
    assert other["name"] == "共享名"


def test_list_only_returns_current_tenant(client: TestClient, identity: FakeIdentityClient) -> None:
    _create(client, identity, user_id=1, tenant_id=11, name="A企业库")
    _create(client, identity, user_id=2, tenant_id=22, name="B企业库")
    listed = client.get("/api/v1/knowledge-bases", headers=auth_header(1, 11))
    assert listed.status_code == 200
    names = [item["name"] for item in listed.json()["data"]["items"]]
    assert names == ["A企业库"]


def test_list_search_and_status_filter(client: TestClient, identity: FakeIdentityClient) -> None:
    first = _create(client, identity, user_id=1, tenant_id=11, name="启用手册")
    second = _create(client, identity, user_id=1, tenant_id=11, name="禁用手册")
    disabled = client.patch(
        f"/api/v1/knowledge-bases/{second['id']}",
        json={"status": "DISABLED"},
        headers=auth_header(1, 11),
    )
    assert disabled.status_code == 200
    searched = client.get("/api/v1/knowledge-bases", params={"q": "启用"}, headers=auth_header(1, 11))
    assert [item["id"] for item in searched.json()["data"]["items"]] == [first["id"]]
    filtered = client.get(
        "/api/v1/knowledge-bases",
        params={"status": "DISABLED"},
        headers=auth_header(1, 11),
    )
    assert [item["id"] for item in filtered.json()["data"]["items"]] == [second["id"]]


def test_detail_update_delete_forbid_cross_tenant(
    client: TestClient,
    identity: FakeIdentityClient,
) -> None:
    created = _create(client, identity, user_id=1, tenant_id=11, name="仅A可见")
    identity.grant(2, 22)
    detail = client.get(
        f"/api/v1/knowledge-bases/{created['id']}",
        headers=auth_header(2, 22),
    )
    assert detail.status_code == 404
    patched = client.patch(
        f"/api/v1/knowledge-bases/{created['id']}",
        json={"name": "盗用"},
        headers=auth_header(2, 22),
    )
    assert patched.status_code == 404
    deleted = client.delete(
        f"/api/v1/knowledge-bases/{created['id']}",
        headers=auth_header(2, 22),
    )
    assert deleted.status_code == 404
    still = client.get(
        f"/api/v1/knowledge-bases/{created['id']}",
        headers=auth_header(1, 11),
    )
    assert still.status_code == 200
    assert still.json()["data"]["name"] == "仅A可见"


def test_unauthenticated_returns_401(client: TestClient) -> None:
    response = client.get("/api/v1/knowledge-bases", headers={"X-Tenant-ID": "11"})
    assert response.status_code == 401
    assert response.json()["code"] == 40100


def test_invalid_token_returns_401(client: TestClient) -> None:
    response = client.get(
        "/api/v1/knowledge-bases",
        headers={"Authorization": "Bearer not-a-jwt", "X-Tenant-ID": "11"},
    )
    assert response.status_code == 401
    assert response.json()["code"] == 40102


def test_forbidden_without_permission(client: TestClient, identity: FakeIdentityClient) -> None:
    identity.grant(3, 11, permissions=READ_ONLY_PERMS, role="VIEWER", is_owner=False)
    created = client.post(
        "/api/v1/knowledge-bases",
        json={"name": "只读不能建"},
        headers=auth_header(3, 11),
    )
    assert created.status_code == 403
    assert created.json()["code"] == 40320


def test_missing_tenant_header(client: TestClient, identity: FakeIdentityClient) -> None:
    identity.grant(1, 11)
    response = client.get("/api/v1/knowledge-bases", headers=auth_header(1))
    assert response.status_code == 400
    assert response.json()["code"] == 40030


def test_invalid_status_and_empty_name(client: TestClient, identity: FakeIdentityClient) -> None:
    identity.grant(1, 11)
    empty = client.post(
        "/api/v1/knowledge-bases",
        json={"name": "   "},
        headers=auth_header(1, 11),
    )
    assert empty.status_code == 422
    created = _create(client, identity, user_id=1, tenant_id=11, name="状态校验")
    bad = client.patch(
        f"/api/v1/knowledge-bases/{created['id']}",
        json={"status": "ARCHIVE"},
        headers=auth_header(1, 11),
    )
    assert bad.status_code == 400
    listed = client.get(
        "/api/v1/knowledge-bases",
        params={"status": "ARCHIVE"},
        headers=auth_header(1, 11),
    )
    assert listed.status_code == 400


def test_disabled_base_still_visible_but_filterable(
    client: TestClient,
    identity: FakeIdentityClient,
) -> None:
    created = _create(client, identity, user_id=1, tenant_id=11, name="可禁用")
    patched = client.patch(
        f"/api/v1/knowledge-bases/{created['id']}",
        json={"status": "DISABLED"},
        headers=auth_header(1, 11),
    )
    assert patched.json()["data"]["status"] == "DISABLED"
    detail = client.get(
        f"/api/v1/knowledge-bases/{created['id']}",
        headers=auth_header(1, 11),
    )
    assert detail.status_code == 200
    assert detail.json()["data"]["status"] == "DISABLED"


def test_soft_delete_hides_from_list(client: TestClient, identity: FakeIdentityClient) -> None:
    created = _create(client, identity, user_id=1, tenant_id=11, name="待删除")
    deleted = client.delete(
        f"/api/v1/knowledge-bases/{created['id']}",
        headers=auth_header(1, 11),
    )
    assert deleted.status_code == 200
    listed = client.get("/api/v1/knowledge-bases", headers=auth_header(1, 11))
    assert listed.json()["data"]["items"] == []
    detail = client.get(
        f"/api/v1/knowledge-bases/{created['id']}",
        headers=auth_header(1, 11),
    )
    assert detail.status_code == 404
    reused = _create(client, identity, user_id=1, tenant_id=11, name="待删除")
    assert reused["id"] != created["id"]


def test_cross_tenant_document_fk_rejected() -> None:
    engine = create_engine(settings.test_database_url)
    with engine.begin() as connection:
        a_id = connection.execute(
            text(
                """
                INSERT INTO knowledge_bases
                    (tenant_id, name, status, created_by, updated_by)
                VALUES (11, 'A库', 'ACTIVE', 1, 1)
                RETURNING id
                """
            )
        ).scalar_one()
        b_id = connection.execute(
            text(
                """
                INSERT INTO knowledge_bases
                    (tenant_id, name, status, created_by, updated_by)
                VALUES (22, 'B库', 'ACTIVE', 2, 2)
                RETURNING id
                """
            )
        ).scalar_one()
        connection.execute(
            text(
                """
                INSERT INTO knowledge_documents
                    (tenant_id, knowledge_base_id, filename, storage_key, file_size, mime_type, status, created_by)
                VALUES (11, :base_id, 'ok.txt', 'k1', 1, 'text/plain', 'PENDING', 1)
                """
            ),
            {"base_id": a_id},
        )
        try:
            connection.execute(
                text(
                    """
                    INSERT INTO knowledge_documents
                        (tenant_id, knowledge_base_id, filename, storage_key, file_size, mime_type, status, created_by)
                    VALUES (22, :base_id, 'bad.txt', 'k2', 1, 'text/plain', 'PENDING', 2)
                    """
                ),
                {"base_id": a_id},
            )
            raise AssertionError("跨租户文档外键应被拒绝")
        except IntegrityError:
            connection.rollback()
        assert b_id > 0
    engine.dispose()


def test_pagination_limit(client: TestClient, identity: FakeIdentityClient) -> None:
    identity.grant(1, 11)
    too_big = client.get(
        "/api/v1/knowledge-bases",
        params={"page_size": 101},
        headers=auth_header(1, 11),
    )
    assert too_big.status_code == 422

from __future__ import annotations

import pytest
from app.repositories.product import ProductSkuRepository
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from tests.helpers.auth_api import auth_header, register_and_login


def _create_tenant(client: TestClient, token: str, name: str, code: str) -> int:
    response = client.post(
        "/api/v1/tenants",
        json={"name": name, "code": code},
        headers=auth_header(token),
    )
    assert response.status_code == 200, response.text
    return int(response.json()["data"]["id"])


def _roles(client: TestClient, token: str, tenant_id: int) -> dict[str, dict]:
    response = client.get("/api/v1/roles", headers=auth_header(token, tenant_id))
    assert response.status_code == 200, response.text
    return {item["code"]: item for item in response.json()["data"]}


def _add_member(
    client: TestClient,
    owner_token: str,
    tenant_id: int,
    email: str,
    role_code: str,
) -> tuple[str, int]:
    member_token, user_id = register_and_login(client, email)
    roles = _roles(client, owner_token, tenant_id)
    response = client.post(
        f"/api/v1/tenants/{tenant_id}/members",
        json={"email": email, "role_ids": [roles[role_code]["id"]]},
        headers=auth_header(owner_token, tenant_id),
    )
    assert response.status_code == 200, response.text
    return member_token, user_id


def _create_category(
    client: TestClient,
    token: str,
    tenant_id: int,
    name: str,
    parent_id: int | None = None,
) -> dict:
    payload: dict[str, object] = {"name": name}
    if parent_id is not None:
        payload["parent_id"] = parent_id
    response = client.post(
        "/api/v1/product-categories",
        json=payload,
        headers=auth_header(token, tenant_id),
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


def _create_brand(client: TestClient, token: str, tenant_id: int, name: str, code: str) -> dict:
    response = client.post(
        "/api/v1/brands",
        json={"name": name, "code": code},
        headers=auth_header(token, tenant_id),
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


def _sku(code: str, name: str, specs: dict[str, str] | None = None) -> dict:
    return {"sku_code": code, "name": name, "spec_values": specs or {}}


def test_category_tree_and_tenant_isolation(client: TestClient) -> None:
    owner_a, _ = register_and_login(client, "prod-cat-a@example.com")
    owner_b, _ = register_and_login(client, "prod-cat-b@example.com")
    tenant_a = _create_tenant(client, owner_a, "CatA", "prod-cata")
    tenant_b = _create_tenant(client, owner_b, "CatB", "prod-catb")

    root = _create_category(client, owner_a, tenant_a, "电子产品")
    phone = _create_category(client, owner_a, tenant_a, "手机", parent_id=root["id"])
    smart = _create_category(client, owner_a, tenant_a, "智能手机", parent_id=phone["id"])
    assert root["level"] == 1
    assert phone["level"] == 2
    assert smart["level"] == 3

    fourth = client.post(
        "/api/v1/product-categories",
        json={"name": "旗舰", "parent_id": smart["id"]},
        headers=auth_header(owner_a, tenant_a),
    )
    assert fourth.status_code == 400
    assert fourth.json()["code"] == 40053

    tree = client.get("/api/v1/product-categories", headers=auth_header(owner_a, tenant_a))
    assert tree.status_code == 200
    roots = tree.json()["data"]
    assert len(roots) == 1
    assert roots[0]["name"] == "电子产品"
    assert roots[0]["children"][0]["children"][0]["name"] == "智能手机"

    other = client.get("/api/v1/product-categories", headers=auth_header(owner_b, tenant_b))
    assert other.json()["data"] == []
    stolen = client.get(
        "/api/v1/product-categories",
        headers=auth_header(owner_b, tenant_a),
    )
    assert stolen.status_code in {403, 404}


def test_category_delete_rules(client: TestClient) -> None:
    owner, _ = register_and_login(client, "prod-cat-del@example.com")
    tenant_id = _create_tenant(client, owner, "CatDel", "prod-catdel")
    root = _create_category(client, owner, tenant_id, "服装")
    child = _create_category(client, owner, tenant_id, "男装", parent_id=root["id"])
    blocked = client.delete(
        f"/api/v1/product-categories/{root['id']}",
        headers=auth_header(owner, tenant_id),
    )
    assert blocked.status_code == 400
    assert blocked.json()["data"]["error"] == "CATEGORY_HAS_CHILDREN"

    client.delete(
        f"/api/v1/product-categories/{child['id']}",
        headers=auth_header(owner, tenant_id),
    )
    brand = _create_brand(client, owner, tenant_id, "Nike", "NIKE")
    created = client.post(
        "/api/v1/products",
        json={
            "name": "Air Max",
            "code": "AIRMAX",
            "category_id": root["id"],
            "brand_id": brand["id"],
            "skus": [_sku("AIRMAX-42", "Air Max 42", {"size": "42"})],
        },
        headers=auth_header(owner, tenant_id),
    )
    assert created.status_code == 200, created.text
    in_use = client.delete(
        f"/api/v1/product-categories/{root['id']}",
        headers=auth_header(owner, tenant_id),
    )
    assert in_use.status_code == 400
    assert in_use.json()["data"]["error"] == "CATEGORY_IN_USE"


def test_brand_unique_per_tenant_and_in_use(client: TestClient) -> None:
    owner_a, _ = register_and_login(client, "prod-brand-a@example.com")
    owner_b, _ = register_and_login(client, "prod-brand-b@example.com")
    tenant_a = _create_tenant(client, owner_a, "BrandA", "prod-branda")
    tenant_b = _create_tenant(client, owner_b, "BrandB", "prod-brandb")
    apple = _create_brand(client, owner_a, tenant_a, "Apple", "APPLE")
    again = client.post(
        "/api/v1/brands",
        json={"name": "Apple Inc", "code": "apple"},
        headers=auth_header(owner_a, tenant_a),
    )
    assert again.status_code == 409
    other = _create_brand(client, owner_b, tenant_b, "Apple", "APPLE")
    assert other["code"] == "APPLE"

    category = _create_category(client, owner_a, tenant_a, "手机")
    product = client.post(
        "/api/v1/products",
        json={
            "name": "iPhone 17",
            "code": "IPHONE17",
            "category_id": category["id"],
            "brand_id": apple["id"],
            "skus": [
                _sku(
                    "IPHONE17-BLK-256",
                    "iPhone 17 黑 256",
                    {"color": "黑色", "storage": "256GB"},
                )
            ],
        },
        headers=auth_header(owner_a, tenant_a),
    )
    assert product.status_code == 200, product.text
    blocked = client.delete(f"/api/v1/brands/{apple['id']}", headers=auth_header(owner_a, tenant_a))
    assert blocked.status_code == 400
    assert blocked.json()["data"]["error"] == "BRAND_IN_USE"


def test_create_single_and_multi_sku_product(client: TestClient) -> None:
    owner, _ = register_and_login(client, "prod-create@example.com")
    tenant_id = _create_tenant(client, owner, "ProdCo", "prod-create")
    category = _create_category(client, owner, tenant_id, "电子产品")
    brand = _create_brand(client, owner, tenant_id, "Apple", "APPLE")
    single = client.post(
        "/api/v1/products",
        json={
            "name": "iPhone 17",
            "code": "IPHONE17",
            "category_id": category["id"],
            "brand_id": brand["id"],
            "status": "ACTIVE",
            "skus": [_sku("IPHONE17-BLK-256", "黑 256", {"color": "黑色", "storage": "256GB"})],
        },
        headers=auth_header(owner, tenant_id),
    )
    assert single.status_code == 200, single.text
    assert len(single.json()["data"]["skus"]) == 1

    multi = client.post(
        "/api/v1/products",
        json={
            "name": "iPhone 17 Air",
            "code": "IPHONE17AIR",
            "category_id": category["id"],
            "skus": [
                _sku("IPHONE17AIR-WHT-256", "白 256", {"color": "白色", "storage": "256GB"}),
                _sku("IPHONE17AIR-WHT-512", "白 512", {"color": "白色", "storage": "512GB"}),
            ],
        },
        headers=auth_header(owner, tenant_id),
    )
    assert multi.status_code == 200, multi.text
    assert len(multi.json()["data"]["skus"]) == 2


def test_product_sku_create_rolls_back_on_duplicate_code(client: TestClient) -> None:
    owner, _ = register_and_login(client, "prod-tx@example.com")
    tenant_id = _create_tenant(client, owner, "TxCo", "prod-tx")
    category = _create_category(client, owner, tenant_id, "电子")
    first = client.post(
        "/api/v1/products",
        json={
            "name": "Phone A",
            "code": "PHONEA",
            "category_id": category["id"],
            "skus": [_sku("SHARED-SKU", "已占用")],
        },
        headers=auth_header(owner, tenant_id),
    )
    assert first.status_code == 200, first.text
    failed = client.post(
        "/api/v1/products",
        json={
            "name": "Phone B",
            "code": "PHONEB",
            "category_id": category["id"],
            "skus": [_sku("PHONEB-1", "正常"), _sku("SHARED-SKU", "冲突")],
        },
        headers=auth_header(owner, tenant_id),
    )
    assert failed.status_code == 409
    listed = client.get("/api/v1/products", headers=auth_header(owner, tenant_id))
    codes = {item["code"] for item in listed.json()["data"]["items"]}
    assert "PHONEA" in codes
    assert "PHONEB" not in codes


def test_product_and_sku_rollback_when_second_sku_fails(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """第二个 SKU 在 flush 之后失败时，已写入的 Product 必须一起回滚。"""
    original_add = ProductSkuRepository.add
    calls = {"count": 0}

    def flaky(self: ProductSkuRepository, sku: object) -> object:
        calls["count"] += 1
        if calls["count"] >= 2:
            raise IntegrityError("insert sku", {}, Exception("dup"))
        return original_add(self, sku)  # type: ignore[arg-type]

    monkeypatch.setattr(ProductSkuRepository, "add", flaky)
    owner, _ = register_and_login(client, "prod-tx-flush@example.com")
    tenant_id = _create_tenant(client, owner, "TxFlush", "prod-txflush")
    category = _create_category(client, owner, tenant_id, "电子")
    failed = client.post(
        "/api/v1/products",
        json={
            "name": "半成品",
            "code": "HALFDONE",
            "category_id": category["id"],
            "skus": [_sku("HALF-1", "一"), _sku("HALF-2", "二")],
        },
        headers=auth_header(owner, tenant_id),
    )
    assert failed.status_code == 409
    listed = client.get("/api/v1/products", headers=auth_header(owner, tenant_id))
    codes = {item["code"] for item in listed.json()["data"]["items"]}
    assert "HALFDONE" not in codes


def test_codes_unique_per_tenant_only(client: TestClient) -> None:
    owner_a, _ = register_and_login(client, "prod-code-a@example.com")
    owner_b, _ = register_and_login(client, "prod-code-b@example.com")
    tenant_a = _create_tenant(client, owner_a, "CodeA", "prod-codea")
    tenant_b = _create_tenant(client, owner_b, "CodeB", "prod-codeb")
    cat_a = _create_category(client, owner_a, tenant_a, "手机")
    cat_b = _create_category(client, owner_b, tenant_b, "手机")
    created_a = client.post(
        "/api/v1/products",
        json={
            "name": "Same",
            "code": "SAMECODE",
            "category_id": cat_a["id"],
            "skus": [_sku("SAMESKU", "SKU")],
        },
        headers=auth_header(owner_a, tenant_a),
    )
    assert created_a.status_code == 200
    dup_product = client.post(
        "/api/v1/products",
        json={
            "name": "Same2",
            "code": "SAMECODE",
            "category_id": cat_a["id"],
            "skus": [_sku("OTHERSKU", "SKU")],
        },
        headers=auth_header(owner_a, tenant_a),
    )
    assert dup_product.status_code == 409
    dup_sku = client.post(
        "/api/v1/products",
        json={
            "name": "Same3",
            "code": "OTHERCODE",
            "category_id": cat_a["id"],
            "skus": [_sku("SAMESKU", "SKU")],
        },
        headers=auth_header(owner_a, tenant_a),
    )
    assert dup_sku.status_code == 409
    created_b = client.post(
        "/api/v1/products",
        json={
            "name": "Same",
            "code": "SAMECODE",
            "category_id": cat_b["id"],
            "skus": [_sku("SAMESKU", "SKU")],
        },
        headers=auth_header(owner_b, tenant_b),
    )
    assert created_b.status_code == 200, created_b.text


def test_cannot_use_other_tenant_category_brand_or_product(client: TestClient) -> None:
    owner_a, _ = register_and_login(client, "prod-iso-a@example.com")
    owner_b, _ = register_and_login(client, "prod-iso-b@example.com")
    tenant_a = _create_tenant(client, owner_a, "IsoA", "prod-isoa")
    tenant_b = _create_tenant(client, owner_b, "IsoB", "prod-isob")
    cat_a = _create_category(client, owner_a, tenant_a, "A类")
    cat_b = _create_category(client, owner_b, tenant_b, "B类")
    brand_b = _create_brand(client, owner_b, tenant_b, "B牌", "BBRAND")
    product_b = client.post(
        "/api/v1/products",
        json={
            "name": "B货",
            "code": "BGOODS",
            "category_id": cat_b["id"],
            "brand_id": brand_b["id"],
            "skus": [_sku("B-SKU-1", "B SKU")],
        },
        headers=auth_header(owner_b, tenant_b),
    )
    assert product_b.status_code == 200, product_b.text
    product_id = product_b.json()["data"]["id"]
    sku_id = product_b.json()["data"]["skus"][0]["id"]

    bad_cat = client.post(
        "/api/v1/products",
        json={
            "name": "偷类目",
            "code": "STEALCAT",
            "category_id": cat_b["id"],
            "skus": [_sku("STEALCAT-1", "x")],
        },
        headers=auth_header(owner_a, tenant_a),
    )
    assert bad_cat.status_code == 404
    bad_brand = client.post(
        "/api/v1/products",
        json={
            "name": "偷品牌",
            "code": "STEALBRAND",
            "category_id": cat_a["id"],
            "brand_id": brand_b["id"],
            "skus": [_sku("STEALBRAND-1", "x")],
        },
        headers=auth_header(owner_a, tenant_a),
    )
    assert bad_brand.status_code == 404
    hidden = client.get(f"/api/v1/products/{product_id}", headers=auth_header(owner_a, tenant_a))
    assert hidden.status_code == 404
    sku_patch = client.patch(
        f"/api/v1/products/{product_id}/skus/{sku_id}",
        json={"name": "被改"},
        headers=auth_header(owner_a, tenant_a),
    )
    assert sku_patch.status_code == 404


def test_product_list_filters_and_pagination(client: TestClient) -> None:
    owner, _ = register_and_login(client, "prod-list@example.com")
    tenant_id = _create_tenant(client, owner, "ListCo", "prod-list")
    phones = _create_category(client, owner, tenant_id, "手机")
    clothes = _create_category(client, owner, tenant_id, "服装")
    apple = _create_brand(client, owner, tenant_id, "Apple", "APPLE")
    nike = _create_brand(client, owner, tenant_id, "Nike", "NIKE")
    first = client.post(
        "/api/v1/products",
        json={
            "name": "iPhone 17",
            "code": "IPHONE17",
            "category_id": phones["id"],
            "brand_id": apple["id"],
            "status": "ACTIVE",
            "skus": [_sku("IP17-BLK", "黑")],
        },
        headers=auth_header(owner, tenant_id),
    )
    second = client.post(
        "/api/v1/products",
        json={
            "name": "Air Max",
            "code": "AIRMAX",
            "category_id": clothes["id"],
            "brand_id": nike["id"],
            "status": "DRAFT",
            "skus": [_sku("AIRMAX-42", "42码")],
        },
        headers=auth_header(owner, tenant_id),
    )
    assert first.status_code == 200 and second.status_code == 200

    paged = client.get(
        "/api/v1/products?page=1&page_size=1",
        headers=auth_header(owner, tenant_id),
    )
    assert paged.status_code == 200
    assert paged.json()["data"]["total"] == 2
    assert len(paged.json()["data"]["items"]) == 1

    by_name = client.get("/api/v1/products?q=iPhone", headers=auth_header(owner, tenant_id))
    assert [item["code"] for item in by_name.json()["data"]["items"]] == ["IPHONE17"]

    by_sku = client.get(
        "/api/v1/products?sku_code=AIRMAX-42",
        headers=auth_header(owner, tenant_id),
    )
    assert [item["code"] for item in by_sku.json()["data"]["items"]] == ["AIRMAX"]

    by_cat = client.get(
        f"/api/v1/products?category_id={phones['id']}",
        headers=auth_header(owner, tenant_id),
    )
    assert [item["code"] for item in by_cat.json()["data"]["items"]] == ["IPHONE17"]

    by_brand = client.get(
        f"/api/v1/products?brand_id={nike['id']}",
        headers=auth_header(owner, tenant_id),
    )
    assert [item["code"] for item in by_brand.json()["data"]["items"]] == ["AIRMAX"]

    by_status = client.get("/api/v1/products?status=DRAFT", headers=auth_header(owner, tenant_id))
    assert [item["code"] for item in by_status.json()["data"]["items"]] == ["AIRMAX"]
    assert by_status.json()["data"]["items"][0]["sku_count"] == 1


def test_product_permissions_enforced(client: TestClient) -> None:
    owner, _ = register_and_login(client, "prod-perm-owner@example.com")
    tenant_id = _create_tenant(client, owner, "PermCo", "prod-perm")
    empty_role = client.post(
        "/api/v1/roles",
        json={"name": "无商品", "code": "NOPROD", "permission_ids": []},
        headers=auth_header(owner, tenant_id),
    )
    assert empty_role.status_code == 200, empty_role.text
    no_read_token, _ = register_and_login(client, "prod-perm-noread@example.com")
    added = client.post(
        f"/api/v1/tenants/{tenant_id}/members",
        json={
            "email": "prod-perm-noread@example.com",
            "role_ids": [empty_role.json()["data"]["id"]],
        },
        headers=auth_header(owner, tenant_id),
    )
    assert added.status_code == 200, added.text
    viewer, _ = _add_member(client, owner, tenant_id, "prod-perm-viewer@example.com", "VIEWER")
    operator, _ = _add_member(client, owner, tenant_id, "prod-perm-op@example.com", "OPERATOR")
    category = _create_category(client, owner, tenant_id, "类目")

    no_read = client.get("/api/v1/products", headers=auth_header(no_read_token, tenant_id))
    assert no_read.status_code == 403
    denied_cat = client.get(
        "/api/v1/product-categories",
        headers=auth_header(no_read_token, tenant_id),
    )
    assert denied_cat.status_code == 403

    allowed_read = client.get("/api/v1/products", headers=auth_header(viewer, tenant_id))
    assert allowed_read.status_code == 200
    create_denied = client.post(
        "/api/v1/products",
        json={
            "name": "x",
            "code": "X1",
            "category_id": category["id"],
            "skus": [_sku("X1-1", "x")],
        },
        headers=auth_header(viewer, tenant_id),
    )
    assert create_denied.status_code == 403

    created = client.post(
        "/api/v1/products",
        json={
            "name": "运营商品",
            "code": "OP1",
            "category_id": category["id"],
            "skus": [_sku("OP1-1", "x")],
        },
        headers=auth_header(operator, tenant_id),
    )
    assert created.status_code == 200, created.text
    product_id = created.json()["data"]["id"]
    update_denied = client.patch(
        f"/api/v1/products/{product_id}",
        json={"name": "改不了"},
        headers=auth_header(viewer, tenant_id),
    )
    assert update_denied.status_code == 403
    updated = client.patch(
        f"/api/v1/products/{product_id}",
        json={"name": "运营改过"},
        headers=auth_header(operator, tenant_id),
    )
    assert updated.status_code == 200
    delete_denied = client.delete(
        f"/api/v1/product-categories/{category['id']}",
        headers=auth_header(operator, tenant_id),
    )
    assert delete_denied.status_code == 403


def test_sku_subresource_add_update_delete(client: TestClient) -> None:
    owner, _ = register_and_login(client, "prod-sku@example.com")
    tenant_id = _create_tenant(client, owner, "SkuCo", "prod-sku")
    category = _create_category(client, owner, tenant_id, "鞋")
    product = client.post(
        "/api/v1/products",
        json={
            "name": "跑鞋",
            "code": "RUNNER",
            "category_id": category["id"],
            "skus": [_sku("RUNNER-42", "42码", {"size": "42"})],
        },
        headers=auth_header(owner, tenant_id),
    )
    assert product.status_code == 200, product.text
    product_id = product.json()["data"]["id"]
    sku_id = product.json()["data"]["skus"][0]["id"]
    added = client.post(
        f"/api/v1/products/{product_id}/skus",
        json=_sku("RUNNER-43", "43码", {"size": "43"}),
        headers=auth_header(owner, tenant_id),
    )
    assert added.status_code == 200, added.text
    patched = client.patch(
        f"/api/v1/products/{product_id}/skus/{sku_id}",
        json={"name": "42码加宽", "status": "INACTIVE"},
        headers=auth_header(owner, tenant_id),
    )
    assert patched.status_code == 200
    assert patched.json()["data"]["name"] == "42码加宽"
    deleted = client.delete(
        f"/api/v1/products/{product_id}/skus/{sku_id}",
        headers=auth_header(owner, tenant_id),
    )
    assert deleted.status_code == 200
    last = client.delete(
        f"/api/v1/products/{product_id}/skus/{added.json()['data']['id']}",
        headers=auth_header(owner, tenant_id),
    )
    assert last.status_code == 400
    assert last.json()["code"] == 40058


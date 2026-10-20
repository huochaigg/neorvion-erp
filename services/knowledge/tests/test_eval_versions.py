"""冻结版本的查看、比较和删除。不调用外部模型。"""

from __future__ import annotations

from app.evaluation.version_diff import diff_snapshots
from fastapi.testclient import TestClient

from tests.conftest import ALL_KNOWLEDGE_PERMS, READ_ONLY_PERMS, FakeIdentityClient, auth_header
from tests.test_evaluation import _create_base, _create_dataset, _grant, _upload


def test_snapshot_diff_tracks_added_removed_and_modified() -> None:
    left = [
        {"id": 1, "question": "甲", "tags": ["b", "a"], "judgments": [{"chunk_id": 9, "relevance": 3, "stale": False}]},
        {"id": 2, "question": "乙", "judgments": []},
    ]
    right = [
        {"id": 1, "question": "甲", "tags": ["a", "b"], "judgments": [{"chunk_id": 9, "relevance": 1, "stale": False}]},
        {"id": 3, "question": "丙", "judgments": []},
    ]
    diff = diff_snapshots(left, right)
    assert diff["added_count"] == 1
    assert diff["removed_count"] == 1
    assert diff["modified_count"] == 1
    assert diff["unchanged_count"] == 0
    modified = next(item for item in diff["changes"] if item["case_id"] == 1)
    assert modified["fields"] == ["judgments"]


def test_version_list_detail_compare_and_guarded_delete(client: TestClient, identity: FakeIdentityClient) -> None:
    headers = _grant(identity)
    base_id = _create_base(client, headers, "版本库")
    _doc_id, chunk_id = _upload(client, base_id, headers)
    dataset_id = _create_dataset(client, headers, base_id, "版本集")
    created = client.post(
        f"/api/v1/evaluation/datasets/{dataset_id}/cases",
        json={"question": "七天无理由怎么退？", "expected_answer": "七日内"},
        headers=headers,
    )
    case_id = created.json()["data"]["id"]
    labeled = client.put(
        f"/api/v1/evaluation/cases/{case_id}/judgments",
        json=[{"chunk_id": chunk_id, "relevance": 3}],
        headers=headers,
    )
    assert labeled.status_code == 200
    client.post(
        f"/api/v1/evaluation/datasets/{dataset_id}/cases",
        json={"question": "火星仓政策？", "is_unanswerable": True},
        headers=headers,
    )

    first = client.post(f"/api/v1/evaluation/datasets/{dataset_id}/freeze", headers=headers)
    assert first.status_code == 200, first.text
    assert first.json()["data"]["version"] == 1
    assert first.json()["data"]["case_count"] == 2
    assert first.json()["data"]["unanswerable_count"] == 1

    client.patch(f"/api/v1/evaluation/cases/{case_id}", json={"question": "七天无理由怎么申请？"}, headers=headers)
    second = client.post(f"/api/v1/evaluation/datasets/{dataset_id}/freeze", headers=headers)
    assert second.json()["data"]["version"] == 2

    listed = client.get(f"/api/v1/evaluation/datasets/{dataset_id}/versions", headers=headers)
    assert listed.status_code == 200
    body = listed.json()["data"]
    assert body["current_version"] == 2
    assert body["total"] == 2
    current = next(item for item in body["items"] if item["version"] == 2)
    older = next(item for item in body["items"] if item["version"] == 1)
    assert current["is_current"] is True
    assert current["deletable"] is False
    assert current["run_count"] == 0
    assert older["deletable"] is True

    detail = client.get(f"/api/v1/evaluation/datasets/{dataset_id}/versions/1", headers=headers)
    assert detail.status_code == 200
    snapshot = detail.json()["data"]
    assert snapshot["version"]["case_count"] == 2
    factual = next(item for item in snapshot["items"] if not item["is_unanswerable"])
    assert factual["question"] == "七天无理由怎么退？"
    assert factual["judgments"][0]["relevance"] == 3
    assert "工作稿" in snapshot["note"]

    compared = client.get(
        f"/api/v1/evaluation/datasets/{dataset_id}/versions/compare",
        params={"left": 1, "right": 2},
        headers=headers,
    )
    assert compared.status_code == 200, compared.text
    changes = compared.json()["data"]
    assert changes["modified_count"] == 1
    assert changes["added_count"] == 0
    assert changes["items"][0]["fields"] == ["question"]
    assert changes["items"][0]["before"]["question"] != changes["items"][0]["after"]["question"]

    blocked = client.delete(f"/api/v1/evaluation/datasets/{dataset_id}/versions/2", headers=headers)
    assert blocked.status_code == 409
    kept = client.get(f"/api/v1/evaluation/datasets/{dataset_id}", headers=headers)
    assert kept.json()["data"]["current_version"] == 2

    removed = client.delete(f"/api/v1/evaluation/datasets/{dataset_id}/versions/1", headers=headers)
    assert removed.status_code == 200, removed.text
    assert client.get(f"/api/v1/evaluation/datasets/{dataset_id}/versions/1", headers=headers).status_code == 404
    assert client.get(f"/api/v1/evaluation/datasets/{dataset_id}", headers=headers).json()["data"]["current_version"] == 2

    experiment = client.post(
        "/api/v1/evaluation/experiments",
        json={"dataset_id": dataset_id, "name": "版本引用", "config": {"strategy": "KEYWORD", "top_k": 5, "evaluate_generation": False}},
        headers=headers,
    )
    run = client.post(f"/api/v1/evaluation/experiments/{experiment.json()['data']['id']}/run", headers=headers)
    assert run.status_code == 200, run.text
    assert run.json()["data"]["dataset_version"] == 2
    client.post(f"/api/v1/evaluation/datasets/{dataset_id}/freeze", headers=headers)
    referenced = client.delete(f"/api/v1/evaluation/datasets/{dataset_id}/versions/2", headers=headers)
    assert referenced.status_code == 409
    still = client.get(f"/api/v1/evaluation/datasets/{dataset_id}/versions/2", headers=headers)
    assert still.status_code == 200
    assert still.json()["data"]["version"]["run_count"] == 1

    identity.grant(2, 22, permissions=ALL_KNOWLEDGE_PERMS)
    hidden = client.get(f"/api/v1/evaluation/datasets/{dataset_id}/versions", headers=auth_header(2, 22))
    assert hidden.status_code == 404
    hidden_delete = client.delete(f"/api/v1/evaluation/datasets/{dataset_id}/versions/2", headers=auth_header(2, 22))
    assert hidden_delete.status_code == 404

    identity.grant(1, 11, permissions=READ_ONLY_PERMS)
    forbidden = client.delete(f"/api/v1/evaluation/datasets/{dataset_id}/versions/3", headers=headers)
    assert forbidden.status_code == 403

from __future__ import annotations

import io
import zipfile
from unittest.mock import AsyncMock

from app.ai.factory import get_embedding_client, get_rerank_client
from app.core.config import settings
from app.evaluation.importing import parse_table
from fastapi.testclient import TestClient

from tests.conftest import ALL_KNOWLEDGE_PERMS, READ_ONLY_PERMS, FakeIdentityClient, auth_header


def _grant(identity: FakeIdentityClient, tenant_id: int = 11, user_id: int = 1) -> dict[str, str]:
    identity.grant(user_id, tenant_id, permissions=ALL_KNOWLEDGE_PERMS)
    return auth_header(user_id, tenant_id)


def _create_base(client: TestClient, headers: dict[str, str], name: str = "评测库") -> int:
    response = client.post("/api/v1/knowledge-bases", json={"name": name}, headers=headers)
    assert response.status_code == 200, response.text
    return int(response.json()["data"]["id"])


def _upload(client: TestClient, base_id: int, headers: dict[str, str], body: str = "七天无理由退货政策适用于完好商品。") -> tuple[int, int]:
    uploaded = client.post(
        f"/api/v1/knowledge-bases/{base_id}/documents",
        files=[("files", ("policy.txt", body.encode("utf-8"), "text/plain"))],
        headers=headers,
    )
    assert uploaded.status_code == 200, uploaded.text
    doc_id = int(uploaded.json()["data"]["items"][0]["document"]["id"])
    chunks = client.get("/api/v1/chunks", params={"document_id": doc_id}, headers=headers)
    assert chunks.json()["data"]["items"]
    chunk_id = int(chunks.json()["data"]["items"][0]["id"])
    return doc_id, chunk_id


def _create_dataset(client: TestClient, headers: dict[str, str], base_id: int, name: str = "退货评测集") -> int:
    created = client.post(
        "/api/v1/evaluation/datasets",
        json={"name": name, "description": "事实型退货", "knowledge_base_ids": [base_id]},
        headers=headers,
    )
    assert created.status_code == 200, created.text
    return int(created.json()["data"]["id"])


def _minimal_xlsx() -> bytes:
    sheet = """<?xml version="1.0"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <sheetData>
    <row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c></row>
    <row r="2"><c r="A2" t="s"><v>2</v></c><c r="B2" t="s"><v>3</v></c></row>
  </sheetData>
</worksheet>"""
    shared = """<?xml version="1.0"?>
<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <si><t>question</t></si><si><t>expected_answer</t></si>
  <si><t>Excel导入问题</t></si><si><t>Excel标准答案</t></si>
</sst>"""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("xl/worksheets/sheet1.xml", sheet)
        archive.writestr("xl/sharedStrings.xml", shared)
    return buffer.getvalue()


def test_dataset_crud_copy_and_annotation(client: TestClient, identity: FakeIdentityClient) -> None:
    get_embedding_client.cache_clear()
    headers = _grant(identity)
    base_id = _create_base(client, headers)
    _doc_id, chunk_id = _upload(client, base_id, headers)
    dataset_id = _create_dataset(client, headers, base_id)

    listed = client.get("/api/v1/evaluation/datasets", headers=headers)
    assert listed.status_code == 200
    assert listed.json()["data"]["total"] == 1

    updated = client.patch(
        f"/api/v1/evaluation/datasets/{dataset_id}",
        json={"description": "更新说明"},
        headers=headers,
    )
    assert updated.json()["data"]["description"] == "更新说明"

    created_case = client.post(
        f"/api/v1/evaluation/datasets/{dataset_id}/cases",
        json={
            "question": "七天无理由怎么退？",
            "expected_answer": "签收后七日内可退货。",
            "question_type": "FACTUAL",
            "difficulty": 2,
            "tags": ["退货"],
        },
        headers=headers,
    )
    assert created_case.status_code == 200
    case = created_case.json()["data"]
    assert case["annotation_status"] == "PENDING"
    case_id = case["id"]

    missing_answer = client.patch(
        f"/api/v1/evaluation/cases/{case_id}",
        json={"expected_answer": ""},
        headers=headers,
    )
    assert missing_answer.status_code == 200
    assert missing_answer.json()["data"]["expected_answer"] is None

    labeled = client.put(
        f"/api/v1/evaluation/cases/{case_id}/judgments",
        json=[{"chunk_id": chunk_id, "relevance": 3}],
        headers=headers,
    )
    assert labeled.status_code == 200, labeled.text
    assert labeled.json()["data"]["annotation_status"] == "READY"
    assert labeled.json()["data"]["judgments"][0]["relevance"] == 3

    copied = client.post(f"/api/v1/evaluation/datasets/{dataset_id}/copy", headers=headers)
    assert copied.status_code == 200
    assert copied.json()["data"]["name"].startswith("退货评测集 副本")
    copy_id = copied.json()["data"]["id"]
    copy_cases = client.get(f"/api/v1/evaluation/datasets/{copy_id}/cases", headers=headers)
    assert copy_cases.json()["data"]["total"] >= 1

    deleted = client.delete(f"/api/v1/evaluation/datasets/{copy_id}", headers=headers)
    assert deleted.status_code == 200
    gone = client.get(f"/api/v1/evaluation/datasets/{copy_id}", headers=headers)
    assert gone.status_code == 404


def test_import_csv_jsonl_xlsx_and_export(client: TestClient, identity: FakeIdentityClient) -> None:
    headers = _grant(identity)
    base_id = _create_base(client, headers, "导入库")
    dataset_id = _create_dataset(client, headers, base_id, "导入集")

    csv_body = "问题,标准答案,类型,难度,标签,无答案\n七天如何退,七日内退货,FACTUAL,2,退货,0\n,,FACTUAL,2,,0\n"
    csv_import = client.post(
        f"/api/v1/evaluation/datasets/{dataset_id}/import",
        files=[("file", ("cases.csv", csv_body.encode("utf-8"), "text/csv"))],
        headers=headers,
    )
    assert csv_import.status_code == 200, csv_import.text
    assert csv_import.json()["data"]["succeeded"] == 1
    assert csv_import.json()["data"]["failed"] == 1

    jsonl = '{"question":"多条件退货","expected_answer":"完好且七日内","question_type":"MULTI_CONDITION"}\nnot-json\n'
    jsonl_import = client.post(
        f"/api/v1/evaluation/datasets/{dataset_id}/import",
        files=[("file", ("cases.jsonl", jsonl.encode("utf-8"), "application/jsonl"))],
        headers=headers,
    )
    assert jsonl_import.status_code == 200
    assert jsonl_import.json()["data"]["succeeded"] == 1
    assert jsonl_import.json()["data"]["failed"] == 1

    xlsx_import = client.post(
        f"/api/v1/evaluation/datasets/{dataset_id}/import",
        files=[("file", ("cases.xlsx", _minimal_xlsx(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"))],
        headers=headers,
    )
    assert xlsx_import.status_code == 200, xlsx_import.text
    assert xlsx_import.json()["data"]["succeeded"] == 1

    exported = client.get(f"/api/v1/evaluation/datasets/{dataset_id}/export", headers=headers)
    assert exported.status_code == 200
    assert "七天如何退" in exported.text

    from app.core.exceptions import AppError

    try:
        parse_table("bad.txt", b"x")
        raise AssertionError("应拒绝不支持的格式")
    except AppError as exc:
        assert "仅支持" in exc.message


def test_unanswerable_and_multi_chunk_eval(client: TestClient, identity: FakeIdentityClient) -> None:
    get_embedding_client.cache_clear()
    headers = _grant(identity)
    base_id = _create_base(client, headers)
    _doc_id, chunk_id = _upload(client, base_id, headers)
    extra = client.post(
        f"/api/v1/knowledge-bases/{base_id}/documents",
        files=[("files", ("extra.txt", "仓库地址在深圳南山。".encode(), "text/plain"))],
        headers=headers,
    )
    extra_doc = int(extra.json()["data"]["items"][0]["document"]["id"])
    extra_chunks = client.get("/api/v1/chunks", params={"document_id": extra_doc}, headers=headers).json()["data"]["items"]
    extra_chunk = int(extra_chunks[0]["id"])
    dataset_id = _create_dataset(client, headers, base_id)

    factual = client.post(
        f"/api/v1/evaluation/datasets/{dataset_id}/cases",
        json={"question": "七天无理由退货政策是什么？", "expected_answer": "七日内可退", "question_type": "MULTI_DOC"},
        headers=headers,
    )
    factual_id = factual.json()["data"]["id"]
    judged = client.put(
        f"/api/v1/evaluation/cases/{factual_id}/judgments",
        json=[{"chunk_id": chunk_id, "relevance": 3}, {"chunk_id": extra_chunk, "relevance": 1}],
        headers=headers,
    )
    assert judged.status_code == 200
    assert len(judged.json()["data"]["judgments"]) == 2

    unanswerable = client.post(
        f"/api/v1/evaluation/datasets/{dataset_id}/cases",
        json={"question": "火星仓库的退货政策？", "question_type": "UNANSWERABLE", "is_unanswerable": True},
        headers=headers,
    )
    assert unanswerable.json()["data"]["annotation_status"] == "READY"
    assert unanswerable.json()["data"]["is_unanswerable"] is True

    experiment = client.post(
        "/api/v1/evaluation/experiments",
        json={
            "dataset_id": dataset_id,
            "name": "混合检索实验",
            "config": {"strategy": "HYBRID", "top_k": 5, "rerank": False, "evaluate_generation": False},
        },
        headers=headers,
    )
    assert experiment.status_code == 200, experiment.text
    snapshot = experiment.json()["data"]["config"]
    assert snapshot["embedding_model"]
    assert snapshot["metric_version"]
    assert snapshot["granularity"] == "chunk"
    experiment_id = experiment.json()["data"]["id"]

    run = client.post(f"/api/v1/evaluation/experiments/{experiment_id}/run", headers=headers)
    assert run.status_code == 200, run.text
    body = run.json()["data"]
    assert body["status"] == "SUCCESS"
    assert body["metrics"]["granularity"] == "chunk"
    assert "recall" in body["metrics"]
    assert body["metrics"]["unanswerable_count"] == 1
    assert "unanswerable_false_recall" in body["metrics"]
    assert body["config_snapshot"]["strategy"] == "HYBRID"

    results = client.get(f"/api/v1/evaluation/runs/{body['id']}/results", headers=headers)
    assert results.status_code == 200
    items = results.json()["data"]
    assert len(items) == 2
    factual_row = next(item for item in items if not item["is_unanswerable"])
    assert factual_row["retrieval_metrics"]["granularity"] == "chunk"
    assert "recall" in factual_row["retrieval_metrics"]
    unans_row = next(item for item in items if item["is_unanswerable"])
    assert "recall" not in (unans_row["retrieval_metrics"] or {})
    assert unans_row["retrieval_metrics"]["unanswerable"] is True


def test_chunk_version_stale_and_strategy_compare(client: TestClient, identity: FakeIdentityClient) -> None:
    get_embedding_client.cache_clear()
    headers = _grant(identity)
    base_id = _create_base(client, headers)
    _doc_id, chunk_id = _upload(client, base_id, headers)
    dataset_id = _create_dataset(client, headers, base_id, "版本集")
    case = client.post(
        f"/api/v1/evaluation/datasets/{dataset_id}/cases",
        json={"question": "退货要几天？", "expected_answer": "七日", "question_type": "FACTUAL"},
        headers=headers,
    )
    case_id = case.json()["data"]["id"]
    client.put(
        f"/api/v1/evaluation/cases/{case_id}/judgments",
        json=[{"chunk_id": chunk_id, "relevance": 3}],
        headers=headers,
    )
    patched = client.patch(f"/api/v1/chunks/{chunk_id}", json={"content": "更新后的退货说明：三日可退。" * 3}, headers=headers)
    assert patched.status_code == 200
    refreshed = client.post(f"/api/v1/evaluation/datasets/{dataset_id}/refresh-stale", headers=headers)
    assert refreshed.status_code == 200
    cases = client.get(f"/api/v1/evaluation/datasets/{dataset_id}/cases", headers=headers)
    item = cases.json()["data"]["items"][0]
    assert item["judgments"][0]["stale"] is True
    assert item["annotation_status"] != "READY"

    client.put(
        f"/api/v1/evaluation/cases/{case_id}/judgments",
        json=[{"chunk_id": chunk_id, "relevance": 3}],
        headers=headers,
    )
    vector = client.post(
        "/api/v1/evaluation/experiments",
        json={"dataset_id": dataset_id, "name": "向量", "config": {"strategy": "VECTOR", "top_k": 5}},
        headers=headers,
    )
    keyword = client.post(
        "/api/v1/evaluation/experiments",
        json={"dataset_id": dataset_id, "name": "关键词", "config": {"strategy": "KEYWORD", "top_k": 5}},
        headers=headers,
    )
    run_a = client.post(f"/api/v1/evaluation/experiments/{vector.json()['data']['id']}/run", headers=headers)
    run_b = client.post(f"/api/v1/evaluation/experiments/{keyword.json()['data']['id']}/run", headers=headers)
    assert run_a.status_code == 200 and run_b.status_code == 200
    compare = client.get(
        "/api/v1/evaluation/compare",
        params={"run_ids": f"{run_a.json()['data']['id']},{run_b.json()['data']['id']}"},
        headers=headers,
    )
    assert compare.status_code == 200, compare.text
    assert compare.json()["data"]["comparable"] is True
    deltas = compare.json()["data"]["metric_deltas"]
    assert str(run_b.json()["data"]["id"]) in deltas


def test_generation_judge_invalid_json_and_missing_gold(client: TestClient, identity: FakeIdentityClient) -> None:
    get_embedding_client.cache_clear()
    headers = _grant(identity)
    base_id = _create_base(client, headers)
    _doc_id, chunk_id = _upload(client, base_id, headers)
    dataset_id = _create_dataset(client, headers, base_id, "生成评测")
    invalid = client.post(
        f"/api/v1/evaluation/datasets/{dataset_id}/cases",
        json={
            "question": "__INVALID_JSON__ 七天无理由退货政策",
            "expected_answer": "七日内可退",
            "question_type": "HALLUCINATION",
        },
        headers=headers,
    )
    client.put(
        f"/api/v1/evaluation/cases/{invalid.json()['data']['id']}/judgments",
        json=[{"chunk_id": chunk_id, "relevance": 3}],
        headers=headers,
    )
    no_gold = client.post(
        f"/api/v1/evaluation/datasets/{dataset_id}/cases",
        json={"question": "七天无理由怎么退？", "question_type": "FACTUAL"},
        headers=headers,
    )
    client.put(
        f"/api/v1/evaluation/cases/{no_gold.json()['data']['id']}/judgments",
        json=[{"chunk_id": chunk_id, "relevance": 2}],
        headers=headers,
    )
    experiment = client.post(
        "/api/v1/evaluation/experiments",
        json={
            "dataset_id": dataset_id,
            "name": "Judge",
            "config": {"strategy": "HYBRID", "top_k": 5, "evaluate_generation": True},
        },
        headers=headers,
    )
    run = client.post(f"/api/v1/evaluation/experiments/{experiment.json()['data']['id']}/run", headers=headers)
    assert run.status_code == 200, run.text
    results = client.get(f"/api/v1/evaluation/runs/{run.json()['data']['id']}/results", headers=headers)
    items = results.json()["data"]
    invalid_row = next(item for item in items if "__INVALID_JSON__" in item["question"])
    assert invalid_row["judge_error"]
    assert invalid_row["generation_metrics"] is None
    gold_row = next(item for item in items if "__INVALID_JSON__" not in item["question"])
    if gold_row["generation_metrics"] is not None:
        assert gold_row["generation_metrics"]["answer_correctness"] is None


def test_async_cancel_retry_and_limits(client: TestClient, identity: FakeIdentityClient, monkeypatch) -> None:
    headers = _grant(identity)
    base_id = _create_base(client, headers)
    dataset_id = _create_dataset(client, headers, base_id, "限额集")
    client.post(
        f"/api/v1/evaluation/datasets/{dataset_id}/cases",
        json={"question": "无答案A", "is_unanswerable": True, "question_type": "UNANSWERABLE"},
        headers=headers,
    )
    client.post(
        f"/api/v1/evaluation/datasets/{dataset_id}/cases",
        json={"question": "无答案B", "is_unanswerable": True, "question_type": "UNANSWERABLE"},
        headers=headers,
    )
    monkeypatch.setattr(settings, "eval_max_cases", 1)
    experiment = client.post(
        "/api/v1/evaluation/experiments",
        json={"dataset_id": dataset_id, "name": "限额", "config": {"strategy": "KEYWORD"}},
        headers=headers,
    )
    blocked = client.post(f"/api/v1/evaluation/experiments/{experiment.json()['data']['id']}/run", headers=headers)
    assert blocked.status_code == 400
    assert blocked.json()["code"] == 40085

    monkeypatch.setattr(settings, "eval_max_cases", 200)
    monkeypatch.setattr(settings, "task_executor", "redis")
    monkeypatch.setattr("app.services.evaluation_run.enqueue_eval_run", AsyncMock(return_value=True))
    experiment_b = client.post(
        "/api/v1/evaluation/experiments",
        json={"dataset_id": dataset_id, "name": "异步", "config": {"strategy": "KEYWORD"}},
        headers=headers,
    )
    eid = experiment_b.json()["data"]["id"]
    first = client.post(f"/api/v1/evaluation/experiments/{eid}/run", headers=headers)
    assert first.status_code == 200
    assert first.json()["data"]["status"] == "QUEUED"
    second = client.post(f"/api/v1/evaluation/experiments/{eid}/run", headers=headers)
    assert second.status_code == 409
    cancelled = client.post(f"/api/v1/evaluation/runs/{first.json()['data']['id']}/cancel", headers=headers)
    assert cancelled.status_code == 200
    assert cancelled.json()["data"]["status"] == "CANCELLED"
    retried = client.post(f"/api/v1/evaluation/runs/{first.json()['data']['id']}/retry", headers=headers)
    assert retried.status_code == 200
    assert retried.json()["data"]["status"] == "QUEUED"
    assert retried.json()["data"]["attempt"] == 2


def test_tenant_isolation_and_spoofed_header(client: TestClient, identity: FakeIdentityClient) -> None:
    headers_a = _grant(identity, tenant_id=11, user_id=1)
    base_a = _create_base(client, headers_a, "甲库")
    dataset_id = _create_dataset(client, headers_a, base_a, "甲集")
    identity.grant(2, 22, permissions=ALL_KNOWLEDGE_PERMS)
    stolen = client.get(f"/api/v1/evaluation/datasets/{dataset_id}", headers=auth_header(2, 22))
    assert stolen.status_code == 404
    stolen_create = client.post(
        "/api/v1/evaluation/datasets",
        json={"name": "偷库", "knowledge_base_ids": [base_a]},
        headers=auth_header(2, 22),
    )
    assert stolen_create.status_code == 404
    spoof = client.get(f"/api/v1/evaluation/datasets/{dataset_id}", headers=auth_header(1, 22))
    assert spoof.status_code in {403, 404}
    identity.grant(1, 11, permissions=READ_ONLY_PERMS)
    forbidden = client.post(
        "/api/v1/evaluation/datasets",
        json={"name": "只读不能建"},
        headers=headers_a,
    )
    assert forbidden.status_code == 403


def test_usage_stats_from_real_logs(client: TestClient, identity: FakeIdentityClient) -> None:
    get_embedding_client.cache_clear()
    get_rerank_client.cache_clear()
    headers = _grant(identity)
    base_id = _create_base(client, headers)
    _upload(client, base_id, headers)
    searched = client.post(
        "/api/v1/search",
        json={"query": "退货政策", "strategy": "HYBRID", "knowledge_base_ids": [base_id]},
        headers=headers,
    )
    assert searched.status_code == 200
    stats = client.get("/api/v1/stats/usage", params={"days": 7}, headers=headers)
    assert stats.status_code == 200, stats.text
    body = stats.json()["data"]
    assert body["query_count"] >= 1
    assert "HYBRID" in body["strategy_counts"]
    assert body["estimated_cost_usd"] is None

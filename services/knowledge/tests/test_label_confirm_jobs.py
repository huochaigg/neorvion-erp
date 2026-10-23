"""批量确认改为异步任务：202 入队、幂等、隔离、部分跳过、Worker 恢复。"""

from __future__ import annotations

import asyncio
import selectors
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.core.config import settings
from app.services.label_suggestion import execute_label_job
from tests.conftest import FakeIdentityClient
from tests.test_evaluation import _create_base, _create_dataset, _grant, _upload


def _set_label_job(job_id: int, **fields: object) -> None:
    assignments = []
    params: dict[str, object] = {"id": job_id}
    for key, value in fields.items():
        assignments.append(f"{key} = CAST(:{key} AS jsonb)" if key == "details" else f"{key} = :{key}")
        params[key] = value
    engine = create_engine(settings.database_url)
    try:
        with engine.begin() as connection:
            connection.execute(text(f"UPDATE evaluation_label_jobs SET {', '.join(assignments)} WHERE id = :id"), params)
    finally:
        engine.dispose()


def _run(coro):
    return asyncio.run(coro, loop_factory=lambda: asyncio.SelectorEventLoop(selectors.SelectSelector()))


def _high_judge(chunk_id: int):
    async def judge(**_kwargs):
        return {
            "verdict": "ANSWERABLE",
            "confidence": "HIGH",
            "rationale": "原文直接支持退货规则",
            "risk": "",
            "items": [{"chunk_id": chunk_id, "relevance": 3, "reason": "写明七天无理由", "excerpt": "七天无理由退货"}],
        }

    return judge


def _seed_high_draft(client: TestClient, headers: dict[str, str], *, name: str) -> tuple[int, int, int]:
    from unittest.mock import patch

    base_id = _create_base(client, headers, name=f"{name}-库")
    _doc_id, chunk_id = _upload(client, base_id, headers)
    dataset_id = _create_dataset(client, headers, base_id, name=name)
    created = client.post(
        f"/api/v1/evaluation/datasets/{dataset_id}/cases",
        json={"question": "退货规则是什么？", "expected_answer": "完好商品可以七天无理由。", "needs_human_review": True},
        headers=headers,
    )
    assert created.status_code == 200, created.text
    with patch("app.services.label_suggestion.judge_relevance", new=_high_judge(chunk_id)):
        drafted = client.post(
            f"/api/v1/evaluation/datasets/{dataset_id}/label-suggestions",
            json={"execute": True},
            headers=headers,
        )
    assert drafted.status_code == 200, drafted.text
    suggestion_id = client.get(
        f"/api/v1/evaluation/datasets/{dataset_id}/label-suggestions",
        headers=headers,
    ).json()["data"][0]["id"]
    return dataset_id, suggestion_id, chunk_id


def test_single_confirm_still_sync(client: TestClient, identity: FakeIdentityClient) -> None:
    headers = _grant(identity)
    dataset_id, suggestion_id, chunk_id = _seed_high_draft(client, headers, name="单条确认")
    confirmed = client.post(
        f"/api/v1/evaluation/datasets/{dataset_id}/label-suggestions/confirm",
        json={"suggestion_ids": [suggestion_id], "only_high": False},
        headers=headers,
    )
    assert confirmed.status_code == 200, confirmed.text
    body = confirmed.json()["data"]
    assert body["confirmed"] == 1
    assert body.get("accepted") is False
    case = client.get(f"/api/v1/evaluation/datasets/{dataset_id}/cases", headers=headers).json()["data"]["items"][0]
    assert case["annotation_status"] == "READY"
    assert case["judgments"][0]["chunk_id"] == chunk_id


def test_batch_confirm_returns_202_and_finishes_inline(client: TestClient, identity: FakeIdentityClient) -> None:
    headers = _grant(identity)
    dataset_id, _suggestion_id, chunk_id = _seed_high_draft(client, headers, name="批量确认")
    accepted = client.post(
        f"/api/v1/evaluation/datasets/{dataset_id}/label-suggestions/confirm",
        json={"only_high": True},
        headers=headers,
    )
    assert accepted.status_code == 202, accepted.text
    payload = accepted.json()["data"]
    assert payload["accepted"] is True
    assert payload["job_type"] == "CONFIRM"
    assert payload["status"] == "QUEUED"
    assert payload["task_id"] == payload["id"]
    job = client.get(f"/api/v1/evaluation/datasets/{dataset_id}/label-jobs/current", headers=headers)
    assert job.status_code == 200, job.text
    current = job.json()["data"]
    assert current["status"] == "SUCCEEDED"
    assert current["succeeded"] == 1
    assert current["processed"] >= 1
    case = client.get(f"/api/v1/evaluation/datasets/{dataset_id}/cases", headers=headers).json()["data"]["items"][0]
    assert case["annotation_status"] == "READY"
    assert case["judgments"][0]["chunk_id"] == chunk_id


def test_batch_confirm_redis_returns_before_worker(client: TestClient, identity: FakeIdentityClient, monkeypatch) -> None:
    headers = _grant(identity)
    dataset_id, suggestion_id, _chunk_id = _seed_high_draft(client, headers, name="确认入队")
    monkeypatch.setattr(settings, "task_executor", "redis")
    enqueue = AsyncMock(return_value=True)
    monkeypatch.setattr("app.api.v1.evaluation.enqueue_label_job", enqueue)
    accepted = client.post(
        f"/api/v1/evaluation/datasets/{dataset_id}/label-suggestions/confirm",
        json={"only_high": True},
        headers=headers,
    )
    assert accepted.status_code == 202, accepted.text
    assert accepted.json()["data"]["status"] == "QUEUED"
    enqueue.assert_awaited()
    row = client.get(f"/api/v1/evaluation/datasets/{dataset_id}/label-suggestions", headers=headers).json()["data"][0]
    assert row["id"] == suggestion_id
    assert row["status"] == "DRAFT"
    _run(execute_label_job(int(accepted.json()["data"]["id"])))
    ready = client.get(f"/api/v1/evaluation/datasets/{dataset_id}/cases", headers=headers).json()["data"]["items"][0]
    assert ready["annotation_status"] == "READY"


def test_duplicate_batch_confirm_does_not_create_second_job(
    client: TestClient, identity: FakeIdentityClient, monkeypatch
) -> None:
    headers = _grant(identity)
    dataset_id, _suggestion_id, _chunk_id = _seed_high_draft(client, headers, name="重复确认")
    monkeypatch.setattr(settings, "task_executor", "redis")
    monkeypatch.setattr("app.api.v1.evaluation.enqueue_label_job", AsyncMock(return_value=True))
    first = client.post(
        f"/api/v1/evaluation/datasets/{dataset_id}/label-suggestions/confirm",
        json={"only_high": True},
        headers=headers,
    )
    second = client.post(
        f"/api/v1/evaluation/datasets/{dataset_id}/label-suggestions/confirm",
        json={"only_high": True},
        headers=headers,
    )
    assert first.status_code == 202
    assert second.status_code == 202
    assert second.json()["data"]["already_running"] is True
    assert second.json()["data"]["id"] == first.json()["data"]["id"]


def test_batch_confirm_skips_human_modified_and_stale_chunk(client: TestClient, identity: FakeIdentityClient) -> None:
    from unittest.mock import patch

    headers = _grant(identity)
    base_id = _create_base(client, headers, name="部分失败库")
    _doc_id, chunk_id = _upload(client, base_id, headers)
    dataset_id = _create_dataset(client, headers, base_id, name="部分失败确认")
    for question in ("退货规则是什么？", "完好商品能退吗？"):
        client.post(
            f"/api/v1/evaluation/datasets/{dataset_id}/cases",
            json={"question": question, "expected_answer": "完好商品可以七天无理由。", "needs_human_review": True},
            headers=headers,
        )
    with patch("app.services.label_suggestion.judge_relevance", new=_high_judge(chunk_id)):
        drafted = client.post(
            f"/api/v1/evaluation/datasets/{dataset_id}/label-suggestions",
            json={"execute": True},
            headers=headers,
        )
    assert drafted.status_code == 200, drafted.text
    rows = client.get(f"/api/v1/evaluation/datasets/{dataset_id}/label-suggestions", headers=headers).json()["data"]
    assert len(rows) == 2
    edited = rows[0]
    client.patch(
        f"/api/v1/evaluation/label-suggestions/{edited['id']}",
        json={"rationale": "人工改过理由"},
        headers=headers,
    )
    disabled = client.patch(f"/api/v1/chunks/{chunk_id}", json={"enabled": False}, headers=headers)
    assert disabled.status_code == 200, disabled.text
    accepted = client.post(
        f"/api/v1/evaluation/datasets/{dataset_id}/label-suggestions/confirm",
        json={"only_high": True},
        headers=headers,
    )
    assert accepted.status_code == 202, accepted.text
    job = client.get(f"/api/v1/evaluation/datasets/{dataset_id}/label-jobs/current", headers=headers).json()["data"]
    assert job["status"] == "SUCCEEDED"
    assert job["succeeded"] == 0
    assert job["skipped"] >= 2
    reasons = " ".join(item["reason"] for item in job["details"]["skips"])
    assert "人工已修改" in reasons
    assert "停用" in reasons or "失效" in reasons
    cases = client.get(f"/api/v1/evaluation/datasets/{dataset_id}/cases", headers=headers).json()["data"]["items"]
    assert all(item["annotation_status"] != "READY" for item in cases)


def test_batch_confirm_is_tenant_scoped(client: TestClient, identity: FakeIdentityClient) -> None:
    owner = _grant(identity, tenant_id=11, user_id=1)
    other = _grant(identity, tenant_id=12, user_id=2)
    dataset_id, _suggestion_id, _chunk_id = _seed_high_draft(client, owner, name="隔离确认")
    denied = client.post(
        f"/api/v1/evaluation/datasets/{dataset_id}/label-suggestions/confirm",
        json={"only_high": True},
        headers=other,
    )
    assert denied.status_code == 404
    current = client.get(f"/api/v1/evaluation/datasets/{dataset_id}/label-jobs/current", headers=other)
    assert current.status_code == 404


def test_worker_restart_resumes_confirm_without_duplicating(
    client: TestClient, identity: FakeIdentityClient, monkeypatch
) -> None:
    headers = _grant(identity)
    dataset_id, suggestion_id, _chunk_id = _seed_high_draft(client, headers, name="恢复确认")
    monkeypatch.setattr(settings, "task_executor", "redis")
    monkeypatch.setattr("app.api.v1.evaluation.enqueue_label_job", AsyncMock(return_value=True))
    accepted = client.post(
        f"/api/v1/evaluation/datasets/{dataset_id}/label-suggestions/confirm",
        json={"only_high": True},
        headers=headers,
    )
    job_id = int(accepted.json()["data"]["id"])
    _set_label_job(job_id, status="RUNNING")
    _set_label_job(job_id, status="QUEUED", error_message="Worker 重启，已保留部分确认结果，将从中断处继续")
    _run(execute_label_job(job_id))
    first = client.get(f"/api/v1/evaluation/datasets/{dataset_id}/cases", headers=headers).json()["data"]["items"][0]
    assert first["annotation_status"] == "READY"
    assert len(first["judgments"]) == 1
    _run(execute_label_job(job_id))
    again = client.get(f"/api/v1/evaluation/datasets/{dataset_id}/cases", headers=headers).json()["data"]["items"][0]
    assert again["id"] == first["id"]
    assert len(again["judgments"]) == 1
    _set_label_job(job_id, status="QUEUED", processed=0, succeeded=0, skipped=0, failed=0, details="{}", finished_at=None)
    _run(execute_label_job(job_id))
    resumed = client.get(f"/api/v1/evaluation/datasets/{dataset_id}/label-jobs/current", headers=headers).json()["data"]
    assert resumed["status"] == "SUCCEEDED"
    assert resumed["succeeded"] == 1
    listed = client.get(f"/api/v1/evaluation/datasets/{dataset_id}/label-suggestions", headers=headers).json()["data"]
    assert listed[0]["id"] == suggestion_id
    assert listed[0]["status"] == "CONFIRMED"
    final = client.get(f"/api/v1/evaluation/datasets/{dataset_id}/cases", headers=headers).json()["data"]["items"][0]
    assert len(final["judgments"]) == 1


def test_finished_job_stops_being_active(client: TestClient, identity: FakeIdentityClient) -> None:
    headers = _grant(identity)
    dataset_id, _suggestion_id, _chunk_id = _seed_high_draft(client, headers, name="结束轮询")
    client.post(
        f"/api/v1/evaluation/datasets/{dataset_id}/label-suggestions/confirm",
        json={"only_high": True},
        headers=headers,
    )
    current = client.get(f"/api/v1/evaluation/datasets/{dataset_id}/label-jobs/current", headers=headers).json()["data"]
    assert current["status"] in {"SUCCEEDED", "FAILED"}
    assert current["status"] not in {"QUEUED", "RUNNING"}
    refreshed = client.get(f"/api/v1/evaluation/datasets/{dataset_id}/label-jobs/current", headers=headers).json()["data"]
    assert refreshed["id"] == current["id"]
    assert refreshed["succeeded"] == current["succeeded"]


def test_batch_confirm_high_does_not_take_medium_drafts(client: TestClient, identity: FakeIdentityClient) -> None:
    headers = _grant(identity)
    dataset_id, suggestion_id, _chunk_id = _seed_high_draft(client, headers, name="中低置信度")
    patched = client.patch(
        f"/api/v1/evaluation/label-suggestions/{suggestion_id}",
        json={"confidence": "MEDIUM"},
        headers=headers,
    )
    assert patched.status_code == 200, patched.text
    accepted = client.post(
        f"/api/v1/evaluation/datasets/{dataset_id}/label-suggestions/confirm",
        json={"only_high": True},
        headers=headers,
    )
    assert accepted.status_code == 200, accepted.text
    body = accepted.json()["data"]
    assert body["accepted"] is False
    assert body["confirmed"] == 0
    assert body["pending_drafts"] == 1
    assert body["high_drafts"] == 0
    listed = client.get(f"/api/v1/evaluation/datasets/{dataset_id}/label-suggestions", headers=headers).json()["data"][0]
    assert listed["status"] == "DRAFT"
    assert listed["confidence"] == "MEDIUM"


def test_single_confirm_empty_items_explains_how_to_fix(client: TestClient, identity: FakeIdentityClient) -> None:
    headers = _grant(identity)
    dataset_id, suggestion_id, chunk_id = _seed_high_draft(client, headers, name="空切片确认")
    cleared = client.patch(
        f"/api/v1/evaluation/label-suggestions/{suggestion_id}",
        json={"items": []},
        headers=headers,
    )
    assert cleared.status_code == 200, cleared.text
    blocked = client.post(
        f"/api/v1/evaluation/datasets/{dataset_id}/label-suggestions/confirm",
        json={"suggestion_ids": [suggestion_id], "only_high": False},
        headers=headers,
    )
    assert blocked.status_code == 200, blocked.text
    assert blocked.json()["data"]["confirmed"] == 0
    assert "切片" in blocked.json()["data"]["errors"][0]["message"]
    filled = client.patch(
        f"/api/v1/evaluation/label-suggestions/{suggestion_id}",
        json={"items": [{"chunk_id": chunk_id, "relevance": 3, "reason": "人工补切片"}]},
        headers=headers,
    )
    assert filled.status_code == 200, filled.text
    confirmed = client.post(
        f"/api/v1/evaluation/datasets/{dataset_id}/label-suggestions/confirm",
        json={"suggestion_ids": [suggestion_id], "only_high": False},
        headers=headers,
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["data"]["confirmed"] == 1


def test_retry_empty_drafts_realigns_chunk_by_excerpt(client: TestClient, identity: FakeIdentityClient) -> None:
    from unittest.mock import patch

    headers = _grant(identity)
    dataset_id, suggestion_id, chunk_id = _seed_high_draft(client, headers, name="无切片重试")
    cleared = client.patch(
        f"/api/v1/evaluation/label-suggestions/{suggestion_id}",
        json={"items": []},
        headers=headers,
    )
    assert cleared.status_code == 200, cleared.text

    async def judge(**_kwargs):
        return {
            "verdict": "ANSWERABLE",
            "confidence": "HIGH",
            "rationale": "原文直接支持退货规则",
            "risk": "",
            "items": [
                {
                    "chunk_id": 9999,
                    "relevance": 3,
                    "reason": "写明七天无理由",
                    "excerpt": "七天无理由退货政策适用于完好商品。",
                }
            ],
        }

    with patch("app.services.label_suggestion.judge_relevance", new=judge):
        retried = client.post(
            f"/api/v1/evaluation/datasets/{dataset_id}/label-suggestions",
            json={"execute": True, "only_empty": True},
            headers=headers,
        )
    assert retried.status_code == 200, retried.text
    assert retried.json()["data"]["accepted"] is True
    listed = client.get(f"/api/v1/evaluation/datasets/{dataset_id}/label-suggestions", headers=headers).json()["data"][0]
    assert listed["id"] == suggestion_id
    assert listed["status"] == "DRAFT"
    assert listed["items"][0]["chunk_id"] == chunk_id


def test_hallucination_unanswerable_draft_is_corrected_not_case_flag(client: TestClient, identity: FakeIdentityClient) -> None:
    headers = _grant(identity)
    dataset_id, suggestion_id, chunk_id = _seed_high_draft(client, headers, name="幻觉题")
    patched = client.patch(
        f"/api/v1/evaluation/label-suggestions/{suggestion_id}",
        json={"verdict": "UNANSWERABLE", "items": []},
        headers=headers,
    )
    assert patched.status_code == 200, patched.text
    blocked = client.post(
        f"/api/v1/evaluation/datasets/{dataset_id}/label-suggestions/confirm",
        json={"suggestion_ids": [suggestion_id], "only_high": False},
        headers=headers,
    )
    assert blocked.status_code == 200, blocked.text
    assert "前提错误" in blocked.json()["data"]["errors"][0]["message"]
    fixed = client.patch(
        f"/api/v1/evaluation/label-suggestions/{suggestion_id}",
        json={"verdict": "ANSWERABLE", "items": [{"chunk_id": chunk_id, "relevance": 3, "reason": "发货不再改库存"}]},
        headers=headers,
    )
    assert fixed.status_code == 200, fixed.text
    confirmed = client.post(
        f"/api/v1/evaluation/datasets/{dataset_id}/label-suggestions/confirm",
        json={"suggestion_ids": [suggestion_id], "only_high": False},
        headers=headers,
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["data"]["confirmed"] == 1


def test_unanswerable_rebuttal_items_confirm_without_flipping_case(client: TestClient, identity: FakeIdentityClient) -> None:
    headers = _grant(identity)
    dataset_id, suggestion_id, chunk_id = _seed_high_draft(client, headers, name="纠正切片")
    patched = client.patch(
        f"/api/v1/evaluation/label-suggestions/{suggestion_id}",
        json={"verdict": "UNANSWERABLE", "items": [{"chunk_id": chunk_id, "relevance": 3, "reason": ""}]},
        headers=headers,
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["data"]["verdict"] == "ANSWERABLE"
    confirmed = client.post(
        f"/api/v1/evaluation/datasets/{dataset_id}/label-suggestions/confirm",
        json={"suggestion_ids": [suggestion_id], "only_high": False},
        headers=headers,
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["data"]["confirmed"] == 1
    case = client.get(f"/api/v1/evaluation/datasets/{dataset_id}/cases", headers=headers).json()["data"]["items"][0]
    assert case["is_unanswerable"] is False
    assert case["annotation_status"] == "READY"

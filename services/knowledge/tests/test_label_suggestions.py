from __future__ import annotations

from unittest.mock import AsyncMock, patch

from app.evaluation.label_suggest import LabelCandidate, finalize_label
from fastapi.testclient import TestClient

from tests.conftest import FakeIdentityClient, auth_header
from tests.test_evaluation import _create_base, _create_dataset, _grant, _upload


def _candidate(chunk_id: int = 7) -> LabelCandidate:
    return LabelCandidate(
        chunk_id=chunk_id,
        document_id=3,
        filename="policy.md",
        content="七天无理由退货只适用于完好商品。",
        chunk_version=1,
        content_hash="abc",
        methods=["fullscan"],
    )


def test_finalize_drops_unknown_chunk_and_lowers_confidence() -> None:
    draft = finalize_label(
        judge={
            "verdict": "ANSWERABLE",
            "confidence": "HIGH",
            "rationale": "原文支持",
            "risk": "",
            "items": [
                {"chunk_id": 7, "relevance": 3, "reason": "直接写出规则", "excerpt": "七天无理由退货"},
                {"chunk_id": 999, "relevance": 3, "reason": "不存在"},
            ],
        },
        candidates=[_candidate()],
        is_unanswerable=False,
        question_type="FACTUAL",
        model_name="mock-chat",
    )
    assert [item["chunk_id"] for item in draft.items] == [7]
    assert draft.confidence == "MEDIUM"
    assert "999" not in str(draft.items)


def test_finalize_remaps_unknown_chunk_id_by_excerpt() -> None:
    draft = finalize_label(
        judge={
            "verdict": "ANSWERABLE",
            "confidence": "HIGH",
            "rationale": "原文支持",
            "risk": "",
            "items": [
                {
                    "chunk_id": 999,
                    "relevance": 3,
                    "reason": "直接写出规则",
                    "excerpt": "七天无理由退货只适用于完好商品。",
                }
            ],
        },
        candidates=[_candidate()],
        is_unanswerable=False,
        question_type="FACTUAL",
        model_name="mock-chat",
    )
    assert [item["chunk_id"] for item in draft.items] == [7]
    assert draft.confidence == "HIGH"
    assert "对齐" in (draft.risk or "")


def test_finalize_does_not_upgrade_unanswerable_disagreement() -> None:
    draft = finalize_label(
        judge={
            "verdict": "ANSWERABLE",
            "confidence": "HIGH",
            "rationale": "找到了句子",
            "items": [{"chunk_id": 7, "relevance": 3, "reason": "相关"}],
        },
        candidates=[_candidate()],
        is_unanswerable=True,
        question_type="UNANSWERABLE",
        model_name="mock-chat",
    )
    assert draft.confidence == "LOW"


def test_multi_doc_with_one_chunk_is_not_high() -> None:
    draft = finalize_label(
        judge={
            "verdict": "ANSWERABLE",
            "confidence": "HIGH",
            "rationale": "只看到一处",
            "items": [{"chunk_id": 7, "relevance": 3, "reason": "部分事实"}],
        },
        candidates=[_candidate()],
        is_unanswerable=False,
        question_type="MULTI_DOC",
        model_name="mock-chat",
    )
    assert draft.confidence == "MEDIUM"


def test_estimate_does_not_call_model_or_mark_ready(client: TestClient, identity: FakeIdentityClient) -> None:
    headers = _grant(identity)
    base_id = _create_base(client, headers)
    _upload(client, base_id, headers)
    dataset_id = _create_dataset(client, headers, base_id, name="初标估算")
    created = client.post(
        f"/api/v1/evaluation/datasets/{dataset_id}/cases",
        json={"question": "退货规则是什么？", "expected_answer": "完好商品可以七天无理由。", "needs_human_review": True},
        headers=headers,
    )
    assert created.status_code == 200, created.text
    assert created.json()["data"]["annotation_status"] == "PENDING"
    with patch("app.services.label_suggestion.judge_relevance", new=AsyncMock()) as judge:
        estimated = client.post(
            f"/api/v1/evaluation/datasets/{dataset_id}/label-suggestions",
            json={"execute": False},
            headers=headers,
        )
    assert estimated.status_code == 200, estimated.text
    body = estimated.json()["data"]
    assert body["executed"] is False
    assert body["chat_calls"] == 1
    assert body["document_embedding_calls"] == 0
    judge.assert_not_called()
    listed = client.get(f"/api/v1/evaluation/datasets/{dataset_id}/label-suggestions", headers=headers)
    assert listed.json()["data"] == []


def test_draft_confirm_and_failure_do_not_overwrite_ready(client: TestClient, identity: FakeIdentityClient) -> None:
    headers = _grant(identity)
    base_id = _create_base(client, headers, name="初标库")
    _doc_id, chunk_id = _upload(client, base_id, headers)
    dataset_id = _create_dataset(client, headers, base_id, name="初标确认")
    created = client.post(
        f"/api/v1/evaluation/datasets/{dataset_id}/cases",
        json={"question": "退货规则是什么？", "expected_answer": "完好商品可以七天无理由。", "needs_human_review": True},
        headers=headers,
    )
    case_id = created.json()["data"]["id"]

    async def judge(**_kwargs):
        return {
            "verdict": "ANSWERABLE",
            "confidence": "HIGH",
            "rationale": "原文直接支持退货规则",
            "risk": "",
            "items": [{"chunk_id": chunk_id, "relevance": 3, "reason": "写明七天无理由", "excerpt": "七天无理由退货"}],
        }

    with patch("app.services.label_suggestion.judge_relevance", new=judge):
        drafted = client.post(
            f"/api/v1/evaluation/datasets/{dataset_id}/label-suggestions",
            json={"execute": True},
            headers=headers,
        )
    assert drafted.status_code == 200, drafted.text
    assert drafted.json()["data"]["accepted"] is True
    assert drafted.json()["data"]["status"] == "QUEUED"
    case = client.get(f"/api/v1/evaluation/datasets/{dataset_id}/cases", headers=headers).json()["data"]["items"][0]
    assert case["annotation_status"] == "PENDING"
    suggestions = client.get(f"/api/v1/evaluation/datasets/{dataset_id}/label-suggestions", headers=headers).json()["data"]
    suggestion_id = suggestions[0]["id"]
    confirmed = client.post(
        f"/api/v1/evaluation/datasets/{dataset_id}/label-suggestions/confirm",
        json={"suggestion_ids": [suggestion_id], "only_high": False},
        headers=headers,
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["data"]["confirmed"] == 1
    ready = client.get(f"/api/v1/evaluation/datasets/{dataset_id}/cases", headers=headers).json()["data"]["items"][0]
    assert ready["annotation_status"] == "READY"
    assert ready["judgments"][0]["chunk_id"] == chunk_id

    async def should_not_run(**_kwargs):
        raise AssertionError("已确认题目不应再次调用模型")

    with patch("app.services.label_suggestion.judge_relevance", new=should_not_run):
        again = client.post(
            f"/api/v1/evaluation/datasets/{dataset_id}/label-suggestions",
            json={"execute": True, "rerun": True},
            headers=headers,
        )
    assert again.status_code == 200, again.text
    assert again.json()["data"]["drafted"] == 0
    still = client.get(f"/api/v1/evaluation/datasets/{dataset_id}/cases", headers=headers).json()["data"]["items"][0]
    assert still["id"] == case_id
    assert still["annotation_status"] == "READY"
    assert still["judgments"][0]["chunk_id"] == chunk_id


def test_model_failure_keeps_case_pending(client: TestClient, identity: FakeIdentityClient) -> None:
    identity.grant(2, 12)
    headers = auth_header(2, 12)
    base_id = _create_base(client, headers, name="失败库")
    _upload(client, base_id, headers)
    dataset_id = _create_dataset(client, headers, base_id, name="初标失败")
    client.post(
        f"/api/v1/evaluation/datasets/{dataset_id}/cases",
        json={"question": "退货规则是什么？", "is_unanswerable": True, "needs_human_review": True},
        headers=headers,
    )

    async def broken(**_kwargs):
        raise RuntimeError("模型超时")

    with patch("app.services.label_suggestion.judge_relevance", new=broken):
        failed = client.post(
            f"/api/v1/evaluation/datasets/{dataset_id}/label-suggestions",
            json={"execute": True},
            headers=headers,
        )
    assert failed.status_code == 200, failed.text
    assert failed.json()["data"]["accepted"] is True
    job = client.get(f"/api/v1/evaluation/datasets/{dataset_id}/label-jobs/current", headers=headers)
    assert job.status_code == 200, job.text
    assert job.json()["data"]["status"] == "FAILED"
    assert job.json()["data"]["failed"] == 1
    case = client.get(f"/api/v1/evaluation/datasets/{dataset_id}/cases", headers=headers).json()["data"]["items"][0]
    assert case["annotation_status"] == "PENDING"
    assert case["is_unanswerable"] is True


def test_deleted_case_keeps_suggestion_but_blocks_review(client: TestClient, identity: FakeIdentityClient) -> None:
    headers = _grant(identity)
    base_id = _create_base(client, headers, name="删题库")
    _doc_id, chunk_id = _upload(client, base_id, headers)
    dataset_id = _create_dataset(client, headers, base_id, name="删题初标")
    created = client.post(
        f"/api/v1/evaluation/datasets/{dataset_id}/cases",
        json={"question": "退货规则是什么？", "expected_answer": "完好商品可以七天无理由。", "needs_human_review": True},
        headers=headers,
    )
    case_id = created.json()["data"]["id"]

    async def judge(**_kwargs):
        return {
            "verdict": "ANSWERABLE",
            "confidence": "HIGH",
            "rationale": "原文直接支持退货规则",
            "risk": "",
            "items": [{"chunk_id": chunk_id, "relevance": 3, "reason": "写明七天无理由", "excerpt": "七天无理由退货"}],
        }

    with patch("app.services.label_suggestion.judge_relevance", new=judge):
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

    deleted = client.delete(f"/api/v1/evaluation/cases/{case_id}", headers=headers)
    assert deleted.status_code == 200, deleted.text

    listed = client.get(f"/api/v1/evaluation/datasets/{dataset_id}/label-suggestions", headers=headers)
    assert listed.status_code == 200, listed.text
    row = listed.json()["data"][0]
    assert row["id"] == suggestion_id
    assert row["case_deleted"] is True
    assert row["question"] == "退货规则是什么？"

    rejected = client.post(
        f"/api/v1/evaluation/label-suggestions/{suggestion_id}/reject",
        json={"note": "驳回"},
        headers=headers,
    )
    assert rejected.status_code == 400
    assert rejected.json()["code"] == 40057

    confirmed = client.post(
        f"/api/v1/evaluation/datasets/{dataset_id}/label-suggestions/confirm",
        json={"suggestion_ids": [suggestion_id], "only_high": False},
        headers=headers,
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["data"]["confirmed"] == 0
    assert "删除" in confirmed.json()["data"]["errors"][0]["message"]

    removed = client.delete(f"/api/v1/evaluation/label-suggestions/{suggestion_id}", headers=headers)
    assert removed.status_code == 200, removed.text
    leftover = client.get(f"/api/v1/evaluation/datasets/{dataset_id}/label-suggestions", headers=headers)
    assert leftover.json()["data"] == []

"""评测断点续跑：阶段 checkpoint、预算、租约、租户隔离。全部使用 Mock 模型，不发起收费调用。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
from app.ai.errors import classify_model_http_error, describe_model_transport
from app.core.config import settings
from app.core.exceptions import AppError
from app.evaluation.retry import call_with_retry
from app.evaluation.stages import InterruptReason, PauseRun, interrupt_code_reason
from app.repositories.evaluation import EvaluationRepository
from app.services.evaluation_run import EvaluationRunService
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from tests.conftest import FakeIdentityClient
from tests.test_evaluation import _create_base, _create_dataset, _grant, _upload


def _empty_search(*_args, **_kwargs):
    return SimpleNamespace(hits=[], latency_ms=1, rerank_degraded=False, rerank_applied=False, stages={})


def _sync_sql(sql: str, params: dict | None = None):
    engine = create_engine(settings.database_url)
    try:
        with engine.begin() as connection:
            return connection.execute(text(sql), params or {})
    finally:
        engine.dispose()


def _start_keyword_experiment(client: TestClient, headers: dict[str, str], dataset_id: int, name: str, **config):
    payload = {"strategy": "KEYWORD", "top_k": 5, "evaluate_generation": False, **config}
    experiment = client.post(
        "/api/v1/evaluation/experiments",
        json={"dataset_id": dataset_id, "name": name, "config": payload},
        headers=headers,
    )
    assert experiment.status_code == 200, experiment.text
    return int(experiment.json()["data"]["id"])


def test_resume_100_cases_from_question_63(client: TestClient, identity: FakeIdentityClient, monkeypatch) -> None:
    headers = _grant(identity)
    base_id = _create_base(client, headers, "续跑库")
    dataset_id = _create_dataset(client, headers, base_id, "续跑100")
    items = [
        {
            "question": f"无答案题{index}",
            "is_unanswerable": True,
            "question_type": "UNANSWERABLE",
            "external_key": f"resume-{index}",
        }
        for index in range(1, 101)
    ]
    upserted = client.post(
        f"/api/v1/evaluation/datasets/{dataset_id}/upsert-cases",
        json={"items": items},
        headers=headers,
    )
    assert upserted.status_code == 200, upserted.text
    assert upserted.json()["data"]["created"] == 100

    search_calls = {"n": 0}

    async def fake_search(self, question, **kwargs):
        search_calls["n"] += 1
        return _empty_search()

    monkeypatch.setattr("app.services.retrieval.RetrievalService.search", fake_search)
    orig = EvaluationRunService._run_case_with_checkpoints
    paused = {"done": False}

    async def wrapped(self, run, case, *args, **kwargs):
        repo = EvaluationRepository(self.session, run.tenant_id)
        rows = await repo.list_results(run.id)
        success = sum(1 for row in rows if row.result_status == "SUCCESS")
        if success >= 62 and not paused["done"]:
            paused["done"] = True
            raise PauseRun(InterruptReason.TOKEN_BUDGET.value, "Token 预算耗尽")
        return await orig(self, run, case, *args, **kwargs)

    monkeypatch.setattr(EvaluationRunService, "_run_case_with_checkpoints", wrapped)
    experiment_id = _start_keyword_experiment(client, headers, dataset_id, "100题续跑")
    started = client.post(f"/api/v1/evaluation/experiments/{experiment_id}/run", headers=headers)
    assert started.status_code == 200, started.text
    run_id = started.json()["data"]["id"]
    paused_run = client.get(f"/api/v1/evaluation/runs/{run_id}", headers=headers).json()["data"]
    assert paused_run["status"] == "PAUSED"
    assert paused_run["interrupt_reason"] == "TOKEN_BUDGET"
    assert paused_run["usage"]["completed_count"] == 62
    assert paused_run["usage"]["pending_count"] == 38
    first_results = client.get(f"/api/v1/evaluation/runs/{run_id}/results", headers=headers).json()["data"]
    assert len(first_results) == 62
    first_questions = {item["question"] for item in first_results}
    first_ids = {item["id"] for item in first_results}
    calls_after_pause = search_calls["n"]
    assert calls_after_pause == 62

    resumed = client.post(
        f"/api/v1/evaluation/runs/{run_id}/resume",
        json={"token_budget": 500000},
        headers=headers,
    )
    assert resumed.status_code == 200, resumed.text
    finished = client.get(f"/api/v1/evaluation/runs/{run_id}", headers=headers).json()["data"]
    assert finished["status"] == "SUCCESS"
    assert finished["usage"]["completed_count"] == 100
    assert finished["usage"]["failed_count"] == 0
    assert search_calls["n"] == 100
    results = client.get(f"/api/v1/evaluation/runs/{run_id}/results", headers=headers).json()["data"]
    assert len(results) == 100
    assert len({item["case_id"] for item in results}) == 100
    unchanged = [item for item in results if item["id"] in first_ids]
    assert len(unchanged) == 62
    assert {item["question"] for item in unchanged} == first_questions

    full_id = _start_keyword_experiment(client, headers, dataset_id, "100题完整")
    full = client.post(f"/api/v1/evaluation/experiments/{full_id}/run", headers=headers)
    assert full.status_code == 200, full.text
    full_run = client.get(f"/api/v1/evaluation/runs/{full.json()['data']['id']}", headers=headers).json()["data"]
    assert full_run["status"] == "SUCCESS"
    assert full_run["metrics"] == finished["metrics"]


def test_judge_failure_reuses_generated_answer(client: TestClient, identity: FakeIdentityClient, monkeypatch) -> None:
    headers = _grant(identity)
    base_id = _create_base(client, headers, "Judge续跑库")
    _doc_id, chunk_id = _upload(client, headers=headers, base_id=base_id)
    dataset_id = _create_dataset(client, headers, base_id, "Judge续跑集")
    case = client.post(
        f"/api/v1/evaluation/datasets/{dataset_id}/cases",
        json={"question": "七天无理由怎么退？", "expected_answer": "七日内可退"},
        headers=headers,
    )
    case_id = case.json()["data"]["id"]
    client.put(
        f"/api/v1/evaluation/cases/{case_id}/judgments",
        json=[{"chunk_id": chunk_id, "relevance": 3}],
        headers=headers,
    )
    chat_calls = {"n": 0}
    judge_calls = {"n": 0}

    async def fake_chat(messages):
        chat_calls["n"] += 1
        return "七日内可退货。", {"prompt_tokens": 12, "completion_tokens": 8}

    async def fake_judge(**kwargs):
        judge_calls["n"] += 1
        if judge_calls["n"] == 1:
            return None, None, "Judge 输出不是合法 JSON"
        return (
            {"faithfulness": 0.9, "answer_relevancy": 0.8, "answer_correctness": 0.7, "subjective": True},
            {"ok": True},
            None,
        )

    monkeypatch.setattr("app.services.evaluation_run.collect_chat", fake_chat)
    monkeypatch.setattr("app.services.evaluation_run.judge_answer", fake_judge)
    experiment = client.post(
        "/api/v1/evaluation/experiments",
        json={
            "dataset_id": dataset_id,
            "name": "Judge复用",
            "config": {"strategy": "KEYWORD", "top_k": 5, "evaluate_generation": True},
        },
        headers=headers,
    )
    run = client.post(f"/api/v1/evaluation/experiments/{experiment.json()['data']['id']}/run", headers=headers)
    assert run.status_code == 200, run.text
    run_id = run.json()["data"]["id"]
    body = client.get(f"/api/v1/evaluation/runs/{run_id}", headers=headers).json()["data"]
    assert body["status"] == "SUCCESS"
    assert body["usage"]["failed_count"] == 1
    first = client.get(f"/api/v1/evaluation/runs/{run_id}/results", headers=headers).json()["data"][0]
    assert first["answer"] == "七日内可退货。"
    assert first["judge_error"]
    assert chat_calls["n"] == 1
    retried = client.post(f"/api/v1/evaluation/runs/{run_id}/retry-failed", headers=headers)
    assert retried.status_code == 200, retried.text
    again = client.get(f"/api/v1/evaluation/runs/{run_id}/results", headers=headers).json()["data"][0]
    assert again["answer"] == "七日内可退货。"
    assert again["judge_error"] is None
    assert again["generation_metrics"]["faithfulness"] == 0.9
    assert chat_calls["n"] == 1
    assert judge_calls["n"] == 2


def test_token_budget_pause_then_resume_with_higher_budget(
    client: TestClient, identity: FakeIdentityClient, monkeypatch
) -> None:
    headers = _grant(identity)
    base_id = _create_base(client, headers, "预算库")
    _doc_id, chunk_id = _upload(client, headers=headers, base_id=base_id)
    dataset_id = _create_dataset(client, headers, base_id, "预算集")
    for index in range(3):
        created = client.post(
            f"/api/v1/evaluation/datasets/{dataset_id}/cases",
            json={"question": f"退货政策{index}？", "expected_answer": "七日"},
            headers=headers,
        )
        client.put(
            f"/api/v1/evaluation/cases/{created.json()['data']['id']}/judgments",
            json=[{"chunk_id": chunk_id, "relevance": 3}],
            headers=headers,
        )
    monkeypatch.setattr("app.services.evaluation_run.estimate_next_call", lambda: 10)

    async def fake_chat(messages):
        return "七日可退。", {"prompt_tokens": 40, "completion_tokens": 20}

    async def fake_judge(**kwargs):
        return {"faithfulness": 1.0, "answer_relevancy": 1.0, "answer_correctness": 1.0}, {}, None

    monkeypatch.setattr("app.services.evaluation_run.collect_chat", fake_chat)
    monkeypatch.setattr("app.services.evaluation_run.judge_answer", fake_judge)
    experiment = client.post(
        "/api/v1/evaluation/experiments",
        json={
            "dataset_id": dataset_id,
            "name": "预算",
            "config": {"strategy": "KEYWORD", "top_k": 3, "evaluate_generation": True, "token_budget": 80},
        },
        headers=headers,
    )
    run = client.post(f"/api/v1/evaluation/experiments/{experiment.json()['data']['id']}/run", headers=headers)
    run_id = run.json()["data"]["id"]
    paused = client.get(f"/api/v1/evaluation/runs/{run_id}", headers=headers).json()["data"]
    assert paused["status"] == "PAUSED"
    assert paused["interrupt_reason"] == "TOKEN_BUDGET"
    used_before = int(paused["usage"]["prompt_tokens"]) + int(paused["usage"]["completion_tokens"])
    assert used_before > 0
    resumed = client.post(f"/api/v1/evaluation/runs/{run_id}/resume", json={"token_budget": 100000}, headers=headers)
    assert resumed.status_code == 200, resumed.text
    finished = client.get(f"/api/v1/evaluation/runs/{run_id}", headers=headers).json()["data"]
    assert finished["status"] == "SUCCESS"
    used_after = int(finished["usage"]["prompt_tokens"]) + int(finished["usage"]["completion_tokens"])
    assert used_after >= used_before
    assert finished["usage"]["completed_count"] == 3


def test_context_overflow_does_not_retry_forever(
    client: TestClient, identity: FakeIdentityClient, monkeypatch
) -> None:
    headers = _grant(identity)
    base_id = _create_base(client, headers, "超限库")
    _doc_id, chunk_id = _upload(client, headers=headers, base_id=base_id)
    dataset_id = _create_dataset(client, headers, base_id, "超限集")
    created = client.post(
        f"/api/v1/evaluation/datasets/{dataset_id}/cases",
        json={"question": "超长上下文？", "expected_answer": "七日"},
        headers=headers,
    )
    client.put(
        f"/api/v1/evaluation/cases/{created.json()['data']['id']}/judgments",
        json=[{"chunk_id": chunk_id, "relevance": 3}],
        headers=headers,
    )
    calls = {"n": 0}

    async def boom(messages):
        calls["n"] += 1
        raise AppError("单次请求超出模型上下文窗口", code=40093, status_code=400)

    monkeypatch.setattr(settings, "eval_model_retries", 5)
    monkeypatch.setattr("app.services.evaluation_run.collect_chat", boom)
    experiment = client.post(
        "/api/v1/evaluation/experiments",
        json={
            "dataset_id": dataset_id,
            "name": "超限",
            "config": {"strategy": "KEYWORD", "evaluate_generation": True},
        },
        headers=headers,
    )
    run = client.post(f"/api/v1/evaluation/experiments/{experiment.json()['data']['id']}/run", headers=headers)
    run_id = run.json()["data"]["id"]
    body = client.get(f"/api/v1/evaluation/runs/{run_id}", headers=headers).json()["data"]
    assert body["status"] == "SUCCESS"
    assert body["usage"]["failed_count"] == 1
    result = client.get(f"/api/v1/evaluation/runs/{run_id}/results", headers=headers).json()["data"][0]
    assert result["result_status"] == "FAILED"
    assert "上下文" in (result["error_message"] or "")
    assert calls["n"] == 1


def test_rate_limit_retries_then_pauses(client: TestClient, identity: FakeIdentityClient, monkeypatch) -> None:
    headers = _grant(identity)
    base_id = _create_base(client, headers, "限流库")
    _doc_id, chunk_id = _upload(client, headers=headers, base_id=base_id)
    dataset_id = _create_dataset(client, headers, base_id, "限流集")
    created = client.post(
        f"/api/v1/evaluation/datasets/{dataset_id}/cases",
        json={"question": "限流题？", "expected_answer": "七日"},
        headers=headers,
    )
    client.put(
        f"/api/v1/evaluation/cases/{created.json()['data']['id']}/judgments",
        json=[{"chunk_id": chunk_id, "relevance": 3}],
        headers=headers,
    )
    calls = {"n": 0}

    async def flaky(messages):
        calls["n"] += 1
        if calls["n"] < 3:
            raise AppError("模型服务限流，请稍后重试", code=42960, status_code=429)
        return "七日可退。", {"prompt_tokens": 4, "completion_tokens": 2}

    async def fake_judge(**kwargs):
        return {"faithfulness": 1.0, "answer_relevancy": 1.0, "answer_correctness": 1.0}, {}, None

    monkeypatch.setattr(settings, "eval_model_retries", 3)
    monkeypatch.setattr(settings, "eval_retry_base_seconds", 0.01)
    monkeypatch.setattr("app.services.evaluation_run.collect_chat", flaky)
    monkeypatch.setattr("app.services.evaluation_run.judge_answer", fake_judge)
    experiment = client.post(
        "/api/v1/evaluation/experiments",
        json={"dataset_id": dataset_id, "name": "429", "config": {"strategy": "KEYWORD", "evaluate_generation": True}},
        headers=headers,
    )
    run = client.post(f"/api/v1/evaluation/experiments/{experiment.json()['data']['id']}/run", headers=headers)
    body = client.get(f"/api/v1/evaluation/runs/{run.json()['data']['id']}", headers=headers).json()["data"]
    assert body["status"] == "SUCCESS"
    assert calls["n"] == 3


async def test_timeout_retries_then_pauses_run(monkeypatch) -> None:
    monkeypatch.setattr(settings, "eval_model_retries", 2)
    monkeypatch.setattr(settings, "eval_retry_base_seconds", 0.01)
    calls = {"n": 0}

    async def always_timeout():
        calls["n"] += 1
        raise AppError("模型服务超时", code=50460, status_code=504)

    try:
        await call_with_retry(always_timeout, what="generate")
        raise AssertionError("expected PauseRun")
    except PauseRun as exc:
        assert exc.reason == InterruptReason.TIMEOUT.value
        assert "可能已产生费用" in exc.message
        assert "已尝试 2 次" in exc.message
        assert "重试 1 次" in exc.message
    assert calls["n"] == 2


async def test_connection_error_pauses_as_network_not_rate_limit(monkeypatch) -> None:
    monkeypatch.setattr(settings, "eval_model_retries", 3)
    monkeypatch.setattr(settings, "eval_retry_base_seconds", 0.01)
    calls = {"n": 0}

    async def always_connect():
        calls["n"] += 1
        raise AppError("无法建立到 Embedding 服务的连接（ConnectError）", code=50262, status_code=502)

    try:
        await call_with_retry(always_connect, what="retrieve")
        raise AssertionError("expected PauseRun")
    except PauseRun as exc:
        assert exc.reason == InterruptReason.NETWORK.value
        assert exc.reason != InterruptReason.RATE_LIMIT.value
        assert "已尝试 3 次" in exc.message
        assert "重试 2 次" in exc.message
        assert "通常不会产生费用" in exc.message
        assert exc.diagnostics["exception_type"] == "AppError"
        assert exc.diagnostics["retry_count"] == 2
    assert calls["n"] == 3


def test_http_errors_keep_rate_limit_for_429_only() -> None:
    headers = httpx.Headers({"retry-after": "2", "x-request-id": "req-39", "authorization": "Bearer sk-secret"})
    limited = classify_model_http_error(429, '{"error":{"message":"slow down"}}', headers=headers)
    denied = classify_model_http_error(403, "forbidden", headers=headers)
    unpaid = classify_model_http_error(402, "insufficient balance")
    upstream = classify_model_http_error(503, "unavailable", headers=headers)
    connect = describe_model_transport(httpx.ConnectTimeout("timed out"), service="Embedding 服务")
    assert limited.code == 42960
    assert interrupt_code_reason(limited) == InterruptReason.RATE_LIMIT.value
    assert limited.data["retry_after_seconds"] == 2
    assert limited.data["request_id"] == "req-39"
    assert denied.code == 40360
    assert interrupt_code_reason(denied) == InterruptReason.FORBIDDEN.value
    assert unpaid.code == 40260
    assert interrupt_code_reason(unpaid) == InterruptReason.INSUFFICIENT_FUNDS.value
    assert upstream.code == 50260
    assert interrupt_code_reason(upstream) == InterruptReason.NETWORK.value
    assert interrupt_code_reason(connect) == InterruptReason.TIMEOUT.value
    assert "sk-secret" not in str(limited.data)


async def test_retry_respects_retry_after_and_skips_auth(monkeypatch) -> None:
    slept: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        slept.append(seconds)

    monkeypatch.setattr("app.evaluation.retry.asyncio.sleep", fake_sleep)
    monkeypatch.setattr(settings, "eval_model_retries", 2)
    calls = {"n": 0}

    async def limited():
        calls["n"] += 1
        raise AppError(
            "模型服务限流，密钥 sk-live-secret",
            code=42960,
            status_code=429,
            data={"retry_after_seconds": 1.5, "exception_type": "HTTPStatusError", "request_id": "req-1"},
        )

    try:
        await call_with_retry(limited, what="retrieve", stage="RETRIEVE", case_id=202)
        raise AssertionError("expected PauseRun")
    except PauseRun as exc:
        assert exc.reason == InterruptReason.RATE_LIMIT.value
        assert exc.diagnostics["retry_count"] == 1
        assert exc.diagnostics["case_id"] == 202
        assert exc.diagnostics["stage"] == "RETRIEVE"
        assert exc.diagnostics["request_id"] == "req-1"
        assert "sk-live-secret" not in exc.diagnostics["last_error"]
        assert "sk-" not in str(exc.diagnostics)
    assert slept == [1.5]
    assert calls["n"] == 2

    auth_calls = {"n": 0}

    async def invalid_key():
        auth_calls["n"] += 1
        raise AppError("模型服务认证失败", code=40160, status_code=502, data={"exception_type": "HTTPStatusError"})

    try:
        await call_with_retry(invalid_key, what="retrieve")
        raise AssertionError("expected PauseRun")
    except PauseRun as exc:
        assert exc.reason == InterruptReason.INVALID_KEY.value
        assert exc.diagnostics["retry_count"] == 0
    assert auth_calls["n"] == 1
    assert slept == [1.5]


def test_worker_restart_requeues_expired_lease(client: TestClient, identity: FakeIdentityClient, monkeypatch) -> None:
    headers = _grant(identity)
    base_id = _create_base(client, headers, "租约库")
    dataset_id = _create_dataset(client, headers, base_id, "租约集")
    for index in range(2):
        client.post(
            f"/api/v1/evaluation/datasets/{dataset_id}/cases",
            json={"question": f"无答案{index}", "is_unanswerable": True, "question_type": "UNANSWERABLE"},
            headers=headers,
        )
    async def fake_search(self, question, **kwargs):
        return _empty_search()

    monkeypatch.setattr("app.services.retrieval.RetrievalService.search", fake_search)
    orig = EvaluationRunService._run_case_with_checkpoints
    paused = {"done": False}

    async def wrapped(self, run, case, *args, **kwargs):
        repo = EvaluationRepository(self.session, run.tenant_id)
        rows = await repo.list_results(run.id)
        if rows and not paused["done"]:
            paused["done"] = True
            raise PauseRun(InterruptReason.WORKER_CRASH.value, "模拟崩溃")
        return await orig(self, run, case, *args, **kwargs)

    monkeypatch.setattr(EvaluationRunService, "_run_case_with_checkpoints", wrapped)
    experiment_id = _start_keyword_experiment(client, headers, dataset_id, "租约恢复")
    started = client.post(f"/api/v1/evaluation/experiments/{experiment_id}/run", headers=headers)
    run_id = started.json()["data"]["id"]
    assert client.get(f"/api/v1/evaluation/runs/{run_id}", headers=headers).json()["data"]["status"] == "PAUSED"

    expired = datetime.now(UTC) - timedelta(seconds=2)
    _sync_sql(
        """
        UPDATE evaluation_runs
        SET status = 'RUNNING', lease_owner = 'dead-worker', lease_until = :expired
        WHERE id = :id
        """,
        {"id": run_id, "expired": expired},
    )
    recovered = _sync_sql(
        """
        UPDATE evaluation_runs
        SET status = 'QUEUED', interrupt_reason = 'WORKER_CRASH', error_message = 'Worker 重启',
            lease_owner = NULL, lease_until = NULL, finished_at = NULL
        WHERE id = :id AND status = 'RUNNING' AND (lease_until IS NULL OR lease_until <= :now)
        """,
        {"id": run_id, "now": datetime.now(UTC)},
    )
    assert recovered.rowcount == 1
    still_held = _sync_sql(
        """
        UPDATE evaluation_runs
        SET status = 'QUEUED'
        WHERE id = :id AND status = 'RUNNING' AND lease_until > :now
        """,
        {"id": run_id, "now": datetime.now(UTC)},
    )
    assert still_held.rowcount == 0
    _sync_sql("UPDATE evaluation_runs SET status = 'PAUSED' WHERE id = :id", {"id": run_id})
    monkeypatch.setattr(EvaluationRunService, "_run_case_with_checkpoints", orig)
    resumed = client.post(f"/api/v1/evaluation/runs/{run_id}/resume", json={}, headers=headers)
    assert resumed.status_code == 200, resumed.text
    finished = client.get(f"/api/v1/evaluation/runs/{run_id}", headers=headers).json()["data"]
    assert finished["status"] == "SUCCESS"
    results = client.get(f"/api/v1/evaluation/runs/{run_id}/results", headers=headers).json()["data"]
    assert len(results) == 2


def test_same_run_concurrent_execute_is_idempotent(
    client: TestClient, identity: FakeIdentityClient, monkeypatch
) -> None:
    headers = _grant(identity)
    base_id = _create_base(client, headers, "并发库")
    dataset_id = _create_dataset(client, headers, base_id, "并发集")
    client.post(
        f"/api/v1/evaluation/datasets/{dataset_id}/cases",
        json={"question": "无答案并发", "is_unanswerable": True, "question_type": "UNANSWERABLE"},
        headers=headers,
    )
    monkeypatch.setattr(settings, "task_executor", "redis")
    monkeypatch.setattr("app.services.evaluation_run.enqueue_eval_run", AsyncMock(return_value=True))
    experiment_id = _start_keyword_experiment(client, headers, dataset_id, "并发租约")
    started = client.post(f"/api/v1/evaluation/experiments/{experiment_id}/run", headers=headers)
    run_id = started.json()["data"]["id"]
    assert started.json()["data"]["status"] == "QUEUED"

    until = datetime.now(UTC) + timedelta(seconds=45)
    first = _sync_sql(
        """
        UPDATE evaluation_runs
        SET lease_owner = 'worker-a', lease_until = :until
        WHERE id = :id AND status IN ('QUEUED', 'PAUSED', 'RUNNING')
          AND (lease_until IS NULL OR lease_until <= :now OR lease_owner = 'worker-a')
        """,
        {"id": run_id, "until": until, "now": datetime.now(UTC)},
    )
    second = _sync_sql(
        """
        UPDATE evaluation_runs
        SET lease_owner = 'worker-b', lease_until = :until
        WHERE id = :id AND status IN ('QUEUED', 'PAUSED', 'RUNNING')
          AND (lease_until IS NULL OR lease_until <= :now OR lease_owner = 'worker-b')
        """,
        {"id": run_id, "until": until, "now": datetime.now(UTC)},
    )
    assert first.rowcount == 1
    assert second.rowcount == 0
    cancelled = client.post(f"/api/v1/evaluation/runs/{run_id}/cancel", headers=headers)
    assert cancelled.status_code == 200
    monkeypatch.setattr(settings, "task_executor", "inline")
    experiment_b = _start_keyword_experiment(client, headers, dataset_id, "并发执行")
    executed = client.post(f"/api/v1/evaluation/experiments/{experiment_b}/run", headers=headers)
    run_b = executed.json()["data"]["id"]
    body = client.get(f"/api/v1/evaluation/runs/{run_b}", headers=headers).json()["data"]
    assert body["status"] == "SUCCESS"
    results = client.get(f"/api/v1/evaluation/runs/{run_b}/results", headers=headers).json()["data"]
    assert len(results) == 1
    assert len({item["case_id"] for item in results}) == 1


def test_pause_cancel_resume_race_and_tenant_isolation(
    client: TestClient, identity: FakeIdentityClient, monkeypatch
) -> None:
    headers = _grant(identity)
    base_id = _create_base(client, headers, "竞态库")
    dataset_id = _create_dataset(client, headers, base_id, "竞态集")
    client.post(
        f"/api/v1/evaluation/datasets/{dataset_id}/cases",
        json={"question": "无答案竞态", "is_unanswerable": True, "question_type": "UNANSWERABLE"},
        headers=headers,
    )
    monkeypatch.setattr(settings, "task_executor", "redis")
    monkeypatch.setattr("app.services.evaluation_run.enqueue_eval_run", AsyncMock(return_value=True))
    experiment_id = _start_keyword_experiment(client, headers, dataset_id, "竞态")
    started = client.post(f"/api/v1/evaluation/experiments/{experiment_id}/run", headers=headers)
    run_id = started.json()["data"]["id"]
    paused = client.post(f"/api/v1/evaluation/runs/{run_id}/pause", headers=headers)
    assert paused.json()["data"]["status"] == "PAUSED"
    cancelled = client.post(f"/api/v1/evaluation/runs/{run_id}/cancel", headers=headers)
    assert cancelled.json()["data"]["status"] == "CANCELLED"
    resume_cancelled = client.post(f"/api/v1/evaluation/runs/{run_id}/resume", json={}, headers=headers)
    assert resume_cancelled.status_code == 400

    other = _grant(identity, tenant_id=12, user_id=2)
    assert client.get(f"/api/v1/evaluation/runs/{run_id}", headers=other).status_code == 404
    assert client.post(f"/api/v1/evaluation/runs/{run_id}/resume", json={}, headers=other).status_code == 404
    assert client.post(f"/api/v1/evaluation/runs/{run_id}/pause", headers=other).status_code == 404


def test_resume_blocked_when_embedding_changed(
    client: TestClient, identity: FakeIdentityClient, monkeypatch
) -> None:
    headers = _grant(identity)
    base_id = _create_base(client, headers, "快照库")
    dataset_id = _create_dataset(client, headers, base_id, "快照集")
    client.post(
        f"/api/v1/evaluation/datasets/{dataset_id}/cases",
        json={"question": "无答案快照", "is_unanswerable": True, "question_type": "UNANSWERABLE"},
        headers=headers,
    )
    monkeypatch.setattr(settings, "task_executor", "redis")
    monkeypatch.setattr("app.services.evaluation_run.enqueue_eval_run", AsyncMock(return_value=True))
    experiment_id = _start_keyword_experiment(client, headers, dataset_id, "快照拦截")
    started = client.post(f"/api/v1/evaluation/experiments/{experiment_id}/run", headers=headers)
    run_id = started.json()["data"]["id"]
    client.post(f"/api/v1/evaluation/runs/{run_id}/pause", headers=headers)
    monkeypatch.setattr(settings, "embedding_model", "changed-embed")
    blocked = client.post(f"/api/v1/evaluation/runs/{run_id}/resume", json={}, headers=headers)
    assert blocked.status_code == 409
    assert blocked.json()["code"] == 40982


async def test_call_with_retry_skips_context_overflow(monkeypatch) -> None:
    monkeypatch.setattr(settings, "eval_model_retries", 4)
    calls = {"n": 0}

    async def overflow():
        calls["n"] += 1
        raise AppError("上下文超限", code=40093, status_code=400)

    try:
        await call_with_retry(overflow, what="generate")
        raise AssertionError("should raise")
    except AppError as exc:
        assert exc.code == 40093
    assert calls["n"] == 1

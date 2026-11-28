from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from app.core.config import settings
from app.models.conversation import MessageStatus
from app.services.chat_reconcile import SubscribeSnapshot, run_is_alive
from app.services.chat_run import ChatLiveRun, hub, subscribe
from app.services.persistent_chat import PersistentTurn


@pytest.fixture(autouse=True)
def _isolate_hub():
    hub._runs.clear()
    yield
    hub._runs.clear()


@pytest.mark.asyncio
async def test_sse_unsubscribe_does_not_cancel_live_run() -> None:
    live = ChatLiveRun(tenant_id=7, user_id=11, conversation_id=1, message_id=180, request_id="req")
    hub.register(live)

    async def disconnected() -> bool:
        return True

    events = [item async for item in subscribe(7, 11, 180, disconnected=disconnected)]
    assert events == []
    assert live.cancel.is_set() is False


@pytest.mark.asyncio
async def test_subscribe_replays_and_deduplicates_by_sequence() -> None:
    live = ChatLiveRun(tenant_id=7, user_id=11, conversation_id=1, message_id=12, request_id="req")
    hub.register(live)
    live.publish("message", {"delta": "一"})
    live.publish("message", {"delta": "二"})
    live.publish("done", {"answer": "一二"})
    live.close()

    first = [(seq, event) async for seq, event, _data in subscribe(7, 11, 12, after=0)]
    second = [(seq, event) async for seq, event, _data in subscribe(7, 11, 12, after=2)]
    assert [item[1] for item in first] == ["message", "message", "done"]
    assert [item[1] for item in second] == ["done"]


@pytest.mark.asyncio
async def test_orphan_like_message_180_is_not_alive() -> None:
    run = SimpleNamespace(
        status="RUNNING",
        tenant_id=7,
        message_id=180,
        worker_instance_id="dead-process:0000",
        heartbeat_at=datetime(2026, 11, 27, 13, 11, 40, tzinfo=UTC),
        started_at=datetime(2026, 11, 27, 13, 11, 40, tzinfo=UTC),
    )

    async def no_lease(_tenant_id: int, _message_id: int) -> bool:
        return False

    import app.services.chat_reconcile as reconcile

    original = reconcile.lease_alive
    reconcile.lease_alive = no_lease
    try:
        assert await run_is_alive(run) is False
    finally:
        reconcile.lease_alive = original


@pytest.mark.asyncio
async def test_debug_mode_holds_same_instance_only_when_hub_still_has_the_task(monkeypatch) -> None:
    from app.services.chat_run import WORKER_INSTANCE_ID

    monkeypatch.setattr(settings, "copilot_debug_disable_lease_recovery", True)
    live = ChatLiveRun(tenant_id=7, user_id=11, conversation_id=1, message_id=53, request_id="req")
    live.task = SimpleNamespace(done=lambda: False)  # type: ignore[assignment]
    hub.register(live)
    run = SimpleNamespace(
        status="RUNNING",
        tenant_id=7,
        message_id=53,
        worker_instance_id=WORKER_INSTANCE_ID,
        heartbeat_at=datetime.now(UTC) - timedelta(hours=12),
        started_at=datetime.now(UTC) - timedelta(hours=12),
    )

    async def no_lease(_tenant_id: int, _message_id: int) -> bool:
        return False

    import app.services.chat_reconcile as reconcile

    original = reconcile.lease_alive
    reconcile.lease_alive = no_lease
    try:
        assert await run_is_alive(run) is True
        hub.drop(7, 53)
        assert await run_is_alive(run) is False
    finally:
        reconcile.lease_alive = original


@pytest.mark.asyncio
async def test_legacy_running_without_lease_fields_is_not_alive() -> None:
    run = SimpleNamespace(
        status="RUNNING",
        tenant_id=7,
        message_id=180,
        worker_instance_id=None,
        heartbeat_at=None,
        lease_until=None,
        started_at=datetime(2026, 11, 27, 13, 11, 40, tzinfo=UTC),
    )

    async def no_lease(_tenant_id: int, _message_id: int) -> bool:
        return False

    import app.services.chat_reconcile as reconcile

    original = reconcile.lease_alive
    reconcile.lease_alive = no_lease
    try:
        assert await run_is_alive(run) is False
    finally:
        reconcile.lease_alive = original


@pytest.mark.asyncio
async def test_registered_run_without_task_is_treated_as_starting() -> None:
    live = ChatLiveRun(tenant_id=7, user_id=11, conversation_id=1, message_id=180, request_id="req")
    hub.register(live)
    run = SimpleNamespace(status="RUNNING", tenant_id=7, message_id=180, worker_instance_id=None)

    async def no_lease(_tenant_id: int, _message_id: int) -> bool:
        return False

    import app.services.chat_reconcile as reconcile

    original = reconcile.lease_alive
    reconcile.lease_alive = no_lease
    try:
        assert await run_is_alive(run) is True
    finally:
        reconcile.lease_alive = original


@pytest.mark.asyncio
async def test_debug_mode_does_not_hold_previous_process_instance(monkeypatch) -> None:
    monkeypatch.setattr(settings, "copilot_debug_disable_lease_recovery", True)
    run = SimpleNamespace(
        status="RUNNING",
        tenant_id=7,
        message_id=53,
        worker_instance_id="previous-debug-process:ffff",
        heartbeat_at=datetime.now(UTC) - timedelta(hours=12),
        started_at=datetime.now(UTC) - timedelta(hours=12),
    )

    async def no_lease(_tenant_id: int, _message_id: int) -> bool:
        return False

    import app.services.chat_reconcile as reconcile

    original = reconcile.lease_alive
    reconcile.lease_alive = no_lease
    try:
        assert await run_is_alive(run) is False
    finally:
        reconcile.lease_alive = original


def test_duplicate_running_request_resubscribes_instead_of_409() -> None:
    turn = PersistentTurn(1, 180, "55ceae2d957a4e3c80002cd7deb8f6e4", [], existing_running=True)
    assert turn.existing_running is True
    assert turn.duplicate_answer is None


def test_production_rejects_debug_timeout_exemption(monkeypatch) -> None:
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "copilot_debug_execution", True)
    monkeypatch.setattr(settings, "iam_jwks_url", "https://iam.example/.well-known/jwks.json")
    monkeypatch.setattr(settings, "model_provider", "openai_compat")
    monkeypatch.setattr(settings, "chat_api_key", "sk-test")
    monkeypatch.setattr(settings, "quota_enforcement_enabled", True)
    monkeypatch.setattr(settings, "action_graph_enabled", True)
    from pydantic import SecretStr

    monkeypatch.setattr(settings, "erp_execution_secret", SecretStr("x" * 32))
    with pytest.raises(RuntimeError, match="调试超时豁免"):
        settings.require_runtime_secrets()


def test_retry_policy_allows_interrupted_read_and_blocks_succeeded_tools() -> None:
    from app.services.conversations import _can_retry, _retry_denied_reason

    assert _can_retry("INTERRUPTED", []) is True
    assert _can_retry("CANCELLED", []) is True
    assert _can_retry("RUNNING", []) is False
    succeeded = [SimpleNamespace(status="SUCCEEDED", tool_name="list_sales_orders")]
    assert _can_retry("INTERRUPTED", succeeded) is False
    assert "成功的工具结果" in (_retry_denied_reason("INTERRUPTED", succeeded) or "")
    unknown_write = [SimpleNamespace(status="RUNNING", tool_name="propose_action")]
    assert _can_retry("FAILED", unknown_write) is False
    assert "写操作" in (_retry_denied_reason("FAILED", unknown_write) or "")


def test_message_status_includes_interrupt_and_timeout() -> None:
    assert MessageStatus.INTERRUPTED.value == "INTERRUPTED"
    assert MessageStatus.TIMED_OUT.value == "TIMED_OUT"


def test_unknown_subscribe_snapshot_does_not_emit_done() -> None:
    snapshot = SubscribeSnapshot(
        kind="unknown",
        message_id=180,
        request_id="req",
        status="RUNNING",
        content="",
        reason="run_not_ready",
    )
    assert snapshot.event_name() == "run_status"
    assert snapshot.to_event()["subscribe_status"] == "unknown"
    terminal = SubscribeSnapshot(
        kind="unavailable",
        message_id=180,
        request_id="req",
        status="INTERRUPTED",
        content="",
        reason="worker_lost",
        can_retry=True,
    )
    assert terminal.event_name() == "done"
    assert terminal.to_event()["can_retry"] is True

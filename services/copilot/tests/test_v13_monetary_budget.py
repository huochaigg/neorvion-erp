from decimal import Decimal
from types import SimpleNamespace

import pytest
from app.core.exceptions import AppError
from app.services import quotas


class _Redis:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    async def eval(self, *args):
        self.calls.append(args)
        if args[1] == 8 and "HSET" in args[0]:
            return [1, 0, args[-7], 1, 0, args[-4]]
        return 1


class _Session:
    def __init__(self, quota, pricing) -> None:
        self.values = [quota, pricing]

    async def scalar(self, _statement):
        return self.values.pop(0)

    def add(self, _row) -> None:
        return None

    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        return None


def _quota():
    return SimpleNamespace(
        requests_per_minute=30,
        requests_per_day=1000,
        monthly_token_limit=1_000_000,
        monthly_budget=Decimal("1.0000"),
        currency="CNY",
        max_concurrent_agents=3,
    )


def _pricing():
    return SimpleNamespace(
        input_price=Decimal("1.00000000"),
        output_price=Decimal("2.00000000"),
        currency="CNY",
        unit_tokens=1_000_000,
        pricing_version="2026-10",
    )


@pytest.mark.asyncio
async def test_monetary_budget_is_reserved_atomically_and_unknown_usage_is_conservative(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis = _Redis()
    monkeypatch.setattr(quotas.settings, "quota_enforcement_enabled", True)
    monkeypatch.setattr(quotas.settings, "budget_max_model_calls_per_request", 12)
    monkeypatch.setattr(quotas, "async_redis", lambda: redis)

    reservation = await quotas.reserve_chat_quota(
        _Session(_quota(), _pricing()), 7, 100, scenario="CHAT"
    )

    assert isinstance(reservation, quotas.QuotaReservation)
    assert reservation.estimated_money_micros == 2400
    await reservation.settle(None)
    settle = redis.calls[-1]
    assert settle[-2:] == (-1, -1)


@pytest.mark.asyncio
async def test_trusted_single_call_usage_settles_with_versioned_price(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis = _Redis()
    monkeypatch.setattr(quotas.settings, "quota_enforcement_enabled", True)
    monkeypatch.setattr(quotas, "async_redis", lambda: redis)
    reservation = await quotas.reserve_chat_quota(
        _Session(_quota(), _pricing()), 7, 100, scenario="INSIGHT"
    )

    await reservation.settle(10, usage_trusted=True)

    settle = redis.calls[-1]
    assert settle[-2:] == (10, 20)


@pytest.mark.asyncio
async def test_budget_with_missing_price_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(quotas.settings, "quota_enforcement_enabled", True)
    with pytest.raises(AppError) as error:
        await quotas.reserve_chat_quota(_Session(_quota(), None), 7, 100)
    assert error.value.code == 50377

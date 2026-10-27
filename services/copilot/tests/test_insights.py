from datetime import UTC, datetime

import pytest
from app.core.exceptions import AppError
from app.insights.detectors import detect, detector_registry

NOW = datetime(2026, 10, 26, 8, tzinfo=UTC)


def test_low_stock_uses_available_inventory_and_threshold() -> None:
    config = detector_registry.validate("LOW_STOCK_RISK", {"threshold": 5})
    rows = detect(
        "LOW_STOCK_RISK",
        config,
        {"items": [{"warehouse_id": 1, "sku_id": 2, "quantity": 10, "reserved_quantity": 8}]},
        now=NOW,
    )
    assert len(rows) == 1
    assert rows[0]["evidence_summary"]["available_quantity"] == 2
    assert rows[0]["evidence_summary"]["threshold"] == 5


def test_purchase_delay_requires_real_expected_arrival_date() -> None:
    config = detector_registry.validate("PURCHASE_ARRIVAL_DELAY", {"grace_days": 0})
    rows = detect(
        "PURCHASE_ARRIVAL_DELAY",
        config,
        {
            "items": [
                {"id": 1, "status": "WAITING_RECEIPT", "expected_arrival_date": None},
                {"id": 2, "status": "WAITING_RECEIPT", "expected_arrival_date": "2026-10-20"},
                {"id": 3, "status": "RECEIVED", "expected_arrival_date": "2026-10-20"},
            ]
        },
        now=NOW,
    )
    assert [x["resource_id"] for x in rows] == ["2"]


def test_overdue_shipment_explicitly_uses_processing_sla() -> None:
    config = detector_registry.validate("OVERDUE_SHIPMENT", {"processing_sla_hours": 24})
    rows = detect(
        "OVERDUE_SHIPMENT",
        config,
        {
            "items": [
                {"id": 8, "status": "WAITING_OUTBOUND", "created_at": "2026-10-24T00:00:00+00:00"}
            ]
        },
        now=NOW,
    )
    assert rows[0]["evidence_summary"]["basis"] == "PROCESSING_SLA"


def test_inventory_coverage_uses_decimal_and_zero_sales_is_not_risk() -> None:
    config = detector_registry.validate(
        "INVENTORY_COVERAGE_RISK",
        {"sku_code": "SKU-1", "lookback_days": 30, "minimum_coverage_days": "7"},
    )
    rows = detect(
        "INVENTORY_COVERAGE_RISK",
        config,
        {"available_quantity": "6", "sales_quantity": "60", "period_days": 30},
        now=NOW,
    )
    assert rows[0]["evidence_summary"]["coverage_days"] == "3.00"
    assert (
        detect(
            "INVENTORY_COVERAGE_RISK",
            config,
            {"available_quantity": "6", "sales_quantity": "0", "period_days": 30},
            now=NOW,
        )
        == []
    )


def test_detector_rejects_dynamic_or_unknown_config() -> None:
    with pytest.raises(AppError):
        detector_registry.validate("LOW_STOCK_RISK", {"threshold": 5, "sql": "DROP TABLE x"})
    with pytest.raises(AppError):
        detector_registry.validate("UNKNOWN", {})


def test_fingerprint_is_stable_for_duplicate_suppression() -> None:
    config = detector_registry.validate("LOW_STOCK_RISK", {"threshold": 5})
    data = {"items": [{"warehouse_id": 1, "sku_id": 2, "available_quantity": 1}]}
    assert (
        detect("LOW_STOCK_RISK", config, data, now=NOW)[0]["fingerprint"]
        == detect("LOW_STOCK_RISK", config, data, now=NOW)[0]["fingerprint"]
    )

from __future__ import annotations

import json
from pathlib import Path

from app.evaluation.metrics import aggregate_metrics, compare_runs, evaluate_case


def _case() -> dict:
    return {
        "expected_behavior": {"expected_refusal": False},
        "expected_tools": {
            "required": ["get_inventory"],
            "optional": ["get_product"],
            "forbidden": ["adjust_inventory"],
        },
        "expected_arguments": [{"tool": "get_inventory", "path": "sku_code", "equals": "SKU-TEST"}],
        "expected_evidence": {"types": ["ERP"]},
        "expected_answer_assertions": [{"kind": "contains", "value": "库存"}],
        "forbidden_actions": ["ERP_WRITE"],
    }


def _result() -> dict:
    return {
        "transport_success": True,
        "agent_completed": True,
        "answer": "库存为 10 [E1]",
        "tool_calls": [
            {
                "name": "get_inventory",
                "arguments": {"sku_code": "SKU-TEST"},
                "status": "SUCCEEDED",
                "duration_ms": 12,
            }
        ],
        "evidences": [
            {
                "citation_id": "E1",
                "source_type": "ERP",
                "valid": True,
                "permission_valid": True,
                "fresh": True,
            }
        ],
        "cited_ids": ["E1"],
        "grounded_claim_total": 1,
        "grounded_claim_supported": 1,
        "unsafe_action_attempts": 0,
        "unsafe_action_executions": 0,
        "latency_ms": 30,
        "model_calls": 1,
        "usage": {"input_tokens": 20, "output_tokens": 8},
    }


def test_deterministic_case_metrics_pass() -> None:
    outcome, metrics, assertions = evaluate_case(_case(), _result())
    assert outcome == "TASK_SUCCESS"
    assert metrics["tool_selection_accuracy"] == 1
    assert metrics["tool_argument_accuracy"] == 1
    assert metrics["citation_validity"] == 1
    assert all(item["passed"] for item in assertions)


def test_security_execution_is_hard_failure_even_when_answer_passes() -> None:
    result = _result() | {"unsafe_action_executions": 1}
    outcome, metrics, _ = evaluate_case(_case(), result)
    assert outcome == "TASK_FAILED"
    assert metrics["unsafe_action_executions"] == 1


def test_unknown_usage_is_not_coerced_to_zero() -> None:
    result = _result()
    result.pop("usage")
    _, metrics, _ = evaluate_case(_case(), result)
    aggregate = aggregate_metrics([{"task_outcome": "TASK_SUCCESS", "metrics": metrics}])
    assert aggregate["input_tokens"] is None
    assert aggregate["estimated_cost"] is None
    assert aggregate["token_applicable_cases"] == 0


def test_indeterminate_is_reported_separately() -> None:
    outcome, _, _ = evaluate_case(
        {
            "expected_behavior": {},
            "expected_tools": {},
            "expected_arguments": [],
            "expected_evidence": {},
            "expected_answer_assertions": [],
            "forbidden_actions": [],
        },
        {"transport_success": True, "agent_completed": True},
    )
    assert outcome == "INDETERMINATE"


def test_comparison_pairs_cases_and_finds_regression() -> None:
    report = compare_runs(
        [{"case_key": "a", "task_outcome": "TASK_SUCCESS", "metrics": {}}],
        [{"case_key": "a", "task_outcome": "TASK_FAILED", "metrics": {}}],
    )
    assert report["regressed"] == ["a"]
    assert report["new_failures"] == ["a"]


def test_v9_catalog_has_required_distribution_and_review_states() -> None:
    rows = json.loads(
        (Path(__file__).parents[1] / "evals" / "v9_agent_100.json").read_text(encoding="utf-8")
    )
    assert len(rows) == 100
    assert sum(item["status"] == "READY" for item in rows) == 40
    assert sum(item["status"] == "NEEDS_REVIEW" for item in rows) == 60
    assert all(item["expected_tools"]["forbidden"] for item in rows)

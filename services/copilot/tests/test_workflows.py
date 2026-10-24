from app.core.config import settings
from app.core.permissions import PermissionCode
from app.models.workflow import WorkflowInstance
from app.tasks.worker import _schedule_reconciliation_retry
from app.workflows.compensation import compensation_registry
from app.workflows.registry import build_workflow_registry


def test_workflow_registry_is_closed_and_separate_from_tools() -> None:
    registry = build_workflow_registry()
    assert {item.workflow_type for item in registry.all()} == {
        "INVENTORY_REPLENISHMENT_WORKFLOW",
        "SALES_ORDER_REVIEW_WORKFLOW",
    }
    replenishment = registry.get("INVENTORY_REPLENISHMENT_WORKFLOW")
    assert PermissionCode.PURCHASE_CREATE.value not in replenishment.permissions
    assert any(step.step_type == "V6_EXECUTION" for step in replenishment.steps)


def test_compensation_never_invents_erp_delete() -> None:
    safe = compensation_registry.for_step("ERP_READ")
    unsafe = compensation_registry.for_step("V6_EXECUTION")
    assert safe.automatic is True and safe.action is None
    assert unsafe.automatic is False and unsafe.action is None


def test_reconciliation_retry_is_bounded(monkeypatch) -> None:
    monkeypatch.setattr(settings, "workflow_reconcile_max_attempts", 2)
    row = WorkflowInstance(
        id=41,
        tenant_id=7,
        user_id=11,
        workflow_type="INVENTORY_REPLENISHMENT_WORKFLOW",
        schema_version=1,
        status="RECONCILING",
        current_step="v6_execution",
        graph_thread_id="business-workflow:41",
        idempotency_key="reconcile-41",
        input_snapshot={},
        result_summary={},
        run_attempts=0,
    )

    retry_event = _schedule_reconciliation_retry(row, 7)
    assert row.status == "RECONCILING"
    assert row.lease_until is not None
    assert retry_event.event_type == "WORKFLOW_RECONCILIATION_RETRY"

    exhausted_event = _schedule_reconciliation_retry(row, 7)
    assert row.status == "NEEDS_MANUAL_INTERVENTION"
    assert row.lease_until is None
    assert exhausted_event.event_type == "WORKFLOW_RECONCILIATION_EXHAUSTED"

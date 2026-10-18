from app.core.exceptions import AppError
from app.models.async_task import AsyncTask
from app.tasks.handlers import _context


def test_worker_context_requires_snapshot() -> None:
    task = AsyncTask(
        task_id="t-missing-snap",
        task_type="REPORT_EXPORT",
        title="export",
        tenant_id=1,
        created_by=999001,
        payload={"kind": "sales_trend"},
    )
    try:
        _context(task)
        raise AssertionError("missing snapshot must not be allowed")
    except AppError as exc:
        assert exc.status_code in {403, 401, 503}
        assert exc.code in {40310, 40330, 40104, 50313}


def test_worker_context_requires_principal() -> None:
    task = AsyncTask(
        task_id="t-no-user",
        task_type="REPORT_EXPORT",
        title="export",
        tenant_id=1,
        created_by=None,
        payload={"kind": "sales_trend"},
    )
    try:
        _context(task)
        raise AssertionError("anonymous worker identity must not be allowed")
    except AppError as exc:
        assert exc.code == 40330

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from procurepilot_api.deps import CurrentMember
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.exports.schemas import ExportCreate, ExportFilters
from procurepilot_api.modules.exports.service import ExportService
from procurepilot_api.modules.savings.service import SavingsService


class _Cursor:
    def __init__(self, rows: list[dict[str, object]] | None = None) -> None:
        self._rows = rows or []

    def __enter__(self) -> _Cursor:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def execute(self, *_args: object, **_kwargs: object) -> None:
        return None

    def fetchall(self) -> list[dict[str, object]]:
        return self._rows

    def fetchone(self) -> dict[str, object]:
        return self._rows[0]


class _Conn:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self._rows = rows

    def __enter__(self) -> _Conn:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def cursor(self, **_kwargs: object) -> _Cursor:
        return _Cursor(self._rows)


def _member() -> CurrentMember:
    return CurrentMember(
        membership_id=uuid4(),
        tenant_id=uuid4(),
        user_id=uuid4(),
        email="buyer@example.test",
        role=MemberRole.buyer,
    )


def test_savings_ledger_read_caps_limit_at_100(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = []
    for _index in range(101):
        saving_id = uuid4()
        rows.append(
            {
                "id": saving_id,
                "purchase_record_id": uuid4(),
                "workspace_product_id": uuid4(),
                "supplier_id": None,
                "status": "pending",
                "baseline_policy": "none_available",
                "baseline_source_landed_cost_ids": [],
                "baseline_unit_price_amount": None,
                "baseline_unit_price_currency": None,
                "baseline_value_amount": None,
                "baseline_value_currency": None,
                "actual_value_amount": "1.0000",
                "actual_value_currency": "GBP",
                "delta_amount": None,
                "delta_currency": None,
                "calculation_version": "saving-baseline-v1",
                "calculation_inputs": {},
                "recorded_by": uuid4(),
                "recorded_at": datetime.now(UTC),
                "verified_by": None,
                "verified_at": None,
            }
        )
    monkeypatch.setattr(
        "procurepilot_api.modules.savings.service._authenticated_db",
        lambda *_args, **_kwargs: _Conn(rows),
    )

    page = SavingsService(settings=object()).list_savings(member=_member(), limit=500)

    assert len(page.items) == 100
    assert page.next_cursor is not None


def test_large_period_export_creation_stays_async_and_does_not_render(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant_id = uuid4()
    job_id = uuid4()
    conn = _Conn(
        [
            {
                "id": job_id,
                "tenant_id": tenant_id,
                "kind": "savings_ledger",
                "format": "xlsx",
                "filters": {"period_start": "2020-01-01", "period_end": "2026-12-31"},
                "status": "queued",
                "created_at": datetime.now(UTC),
                "started_at": None,
                "completed_at": None,
                "row_count": None,
                "download_url": None,
                "error": None,
            }
        ]
    )
    enqueued = {"count": 0}
    monkeypatch.setattr(
        "procurepilot_api.modules.exports.service._authenticated_db",
        lambda *_args, **_kwargs: conn,
    )
    monkeypatch.setattr(
        "procurepilot_api.modules.exports.service._enqueue_export_job",
        lambda *_args, **_kwargs: enqueued.__setitem__("count", enqueued["count"] + 1),
    )

    job = ExportService(settings=object()).create_job(
        member=_member().model_copy(update={"tenant_id": tenant_id}),
        payload=ExportCreate(
            kind="savings_ledger",
            format="xlsx",
            filters=ExportFilters(period_start="2020-01-01", period_end="2026-12-31"),
        ),
    )

    assert job.status == "queued"
    assert enqueued["count"] == 1

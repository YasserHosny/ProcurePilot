"""The job response carries the settings it was run with, so a rerun can reuse them exactly."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from procurepilot_api.modules.offers.basket_service import _job


def _row(snapshot: object) -> dict[str, object]:
    return {
        "id": uuid4(),
        "supplier_ids": [uuid4(), uuid4()],
        "items": [{"workspace_product_id": str(uuid4()), "quantity": "10.000000"}],
        "status": "completed",
        "result": None,
        "error": None,
        "created_at": datetime(2026, 11, 3, tzinfo=UTC),
        "request_snapshot": snapshot,
    }


def test_job_returns_the_risk_urgency_exclusions_and_weights_it_ran_with() -> None:
    excluded = str(uuid4())
    weights = {
        "price": 0.5,
        "preferred_supplier": 0.1,
        "risk": 0.2,
        "lead_time": 0.1,
        "quality": 0.1,
    }
    job = _job(
        _row(
            {
                "kind": "advanced_basket_optimisation",
                "risk_tolerance": "low",
                "urgency": "urgent",
                "excluded_supplier_ids": [excluded],
                "weights": weights,
            }
        )
    )

    assert job.request_settings is not None
    assert job.request_settings.risk_tolerance == "low"
    assert job.request_settings.urgency == "urgent"
    assert [str(i) for i in job.request_settings.excluded_supplier_ids] == [excluded]
    assert job.request_settings.weights.price == 0.5


def test_job_without_recorded_settings_says_so_instead_of_guessing() -> None:
    # Older jobs and the plain two-supplier basket never stored them.
    assert _job(_row({"pack_snapshot": {}})).request_settings is None
    assert _job(_row(None)).request_settings is None

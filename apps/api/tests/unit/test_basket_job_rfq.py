"""Spec 024 T008: a basket job started from an RFQ says which RFQ."""

from datetime import UTC, datetime
from uuid import uuid4

from procurepilot_api.modules.offers.basket_service import _job


def _row(**extra: object) -> dict[str, object]:
    return {
        "id": uuid4(),
        "supplier_ids": [uuid4(), uuid4()],
        "items": [],
        "status": "queued",
        "created_at": datetime.now(UTC),
        **extra,
    }


def test_a_job_from_an_rfq_names_it() -> None:
    rfq_id = uuid4()
    assert _job(_row(rfq_id=rfq_id)).rfq_id == rfq_id


def test_a_standalone_job_has_no_rfq() -> None:
    assert _job(_row()).rfq_id is None
    assert _job(_row(rfq_id=None)).rfq_id is None

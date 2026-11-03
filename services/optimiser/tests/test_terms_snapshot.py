"""A job's commercial-terms snapshot is what the buyer saw; an empty one is still a snapshot."""

from __future__ import annotations

from uuid import uuid4

import pytest

from procurepilot_optimiser_worker import repository
from procurepilot_optimiser_worker.models import (
    AdvancedBasketRequest,
    AdvancedOfferInput,
    BasketItem,
    Money,
    OptimisationHardConstraints,
)


def _request() -> AdvancedBasketRequest:
    return AdvancedBasketRequest(
        id=uuid4(),
        tenant_id=uuid4(),
        supplier_ids=[uuid4(), uuid4()],
        items=[BasketItem(workspace_product_id=uuid4(), quantity="1.000000")],
        hard_constraints=OptimisationHardConstraints(),
        rule_version="advanced-basket-v1",
    )


@pytest.mark.parametrize(
    ("snapshot", "live_terms_read"),
    [
        ({"rule_version": "advanced-basket-v1"}, True),  # nothing was captured: read the live terms
        ({"rule_version": "advanced-basket-v1", "supplier_terms": []}, False),  # captured: none
    ],
)
def test_live_terms_replace_only_a_snapshot_that_was_never_taken(
    monkeypatch: pytest.MonkeyPatch, snapshot: dict[str, object], live_terms_read: bool
) -> None:
    request = _request()
    offer = AdvancedOfferInput(
        offer_id=uuid4(),
        workspace_product_id=request.items[0].workspace_product_id,
        supplier_id=request.supplier_ids[0],
        quantity="1.000000",
        total_landed_cost=Money(amount="10.0000", currency="GBP"),
        unit_landed_cost=Money(amount="10.0000", currency="GBP"),
        source_landed_cost_id=uuid4(),
    )
    reads: list[int] = []

    def read_live_terms(conn: object, *, request: object) -> list[object]:
        reads.append(1)
        return []

    monkeypatch.setattr(repository, "_load_advanced_job_snapshot", lambda *a, **k: ({}, snapshot))
    monkeypatch.setattr(repository, "_advanced_request_from_snapshot", lambda **k: request)
    monkeypatch.setattr(repository, "read_current_advanced_offers", lambda *a, **k: [offer])
    monkeypatch.setattr(repository, "read_supplier_terms", read_live_terms)
    monkeypatch.setattr(repository, "read_supplier_risks", lambda *a, **k: [])

    repository.load_advanced_optimisation_input(object(), job_id=uuid4(), tenant_id=uuid4())

    assert bool(reads) is live_terms_read

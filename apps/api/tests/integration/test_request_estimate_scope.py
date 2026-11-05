"""A request line's estimate is read in the caller's workspace, not as the table owner (PPS-185).


`RequestsService._estimate_products` used to read `landed_cost`, `current_match_decision` and
`purchase_request` over a bare owner connection, so what it could see was decided only by the
product ids the caller had already passed through RLS. It now reads inside the caller's own
database role and claims, so a product or request of another workspace has no estimate.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from integration.catalogue_helpers import TEST_DATABASE_URL
from integration.smart_compare_helpers import (
    add_costed_offer,
    committed_smart_context,
    member_from_workspace,
    settings_for_test_db,
)
from procurepilot_api.modules.requests.service import RequestsService

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL not set; needs Postgres with the migrations applied",
)


def test_a_caller_gets_the_estimate_of_their_own_product(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = settings_for_test_db(monkeypatch)
    with committed_smart_context("p161-own") as own:
        add_costed_offer(own, supplier_id=own.supplier_ids[0], amount=Decimal("42.00"))
        (estimate,) = RequestsService(settings)._estimate_products(
            [own.product_id], member=member_from_workspace(own.workspace)
        )
    assert estimate.unit_price_amount == Decimal("42.00")
    assert estimate.source_landed_cost_id is not None


def test_a_product_of_another_workspace_has_no_estimate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = settings_for_test_db(monkeypatch)
    with committed_smart_context("p161-a") as caller, committed_smart_context("p161-b") as other:
        add_costed_offer(other, supplier_id=other.supplier_ids[0], amount=Decimal("77.00"))
        (estimate,) = RequestsService(settings)._estimate_products(
            [other.product_id], member=member_from_workspace(caller.workspace)
        )
    assert estimate.unit_price_amount is None
    assert estimate.source_landed_cost_id is None

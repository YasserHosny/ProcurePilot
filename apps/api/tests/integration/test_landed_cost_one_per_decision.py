"""A decision's cost is its latest landed_cost row (ADR-021).

landed_cost is append-only, so a rule change appends a row for an existing decision: since
landed-cost-v2 a decision can hold a v1 row and a v2 row (the PPS-122 correction, a repaired
decision). Readers that list offers, price history or alert rows must count that decision once.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg.types.json import Jsonb

from integration.catalogue_helpers import TEST_DATABASE_URL
from integration.smart_compare_helpers import (
    CostedOffer,
    add_costed_offer,
    committed_smart_context,
    settings_for_test_db,
)
from procurepilot_api.modules.alerts import conditions
from procurepilot_api.modules.offers.service import OfferService
from procurepilot_api.modules.savings import baseline

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is not set; needs a migrated local Postgres",
)


def _append_v2_row(offer: CostedOffer, *, amount: Decimal, recorded_at: datetime) -> UUID:
    """The same offer recomputed under landed-cost-v2: same total, appended, never updated."""
    landed_cost_id = uuid4()
    raw_inputs = {
        "quantity": "1.000000",
        "normalised_base_quantity": "30.000000",
        "base_unit": "litre",
        "unit_price": {"amount": f"{amount:.4f}", "currency": "GBP"},
        "vat_rate": "0.0000",
        "vat_amount": {"amount": "0.0000", "currency": "GBP"},
        "delivery_fee": {"amount": "0.0000", "currency": "GBP"},
        "discount": {"amount": "0.0000", "currency": "GBP"},
        "other_charges": {"amount": "0.0000", "currency": "GBP"},
        "prices_include_vat": False,
    }
    with psycopg.connect(TEST_DATABASE_URL, prepare_threshold=None) as conn:
        conn.execute(
            """
            insert into landed_cost (
              id, tenant_id, quotation_line_id, match_decision_id, quantity,
              normalised_base_quantity, base_unit, unit_price_amount, unit_price_currency,
              vat_amount, vat_currency, delivery_fee_amount, delivery_fee_currency,
              discount_amount, discount_currency, other_charges_amount, other_charges_currency,
              total_amount, total_currency, raw_inputs, rule_version, valid_from, valid_to,
              recorded_at
            )
            select %s, tenant_id, quotation_line_id, match_decision_id, quantity,
                   normalised_base_quantity, base_unit, unit_price_amount, unit_price_currency,
                   0, vat_currency, 0, delivery_fee_currency, 0, discount_currency,
                   0, other_charges_currency, total_amount, total_currency, %s,
                   'landed-cost-v2', valid_from, valid_to, %s
            from landed_cost where id = %s
            """,
            (landed_cost_id, Jsonb(raw_inputs), recorded_at, offer.landed_cost_id),
        )
    return landed_cost_id


def test_a_decision_with_a_v1_and_a_v2_row_is_counted_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = settings_for_test_db(monkeypatch)
    now = datetime.now(UTC)
    with committed_smart_context("one-cost-per-decision") as context:
        offer = add_costed_offer(
            context,
            supplier_id=context.supplier_ids[0],
            amount=Decimal("30.0000"),
            recorded_at=now - timedelta(days=1),
        )
        v2_id = _append_v2_row(offer, amount=Decimal("30.0000"), recorded_at=now)

        # The offer list shows one offer for the supplier, the newer row.
        compare_offers = conditions._landed_cost_offers(
            settings, context.member, context.product_id
        )
        assert [o.id for o in compare_offers] == [v2_id]

        # Not flagged as a duplicate of itself.
        assert (
            conditions._duplicate_line_alerts(
                context.member, compare_offers, context.product_id, now
            )
            == []
        )

        # One price-history point for the decision, in offers and in savings.
        history = OfferService(settings).price_history(
            member=context.member, product_id=context.product_id
        )
        assert [point.landed_cost_id for point in history.points] == [v2_id]
        with psycopg.connect(TEST_DATABASE_URL, prepare_threshold=None) as conn:
            points, _rows = baseline._price_history_points(conn, context.product_id)
        assert [point.landed_cost_id for point in points] == [v2_id]

        # The v1 row is still there as evidence.
        with psycopg.connect(TEST_DATABASE_URL, prepare_threshold=None) as conn:
            count = conn.execute(
                "select count(*) from landed_cost where match_decision_id = %s",
                (offer.match_decision_id,),
            ).fetchone()
        assert count == (2,)

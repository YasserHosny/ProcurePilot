from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from integration.catalogue_helpers import TEST_DATABASE_URL
from integration.smart_compare_helpers import (
    add_costed_offer,
    committed_smart_context,
    settings_for_test_db,
)
from procurepilot_api.errors import NotFoundError
from procurepilot_api.modules.offers.service import OfferService

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is not set; needs a migrated local Postgres",
)


def test_compare_reads_real_reviewed_offers_and_excludes_expired_from_recommendation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = settings_for_test_db(monkeypatch)
    with committed_smart_context("offers-expired") as context:
        expired = add_costed_offer(
            context,
            supplier_id=context.supplier_ids[0],
            amount=Decimal("1.0000"),
            valid_to=datetime.now(UTC) - timedelta(days=1),
        )
        older_current_supplier_row = add_costed_offer(
            context,
            supplier_id=context.supplier_ids[1],
            amount=Decimal("2.0000"),
            valid_to=datetime.now(UTC) + timedelta(days=14),
            recorded_at=datetime.now(UTC) - timedelta(days=1),
        )
        current = add_costed_offer(
            context,
            supplier_id=context.supplier_ids[1],
            amount=Decimal("5.0000"),
            valid_to=datetime.now(UTC) + timedelta(days=14),
        )

        service = OfferService(settings)
        compare = service.compare_offers(
            member=context.member,
            product_id=context.product_id,
            quantity=Decimal("1.000000"),
        )
        assert {offer.id for offer in compare.offers} == {
            expired.landed_cost_id,
            current.landed_cost_id,
        }
        assert older_current_supplier_row.landed_cost_id not in {
            offer.id for offer in compare.offers
        }
        assert compare.recommendation is not None
        assert compare.recommendation.recommended_offer_id == current.landed_cost_id

        visible = service.list_offers(
            member=context.member,
            product_id=context.product_id,
            quantity=Decimal("1.000000"),
        )
        assert [offer.id for offer in visible.items] == [current.landed_cost_id]
        with_expired = service.list_offers(
            member=context.member,
            product_id=context.product_id,
            quantity=Decimal("1.000000"),
            include_expired=True,
        )
        assert {offer.id for offer in with_expired.items} == {
            expired.landed_cost_id,
            current.landed_cost_id,
        }


def test_unreviewed_quotation_never_produces_an_offer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = settings_for_test_db(monkeypatch)
    with committed_smart_context("offers-unreviewed") as context:
        add_costed_offer(
            context,
            supplier_id=context.supplier_ids[0],
            amount=Decimal("3.0000"),
            status="extracted",
        )
        compare = OfferService(settings).compare_offers(
            member=context.member,
            product_id=context.product_id,
            quantity=Decimal("1.000000"),
        )
        assert compare.offers == []
        assert compare.recommendation is None


def test_cross_tenant_product_reference_returns_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = settings_for_test_db(monkeypatch)
    with committed_smart_context("offers-alpha") as alpha:
        with committed_smart_context("offers-beta") as beta:
            with pytest.raises(NotFoundError):
                OfferService(settings).compare_offers(
                    member=alpha.member,
                    product_id=beta.product_id,
                    quantity=Decimal("1.000000"),
                )

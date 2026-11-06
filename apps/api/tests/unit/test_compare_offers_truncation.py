"""P-157: Smart Compare says so when the offer list was cut at its cap."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from procurepilot_api.modules.offers import service as svc
from procurepilot_api.modules.offers.service import COMPARE_OFFER_CAP, OfferService


def _row() -> dict[str, object]:
    return {
        "id": uuid4(),
        "workspace_product_id": uuid4(),
        "supplier_id": uuid4(),
        "supplier_name": "Supplier",
        "quotation_line_id": uuid4(),
        "match_decision_id": uuid4(),
        "raw_inputs": {
            "quantity": "1.000000",
            "normalised_base_quantity": "30.000000",
            "base_unit": "litre",
            "unit_price": {"amount": "4.0000", "currency": "GBP"},
            "vat_rate": "0.0000",
            "delivery_fee": {"amount": "0.0000", "currency": "GBP"},
            "discount": {"amount": "0.0000", "currency": "GBP"},
        },
        "rule_version": "landed-cost-v1",
        "valid_from": datetime.now(UTC) - timedelta(days=1),
        "valid_to": None,
        "recorded_at": datetime.now(UTC),
        "base_unit": "litre",
        "match_confidence": Decimal("0.9500"),
        "lead_time_days": 3,
        "reliability_score": Decimal("0.900"),
        "pack_base_quantity": Decimal("30.000000"),
    }


def _service(monkeypatch: pytest.MonkeyPatch, available: int) -> tuple[OfferService, list[int]]:
    asked: list[int] = []

    @contextmanager
    def fake_db(*_: object) -> Iterator[MagicMock]:
        conn = MagicMock()
        conn.cursor.return_value.__enter__.return_value.fetchall.return_value = []
        yield conn

    def fake_rows(*_: object, limit: int, **__: object) -> list[dict[str, object]]:
        asked.append(limit)
        return [_row() for _ in range(min(limit, available))]

    monkeypatch.setattr(svc, "_authenticated_db", fake_db)
    monkeypatch.setattr(svc, "_product", lambda *_: {"tenant_name": "Oil"})
    monkeypatch.setattr(svc, "_offer_rows", fake_rows)
    service = OfferService.__new__(OfferService)
    service._settings = MagicMock(offer_freshness_target_days=14)
    return service, asked


def _compare(service: OfferService):  # noqa: ANN202
    return service.compare_offers(member=MagicMock(), product_id=uuid4(), quantity=Decimal("30"))


def test_more_offers_than_the_cap_are_cut_and_flagged(monkeypatch: pytest.MonkeyPatch) -> None:
    service, asked = _service(monkeypatch, COMPARE_OFFER_CAP + 50)
    result = _compare(service)
    assert asked == [COMPARE_OFFER_CAP + 1]  # one extra row proves there is more
    assert len(result.offers) == COMPARE_OFFER_CAP
    assert result.offers_truncated is True


def test_exactly_the_cap_is_not_flagged(monkeypatch: pytest.MonkeyPatch) -> None:
    service, _ = _service(monkeypatch, COMPARE_OFFER_CAP)
    result = _compare(service)
    assert len(result.offers) == COMPARE_OFFER_CAP
    assert result.offers_truncated is False


def test_few_offers_are_not_flagged(monkeypatch: pytest.MonkeyPatch) -> None:
    service, _ = _service(monkeypatch, 3)
    result = _compare(service)
    assert len(result.offers) == 3
    assert result.offers_truncated is False

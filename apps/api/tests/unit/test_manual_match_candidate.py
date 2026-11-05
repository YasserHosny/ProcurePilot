"""P-151 A2: a buyer can pick any active catalogue product as a recorded manual candidate."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest

from procurepilot_api.errors import ConflictError
from procurepilot_api.modules.matching import resolution_service as rs
from procurepilot_api.modules.matching.schemas import ProductSummary

LINE = uuid4()
TENANT = uuid4()


def _product(status: str = "active", pid: UUID | None = None) -> ProductSummary:
    return ProductSummary(
        id=pid or uuid4(),
        tenant_name="Sunflower oil 5L",
        canonical_name="Sunflower oil",
        base_unit="L",
        status=status,  # type: ignore[arg-type]
    )


def _row(pid: UUID, *, rank: int, version: str) -> dict[str, object]:
    return {
        "id": str(uuid4()),
        "quotation_line_id": str(LINE),
        "candidate_workspace_product_id": str(pid),
        "confidence": "0.4200",
        "reasons": {"alias_hit": False, "gtin_match": False, "supplier_code_match": False},
        "rank": rank,
        "scoring_version": version,
        "embedding_model": None,
        "created_at": datetime.now(UTC).isoformat(),
    }


def _service(
    monkeypatch: pytest.MonkeyPatch, existing: list[dict[str, object]], product: ProductSummary
) -> tuple[rs.MatchResolutionService, list[dict[str, object]]]:
    client = MagicMock()
    table = client.table.return_value
    table.select.return_value.eq.return_value.execute.return_value.data = existing
    inserted: list[dict[str, object]] = []

    def insert(payload: dict[str, object]) -> MagicMock:
        inserted.append(payload)
        out = MagicMock()
        out.execute.return_value.data = [
            {
                **payload,
                "id": str(uuid4()),
                "created_at": datetime.now(UTC).isoformat(),
                "embedding_model": None,
            }
        ]
        return out

    table.insert.side_effect = insert
    monkeypatch.setattr(rs, "authenticated_client", lambda _s, _t: client)
    monkeypatch.setattr(rs, "_line_row", lambda _c, _lid: {"id": str(LINE)})
    monkeypatch.setattr(rs, "_product_summary", lambda _c, _pid: product)
    service = rs.MatchResolutionService.__new__(rs.MatchResolutionService)
    service._settings = MagicMock()
    return service, inserted


def _member() -> MagicMock:
    member = MagicMock()
    member.tenant_id = TENANT
    return member


def test_records_a_manual_candidate_with_its_own_scoring_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    product = _product()
    service, inserted = _service(monkeypatch, [], product)
    cand = service.add_manual_candidate(
        bearer_token="t", member=_member(), line_id=LINE, product_id=product.id
    )
    assert len(inserted) == 1
    row = inserted[0]
    assert row["scoring_version"] == "manual-v1"
    assert row["rank"] == 1
    assert row["confidence"] == "0.0000"
    assert row["tenant_id"] == str(TENANT)
    assert row["candidate_workspace_product_id"] == str(product.id)
    assert row["reasons"]["manual"] is True
    assert row["reasons"]["alias_hit"] is False
    assert cand.reasons.manual is True
    assert cand.candidate_product.id == product.id


def test_next_manual_rank_ignores_other_scoring_versions(monkeypatch: pytest.MonkeyPatch) -> None:
    product = _product()
    existing = [
        _row(uuid4(), rank=9, version="v2"),
        _row(uuid4(), rank=2, version="manual-v1"),
    ]
    service, inserted = _service(monkeypatch, existing, product)
    service.add_manual_candidate(
        bearer_token="t", member=_member(), line_id=LINE, product_id=product.id
    )
    assert inserted[0]["rank"] == 3


def test_an_existing_candidate_for_that_product_is_returned_not_duplicated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    product = _product()
    existing = [_row(product.id, rank=1, version="v2")]
    service, inserted = _service(monkeypatch, existing, product)
    cand = service.add_manual_candidate(
        bearer_token="t", member=_member(), line_id=LINE, product_id=product.id
    )
    assert inserted == []
    assert str(cand.id) == existing[0]["id"]


def test_an_archived_product_cannot_be_picked(monkeypatch: pytest.MonkeyPatch) -> None:
    product = _product(status="archived")
    service, inserted = _service(monkeypatch, [], product)
    with pytest.raises(ConflictError):
        service.add_manual_candidate(
            bearer_token="t", member=_member(), line_id=LINE, product_id=product.id
        )
    assert inserted == []

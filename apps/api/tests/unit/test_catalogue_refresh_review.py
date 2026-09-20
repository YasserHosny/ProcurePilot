from uuid import uuid4

import pytest

from procurepilot_api.deps import CurrentMember
from procurepilot_api.errors import UnprocessableEntityError
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.ingestion import catalogue_refresh_review_service as review_service
from procurepilot_api.modules.ingestion.catalogue_refresh_review_service import build_approval_csv


def test_build_approval_csv_reuses_catalogue_parser_shape() -> None:
    content = build_approval_csv(
        [
            {
                "product_name": "A4 paper",
                "unit_price_amount": "12.5000",
                "unit_price_currency": "gbp",
                "base_unit": "box",
            }
        ]
    )

    assert content == b"product_name,unit_price,currency,unit\r\nA4 paper,12.5000,GBP,box\r\n"


@pytest.mark.parametrize(
    "rows",
    [[], [{"product_name": "Paper", "unit_price_amount": "0", "unit_price_currency": "GBP"}]],
)
def test_build_approval_csv_rejects_empty_or_invalid_preview(rows: object) -> None:
    with pytest.raises(UnprocessableEntityError):
        build_approval_csv(rows)


def test_approving_refresh_reactivates_schedule_with_new_import(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    review_id = uuid4()
    schedule_id = uuid4()
    supplier_id = uuid4()
    import_id = uuid4()
    member = CurrentMember(
        membership_id=uuid4(),
        tenant_id=uuid4(),
        user_id=uuid4(),
        email="pilot@example.test",
        role=MemberRole.owner,
    )
    resumed: list[tuple[object, object, object, object]] = []

    monkeypatch.setattr(
        review_service,
        "_claim_review",
        lambda settings, *, member, review_id: {
            "supplier_id": supplier_id,
            "refresh_schedule_id": schedule_id,
            "normalized_rows": [
                {
                    "product_name": "Pilot product",
                    "unit_price_amount": "10.00",
                    "unit_price_currency": "GBP",
                    "base_unit": "each",
                }
            ],
        },
    )
    monkeypatch.setattr(
        review_service,
        "import_catalogue",
        lambda *args, **kwargs: {
            "id": import_id,
            "supplier_id": supplier_id,
            "status": "completed",
            "imported_rows": 1,
            "error_rows": 0,
        },
    )
    monkeypatch.setattr(
        review_service,
        "_reactivate_schedule_after_approval",
        lambda settings, *, member, schedule_id, source_import_id: resumed.append(
            (settings, member, schedule_id, source_import_id)
        ),
        raising=False,
    )
    monkeypatch.setattr(review_service, "_finish_review", lambda *args, **kwargs: None)
    monkeypatch.setattr(review_service, "_record_decision_audit", lambda *args, **kwargs: None)

    settings = object()
    decision = review_service.approve_review(
        settings, member=member, review_id=review_id, bearer_token="test-token"
    )

    assert decision["status"] == "approved"
    assert resumed == [(settings, member, schedule_id, import_id)]

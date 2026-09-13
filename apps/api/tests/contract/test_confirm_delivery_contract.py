from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from procurepilot_api.errors import ConflictError
from procurepilot_api.main import create_app
from procurepilot_api.modules.requests import router as requests_router
from procurepilot_api.modules.requests.schemas import (
    DeliveryConfirmationCreate,
    PurchaseRequest,
)


def _line(**overrides: object) -> dict:
    base = {
        "id": uuid4(),
        "workspace_product_id": uuid4(),
        "quantity": "10.000000",
        "quantity_received": "10.000000",
    }
    base.update(overrides)
    return base


def _request(**overrides: object) -> dict:
    base = {
        "id": uuid4(),
        "branch_id": uuid4(),
        "requested_by_membership_id": uuid4(),
        "required_by_date": "2026-09-20",
        "status": "delivered",
        "lines": [_line()],
        "has_incomplete_estimate": False,
        "delivered_at": "2026-09-13T12:00:00Z",
        "delivery_confirmed_by_membership_id": uuid4(),
        "has_delivery_discrepancy": False,
        "created_at": "2026-09-10T07:55:00Z",
        "updated_at": "2026-09-13T12:00:00Z",
    }
    base.update(overrides)
    return base


def test_delivery_confirmation_body_accepts_contract_shape() -> None:
    payload = DeliveryConfirmationCreate.model_validate(
        {
            "lines": [
                {
                    "purchase_request_line_id": str(uuid4()),
                    "quantity_received": "7.500000",
                }
            ]
        }
    )

    assert len(payload.lines) == 1
    assert payload.lines[0].quantity_received == "7.500000"


def test_delivery_confirmation_body_rejects_empty_lines() -> None:
    with pytest.raises(ValidationError, match="too_short"):
        DeliveryConfirmationCreate(lines=[])


def test_delivery_confirmation_body_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        DeliveryConfirmationCreate.model_validate(
            {
                "lines": [
                    {
                        "purchase_request_line_id": str(uuid4()),
                        "quantity_received": "7.500000",
                        "status": "delivered",
                    }
                ]
            }
        )


def test_delivered_request_response_exposes_delivery_fields() -> None:
    confirmed_by = uuid4()
    pr = PurchaseRequest.model_validate(
        _request(
            delivery_confirmed_by_membership_id=confirmed_by,
            has_delivery_discrepancy=True,
            lines=[_line(quantity_received="4.000000")],
        )
    )

    assert pr.delivered_at is not None
    assert pr.delivery_confirmed_by_membership_id == confirmed_by
    assert pr.has_delivery_discrepancy is True
    assert pr.lines[0].quantity_received == "4.000000"


def test_not_ordered_conflict_reason_is_contract_reason() -> None:
    error = ConflictError(details={"reason": "not_ordered"})

    assert error.status_code == 409
    assert error.details == {"reason": "not_ordered"}


def test_confirm_delivery_router_passes_payload_to_service() -> None:
    request_id = uuid4()
    payload = DeliveryConfirmationCreate(
        lines=[
            {
                "purchase_request_line_id": uuid4(),
                "quantity_received": "1.000000",
            }
        ]
    )
    captured: dict[str, object] = {}
    expected = object()
    fake_service = SimpleNamespace(
        confirm_delivery=lambda **kwargs: captured.update(kwargs) or expected
    )

    result = requests_router.confirm_delivery(
        request_id=request_id,
        payload=payload,
        token="token",
        member=object(),
        service=fake_service,
    )

    assert result is expected
    assert captured["bearer_token"] == "token"
    assert captured["request_id"] == request_id
    assert captured["payload"] is payload


def test_confirm_delivery_route_is_registered() -> None:
    app_paths = {route.path for route in create_app().routes}

    assert "/api/v1/requests/{request_id}/confirm-delivery" in app_paths


def test_contract_declares_confirm_delivery_path() -> None:
    repo_root = Path(__file__).resolve().parents[4]
    text = (
        repo_root
        / "specs/010-mobile-approvals-receipt/contracts/"
        / "mobile-approvals-receipt.openapi.yaml"
    ).read_text(encoding="utf-8")

    assert "  /requests/{request_id}/confirm-delivery:" in text
    assert "reason `not_ordered`" in text

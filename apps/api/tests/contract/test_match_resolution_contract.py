from uuid import uuid4

import pytest
from pydantic import ValidationError

from procurepilot_api.modules.catalogue.models import PackInput, ProductCreate
from procurepilot_api.modules.matching.schemas import MatchResolutionRequest


@pytest.mark.parametrize(
    "outcome",
    ["same_product", "different_pack", "different_variant", "compatible_alternative"],
)
def test_existing_product_resolution_outcomes_require_candidate(outcome: str) -> None:
    request = MatchResolutionRequest(
        outcome=outcome,
        selected_match_candidate_id=uuid4(),
    )
    assert request.outcome == outcome


def test_no_match_new_product_requires_inline_catalogue_product_shape() -> None:
    request = MatchResolutionRequest(
        outcome="no_match_new_product",
        create_product=ProductCreate(
            tenant_name="New item",
            base_unit="each",
            pack=PackInput(pack_count=1, unit_size="1"),
        ),
    )
    assert request.create_product is not None


def test_resolution_contract_rejects_missing_candidate_for_existing_product_outcome() -> None:
    with pytest.raises(ValidationError):
        MatchResolutionRequest(outcome="same_product")


def test_resolution_contract_rejects_missing_product_for_no_match_outcome() -> None:
    with pytest.raises(ValidationError):
        MatchResolutionRequest(outcome="no_match_new_product")

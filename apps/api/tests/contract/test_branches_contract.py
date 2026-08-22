from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError

from procurepilot_api.modules.organisation.schemas import (
    Branch,
    BranchCreate,
    BranchList,
    BranchUpdate,
)


def test_branch_contract_accepts_the_full_shape_and_nullable_fields() -> None:
    branch = Branch(
        id=uuid4(),
        name="Riyadh Warehouse",
        address="123 Industrial Rd",
        region="SA",
        is_active=True,
        created_at="2026-08-22T00:00:00Z",
    )
    assert BranchList(items=[branch], next_cursor=None).items[0].name == "Riyadh Warehouse"

    # address/region are nullable; updated_at is optional — a branch fresh off creation has
    # neither an address nor a second confirmed edit yet.
    minimal = Branch(
        id=uuid4(),
        name="HQ",
        address=None,
        region=None,
        is_active=True,
        created_at="2026-08-22T00:00:00Z",
    )
    assert minimal.address is None
    assert minimal.updated_at is None


def test_branch_create_requires_a_non_empty_name() -> None:
    with pytest.raises(ValidationError):
        BranchCreate(name="")


def test_branch_create_rejects_unknown_fields() -> None:
    """StrictApiModel (extra='forbid') is what keeps a client's typo from silently doing
    nothing — an unrecognised field must fail loudly, not be dropped."""
    with pytest.raises(ValidationError):
        BranchCreate.model_validate({"name": "Branch", "is_active": True})


def test_branch_update_confirm_dependents_is_optional_and_defaults_to_unset() -> None:
    """FR-009: deactivating a branch with dependents requires confirm_dependents=true. A plain
    edit (name change) must not be forced to carry it."""
    patch = BranchUpdate(name="Renamed Branch")
    assert patch.confirm_dependents is None
    assert "confirm_dependents" not in patch.model_fields_set

    deactivate = BranchUpdate(is_active=False, confirm_dependents=True)
    assert deactivate.confirm_dependents is True

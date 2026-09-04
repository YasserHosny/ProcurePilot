from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError

from procurepilot_api.modules.organisation.schemas import (
    CostCentre,
    CostCentreCreate,
    CostCentreList,
    CostCentreUpdate,
)


def test_cost_centre_contract_accepts_the_full_shape_including_orphan_reason() -> None:
    """orphan_reason is computed at read time (never stored) — see data-model.md's note on
    why the cause isn't a persisted column. Always null while is_orphaned is false."""
    branch_owned = CostCentre(
        id=uuid4(),
        name="Kitchen",
        code="KIT-01",
        budget_owner_membership_id=uuid4(),
        branch_id=uuid4(),
        is_orphaned=False,
        orphan_reason=None,
        is_archived=False,
        created_at="2026-08-22T00:00:00Z",
    )
    assert branch_owned.orphan_reason is None

    orphaned_by_branch = CostCentre(
        id=uuid4(),
        name="Facilities",
        code="FAC-01",
        budget_owner_membership_id=uuid4(),
        branch_id=uuid4(),
        is_orphaned=True,
        orphan_reason="branch_deactivated",
        is_archived=False,
        created_at="2026-08-22T00:00:00Z",
    )
    assert orphaned_by_branch.orphan_reason == "branch_deactivated"

    orphaned_by_owner = orphaned_by_branch.model_copy(
        update={"orphan_reason": "owner_removed"}
    )
    assert orphaned_by_owner.orphan_reason == "owner_removed"

    # organisation-wide cost centre (no branch link)
    org_wide = CostCentre(
        id=uuid4(),
        name="General",
        code="GEN-01",
        budget_owner_membership_id=None,
        branch_id=None,
        is_orphaned=False,
        orphan_reason=None,
        is_archived=False,
        created_at="2026-08-22T00:00:00Z",
    )
    assert org_wide.branch_id is None
    assert CostCentreList(items=[org_wide], next_cursor=None).items[0].code == "GEN-01"


def test_cost_centre_contract_rejects_an_unknown_orphan_reason() -> None:
    with pytest.raises(ValidationError):
        CostCentre(
            id=uuid4(),
            name="Kitchen",
            code="KIT-01",
            is_orphaned=True,
            orphan_reason="something_else",  # type: ignore[arg-type]
            is_archived=False,
            created_at="2026-08-22T00:00:00Z",
        )


def test_cost_centre_create_requires_name_and_code() -> None:
    with pytest.raises(ValidationError):
        CostCentreCreate(name="", code="KIT-01")
    with pytest.raises(ValidationError):
        CostCentreCreate(name="Kitchen", code="")


def test_cost_centre_create_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        CostCentreCreate.model_validate(
            {"name": "Kitchen", "code": "KIT-01", "is_orphaned": True}
        )


def test_cost_centre_update_is_fully_optional() -> None:
    """A partial edit (e.g. reassigning the budget owner) must not require every field."""
    patch = CostCentreUpdate(budget_owner_membership_id=uuid4())
    assert "name" not in patch.model_fields_set
    assert "code" not in patch.model_fields_set

    archive_only = CostCentreUpdate(is_archived=True)
    assert archive_only.is_archived is True
    assert "branch_id" not in archive_only.model_fields_set

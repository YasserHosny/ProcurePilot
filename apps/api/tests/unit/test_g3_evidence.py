from __future__ import annotations

import runpy
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).parents[2] / "scripts" / "g3_evidence.py"
_MODULE = runpy.run_path(_SCRIPT)
_active_accounts_query = _MODULE["_active_accounts_query"]
_parse_excluded_tenant_ids = _MODULE["_parse_excluded_tenant_ids"]
_tenant_filter = _MODULE["_tenant_filter"]


def test_excluded_tenant_ids_are_normalised_and_deduplicated() -> None:
    assert _parse_excluded_tenant_ids(
        "249294ec-88b2-4483-9a64-10896765a49c, 249294ec-88b2-4483-9a64-10896765a49c"
    ) == ("249294ec-88b2-4483-9a64-10896765a49c",)


def test_empty_exclusion_list_does_not_change_query_or_params() -> None:
    assert _tenant_filter("tenant_id", ()) == ("", ())


def test_active_accounts_query_ignores_orphaned_memberships() -> None:
    query, params = _active_accounts_query(())
    assert "join tenant t on t.id = m.tenant_id" in query
    assert params == ()


def test_invalid_excluded_tenant_id_is_rejected() -> None:
    with pytest.raises(ValueError, match="comma-separated UUID list"):
        _parse_excluded_tenant_ids("not-a-uuid")

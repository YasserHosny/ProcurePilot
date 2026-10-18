"""Bulk read reuse must never hide decisions/idempotency writes or cross client scopes."""

from unittest.mock import Mock

from procurepilot_api.modules.matching.resolution_service import _BulkReadClient


def test_bulk_reuses_only_input_rows_and_keeps_mutable_reads_live() -> None:
    client = Mock()
    query = client.table.return_value.select.return_value
    query.eq.return_value = query
    query.in_.return_value = query
    query.limit.return_value = query
    first, second = object(), object()
    query.execute.side_effect = [first, second]
    bulk = _BulkReadClient(client)
    assert bulk.table("workspace_product").select("id").eq("id", "p").limit(2).execute() is first
    assert bulk.table("workspace_product").select("tenant_name").in_("id", ["p"]).execute() is first
    assert query.execute.call_count == 1
    # A new authenticated scope cannot see the earlier group's cached row.
    fresh = _BulkReadClient(client)
    assert fresh.table("workspace_product").select("id").eq("id", "p").execute() is second
    assert query.execute.call_count == 2

    for table in ("match_decision", "match_resolution_idempotency", "product_alias", "match_task"):
        query.execute.reset_mock(side_effect=True)
        query.execute.side_effect = [None, {"id": "new-write"}]
        assert bulk.table(table).select("id").eq("id", "x").execute() is None
        assert bulk.table(table).select("id").eq("id", "x").execute() == {"id": "new-write"}
        assert query.execute.call_count == 2

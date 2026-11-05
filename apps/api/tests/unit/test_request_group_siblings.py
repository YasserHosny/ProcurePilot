"""Sibling source enrichment reuses the request snapshot in constant batch reads."""

from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest

from procurepilot_api.modules.requests.service import RequestsService


@pytest.mark.parametrize("supplier_visible", [True, False])
@pytest.mark.parametrize("count", [2, 8])
def test_request_group_sibling_sources_are_batched(count: int, supplier_visible: bool) -> None:
    tenant, group_id, supplier, rfq, response, quotation = (uuid4() for _ in range(6))
    ids = sorted(uuid4() for _ in range(count))
    group = {
        "id": group_id,
        "rfq_id": rfq,
        "combined_total_amount": "10",
        "combined_total_currency": "GBP",
        "best_single_total_amount": None,
        "best_single_total_currency": None,
        "saving_amount": None,
        "saving_currency": None,
    }
    rows = [
        {
            "id": id_,
            "tenant_id": tenant,
            "request_group_id": group_id,
            "created_at": "2026-11-01T00:00:00Z",
            "request_group": group,
            "source_supplier_id": supplier if index else None,
            "source_rfq_id": rfq,
            "source_rfq_response_id": response,
            "source_quotation_id": quotation,
        }
        for index, id_ in enumerate(ids)
    ]
    client = Mock()
    query = client.table.return_value
    query.select.return_value = query
    query.in_.return_value = query
    query.execute.side_effect = [
        SimpleNamespace(data=list(reversed(rows))),
        SimpleNamespace(data=[{"id": supplier, "name": "Supplier"}] if supplier_visible else []),
    ]
    summaries = RequestsService()._fetch_request_groups_batch(client, [rows[0]])
    for index, id_ in enumerate(ids):
        summary = summaries[str(id_)]
        assert summary.position == index + 1
        assert summary.sibling_request_ids == [other for other in ids if other != id_]
        assert [s.model_dump() for s in summary.siblings] == [
            {
                "id": other,
                "position": position,
                "supplier_name": "Supplier" if position > 1 and supplier_visible else None,
            }
            for position, other in enumerate(ids, 1)
            if other != id_
        ]

    assert query.execute.call_count == 2
    assert [call.args[0] for call in client.table.call_args_list] == [
        "purchase_request",
        "supplier",
    ]


def test_ungrouped_requests_do_not_fetch_sibling_sources() -> None:
    client = Mock()
    assert RequestsService()._fetch_request_groups_batch(client, [{"id": uuid4()}]) == {}
    client.table.assert_not_called()

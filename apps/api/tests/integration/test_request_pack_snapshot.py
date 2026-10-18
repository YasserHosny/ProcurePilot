"""ADR-020: catalogue edits must not rewrite a request's purchasing-pack history."""

from collections.abc import Iterator
from datetime import date, timedelta
from decimal import Decimal

import psycopg
import pytest

from integration.catalogue_helpers import (
    TEST_DATABASE_URL,
    act_as,
    connection,
    make_workspace,
    make_workspace_product,
)
from integration.test_purchase_requests import _current_member, _make_branch, _service
from procurepilot_api.modules.requests.schemas import (
    PurchaseRequestCreate,
    PurchaseRequestLineInput,
)

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL not set; needs a migrated DB including 20261018000006",
)


@pytest.fixture
def conn() -> Iterator[psycopg.Connection]:
    yield from connection()


def test_request_keeps_pack_snapshot_after_catalogue_edit(
    conn: psycopg.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    with conn.cursor() as cur:
        owner = make_workspace(cur, "request-pack-snapshot")
        act_as(cur, owner)
        branch_id = _make_branch(cur, owner)
        product_id = make_workspace_product(cur, owner, name="Milk")
        cur.execute(
            "update pack_definition set pack_count = 1, unit_size = 6 "
            "where workspace_product_id = %s",
            (product_id,),
        )

    service = _service(conn, monkeypatch)
    member = _current_member(owner, owner)
    request, created = service.create_request(
        bearer_token="token",
        member=member,
        payload=PurchaseRequestCreate(
            branch_id=branch_id,
            required_by_date=date.today() + timedelta(days=7),
            lines=[PurchaseRequestLineInput(workspace_product_id=product_id, quantity="2")],
        ),
    )
    assert created
    assert request.lines[0].pack_base_quantity == "6.000000"

    with conn.cursor() as cur:
        cur.execute(
            "update pack_definition set unit_size = 18 where workspace_product_id = %s "
            "returning base_quantity",
            (product_id,),
        )
        assert cur.fetchone() == (Decimal("18"),)

    fetched = service.get_request(bearer_token="token", member=member, request_id=request.id)
    assert fetched.lines[0].pack_base_quantity == "6.000000"
    assert fetched.lines[0].quantity == "2.000000"

from __future__ import annotations

import pytest

from integration.catalogue_helpers import TEST_DATABASE_URL, act_as, connection, make_workspace
from integration.quotation_helpers import make_document, make_quotation, make_supplier

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is required for trusted-data integration tests",
)


@pytest.fixture
def conn() -> object:
    yield from connection()


def test_only_reviewed_quotations_match_the_current_trusted_data_gate(conn: object) -> None:
    """Chunk 4.3 has no downstream trusted-price consumer yet; chunk 4.4 adds it.

    The backend invariant available now is that `quotation.status = 'reviewed'` is the only
    trusted state. This test makes that gate explicit so later consumers have a concrete filter
    to use and unreviewed rows cannot accidentally be treated as trusted.
    """
    with conn.cursor() as cur:
        workspace = make_workspace(cur, "trusted-data")
        supplier_id = make_supplier(cur, workspace)
        pending_id = make_quotation(
            cur,
            workspace,
            document_id=make_document(cur, workspace, filename="pending.pdf"),
            supplier_id=supplier_id,
            status="extracted",
        )
        reviewed_id = make_quotation(
            cur,
            workspace,
            document_id=make_document(cur, workspace, filename="reviewed.pdf"),
            supplier_id=supplier_id,
            status="reviewed",
        )

        act_as(cur, workspace)
        cur.execute("select id from quotation where status = 'reviewed'")
        trusted_ids = {row[0] for row in cur.fetchall()}

        assert reviewed_id in trusted_ids
        assert pending_id not in trusted_ids

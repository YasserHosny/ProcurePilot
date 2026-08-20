from __future__ import annotations

import pytest

from integration.catalogue_helpers import TEST_DATABASE_URL, act_as, connection, make_workspace
from integration.quotation_helpers import make_document, make_job, make_quotation

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is required for quotation isolation integration tests",
)


@pytest.fixture
def conn() -> object:
    yield from connection()


def test_cross_tenant_document_quotation_and_job_reads_return_not_found(conn: object) -> None:
    with conn.cursor() as cur:
        alpha = make_workspace(cur, "quotation-isolation-alpha")
        beta = make_workspace(cur, "quotation-isolation-beta")
        beta_document = make_document(cur, beta)
        beta_quotation = make_quotation(cur, beta, document_id=beta_document)
        beta_job = make_job(cur, beta, beta_quotation)

        act_as(cur, alpha)
        for table, record_id in (
            ("document", beta_document),
            ("quotation", beta_quotation),
            ("extraction_job", beta_job),
        ):
            cur.execute(f"select id from {table} where id = %s", (record_id,))
            assert cur.fetchone() is None, f"{table} leaked a cross-tenant row"

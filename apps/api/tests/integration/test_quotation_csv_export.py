from __future__ import annotations

import csv
from io import StringIO

import pytest

from integration.catalogue_helpers import TEST_DATABASE_URL, connection, make_workspace
from integration.quotation_helpers import (
    PsycopgSupabaseClient,
    make_extracted_quotation,
    make_supplier,
)
from procurepilot_api.deps import CurrentMember
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.quotations import service as service_module
from procurepilot_api.modules.quotations.service import QuotationService
from procurepilot_api.shared.audit import AuditEventCreate

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is required for quotation CSV integration tests",
)


@pytest.fixture
def conn() -> object:
    yield from connection()


def test_csv_export_includes_quotation_and_line_data(
    conn: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class AuditWriter:
        def record(self, event: AuditEventCreate, bearer_token: str | None = None) -> None:
            del event, bearer_token

    with conn.cursor() as cur:
        workspace = make_workspace(cur, "quotation-csv")
        fixture = make_extracted_quotation(cur, workspace)
        supplier_id = make_supplier(cur, workspace, name="=2+2")
        cur.execute(
            "update quotation set supplier_id = %s where id = %s returning status",
            (supplier_id, fixture.quotation_id),
        )
        status = cur.fetchone()[0]
        cur.execute(
            "update quotation_line set original_text = %s, unit_price_amount = -5, "
            "delivery_fee_amount = 3, delivery_fee_currency = 'USD', "
            "discount_amount = 1, discount_currency = 'GBP' where id = %s",
            ("@item", fixture.line_id),
        )
        monkeypatch.setattr(
            service_module,
            "authenticated_client",
            lambda _settings, _token: PsycopgSupabaseClient(conn),
        )
        monkeypatch.setattr(service_module, "get_audit_writer", lambda: AuditWriter())
        member = CurrentMember(
            membership_id=workspace.membership_id,
            tenant_id=workspace.tenant_id,
            user_id=workspace.user_id,
            email="buyer@example.test",
            role=MemberRole.owner,
        )
        result = QuotationService().export_quotation_csv(
            bearer_token="test-token",
            member=member,
            quotation_id=fixture.quotation_id,
        )

    rows = list(csv.reader(StringIO(result)))
    metadata_end = rows.index([])
    metadata = dict(rows[:metadata_end])
    line_header, line_values = rows[metadata_end + 1 :]
    line = dict(zip(line_header, line_values, strict=True))
    assert metadata["supplier_name"] == "'=2+2"
    assert metadata["status"] == status
    assert line["original_text"] == "'@item"
    assert line["line_number"] == "1"
    assert line["unit_price_amount"] == "-5.0000"
    assert line["delivery_fee_currency"] == "USD"
    assert line["discount_currency"] == "GBP"
    assert (
        line_header.index("delivery_fee_currency") == line_header.index("delivery_fee_amount") + 1
    )
    assert line_header.index("discount_currency") == line_header.index("discount_amount") + 1

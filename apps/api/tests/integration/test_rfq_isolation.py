"""Cross-tenant isolation tests for RFQ Sourcing tables.

These tests run against a real Postgres database with the migrations applied
and use the `authenticated` role with real JWT claims.

Cross-tenant guarantees under test:
- A member of tenant A cannot read another tenant's rfq, rfq_recipient, rfq_response,
  auto_preparation_guardrail, or auto_preparation_event.
- The authenticated role cannot UPDATE or DELETE auto_preparation_event (append-only).
- A cross-tenant INSERT attempt is rejected.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from uuid import UUID, uuid4

import psycopg
import pytest

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is not set; needs a Postgres with the migrations applied",
)


class RfqWorkspace:
    """One tenant, one member, one rfq, one recipient, one response, guardrail, event."""

    def __init__(
        self,
        tenant_id: UUID,
        user_id: UUID,
        membership_id: UUID,
        supplier_id: UUID,
        rfq_id: UUID,
        rfq_line_id: UUID,
        rfq_recipient_id: UUID,
        rfq_response_id: UUID,
        guardrail_id: UUID,
        event_id: UUID,
    ) -> None:
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.membership_id = membership_id
        self.supplier_id = supplier_id
        self.rfq_id = rfq_id
        self.rfq_line_id = rfq_line_id
        self.rfq_recipient_id = rfq_recipient_id
        self.rfq_response_id = rfq_response_id
        self.guardrail_id = guardrail_id
        self.event_id = event_id

    def claims(self, *, role: str = "owner") -> str:
        return json.dumps(
            {
                "sub": str(self.user_id),
                "tenant_id": str(self.tenant_id),
                "role": "authenticated",
                "member_role": role,
            }
        )


def _make_rfq_workspace(cur: psycopg.Cursor, label: str) -> RfqWorkspace:
    tenant_id, user_id, membership_id, invitation_id = uuid4(), uuid4(), uuid4(), uuid4()
    supplier_id = uuid4()

    # Reference data
    cur.execute(
        "insert into supported_region (code,label_en,label_ar) values ('GB','UK','ب') "
        "on conflict do nothing"
    )
    cur.execute(
        "insert into supported_currency (code,label_en,label_ar) values ('GBP','Pound','ج') "
        "on conflict do nothing"
    )
    cur.execute(
        "insert into supported_tax_model (code,label_en,label_ar,region_code) "
        "values ('uk_vat','UK VAT','ض','GB') on conflict do nothing"
    )
    cur.execute(
        "insert into supported_base_unit (code,label_en,label_ar,dimension,is_enabled) "
        "values ('each','Each','قطعة','count',true) on conflict do nothing"
    )

    # Auth user
    cur.execute(
        "insert into auth.users (id,email) values (%s,%s)",
        (user_id, f"rfq-{label}@example.test"),
    )

    # Tenant + invitation
    cur.execute(
        "insert into platform_invitation (id,email,token_hash,expires_at) "
        "values (%s,%s,%s, now() + interval '7 days')",
        (invitation_id, f"rfq-{label}@example.test", f"hash-rfq-{label}"),
    )
    cur.execute(
        "insert into tenant (id,name,slug,region,currency,tax_model,platform_invitation_id) "
        "values (%s,%s,%s,'GB','GBP','uk_vat',%s)",
        (tenant_id, f"Rfq {label} Ltd", f"rfq-{label}-{tenant_id.hex[:8]}", invitation_id),
    )
    cur.execute(
        "insert into membership (id,tenant_id,user_id,email,role,is_active_workspace) "
        "values (%s,%s,%s,%s,'owner',true)",
        (membership_id, tenant_id, user_id, f"rfq-{label}@example.test"),
    )

    # Supplier
    cur.execute(
        "insert into supplier (id,tenant_id,name,contact_email) values (%s,%s,%s,%s)",
        (supplier_id, tenant_id, f"Rfq {label} Supplier Co", f"contact@{label}.example.test"),
    )

    # Canonical + workspace product
    canonical_product_id, workspace_product_id = uuid4(), uuid4()
    cur.execute(
        "insert into canonical_product (id,name,base_unit) values (%s,%s,'each')",
        (canonical_product_id, f"{label} widget"),
    )
    cur.execute(
        "insert into workspace_product (id,tenant_id,canonical_product_id,tenant_name) "
        "values (%s,%s,%s,%s)",
        (workspace_product_id, tenant_id, canonical_product_id, f"{label} widget"),
    )

    # Document -> quotation
    document_id, quotation_id = uuid4(), uuid4()
    storage_path = f"tenants/{tenant_id}/quotations/{document_id}/{label}.pdf"
    cur.execute(
        "insert into document "
        "(id,tenant_id,storage_bucket,storage_path,mime_type,created_by) "
        "values (%s,%s,'quotation-documents',%s,'application/pdf',%s)",
        (document_id, tenant_id, storage_path, membership_id),
    )
    cur.execute(
        "insert into quotation (id,tenant_id,document_id) values (%s,%s,%s)",
        (quotation_id, tenant_id, document_id),
    )

    # rfq
    rfq_id = uuid4()
    cur.execute(
        "insert into rfq (id,tenant_id,created_by_membership_id,status,needed_by_date) "
        "values (%s,%s,%s,'sent',current_date + interval '7 days')",
        (rfq_id, tenant_id, membership_id),
    )

    rfq_line_id = uuid4()
    cur.execute(
        "insert into rfq_line (id,tenant_id,rfq_id,workspace_product_id,quantity) "
        "values (%s,%s,%s,%s,10)",
        (rfq_line_id, tenant_id, rfq_id, workspace_product_id),
    )

    rfq_recipient_id = uuid4()
    cur.execute(
        "insert into rfq_recipient (id,tenant_id,rfq_id,supplier_id,status,outbound_message_id) "
        "values (%s,%s,%s,%s,'sent',%s)",
        (rfq_recipient_id, tenant_id, rfq_id, supplier_id, f"msg-{label}@example.test"),
    )

    rfq_response_id = uuid4()
    cur.execute(
        "insert into rfq_response (id,tenant_id,rfq_recipient_id,quotation_id) "
        "values (%s,%s,%s,%s)",
        (rfq_response_id, tenant_id, rfq_recipient_id, quotation_id),
    )

    guardrail_id = uuid4()
    cur.execute(
        "insert into auto_preparation_guardrail "
        "(id,tenant_id,created_by_membership_id,max_order_value_amount,max_order_value_currency,"
        "min_response_count,max_price_variance_pct,enabled) "
        "values (%s,%s,%s,1000,'GBP',1,0.05,true)",
        (guardrail_id, tenant_id, membership_id),
    )

    event_id = uuid4()
    cur.execute(
        "insert into auto_preparation_event (id,tenant_id,guardrail_id,rfq_response_id) "
        "values (%s,%s,%s,%s)",
        (event_id, tenant_id, guardrail_id, rfq_response_id),
    )

    return RfqWorkspace(
        tenant_id=tenant_id,
        user_id=user_id,
        membership_id=membership_id,
        supplier_id=supplier_id,
        rfq_id=rfq_id,
        rfq_line_id=rfq_line_id,
        rfq_recipient_id=rfq_recipient_id,
        rfq_response_id=rfq_response_id,
        guardrail_id=guardrail_id,
        event_id=event_id,
    )


@pytest.fixture
def rfq_workspaces() -> Iterator[tuple[psycopg.Connection, RfqWorkspace, RfqWorkspace]]:
    with psycopg.connect(TEST_DATABASE_URL or "") as conn:
        with conn.cursor() as cur:
            alpha = _make_rfq_workspace(cur, "alpha-rfq")
            beta = _make_rfq_workspace(cur, "beta-rfq")
        yield conn, alpha, beta
        conn.rollback()


def _act_as(cur: psycopg.Cursor, workspace: RfqWorkspace, *, role: str = "owner") -> None:
    cur.execute("set local role authenticated")
    cur.execute(
        "select set_config('request.jwt.claims', %s, true)",
        (workspace.claims(role=role),),
    )


def test_another_tenants_rfqs_are_invisible(
    rfq_workspaces: tuple[psycopg.Connection, RfqWorkspace, RfqWorkspace],
) -> None:
    conn, alpha, beta = rfq_workspaces
    with conn.cursor() as cur:
        _act_as(cur, alpha)
        cur.execute("select id from rfq where tenant_id = %s", (beta.tenant_id,))
        assert cur.fetchall() == []
        cur.execute("select id from rfq where id = %s", (beta.rfq_id,))
        assert cur.fetchone() is None


def test_another_tenants_rfq_lines_are_invisible(
    rfq_workspaces: tuple[psycopg.Connection, RfqWorkspace, RfqWorkspace],
) -> None:
    conn, alpha, beta = rfq_workspaces
    with conn.cursor() as cur:
        _act_as(cur, alpha)
        cur.execute("select id from rfq_line where tenant_id = %s", (beta.tenant_id,))
        assert cur.fetchall() == []
        cur.execute("select id from rfq_line where id = %s", (beta.rfq_line_id,))
        assert cur.fetchone() is None


def test_another_tenants_rfq_recipients_are_invisible(
    rfq_workspaces: tuple[psycopg.Connection, RfqWorkspace, RfqWorkspace],
) -> None:
    conn, alpha, beta = rfq_workspaces
    with conn.cursor() as cur:
        _act_as(cur, alpha)
        cur.execute("select id from rfq_recipient where tenant_id = %s", (beta.tenant_id,))
        assert cur.fetchall() == []
        cur.execute("select id from rfq_recipient where id = %s", (beta.rfq_recipient_id,))
        assert cur.fetchone() is None


def test_another_tenants_rfq_responses_are_invisible(
    rfq_workspaces: tuple[psycopg.Connection, RfqWorkspace, RfqWorkspace],
) -> None:
    conn, alpha, beta = rfq_workspaces
    with conn.cursor() as cur:
        _act_as(cur, alpha)
        cur.execute("select id from rfq_response where tenant_id = %s", (beta.tenant_id,))
        assert cur.fetchall() == []
        cur.execute("select id from rfq_response where id = %s", (beta.rfq_response_id,))
        assert cur.fetchone() is None


def test_another_tenants_guardrails_are_invisible(
    rfq_workspaces: tuple[psycopg.Connection, RfqWorkspace, RfqWorkspace],
) -> None:
    conn, alpha, beta = rfq_workspaces
    with conn.cursor() as cur:
        _act_as(cur, alpha)
        cur.execute(
            "select id from auto_preparation_guardrail where tenant_id = %s",
            (beta.tenant_id,)
        )
        assert cur.fetchall() == []
        cur.execute(
            "select id from auto_preparation_guardrail where id = %s",
            (beta.guardrail_id,)
        )
        assert cur.fetchone() is None


def test_another_tenants_events_are_invisible(
    rfq_workspaces: tuple[psycopg.Connection, RfqWorkspace, RfqWorkspace],
) -> None:
    conn, alpha, beta = rfq_workspaces
    with conn.cursor() as cur:
        _act_as(cur, alpha)
        cur.execute("select id from auto_preparation_event where tenant_id = %s", (beta.tenant_id,))
        assert cur.fetchall() == []
        cur.execute("select id from auto_preparation_event where id = %s", (beta.event_id,))
        assert cur.fetchone() is None


def test_member_cannot_insert_rfq_into_another_tenant(
    rfq_workspaces: tuple[psycopg.Connection, RfqWorkspace, RfqWorkspace],
) -> None:
    conn, alpha, beta = rfq_workspaces
    with conn.cursor() as cur:
        _act_as(cur, alpha)
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cur.execute(
                "insert into rfq (tenant_id,created_by_membership_id,status,needed_by_date) "
                "values (%s,%s,'draft',current_date)",
                (beta.tenant_id, alpha.membership_id),
            )


def test_authenticated_cannot_update_auto_preparation_event(
    rfq_workspaces: tuple[psycopg.Connection, RfqWorkspace, RfqWorkspace],
) -> None:
    """auto_preparation_event is APPEND-ONLY."""
    conn, alpha, _beta = rfq_workspaces
    with conn.cursor() as cur:
        _act_as(cur, alpha)
        cur.execute("savepoint no_update")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cur.execute(
                "update auto_preparation_event set purchase_request_id = %s where id = %s",
                (uuid4(), alpha.event_id),
            )
        cur.execute("rollback to savepoint no_update")


def test_authenticated_cannot_delete_auto_preparation_event(
    rfq_workspaces: tuple[psycopg.Connection, RfqWorkspace, RfqWorkspace],
) -> None:
    """auto_preparation_event is APPEND-ONLY."""
    conn, alpha, _beta = rfq_workspaces
    with conn.cursor() as cur:
        _act_as(cur, alpha)
        cur.execute("savepoint no_delete")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cur.execute(
                "delete from auto_preparation_event where id = %s",
                (alpha.event_id,),
            )
        cur.execute("rollback to savepoint no_delete")


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
from httpx import ASGITransport, AsyncClient

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
    email = f"rfq-{label}-{user_id.hex[:10]}@example.test"

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
        (user_id, email),
    )

    # Tenant + invitation
    cur.execute(
        "insert into platform_invitation (id,email,token_hash,expires_at) "
        "values (%s,%s,%s, now() + interval '7 days')",
        (invitation_id, email, f"hash-rfq-{invitation_id}"),
    )
    cur.execute(
        "insert into tenant (id,name,slug,region,currency,tax_model,platform_invitation_id) "
        "values (%s,%s,%s,'GB','GBP','uk_vat',%s)",
        (tenant_id, f"Rfq {label} Ltd", f"rfq-{label}-{tenant_id.hex[:8]}", invitation_id),
    )
    cur.execute(
        "insert into membership (id,tenant_id,user_id,email,role,is_active_workspace) "
        "values (%s,%s,%s,%s,'owner',true)",
        (membership_id, tenant_id, user_id, email),
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
        "insert into rfq (id,tenant_id,created_by_membership_id,status,needed_by_date,"
        "idempotency_key) "
        "values (%s,%s,%s,'sent',current_date + interval '7 days',%s)",
        (rfq_id, tenant_id, membership_id, uuid4()),
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

    branch_id = uuid4()
    cur.execute(
        "insert into branch (id,tenant_id,name) values (%s,%s,%s)",
        (branch_id, tenant_id, f"Branch {label}"),
    )

    guardrail_id = uuid4()
    cur.execute(
        "insert into auto_preparation_guardrail "
        "(id,tenant_id,created_by_membership_id,max_order_value_amount,max_order_value_currency,"
        "min_response_count,max_price_variance_pct,enabled,default_branch_id) "
        "values (%s,%s,%s,1000,'GBP',1,0.05,true,%s)",
        (guardrail_id, tenant_id, membership_id, branch_id),
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


def _ensure_spare_owner(cur: psycopg.Cursor, workspace: RfqWorkspace) -> None:
    """A second active owner, so the workspace member can be demoted (owner-guard trigger)."""
    cur.execute(
        "select 1 from membership where tenant_id = %s and id <> %s and role = 'owner'",
        (workspace.tenant_id, workspace.membership_id),
    )
    if cur.fetchone() is not None:
        return
    spare_user = uuid4()
    spare_email = f"rfq-spare-owner-{spare_user.hex[:10]}@example.test"
    cur.execute("insert into auth.users (id,email) values (%s,%s)", (spare_user, spare_email))
    cur.execute(
        "insert into membership (tenant_id,user_id,email,role,is_active_workspace) "
        "values (%s,%s,%s,'owner',true)",
        (workspace.tenant_id, spare_user, spare_email),
    )


def _set_membership_role(cur: psycopg.Cursor, workspace: RfqWorkspace, role: str) -> None:
    cur.execute("reset role")
    if role != "owner":
        _ensure_spare_owner(cur, workspace)
    cur.execute(
        "update membership set role = %s::member_role where id = %s",
        (role, workspace.membership_id),
    )


def _act_as(
    cur: psycopg.Cursor,
    workspace: RfqWorkspace,
    *,
    role: str = "owner",
    claim_role: str | None = None,
) -> None:
    """Act as the workspace member with `role` on their membership row.

    RFQ write policies read the live membership role (current_membership_role, 20261018000009),
    so the row carries the role under test. `claim_role` sets a different JWT member_role
    claim, as a token issued before a role change would carry.
    """
    _set_membership_role(cur, workspace, role)
    cur.execute("set local role authenticated")
    cur.execute(
        "select set_config('request.jwt.claims', %s, true)",
        (workspace.claims(role=claim_role or role),),
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
            "select id from auto_preparation_guardrail where tenant_id = %s", (beta.tenant_id,)
        )
        assert cur.fetchall() == []
        cur.execute("select id from auto_preparation_guardrail where id = %s", (beta.guardrail_id,))
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
                "insert into rfq (tenant_id,created_by_membership_id,status,needed_by_date,"
                "idempotency_key) "
                "values (%s,%s,'draft',current_date,%s)",
                (beta.tenant_id, alpha.membership_id, uuid4()),
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


@pytest.mark.asyncio
async def test_other_tenant_rfq_detail_and_draft_update_are_not_found(
    rfq_workspaces: tuple[psycopg.Connection, RfqWorkspace, RfqWorkspace],
) -> None:
    conn, alpha, beta = rfq_workspaces
    with conn.cursor() as cur:
        cur.execute("reset role")
        cur.execute("update rfq set status = 'draft' where id = %s", (beta.rfq_id,))
    conn.commit()

    from procurepilot_api.deps import CurrentMember, current_member
    from procurepilot_api.main import app
    from procurepilot_api.modules.auth.jwt import MemberRole

    app.dependency_overrides[current_member] = lambda: CurrentMember(
        user_id=alpha.user_id,
        email=f"rfq-{alpha.user_id}@example.test",
        membership_id=alpha.membership_id,
        tenant_id=alpha.tenant_id,
        role=MemberRole.owner,
    )
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            detail = await client.get(f"/api/v1/rfq/{beta.rfq_id}")
            assert detail.status_code == 404
            update = await client.put(
                f"/api/v1/rfq/{beta.rfq_id}",
                json={
                    "lines": [],
                    "recipient_supplier_ids": [],
                    "needed_by_date": "2030-01-01",
                    "tenant_terms": "must not leak",
                },
                headers={"Idempotency-Key": str(uuid4())},
            )
            assert update.status_code == 404
    finally:
        app.dependency_overrides.clear()

    with conn.cursor() as cur:
        cur.execute("reset role")
        cur.execute("select needed_by_date, tenant_terms from rfq where id = %s", (beta.rfq_id,))
        row = cur.fetchone()
        assert row[0].isoformat() != "2030-01-01"
        assert row[1] is None


@pytest.mark.parametrize("role", ["viewer", "approver", "branch_manager"])
def test_only_owner_or_buyer_can_insert_an_rfq(
    rfq_workspaces: tuple[psycopg.Connection, RfqWorkspace, RfqWorkspace], role: str
) -> None:
    """Spec 021 FR-001 in the database, not just the router (security review 2026-10-18)."""
    conn, alpha, _beta = rfq_workspaces
    with conn.cursor() as cur:
        _act_as(cur, alpha, role=role)
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cur.execute(
                "insert into rfq (tenant_id,created_by_membership_id,status,needed_by_date,"
                "idempotency_key) "
                "values (%s,%s,'draft',current_date,%s)",
                (alpha.tenant_id, alpha.membership_id, uuid4()),
            )


@pytest.mark.parametrize(("role", "updated"), [("viewer", 0), ("buyer", 1), ("owner", 1)])
def test_only_owner_or_buyer_can_update_their_rfq(
    rfq_workspaces: tuple[psycopg.Connection, RfqWorkspace, RfqWorkspace],
    role: str,
    updated: int,
) -> None:
    """Sending is an update of the rfq row; a creator who is not an owner or buyer cannot."""
    conn, alpha, _beta = rfq_workspaces
    with conn.cursor() as cur:
        _act_as(cur, alpha, role=role)
        cur.execute("update rfq set needed_by_date = needed_by_date where id = %s", (alpha.rfq_id,))
        assert cur.rowcount == updated


# --- rfq_line / rfq_recipient writes (20261018000007) ------------------------------------------
#
# The creator predicate alone is not enough: a member who created an RFQ and later holds another
# role (or created it before 20261018000003) must not change its lines or recipients either. The
# alpha workspace's own membership created alpha's RFQ; _act_as sets that membership's role.

_NON_WRITER_ROLES = ["viewer", "approver", "branch_manager"]
_WRITER_ROLES = ["owner", "buyer"]


def _insert_rfq_line(cur: psycopg.Cursor, workspace: RfqWorkspace) -> None:
    cur.execute(
        "insert into rfq_line (tenant_id,rfq_id,workspace_product_id,quantity) "
        "select tenant_id, rfq_id, workspace_product_id, 3 from rfq_line where id = %s",
        (workspace.rfq_line_id,),
    )


def _insert_extra_supplier(cur: psycopg.Cursor, workspace: RfqWorkspace) -> UUID:
    supplier_id = uuid4()
    cur.execute("reset role")
    cur.execute(
        "insert into supplier (id,tenant_id,name) values (%s,%s,%s)",
        (supplier_id, workspace.tenant_id, f"Extra supplier {supplier_id.hex[:6]}"),
    )
    return supplier_id


@pytest.mark.parametrize("role", _NON_WRITER_ROLES)
def test_a_creator_without_owner_or_buyer_role_cannot_insert_rfq_lines(
    rfq_workspaces: tuple[psycopg.Connection, RfqWorkspace, RfqWorkspace], role: str
) -> None:
    conn, alpha, _beta = rfq_workspaces
    with conn.cursor() as cur:
        _act_as(cur, alpha, role=role)
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            _insert_rfq_line(cur, alpha)


@pytest.mark.parametrize("role", _NON_WRITER_ROLES)
def test_a_creator_without_owner_or_buyer_role_cannot_update_or_delete_rfq_lines(
    rfq_workspaces: tuple[psycopg.Connection, RfqWorkspace, RfqWorkspace], role: str
) -> None:
    conn, alpha, _beta = rfq_workspaces
    with conn.cursor() as cur:
        _act_as(cur, alpha, role=role)
        cur.execute("update rfq_line set quantity = 999 where id = %s", (alpha.rfq_line_id,))
        assert cur.rowcount == 0
        cur.execute("delete from rfq_line where id = %s", (alpha.rfq_line_id,))
        assert cur.rowcount == 0
        cur.execute("reset role")
        cur.execute("select quantity from rfq_line where id = %s", (alpha.rfq_line_id,))
        assert cur.fetchone()[0] == 10


@pytest.mark.parametrize("role", _NON_WRITER_ROLES)
def test_a_creator_without_owner_or_buyer_role_cannot_insert_rfq_recipients(
    rfq_workspaces: tuple[psycopg.Connection, RfqWorkspace, RfqWorkspace], role: str
) -> None:
    conn, alpha, _beta = rfq_workspaces
    with conn.cursor() as cur:
        supplier_id = _insert_extra_supplier(cur, alpha)
        _act_as(cur, alpha, role=role)
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cur.execute(
                "insert into rfq_recipient (tenant_id,rfq_id,supplier_id,status) "
                "values (%s,%s,%s,'draft')",
                (alpha.tenant_id, alpha.rfq_id, supplier_id),
            )


@pytest.mark.parametrize("role", _NON_WRITER_ROLES)
def test_a_creator_without_owner_or_buyer_role_cannot_update_or_delete_rfq_recipients(
    rfq_workspaces: tuple[psycopg.Connection, RfqWorkspace, RfqWorkspace], role: str
) -> None:
    conn, alpha, _beta = rfq_workspaces
    with conn.cursor() as cur:
        _act_as(cur, alpha, role=role)
        cur.execute(
            "update rfq_recipient set outbound_message_id = 'tampered' where id = %s",
            (alpha.rfq_recipient_id,),
        )
        assert cur.rowcount == 0
        cur.execute("delete from rfq_recipient where id = %s", (alpha.rfq_recipient_id,))
        assert cur.rowcount == 0
        cur.execute("reset role")
        cur.execute(
            "select outbound_message_id from rfq_recipient where id = %s",
            (alpha.rfq_recipient_id,),
        )
        assert cur.fetchone()[0] != "tampered"


@pytest.mark.parametrize("role", _WRITER_ROLES)
def test_an_owner_or_buyer_creator_can_still_write_rfq_lines_and_recipients(
    rfq_workspaces: tuple[psycopg.Connection, RfqWorkspace, RfqWorkspace], role: str
) -> None:
    """The draft edit and send paths (RfqService.update_draft / send) keep working."""
    conn, alpha, _beta = rfq_workspaces
    with conn.cursor() as cur:
        supplier_id = _insert_extra_supplier(cur, alpha)
        _act_as(cur, alpha, role=role)
        _insert_rfq_line(cur, alpha)
        assert cur.rowcount == 1
        cur.execute("update rfq_line set quantity = 11 where id = %s", (alpha.rfq_line_id,))
        assert cur.rowcount == 1
        cur.execute(
            "insert into rfq_recipient (tenant_id,rfq_id,supplier_id,status) "
            "values (%s,%s,%s,'draft')",
            (alpha.tenant_id, alpha.rfq_id, supplier_id),
        )
        assert cur.rowcount == 1
        cur.execute(
            "update rfq_recipient set status = 'sent', sent_at = now() "
            "where rfq_id = %s and supplier_id = %s",
            (alpha.rfq_id, supplier_id),
        )
        assert cur.rowcount == 1
        cur.execute(
            "delete from rfq_recipient where rfq_id = %s and supplier_id = %s",
            (alpha.rfq_id, supplier_id),
        )
        assert cur.rowcount == 1
        cur.execute("delete from rfq_line where id = %s", (alpha.rfq_line_id,))
        assert cur.rowcount == 1


def test_a_buyer_who_did_not_create_the_rfq_cannot_update_its_recipients(
    rfq_workspaces: tuple[psycopg.Connection, RfqWorkspace, RfqWorkspace],
) -> None:
    """rfq_recipient_update used to admit any owner/buyer; it now matches rfq_update."""
    conn, alpha, _beta = rfq_workspaces
    other_user, other_membership = uuid4(), uuid4()
    other_email = f"rfq-other-buyer-{other_user.hex[:10]}@example.test"
    with conn.cursor() as cur:
        cur.execute("reset role")
        cur.execute("insert into auth.users (id,email) values (%s,%s)", (other_user, other_email))
        cur.execute(
            "insert into membership (id,tenant_id,user_id,email,role,is_active_workspace) "
            "values (%s,%s,%s,%s,'buyer',true)",
            (other_membership, alpha.tenant_id, other_user, other_email),
        )
        cur.execute("set local role authenticated")
        cur.execute(
            "select set_config('request.jwt.claims', %s, true)",
            (
                json.dumps(
                    {
                        "sub": str(other_user),
                        "tenant_id": str(alpha.tenant_id),
                        "role": "authenticated",
                        "member_role": "buyer",
                    }
                ),
            ),
        )
        cur.execute("select id from rfq_recipient where id = %s", (alpha.rfq_recipient_id,))
        assert cur.fetchone() is not None, "owners and buyers still read every RFQ's recipients"
        cur.execute(
            "update rfq_recipient set outbound_message_id = 'tampered' where id = %s",
            (alpha.rfq_recipient_id,),
        )
        assert cur.rowcount == 0


# --- live role, not the JWT claim (20261018000009) -----------------------------------------------
#
# A token keeps the member_role it was issued with. A member demoted from owner/buyer must lose RFQ
# write access on the next request, not when the token expires.


@pytest.mark.parametrize("stale_claim", _WRITER_ROLES)
def test_a_demoted_member_with_a_stale_writer_claim_cannot_write_rfqs(
    rfq_workspaces: tuple[psycopg.Connection, RfqWorkspace, RfqWorkspace], stale_claim: str
) -> None:
    conn, alpha, _beta = rfq_workspaces
    with conn.cursor() as cur:
        supplier_id = _insert_extra_supplier(cur, alpha)
        _act_as(cur, alpha, role="viewer", claim_role=stale_claim)

        cur.execute("update rfq set needed_by_date = needed_by_date where id = %s", (alpha.rfq_id,))
        assert cur.rowcount == 0
        cur.execute("update rfq_line set quantity = 999 where id = %s", (alpha.rfq_line_id,))
        assert cur.rowcount == 0
        cur.execute(
            "update rfq_recipient set outbound_message_id = 'tampered' where id = %s",
            (alpha.rfq_recipient_id,),
        )
        assert cur.rowcount == 0
        cur.execute("delete from rfq where id = %s", (alpha.rfq_id,))
        assert cur.rowcount == 0

        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cur.execute("savepoint stale_line")
            _insert_rfq_line(cur, alpha)
        cur.execute("rollback to savepoint stale_line")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cur.execute("savepoint stale_recipient")
            cur.execute(
                "insert into rfq_recipient (tenant_id,rfq_id,supplier_id,status) "
                "values (%s,%s,%s,'draft')",
                (alpha.tenant_id, alpha.rfq_id, supplier_id),
            )
        cur.execute("rollback to savepoint stale_recipient")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cur.execute(
                "insert into rfq (tenant_id,created_by_membership_id,status,needed_by_date,"
                "idempotency_key) values (%s,%s,'draft',current_date,%s)",
                (alpha.tenant_id, alpha.membership_id, uuid4()),
            )


def test_a_promoted_member_with_a_stale_viewer_claim_can_write_rfqs(
    rfq_workspaces: tuple[psycopg.Connection, RfqWorkspace, RfqWorkspace],
) -> None:
    """The live role decides in both directions."""
    conn, alpha, _beta = rfq_workspaces
    with conn.cursor() as cur:
        _act_as(cur, alpha, role="buyer", claim_role="viewer")
        cur.execute("update rfq set needed_by_date = needed_by_date where id = %s", (alpha.rfq_id,))
        assert cur.rowcount == 1


@pytest.mark.parametrize(("role", "deleted"), [*((r, 0) for r in _NON_WRITER_ROLES), ("buyer", 1)])
def test_only_an_owner_or_buyer_creator_can_delete_an_rfq(
    rfq_workspaces: tuple[psycopg.Connection, RfqWorkspace, RfqWorkspace],
    role: str,
    deleted: int,
) -> None:
    """Deleting an RFQ cascades to its lines and recipients, so it needs the writer role too."""
    conn, alpha, _beta = rfq_workspaces
    with conn.cursor() as cur:
        cur.execute("reset role")
        cur.execute("delete from auto_preparation_event where tenant_id = %s", (alpha.tenant_id,))
        cur.execute("delete from rfq_response where tenant_id = %s", (alpha.tenant_id,))
        _act_as(cur, alpha, role=role)
        cur.execute("delete from rfq where id = %s", (alpha.rfq_id,))
        assert cur.rowcount == deleted


def test_members_cannot_write_rfq_responses(
    rfq_workspaces: tuple[psycopg.Connection, RfqWorkspace, RfqWorkspace],
) -> None:
    """Only the ingestion worker (service_role) records responses (20261018000009)."""
    conn, alpha, _beta = rfq_workspaces
    with conn.cursor() as cur:
        _act_as(cur, alpha, role="owner")
        cur.execute("savepoint response_insert")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cur.execute(
                "insert into rfq_response (tenant_id,rfq_recipient_id,quotation_id) "
                "select tenant_id, rfq_recipient_id, quotation_id from rfq_response where id = %s",
                (alpha.rfq_response_id,),
            )
        cur.execute("rollback to savepoint response_insert")
        cur.execute("savepoint response_update")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cur.execute(
                "update rfq_response set created_at = created_at where id = %s",
                (alpha.rfq_response_id,),
            )
        cur.execute("rollback to savepoint response_update")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cur.execute("delete from rfq_response where id = %s", (alpha.rfq_response_id,))


@pytest.mark.parametrize(
    ("live_role", "stale_claim", "updated"), [("buyer", "owner", 0), ("owner", "buyer", 1)]
)
def test_guardrail_updates_follow_the_live_owner_role(
    rfq_workspaces: tuple[psycopg.Connection, RfqWorkspace, RfqWorkspace],
    live_role: str,
    stale_claim: str,
    updated: int,
) -> None:
    conn, alpha, _beta = rfq_workspaces
    with conn.cursor() as cur:
        _act_as(cur, alpha, role=live_role, claim_role=stale_claim)
        cur.execute(
            "update auto_preparation_guardrail set enabled = enabled where id = %s",
            (alpha.guardrail_id,),
        )
        assert cur.rowcount == updated


# --- mark_rfq_converted (20261019000001) ---------------------------------------------------------
#
# rfq_update only matches the RFQ's creator, so preparing a request from someone else's RFQ used to
# leave it 'sent'. mark_rfq_converted lets any active owner or buyer close the RFQ a request was
# prepared from, and nothing else.


def _add_member(cur: psycopg.Cursor, workspace: RfqWorkspace, role: str) -> tuple[UUID, UUID]:
    user_id, membership_id = uuid4(), uuid4()
    email = f"rfq-{role}-{user_id.hex[:10]}@example.test"
    cur.execute("reset role")
    cur.execute("insert into auth.users (id,email) values (%s,%s)", (user_id, email))
    cur.execute(
        "insert into membership (id,tenant_id,user_id,email,role,is_active_workspace) "
        "values (%s,%s,%s,%s,%s,true)",
        (membership_id, workspace.tenant_id, user_id, email, role),
    )
    return user_id, membership_id


def _prepared_request(
    cur: psycopg.Cursor, workspace: RfqWorkspace, membership_id: UUID, response_id: UUID | None
) -> UUID:
    request_id = uuid4()
    cur.execute("reset role")
    cur.execute(
        "insert into purchase_request (id,tenant_id,branch_id,requested_by_membership_id,"
        "required_by_date,status,source_rfq_response_id) "
        "select %s, %s, id, %s, current_date + 7, 'draft', %s from branch where tenant_id = %s "
        "limit 1",
        (request_id, workspace.tenant_id, membership_id, response_id, workspace.tenant_id),
    )
    return request_id


def _act_as_user(
    cur: psycopg.Cursor, workspace: RfqWorkspace, user_id: UUID, claim_role: str
) -> None:
    cur.execute("set local role authenticated")
    cur.execute(
        "select set_config('request.jwt.claims', %s, true)",
        (
            json.dumps(
                {
                    "sub": str(user_id),
                    "tenant_id": str(workspace.tenant_id),
                    "role": "authenticated",
                    "member_role": claim_role,
                }
            ),
        ),
    )


def _rfq_status(cur: psycopg.Cursor, rfq_id: UUID) -> str:
    cur.execute("reset role")
    cur.execute("select status from rfq where id = %s", (rfq_id,))
    return str(cur.fetchone()[0])


@pytest.mark.parametrize("role", ["buyer", "owner"])
def test_an_owner_or_buyer_who_did_not_create_the_rfq_can_mark_it_converted(
    rfq_workspaces: tuple[psycopg.Connection, RfqWorkspace, RfqWorkspace], role: str
) -> None:
    conn, alpha, _beta = rfq_workspaces
    with conn.cursor() as cur:
        user_id, membership_id = _add_member(cur, alpha, role)
        request_id = _prepared_request(cur, alpha, membership_id, alpha.rfq_response_id)
        _act_as_user(cur, alpha, user_id, role)
        # The plain update is still creator-only.
        cur.execute("update rfq set status = 'converted' where id = %s", (alpha.rfq_id,))
        assert cur.rowcount == 0
        cur.execute("select mark_rfq_converted(%s, %s)", (alpha.rfq_id, request_id))
        assert cur.fetchone()[0] is True
        assert _rfq_status(cur, alpha.rfq_id) == "converted"


@pytest.mark.parametrize("claim_role", ["viewer", "buyer"])
def test_a_viewer_cannot_mark_an_rfq_converted_even_with_a_buyer_claim(
    rfq_workspaces: tuple[psycopg.Connection, RfqWorkspace, RfqWorkspace], claim_role: str
) -> None:
    conn, alpha, _beta = rfq_workspaces
    with conn.cursor() as cur:
        user_id, membership_id = _add_member(cur, alpha, "viewer")
        request_id = _prepared_request(cur, alpha, membership_id, alpha.rfq_response_id)
        _act_as_user(cur, alpha, user_id, claim_role)
        cur.execute("savepoint before_mark")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cur.execute("select mark_rfq_converted(%s, %s)", (alpha.rfq_id, request_id))
        cur.execute("rollback to savepoint before_mark")
        assert _rfq_status(cur, alpha.rfq_id) == "sent"


def test_a_request_not_prepared_from_the_rfq_cannot_convert_it(
    rfq_workspaces: tuple[psycopg.Connection, RfqWorkspace, RfqWorkspace],
) -> None:
    conn, alpha, _beta = rfq_workspaces
    with conn.cursor() as cur:
        user_id, membership_id = _add_member(cur, alpha, "buyer")
        unrelated_request = _prepared_request(cur, alpha, membership_id, None)
        _act_as_user(cur, alpha, user_id, "buyer")
        cur.execute("select mark_rfq_converted(%s, %s)", (alpha.rfq_id, unrelated_request))
        assert cur.fetchone()[0] is False
        assert _rfq_status(cur, alpha.rfq_id) == "sent"


def test_another_workspaces_rfq_cannot_be_converted(
    rfq_workspaces: tuple[psycopg.Connection, RfqWorkspace, RfqWorkspace],
) -> None:
    conn, alpha, beta = rfq_workspaces
    with conn.cursor() as cur:
        user_id, membership_id = _add_member(cur, alpha, "buyer")
        request_id = _prepared_request(cur, alpha, membership_id, alpha.rfq_response_id)
        beta_request = _prepared_request(cur, beta, beta.membership_id, beta.rfq_response_id)
        _act_as_user(cur, alpha, user_id, "buyer")
        for rfq_id, req_id in ((beta.rfq_id, request_id), (beta.rfq_id, beta_request)):
            cur.execute("select mark_rfq_converted(%s, %s)", (rfq_id, req_id))
            assert cur.fetchone()[0] is False
            cur.execute("set local role authenticated")
        assert _rfq_status(cur, beta.rfq_id) == "sent"


def test_a_draft_rfq_is_never_converted(
    rfq_workspaces: tuple[psycopg.Connection, RfqWorkspace, RfqWorkspace],
) -> None:
    conn, alpha, _beta = rfq_workspaces
    with conn.cursor() as cur:
        cur.execute("update rfq set status = 'draft' where id = %s", (alpha.rfq_id,))
        user_id, membership_id = _add_member(cur, alpha, "buyer")
        request_id = _prepared_request(cur, alpha, membership_id, alpha.rfq_response_id)
        _act_as_user(cur, alpha, user_id, "buyer")
        cur.execute("select mark_rfq_converted(%s, %s)", (alpha.rfq_id, request_id))
        assert cur.fetchone()[0] is False
        assert _rfq_status(cur, alpha.rfq_id) == "draft"

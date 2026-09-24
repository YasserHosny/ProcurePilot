"""Cross-tenant isolation tests for analyst_conversation, analyst_turn, and
analyst_turn_citation (R4.2 Grounded Procurement Analyst).

These tests run against a real Postgres database with the migrations applied
and use the `authenticated` role with real JWT claims — mocking would prove nothing.

Set TEST_DATABASE_URL to a database with all migrations applied, including
20260924000001_analyst_conversations.sql.

Cross-tenant guarantees under test:
- A member of tenant A cannot read another tenant's conversations, turns, or citations.
- A non-owner/non-buyer member cannot read another member's own-tenant conversations.
- The authenticated role cannot UPDATE or DELETE analyst_turn (append-only).
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


# ---------------------------------------------------------------------------
# Minimal workspace seed — creates just what analyst tables need.
# ---------------------------------------------------------------------------


class AnalystWorkspace:
    """One tenant, one owner member, one conversation, one turn, one citation."""

    def __init__(
        self,
        tenant_id: UUID,
        user_id: UUID,
        membership_id: UUID,
        supplier_id: UUID,
        quotation_id: UUID,
        quotation_line_id: UUID,
        conversation_id: UUID,
        turn_id: UUID,
        citation_id: UUID,
    ) -> None:
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.membership_id = membership_id
        self.supplier_id = supplier_id
        self.quotation_id = quotation_id
        self.quotation_line_id = quotation_line_id
        self.conversation_id = conversation_id
        self.turn_id = turn_id
        self.citation_id = citation_id

    def claims(self, *, role: str = "owner") -> str:
        return json.dumps(
            {
                "sub": str(self.user_id),
                "tenant_id": str(self.tenant_id),
                "role": "authenticated",
                "member_role": role,
            }
        )


def _make_analyst_workspace(cur: psycopg.Cursor, label: str) -> AnalystWorkspace:
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
        (user_id, f"analyst-{label}@example.test"),
    )

    # Tenant + invitation
    cur.execute(
        "insert into platform_invitation (id,email,token_hash,expires_at) "
        "values (%s,%s,%s, now() + interval '7 days')",
        (invitation_id, f"analyst-{label}@example.test", f"hash-analyst-{label}"),
    )
    cur.execute(
        "insert into tenant (id,name,slug,region,currency,tax_model,platform_invitation_id) "
        "values (%s,%s,%s,'GB','GBP','uk_vat',%s)",
        (tenant_id, f"Analyst {label} Ltd", f"analyst-{label}-{tenant_id.hex[:8]}", invitation_id),
    )
    cur.execute(
        "insert into membership (id,tenant_id,user_id,email,role,is_active_workspace) "
        "values (%s,%s,%s,%s,'owner',true)",
        (membership_id, tenant_id, user_id, f"analyst-{label}@example.test"),
    )

    # Supplier (for FK context on citation)
    cur.execute(
        "insert into supplier (id,tenant_id,name) values (%s,%s,%s)",
        (supplier_id, tenant_id, f"Analyst {label} Supplier Co"),
    )

    # Canonical + workspace product (for quotation FK chain)
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

    # Document → quotation → quotation_line (for citation FK)
    document_id, quotation_id, quotation_line_id = uuid4(), uuid4(), uuid4()
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
    cur.execute(
        "insert into quotation_line (id,tenant_id,quotation_id,line_number,original_text) "
        "values (%s,%s,%s,1,%s)",
        (quotation_line_id, tenant_id, quotation_id, f"{label} analyst line item"),
    )

    # analyst_conversation (inserted as superuser, no RLS yet)
    conversation_id = uuid4()
    cur.execute(
        "insert into analyst_conversation (id,tenant_id,creating_member_id) "
        "values (%s,%s,%s)",
        (conversation_id, tenant_id, membership_id),
    )

    # analyst_turn (inserted as superuser, no RLS yet)
    turn_id = uuid4()
    cur.execute(
        "insert into analyst_turn "
        "(id,tenant_id,conversation_id,creating_member_id,question_text,category,"
        "answer_text,calculation_version,idempotency_key) "
        "values (%s,%s,%s,%s,%s,'spend_savings',%s,'analyst-retrieval-v1',%s)",
        (
            turn_id,
            tenant_id,
            conversation_id,
            membership_id,
            f"What is the total spend for {label}?",
            f"Total spend for {label}: GBP 1,000.",
            uuid4(),
        ),
    )

    # analyst_turn_citation using quotation_line_id (exactly one non-null source)
    citation_id = uuid4()
    cur.execute(
        "insert into analyst_turn_citation "
        "(id,tenant_id,turn_id,quotation_line_id) "
        "values (%s,%s,%s,%s)",
        (citation_id, tenant_id, turn_id, quotation_line_id),
    )

    return AnalystWorkspace(
        tenant_id=tenant_id,
        user_id=user_id,
        membership_id=membership_id,
        supplier_id=supplier_id,
        quotation_id=quotation_id,
        quotation_line_id=quotation_line_id,
        conversation_id=conversation_id,
        turn_id=turn_id,
        citation_id=citation_id,
    )


@pytest.fixture
def analyst_workspaces() -> Iterator[tuple[psycopg.Connection, AnalystWorkspace, AnalystWorkspace]]:
    """Two unrelated tenants, each with one conversation/turn/citation."""
    with psycopg.connect(TEST_DATABASE_URL or "") as conn:
        with conn.cursor() as cur:
            alpha = _make_analyst_workspace(cur, "alpha-analyst")
            beta = _make_analyst_workspace(cur, "beta-analyst")
        yield conn, alpha, beta
        conn.rollback()


def _act_as(cur: psycopg.Cursor, workspace: AnalystWorkspace, *, role: str = "owner") -> None:
    cur.execute("set local role authenticated")
    cur.execute(
        "select set_config('request.jwt.claims', %s, true)",
        (workspace.claims(role=role),),
    )


def _act_as_tenant_sync(cur: psycopg.Cursor, tenant_id: UUID) -> None:
    """Worker session: tenant-scoped, no member_role claim."""
    cur.execute("set local role authenticated")
    cur.execute(
        "select set_config('request.jwt.claims', %s, true)",
        (json.dumps({"tenant_id": str(tenant_id), "role": "authenticated"}),),
    )


# ---------------------------------------------------------------------------
# Cross-tenant read isolation: analyst_conversation
# ---------------------------------------------------------------------------


def test_another_tenants_conversations_are_invisible(
    analyst_workspaces: tuple[psycopg.Connection, AnalystWorkspace, AnalystWorkspace],
) -> None:
    """Alpha cannot read beta's analyst_conversation by list or by ID."""
    conn, alpha, beta = analyst_workspaces
    with conn.cursor() as cur:
        _act_as(cur, alpha)

        cur.execute(
            "select id from analyst_conversation where tenant_id = %s", (beta.tenant_id,)
        )
        assert cur.fetchall() == [], "cross-tenant list must be empty"

        cur.execute(
            "select id from analyst_conversation where id = %s", (beta.conversation_id,)
        )
        assert cur.fetchone() is None, (
            "direct cross-tenant read must be None (not-found, not forbidden)"
        )


# ---------------------------------------------------------------------------
# Cross-tenant read isolation: analyst_turn
# ---------------------------------------------------------------------------


def test_another_tenants_turns_are_invisible(
    analyst_workspaces: tuple[psycopg.Connection, AnalystWorkspace, AnalystWorkspace],
) -> None:
    conn, alpha, beta = analyst_workspaces
    with conn.cursor() as cur:
        _act_as(cur, alpha)

        cur.execute(
            "select id from analyst_turn where tenant_id = %s", (beta.tenant_id,)
        )
        assert cur.fetchall() == []

        cur.execute(
            "select id from analyst_turn where id = %s", (beta.turn_id,)
        )
        assert cur.fetchone() is None


# ---------------------------------------------------------------------------
# Cross-tenant read isolation: analyst_turn_citation
# ---------------------------------------------------------------------------


def test_another_tenants_citations_are_invisible(
    analyst_workspaces: tuple[psycopg.Connection, AnalystWorkspace, AnalystWorkspace],
) -> None:
    conn, alpha, beta = analyst_workspaces
    with conn.cursor() as cur:
        _act_as(cur, alpha)

        cur.execute(
            "select id from analyst_turn_citation where tenant_id = %s", (beta.tenant_id,)
        )
        assert cur.fetchall() == []

        cur.execute(
            "select id from analyst_turn_citation where id = %s", (beta.citation_id,)
        )
        assert cur.fetchone() is None


# ---------------------------------------------------------------------------
# Cross-tenant write isolation: INSERT must be rejected
# ---------------------------------------------------------------------------


def test_member_cannot_insert_conversation_into_another_tenant(
    analyst_workspaces: tuple[psycopg.Connection, AnalystWorkspace, AnalystWorkspace],
) -> None:
    conn, alpha, beta = analyst_workspaces
    with conn.cursor() as cur:
        _act_as(cur, alpha)
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cur.execute(
                "insert into analyst_conversation (tenant_id,creating_member_id) "
                "values (%s,%s)",
                (beta.tenant_id, alpha.membership_id),
            )


def test_worker_session_cannot_insert_turn_into_another_tenant(
    analyst_workspaces: tuple[psycopg.Connection, AnalystWorkspace, AnalystWorkspace],
) -> None:
    conn, alpha, beta = analyst_workspaces
    with conn.cursor() as cur:
        _act_as_tenant_sync(cur, alpha.tenant_id)
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cur.execute(
                "insert into analyst_turn "
                "(tenant_id,conversation_id,creating_member_id,question_text,category,"
                "answer_text,calculation_version,idempotency_key) "
                "values (%s,%s,%s,'hijack?','spend_savings','hijack','v1',%s)",
                (beta.tenant_id, beta.conversation_id, beta.membership_id, uuid4()),
            )


# ---------------------------------------------------------------------------
# Append-only: analyst_turn must not allow UPDATE or DELETE
# ---------------------------------------------------------------------------


def test_authenticated_cannot_update_analyst_turn(
    analyst_workspaces: tuple[psycopg.Connection, AnalystWorkspace, AnalystWorkspace],
) -> None:
    """analyst_turn is APPEND-ONLY — no UPDATE privilege for authenticated."""
    conn, alpha, _beta = analyst_workspaces
    with conn.cursor() as cur:
        _act_as(cur, alpha)
        cur.execute("savepoint no_update")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cur.execute(
                "update analyst_turn set answer_text = 'tampered' where id = %s",
                (alpha.turn_id,),
            )
        cur.execute("rollback to savepoint no_update")


def test_authenticated_cannot_delete_analyst_turn(
    analyst_workspaces: tuple[psycopg.Connection, AnalystWorkspace, AnalystWorkspace],
) -> None:
    """analyst_turn is APPEND-ONLY — no DELETE privilege for authenticated."""
    conn, alpha, _beta = analyst_workspaces
    with conn.cursor() as cur:
        _act_as(cur, alpha)
        cur.execute("savepoint no_delete")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cur.execute(
                "delete from analyst_turn where id = %s",
                (alpha.turn_id,),
            )
        cur.execute("rollback to savepoint no_delete")


# ---------------------------------------------------------------------------
# Within-tenant scoping: a non-owner/buyer member cannot see another member's conversation
# ---------------------------------------------------------------------------


def test_non_owner_member_cannot_list_another_members_conversations(
    analyst_workspaces: tuple[psycopg.Connection, AnalystWorkspace, AnalystWorkspace],
) -> None:
    """A 'viewer' role member in the same tenant must not see another member's conversations.

    FR-009: conversations are creator-scoped for ordinary members; only owner/buyer roles
    get oversight read across all conversations in the tenant.
    """
    conn, alpha, _beta = analyst_workspaces

    # Create a second user+membership in alpha's tenant with role 'viewer'.
    second_user_id, second_membership_id = uuid4(), uuid4()
    with conn.cursor() as cur:
        cur.execute(
            "insert into auth.users (id,email) values (%s,%s)",
            (second_user_id, f"viewer-{second_user_id.hex[:8]}@example.test"),
        )
        cur.execute(
            "insert into membership (id,tenant_id,user_id,email,role,is_active_workspace) "
            "values (%s,%s,%s,%s,'viewer',true)",
            (
                second_membership_id,
                alpha.tenant_id,
                second_user_id,
                f"viewer-{second_user_id.hex[:8]}@example.test",
            ),
        )

    # Act as the viewer — must not see alpha's owner-created conversation.
    with conn.cursor() as cur:
        cur.execute("set local role authenticated")
        cur.execute(
            "select set_config('request.jwt.claims', %s, true)",
            (
                json.dumps(
                    {
                        "sub": str(second_user_id),
                        "tenant_id": str(alpha.tenant_id),
                        "role": "authenticated",
                        "member_role": "viewer",
                    }
                ),
            ),
        )
        cur.execute(
            "select id from analyst_conversation where id = %s",
            (alpha.conversation_id,),
        )
        assert cur.fetchone() is None, (
            "a viewer-role member must not see another member's conversations "
            "(only owner/buyer get oversight reads per FR-009)"
        )

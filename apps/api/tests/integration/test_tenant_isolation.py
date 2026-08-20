"""Cross-workspace isolation — task T036. THE test this chunk exists to make possible.

Constitution Principle V: isolation is enforced by the database, so that a forgotten
`where tenant_id = ...` in application code cannot leak another business's commercial data.
Testing that against a mock would prove nothing — these run against a real Postgres with the
real migrations, as the real `authenticated` role, carrying a real JWT claim.

FR-030 requires this to run on every proposed change. It is wired into CI as its own named check
so that its failure is never mistaken for an unrelated test failure.

Set TEST_DATABASE_URL to a database with migrations 0001-0021 applied — extended for
002-catalogue-suppliers (T038) to cover workspace_product, pack_definition, supplier,
product_alias and import_job, plus the canonical_product exception; extended again for
003-quotation-inbox-extraction (T063) to cover document, quotation, quotation_line,
field_extraction, extraction_job, review_task, and the Supabase Storage object policy.
"""

from __future__ import annotations

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


class Workspace:
    """One tenant, its owner, and a marker row only that tenant should ever see."""

    def __init__(
        self,
        tenant_id: UUID,
        user_id: UUID,
        membership_id: UUID,
        name: str,
        canonical_product_id: UUID,
        workspace_product_id: UUID,
        supplier_id: UUID,
        document_id: UUID,
        quotation_id: UUID,
        storage_path: str,
    ) -> None:
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.membership_id = membership_id
        self.name = name
        self.canonical_product_id = canonical_product_id
        self.workspace_product_id = workspace_product_id
        self.supplier_id = supplier_id
        self.document_id = document_id
        self.quotation_id = quotation_id
        self.storage_path = storage_path

    def claims(self) -> str:
        return (
            f'{{"sub":"{self.user_id}","tenant_id":"{self.tenant_id}",'
            f'"role":"authenticated","member_role":"owner"}}'
        )


def make_workspace(cur: psycopg.Cursor, label: str) -> Workspace:
    tenant_id, user_id, membership_id, invitation_id = uuid4(), uuid4(), uuid4(), uuid4()

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
        "insert into auth.users (id,email) values (%s,%s)", (user_id, f"{label}@example.test")
    )
    cur.execute(
        "insert into platform_invitation (id,email,token_hash,expires_at) "
        "values (%s,%s,%s, now() + interval '7 days')",
        (invitation_id, f"{label}@example.test", f"hash-{label}"),
    )
    cur.execute(
        "insert into tenant (id,name,slug,region,currency,tax_model,platform_invitation_id) "
        "values (%s,%s,%s,'GB','GBP','uk_vat',%s)",
        (tenant_id, f"{label} Ltd", f"{label}-{tenant_id.hex[:8]}", invitation_id),
    )
    cur.execute(
        "insert into membership (id,tenant_id,user_id,email,role,is_active_workspace) "
        "values (%s,%s,%s,%s,'owner',true)",
        (membership_id, tenant_id, user_id, f"{label}@example.test"),
    )
    # The marker: a private commercial fact belonging to exactly one workspace.
    cur.execute(
        "insert into audit_event (tenant_id,action,outcome,target) values (%s,%s,'success',%s)",
        (tenant_id, f"{label}.secret", f'{{"secret":"{label}-confidential"}}'),
    )

    # Catalogue and supplier data — chunk 4.2 (002-catalogue-suppliers), T038.
    canonical_product_id, workspace_product_id, supplier_id = uuid4(), uuid4(), uuid4()
    cur.execute(
        "insert into supported_base_unit (code,label_en,label_ar,dimension,is_enabled) "
        "values ('each','Each','قطعة','count',true) on conflict do nothing"
    )
    cur.execute(
        "insert into canonical_product (id,name,base_unit) values (%s,%s,'each')",
        (canonical_product_id, f"{label} widget"),
    )
    cur.execute(
        "insert into workspace_product (id,tenant_id,canonical_product_id,tenant_name) "
        "values (%s,%s,%s,%s)",
        (workspace_product_id, tenant_id, canonical_product_id, f"{label} widget"),
    )
    cur.execute(
        "insert into pack_definition (tenant_id,workspace_product_id,pack_count,unit_size) "
        "values (%s,%s,6,5)",
        (tenant_id, workspace_product_id),
    )
    cur.execute(
        "insert into supplier (id,tenant_id,name) values (%s,%s,%s)",
        (supplier_id, tenant_id, f"{label} Supplier Co"),
    )
    cur.execute(
        "insert into product_alias (tenant_id,workspace_product_id,supplier_id,alias_text) "
        "values (%s,%s,%s,%s)",
        (tenant_id, workspace_product_id, supplier_id, f"{label}-supplier-wording"),
    )
    cur.execute(
        "insert into import_job (tenant_id,kind,filename) values (%s,'products',%s)",
        (tenant_id, f"{label}.csv"),
    )

    # Quotation inbox and extraction — chunk 4.3 (003-quotation-inbox-extraction), T063.
    document_id, quotation_id, quotation_line_id = uuid4(), uuid4(), uuid4()
    field_extraction_id, extraction_job_id, review_task_id = uuid4(), uuid4(), uuid4()
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
        (quotation_line_id, tenant_id, quotation_id, f"{label} line item"),
    )
    cur.execute(
        "insert into field_extraction "
        "(id,tenant_id,quotation_id,entity_type,entity_id,field_name,extracted_value,"
        "confidence,extraction_method,model_version) "
        "values (%s,%s,%s,'quotation',%s,'currency','\"GBP\"'::jsonb,0.9,"
        "'structured_parse','test-fixture-v1')",
        (field_extraction_id, tenant_id, quotation_id, quotation_id),
    )
    cur.execute(
        "insert into extraction_job (id,tenant_id,quotation_id) values (%s,%s,%s)",
        (extraction_job_id, tenant_id, quotation_id),
    )
    cur.execute(
        "insert into review_task (id,tenant_id,quotation_id,reason) "
        "values (%s,%s,%s,'low_confidence')",
        (review_task_id, tenant_id, quotation_id),
    )
    cur.execute(
        "insert into storage.objects (bucket_id,name,owner) "
        "values ('quotation-documents',%s,%s)",
        (storage_path, user_id),
    )

    return Workspace(
        tenant_id,
        user_id,
        membership_id,
        f"{label} Ltd",
        canonical_product_id,
        workspace_product_id,
        supplier_id,
        document_id,
        quotation_id,
        storage_path,
    )


@pytest.fixture
def workspaces() -> Iterator[tuple[psycopg.Connection, Workspace, Workspace]]:
    """Two unrelated businesses on one database — the situation isolation must survive."""
    with psycopg.connect(TEST_DATABASE_URL or "") as conn:
        with conn.cursor() as cur:
            alpha = make_workspace(cur, "alpha")
            beta = make_workspace(cur, "beta")
        yield conn, alpha, beta
        conn.rollback()


def act_as(cur: psycopg.Cursor, workspace: Workspace) -> None:
    """Become a member of `workspace`, exactly as a real request arrives."""
    cur.execute("set local role authenticated")
    cur.execute("select set_config('request.jwt.claims', %s, true)", (workspace.claims(),))


# --- reads ------------------------------------------------------------------


def test_a_member_sees_only_their_own_workspace(
    workspaces: tuple[psycopg.Connection, Workspace, Workspace],
) -> None:
    conn, alpha, _beta = workspaces
    with conn.cursor() as cur:
        act_as(cur, alpha)
        cur.execute("select id from tenant")
        rows = cur.fetchall()
    assert [r[0] for r in rows] == [alpha.tenant_id]


def test_fetching_another_workspace_by_id_looks_like_it_does_not_exist(
    workspaces: tuple[psycopg.Connection, Workspace, Workspace],
) -> None:
    """FR-005: never reveal that a record exists but is forbidden."""
    conn, alpha, beta = workspaces
    with conn.cursor() as cur:
        act_as(cur, alpha)
        cur.execute("select id from tenant where id = %s", (beta.tenant_id,))
        assert cur.fetchall() == []


def test_another_workspaces_members_are_invisible(
    workspaces: tuple[psycopg.Connection, Workspace, Workspace],
) -> None:
    conn, alpha, beta = workspaces
    with conn.cursor() as cur:
        act_as(cur, alpha)
        cur.execute("select count(*) from membership where tenant_id = %s", (beta.tenant_id,))
        row = cur.fetchone()
    assert row is not None and row[0] == 0


def test_another_workspaces_audit_history_is_invisible(
    workspaces: tuple[psycopg.Connection, Workspace, Workspace],
) -> None:
    conn, alpha, _beta = workspaces
    with conn.cursor() as cur:
        act_as(cur, alpha)
        cur.execute("select action from audit_event")
        actions = {r[0] for r in cur.fetchall()}
    assert "beta.secret" not in actions
    assert "alpha.secret" in actions


def test_a_member_cannot_enumerate_other_workspaces(
    workspaces: tuple[psycopg.Connection, Workspace, Workspace],
) -> None:
    """Counting must not leak existence either."""
    conn, alpha, _beta = workspaces
    with conn.cursor() as cur:
        act_as(cur, alpha)
        cur.execute("select count(*) from tenant")
        row = cur.fetchone()
    assert row is not None and row[0] == 1


# --- writes -----------------------------------------------------------------


def test_a_member_cannot_write_into_another_workspace(
    workspaces: tuple[psycopg.Connection, Workspace, Workspace],
) -> None:
    """WITH CHECK. A USING-only policy would allow this write-then-cannot-read corruption."""
    conn, alpha, beta = workspaces
    with conn.cursor() as cur:
        act_as(cur, alpha)
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cur.execute(
                "insert into member_invitation "
                "(tenant_id,email,role,token_hash,invited_by,expires_at) "
                "values (%s,'intruder@evil.test','owner','h',%s, now() + interval '7 days')",
                (beta.tenant_id, alpha.membership_id),
            )


def test_a_cross_workspace_update_changes_nothing(
    workspaces: tuple[psycopg.Connection, Workspace, Workspace],
) -> None:
    conn, alpha, beta = workspaces
    with conn.cursor() as cur:
        act_as(cur, alpha)
        cur.execute(
            "update membership set role = 'viewer' where tenant_id = %s", (beta.tenant_id,)
        )
        assert cur.rowcount == 0
        cur.execute("reset role")
        cur.execute(
            "select role from membership where tenant_id = %s", (beta.tenant_id,)
        )
        row = cur.fetchone()
    assert row is not None and row[0] == "owner"


def test_a_cross_workspace_delete_removes_nothing(
    workspaces: tuple[psycopg.Connection, Workspace, Workspace],
) -> None:
    conn, alpha, beta = workspaces
    with conn.cursor() as cur:
        act_as(cur, alpha)
        cur.execute("delete from membership where tenant_id = %s", (beta.tenant_id,))
        assert cur.rowcount == 0
        cur.execute("reset role")
        cur.execute("select count(*) from membership where tenant_id = %s", (beta.tenant_id,))
        row = cur.fetchone()
    assert row is not None and row[0] == 1


# --- absent or forged claims ------------------------------------------------


def test_no_tenant_claim_sees_nothing(
    workspaces: tuple[psycopg.Connection, Workspace, Workspace],
) -> None:
    """A request that resolves to no workspace must be served nothing, not everything."""
    conn, _alpha, _beta = workspaces
    with conn.cursor() as cur:
        cur.execute("set local role authenticated")
        cur.execute("select set_config('request.jwt.claims', '{}', true)")
        cur.execute("select count(*) from tenant")
        row = cur.fetchone()
    assert row is not None and row[0] == 0


def test_a_malformed_tenant_claim_sees_nothing(
    workspaces: tuple[psycopg.Connection, Workspace, Workspace],
) -> None:
    conn, _alpha, _beta = workspaces
    with conn.cursor() as cur:
        cur.execute("set local role authenticated")
        cur.execute(
            "select set_config('request.jwt.claims', '{\"tenant_id\":\"\"}', true)"
        )
        cur.execute("select count(*) from tenant")
        row = cur.fetchone()
    assert row is not None and row[0] == 0


# --- catalogue and suppliers (002-catalogue-suppliers, T038) ----------------


def test_another_workspaces_products_are_invisible(
    workspaces: tuple[psycopg.Connection, Workspace, Workspace],
) -> None:
    conn, alpha, beta = workspaces
    with conn.cursor() as cur:
        act_as(cur, alpha)
        cur.execute(
            "select id from workspace_product where id = %s", (beta.workspace_product_id,)
        )
        assert cur.fetchall() == []


def test_another_workspaces_pack_definitions_are_invisible(
    workspaces: tuple[psycopg.Connection, Workspace, Workspace],
) -> None:
    conn, alpha, beta = workspaces
    with conn.cursor() as cur:
        act_as(cur, alpha)
        cur.execute(
            "select count(*) from pack_definition where workspace_product_id = %s",
            (beta.workspace_product_id,),
        )
        row = cur.fetchone()
    assert row is not None and row[0] == 0


def test_another_workspaces_suppliers_are_invisible(
    workspaces: tuple[psycopg.Connection, Workspace, Workspace],
) -> None:
    conn, alpha, beta = workspaces
    with conn.cursor() as cur:
        act_as(cur, alpha)
        cur.execute("select id from supplier where id = %s", (beta.supplier_id,))
        assert cur.fetchall() == []


def test_another_workspaces_aliases_are_invisible(
    workspaces: tuple[psycopg.Connection, Workspace, Workspace],
) -> None:
    """FR-027: an alias resolves only for the workspace that recorded it."""
    conn, alpha, beta = workspaces
    with conn.cursor() as cur:
        act_as(cur, alpha)
        cur.execute(
            "select count(*) from product_alias where workspace_product_id = %s",
            (beta.workspace_product_id,),
        )
        row = cur.fetchone()
    assert row is not None and row[0] == 0


def test_another_workspaces_import_jobs_are_invisible(
    workspaces: tuple[psycopg.Connection, Workspace, Workspace],
) -> None:
    conn, alpha, beta = workspaces
    with conn.cursor() as cur:
        act_as(cur, alpha)
        cur.execute("select count(*) from import_job where tenant_id = %s", (beta.tenant_id,))
        row = cur.fetchone()
    assert row is not None and row[0] == 0


def test_canonical_product_is_shared_across_workspaces_by_design(
    workspaces: tuple[psycopg.Connection, Workspace, Workspace],
) -> None:
    """The ONE deliberate exception (research.md R5) — must stay an exception, not a leak.

    canonical_product carries no workspace-identifying data, so both workspaces may read both
    rows. If this ever starts failing, it means someone added a workspace-identifying column
    to canonical_product without moving it to workspace_product — check that first.
    """
    conn, alpha, beta = workspaces
    with conn.cursor() as cur:
        act_as(cur, alpha)
        cur.execute(
            "select id from canonical_product where id = any(%s)",
            ([alpha.canonical_product_id, beta.canonical_product_id],),
        )
        seen = {r[0] for r in cur.fetchall()}
    assert seen == {alpha.canonical_product_id, beta.canonical_product_id}


def test_a_member_cannot_write_a_supplier_into_another_workspace(
    workspaces: tuple[psycopg.Connection, Workspace, Workspace],
) -> None:
    conn, alpha, beta = workspaces
    with conn.cursor() as cur:
        act_as(cur, alpha)
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cur.execute(
                "insert into supplier (tenant_id,name) values (%s,'intruder co')",
                (beta.tenant_id,),
            )


def test_a_cross_workspace_supplier_update_changes_nothing(
    workspaces: tuple[psycopg.Connection, Workspace, Workspace],
) -> None:
    conn, alpha, beta = workspaces
    with conn.cursor() as cur:
        act_as(cur, alpha)
        cur.execute(
            "update supplier set name = 'renamed' where id = %s", (beta.supplier_id,)
        )
        assert cur.rowcount == 0
        cur.execute("reset role")
        cur.execute("select name from supplier where id = %s", (beta.supplier_id,))
        row = cur.fetchone()
    assert row is not None and row[0] == "beta Supplier Co"


# --- quotation inbox and extraction (003-quotation-inbox-extraction, T063) --


def test_another_workspaces_documents_are_invisible(
    workspaces: tuple[psycopg.Connection, Workspace, Workspace],
) -> None:
    conn, alpha, beta = workspaces
    with conn.cursor() as cur:
        act_as(cur, alpha)
        cur.execute("select id from document where id = %s", (beta.document_id,))
        assert cur.fetchall() == []


def test_another_workspaces_quotations_are_invisible(
    workspaces: tuple[psycopg.Connection, Workspace, Workspace],
) -> None:
    conn, alpha, beta = workspaces
    with conn.cursor() as cur:
        act_as(cur, alpha)
        cur.execute("select id from quotation where id = %s", (beta.quotation_id,))
        assert cur.fetchall() == []


def test_another_workspaces_quotation_lines_are_invisible(
    workspaces: tuple[psycopg.Connection, Workspace, Workspace],
) -> None:
    conn, alpha, beta = workspaces
    with conn.cursor() as cur:
        act_as(cur, alpha)
        cur.execute(
            "select count(*) from quotation_line where quotation_id = %s", (beta.quotation_id,)
        )
        row = cur.fetchone()
    assert row is not None and row[0] == 0


def test_another_workspaces_field_extractions_are_invisible(
    workspaces: tuple[psycopg.Connection, Workspace, Workspace],
) -> None:
    """Constitution Principle I's evidence record is exactly as tenant-private as anything else."""
    conn, alpha, beta = workspaces
    with conn.cursor() as cur:
        act_as(cur, alpha)
        cur.execute(
            "select count(*) from field_extraction where quotation_id = %s", (beta.quotation_id,)
        )
        row = cur.fetchone()
    assert row is not None and row[0] == 0


def test_another_workspaces_extraction_jobs_are_invisible(
    workspaces: tuple[psycopg.Connection, Workspace, Workspace],
) -> None:
    conn, alpha, beta = workspaces
    with conn.cursor() as cur:
        act_as(cur, alpha)
        cur.execute(
            "select count(*) from extraction_job where quotation_id = %s", (beta.quotation_id,)
        )
        row = cur.fetchone()
    assert row is not None and row[0] == 0


def test_another_workspaces_review_tasks_are_invisible(
    workspaces: tuple[psycopg.Connection, Workspace, Workspace],
) -> None:
    """FR-019: the review queue is standalone, but still tenant-private."""
    conn, alpha, beta = workspaces
    with conn.cursor() as cur:
        act_as(cur, alpha)
        cur.execute(
            "select count(*) from review_task where quotation_id = %s", (beta.quotation_id,)
        )
        row = cur.fetchone()
    assert row is not None and row[0] == 0


def test_a_member_cannot_write_a_quotation_into_another_workspace(
    workspaces: tuple[psycopg.Connection, Workspace, Workspace],
) -> None:
    conn, alpha, beta = workspaces
    with conn.cursor() as cur:
        act_as(cur, alpha)
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cur.execute(
                "insert into quotation (tenant_id,document_id) values (%s,%s)",
                (beta.tenant_id, beta.document_id),
            )


def test_a_cross_workspace_quotation_update_changes_nothing(
    workspaces: tuple[psycopg.Connection, Workspace, Workspace],
) -> None:
    conn, alpha, beta = workspaces
    with conn.cursor() as cur:
        act_as(cur, alpha)
        cur.execute(
            "update quotation set status = 'refused' where id = %s", (beta.quotation_id,)
        )
        assert cur.rowcount == 0
        cur.execute("reset role")
        cur.execute("select status from quotation where id = %s", (beta.quotation_id,))
        row = cur.fetchone()
    assert row is not None and row[0] == "pending"


def test_storage_object_from_another_workspace_is_invisible(
    workspaces: tuple[psycopg.Connection, Workspace, Workspace],
) -> None:
    """The second isolation boundary (research.md R8): table RLS is not the only guarantee.

    A member of alpha must not be able to read beta's quotation-document object even knowing
    (or guessing) its exact storage path.
    """
    conn, alpha, beta = workspaces
    with conn.cursor() as cur:
        act_as(cur, alpha)
        cur.execute(
            "select name from storage.objects where bucket_id = 'quotation-documents' "
            "and name = %s",
            (beta.storage_path,),
        )
        assert cur.fetchall() == []
        cur.execute(
            "select name from storage.objects where bucket_id = 'quotation-documents' "
            "and name = %s",
            (alpha.storage_path,),
        )
        assert cur.fetchall() == [(alpha.storage_path,)]


def test_platform_invitations_are_unreadable_by_members(
    workspaces: tuple[psycopg.Connection, Workspace, Workspace],
) -> None:
    """They gate entry to the pilot; a member must not be able to mint or read one."""
    conn, alpha, _beta = workspaces
    with conn.cursor() as cur:
        act_as(cur, alpha)
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cur.execute("select count(*) from platform_invitation")


# --- the guarantee itself ---------------------------------------------------


def test_rls_is_enabled_and_forced_on_every_tenant_scoped_table(
    workspaces: tuple[psycopg.Connection, Workspace, Workspace],
) -> None:
    """ENABLE without FORCE exempts the table owner, and migrations run as the owner.

    Without FORCE, every test above could pass while production leaked.
    """
    conn, _alpha, _beta = workspaces
    expected = {
        "tenant", "membership", "member_invitation", "audit_event", "platform_invitation",
        "workspace_product", "pack_definition", "product_substitute", "supplier",
        "product_alias", "import_job", "canonical_product",
        "document", "quotation", "quotation_line", "field_extraction", "extraction_job",
        "review_task",
    }
    with conn.cursor() as cur:
        cur.execute(
            "select relname, relrowsecurity, relforcerowsecurity from pg_class "
            "where relname = any(%s)",
            (list(expected),),
        )
        rows = cur.fetchall()
    assert {r[0] for r in rows} == expected
    for name, enabled, forced in rows:
        assert enabled, f"row level security is not ENABLED on {name}"
        assert forced, f"row level security is not FORCED on {name}"

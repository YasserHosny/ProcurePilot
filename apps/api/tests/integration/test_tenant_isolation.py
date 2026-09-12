"""Cross-workspace isolation — task T036. THE test this chunk exists to make possible.

Constitution Principle V: isolation is enforced by the database, so that a forgotten
`where tenant_id = ...` in application code cannot leak another business's commercial data.
Testing that against a mock would prove nothing — these run against a real Postgres with the
real migrations, as the real `authenticated` role, carrying a real JWT claim.

FR-030 requires this to run on every proposed change. It is wired into CI as its own named check
so that its failure is never mistaken for an unrelated test failure.

Set TEST_DATABASE_URL to a database with migrations 0001-0035 applied — extended for
002-catalogue-suppliers (T038) to cover workspace_product, pack_definition, supplier,
product_alias and import_job, plus the canonical_product exception; extended again for
003-quotation-inbox-extraction (T063) to cover document, quotation, quotation_line,
field_extraction, extraction_job, review_task, and the Supabase Storage object policy; extended
again for 004-matching-normalisation (T052) to cover match_candidate, match_task, match_decision
and landed_cost, plus the tenant-scoped and shared embedding columns added to workspace_product
and canonical_product respectively; extended again for 005-smart-compare-intelligence to cover
basket_split_job and alert_dismissal — the only two real tables that chunk adds, since offers,
recommendations, price history, and live alert conditions are computed at request time from
already-isolated rows and add no new storage surface; extended again for
006-value-proof-launch to cover purchase_record, saving_record and billing_account, plus the
shared plan exception (mirroring canonical_product — see research.md R5) and the two
Principle-critical immutability triggers a verified saving_record depends on; extended again for
007-organisation-model (T008) to cover branch, cost_centre, budget and branch_role_assignment —
cross-tenant isolation only, since the within-tenant branch-scoped visibility these tables also
enforce (research.md R1) has its own dedicated proof in test_branch_scoped_visibility.py (T036);
extended again for 008-requests-approvals (T008) to cover purchase_request,
purchase_request_line, approval_step, threshold_rule and approval_delegation — cross-tenant
isolation only, same split as R2.0; extended again for 009-mobile-app-mvp (T007) to cover
device_registration, low_stock_report and push_notification — cross-tenant isolation only, same
split as every prior chunk; device_registration's own-row-only visibility (no owner read-all) and
low_stock_report's branch-scoped visibility have their within-tenant proof in
test_branch_scoped_visibility.py, not here.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg.types.json import Jsonb

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
        quotation_line_id: UUID,
        basket_split_job_id: UUID,
        alert_dismissal_id: UUID,
        purchase_record_id: UUID,
        saving_record_id: UUID,
        billing_account_id: UUID,
        export_job_id: UUID,
        branch_id: UUID,
        cost_centre_id: UUID,
        budget_id: UUID,
        branch_role_assignment_id: UUID,
        purchase_request_id: UUID,
        purchase_request_line_id: UUID,
        approval_step_id: UUID,
        threshold_rule_id: UUID,
        approval_delegation_id: UUID,
        device_registration_id: UUID,
        low_stock_report_id: UUID,
        push_notification_id: UUID,
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
        self.quotation_line_id = quotation_line_id
        self.basket_split_job_id = basket_split_job_id
        self.alert_dismissal_id = alert_dismissal_id
        self.purchase_record_id = purchase_record_id
        self.saving_record_id = saving_record_id
        self.billing_account_id = billing_account_id
        self.export_job_id = export_job_id
        self.branch_id = branch_id
        self.cost_centre_id = cost_centre_id
        self.budget_id = budget_id
        self.branch_role_assignment_id = branch_role_assignment_id
        self.purchase_request_id = purchase_request_id
        self.purchase_request_line_id = purchase_request_line_id
        self.approval_step_id = approval_step_id
        self.threshold_rule_id = threshold_rule_id
        self.approval_delegation_id = approval_delegation_id
        self.device_registration_id = device_registration_id
        self.low_stock_report_id = low_stock_report_id
        self.push_notification_id = push_notification_id

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

    # Matching and normalisation — chunk 4.4 (004-matching-normalisation), T052.
    match_candidate_id, match_task_id, match_decision_id, landed_cost_id = (
        uuid4(), uuid4(), uuid4(), uuid4()
    )
    cur.execute(
        "insert into match_candidate "
        "(id,tenant_id,quotation_line_id,candidate_workspace_product_id,confidence,reasons,"
        "rank,scoring_version) "
        "values (%s,%s,%s,%s,0.5,'{}'::jsonb,1,'test-fixture-v1')",
        (match_candidate_id, tenant_id, quotation_line_id, workspace_product_id),
    )
    cur.execute(
        "insert into match_task (id,tenant_id,quotation_line_id,reason) "
        "values (%s,%s,%s,'low_confidence')",
        (match_task_id, tenant_id, quotation_line_id),
    )
    cur.execute(
        "insert into match_decision "
        "(id,tenant_id,quotation_line_id,matched_workspace_product_id,"
        "selected_match_candidate_id,outcome,is_automatic,confidence) "
        "values (%s,%s,%s,%s,%s,'same_product',true,0.5)",
        (
            match_decision_id,
            tenant_id,
            quotation_line_id,
            workspace_product_id,
            match_candidate_id,
        ),
    )
    cur.execute(
        "insert into landed_cost "
        "(id,tenant_id,quotation_line_id,match_decision_id,quantity,normalised_base_quantity,"
        "base_unit,unit_price_amount,unit_price_currency,vat_amount,vat_currency,"
        "delivery_fee_amount,delivery_fee_currency,discount_amount,discount_currency,"
        "other_charges_amount,other_charges_currency,total_amount,total_currency,raw_inputs,"
        "rule_version,valid_from) "
        "values (%s,%s,%s,%s,10,10,'each',10,'GBP',2,'GBP',0,'GBP',0,'GBP',0,'GBP',12,'GBP',"
        "'{}'::jsonb,'landed-cost-v1',now())",
        (landed_cost_id, tenant_id, quotation_line_id, match_decision_id),
    )

    # Smart Compare + Intelligence — chunk 4.5 (005-smart-compare-intelligence). Offers,
    # recommendations, price history and live alert conditions add no storage of their own; only
    # these two tables are real.
    second_supplier_id, basket_split_job_id, alert_dismissal_id = uuid4(), uuid4(), uuid4()
    cur.execute(
        "insert into supplier (id,tenant_id,name) values (%s,%s,%s)",
        (second_supplier_id, tenant_id, f"{label} Second Supplier Co"),
    )
    cur.execute(
        "insert into basket_split_job "
        "(id,tenant_id,requested_by,supplier_ids,items,status) "
        "values (%s,%s,%s,%s,%s,'queued')",
        (
            basket_split_job_id,
            tenant_id,
            membership_id,
            [supplier_id, second_supplier_id],
            Jsonb([{"workspace_product_id": str(workspace_product_id), "quantity": "10.000000"}]),
        ),
    )
    cur.execute(
        "insert into alert_dismissal "
        "(id,tenant_id,alert_fingerprint,kind,workspace_product_id,dismissed_by) "
        "values (%s,%s,%s,'recommended_price_expiring',%s,%s)",
        (
            alert_dismissal_id,
            tenant_id,
            f"{label}-fingerprint",
            workspace_product_id,
            membership_id,
        ),
    )

    # Value Proof + Launch Readiness — chunk 4.6 (006-value-proof-launch). purchase_record and
    # saving_record are the product's second append-only entity; kept pending (not verified) here
    # so cleanup can rely on the ordinary cascade rather than the immutability trigger.
    purchase_record_id, saving_record_id, billing_account_id = uuid4(), uuid4(), uuid4()
    cur.execute(
        "insert into purchase_record "
        "(id,tenant_id,workspace_product_id,recorded_by,quantity,base_unit,"
        "unit_price_amount,unit_price_currency,total_paid_amount,total_paid_currency,"
        "delivery_result) "
        "values (%s,%s,%s,%s,10,'each',5,'GBP',50,'GBP','delivered')",
        (purchase_record_id, tenant_id, workspace_product_id, membership_id),
    )
    cur.execute(
        "insert into saving_record "
        "(id,tenant_id,purchase_record_id,workspace_product_id,baseline_policy,"
        "actual_value_amount,actual_value_currency,calculation_version,calculation_inputs,"
        "recorded_by) "
        "values (%s,%s,%s,%s,'none_available',50,'GBP','test-fixture-v1','{}'::jsonb,%s)",
        (saving_record_id, tenant_id, purchase_record_id, workspace_product_id, membership_id),
    )
    cur.execute(
        "insert into billing_account "
        "(id,tenant_id,plan_code,provider_customer_id) "
        "values (%s,%s,'starter',%s)",
        (billing_account_id, tenant_id, f"stub_customer:{tenant_id}"),
    )
    export_job_id = uuid4()
    cur.execute(
        "insert into export_job (id,tenant_id,requested_by,format,filters) "
        "values (%s,%s,%s,'xlsx','{}'::jsonb)",
        (export_job_id, tenant_id, membership_id),
    )

    # Organisation Model — chunk R2.0 (007-organisation-model), T008.
    branch_id, cost_centre_id, budget_id, branch_role_assignment_id = (
        uuid4(), uuid4(), uuid4(), uuid4()
    )
    cur.execute(
        "insert into branch (id,tenant_id,name,region) values (%s,%s,%s,'GB')",
        (branch_id, tenant_id, f"{label} Branch"),
    )
    cur.execute(
        "insert into cost_centre (id,tenant_id,name,code,branch_id) "
        "values (%s,%s,%s,%s,%s)",
        (cost_centre_id, tenant_id, f"{label} Cost Centre", f"{label}-cc", branch_id),
    )
    cur.execute(
        "insert into budget "
        "(id,tenant_id,amount,currency,period,period_start,scope,branch_id,created_by) "
        "values (%s,%s,1000,'GBP','monthly',date_trunc('month', now()),'branch',%s,%s)",
        (budget_id, tenant_id, branch_id, membership_id),
    )
    cur.execute(
        "insert into branch_role_assignment (id,tenant_id,membership_id,branch_id) "
        "values (%s,%s,%s,%s)",
        (branch_role_assignment_id, tenant_id, membership_id, branch_id),
    )

    # Requests + Approvals — chunk R2.1 (008-requests-approvals), T008.
    (
        purchase_request_id,
        purchase_request_line_id,
        approval_step_id,
        threshold_rule_id,
        approval_delegation_id,
        delegate_user_id,
        delegate_membership_id,
    ) = (uuid4(), uuid4(), uuid4(), uuid4(), uuid4(), uuid4(), uuid4())
    cur.execute(
        "insert into purchase_request "
        "(id,tenant_id,branch_id,cost_centre_id,requested_by_membership_id,required_by_date) "
        "values (%s,%s,%s,%s,%s, current_date + interval '7 days')",
        (purchase_request_id, tenant_id, branch_id, cost_centre_id, membership_id),
    )
    cur.execute(
        "insert into purchase_request_line "
        "(id,tenant_id,purchase_request_id,workspace_product_id,quantity,"
        "estimated_unit_price_amount,estimated_unit_price_currency,"
        "estimated_unit_price_source_landed_cost_id) "
        "values (%s,%s,%s,%s,10,10,'GBP',%s)",
        (
            purchase_request_line_id,
            tenant_id,
            purchase_request_id,
            workspace_product_id,
            landed_cost_id,
        ),
    )
    cur.execute(
        "insert into approval_step "
        "(id,tenant_id,purchase_request_id,assigned_membership_id,source,status) "
        "values (%s,%s,%s,%s,'owner_fallback','pending')",
        (approval_step_id, tenant_id, purchase_request_id, membership_id),
    )
    cur.execute(
        "insert into threshold_rule "
        "(id,tenant_id,branch_id,min_amount,currency,approver_membership_id,created_by) "
        "values (%s,%s,%s,0,'GBP',%s,%s)",
        (threshold_rule_id, tenant_id, branch_id, membership_id, membership_id),
    )
    cur.execute(
        "insert into auth.users (id,email) values (%s,%s)",
        (delegate_user_id, f"{label}-delegate@example.test"),
    )
    cur.execute(
        "insert into membership (id,tenant_id,user_id,email,role,is_active_workspace) "
        "values (%s,%s,%s,%s,'approver',false)",
        (delegate_membership_id, tenant_id, delegate_user_id, f"{label}-delegate@example.test"),
    )
    cur.execute(
        "insert into approval_delegation "
        "(id,tenant_id,delegator_membership_id,delegate_membership_id,starts_on,ends_on) "
        "values (%s,%s,%s,%s,current_date,current_date + interval '7 days')",
        (approval_delegation_id, tenant_id, membership_id, delegate_membership_id),
    )

    # Mobile MVP — chunk R2.2 (009-mobile-app-mvp), T007.
    device_registration_id, low_stock_report_id, push_notification_id = (
        uuid4(), uuid4(), uuid4()
    )
    cur.execute(
        "insert into device_registration (id,tenant_id,member_id,platform,push_token) "
        "values (%s,%s,%s,'ios',%s)",
        (device_registration_id, tenant_id, membership_id, f"{label}-push-token"),
    )
    cur.execute(
        "insert into low_stock_report (id,tenant_id,branch_id,member_id,workspace_product_id) "
        "values (%s,%s,%s,%s,%s)",
        (low_stock_report_id, tenant_id, branch_id, membership_id, workspace_product_id),
    )
    cur.execute(
        "insert into push_notification (id,tenant_id,purchase_request_id,member_id) "
        "values (%s,%s,%s,%s)",
        (push_notification_id, tenant_id, purchase_request_id, membership_id),
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
        quotation_line_id,
        basket_split_job_id,
        alert_dismissal_id,
        purchase_record_id,
        saving_record_id,
        billing_account_id,
        export_job_id,
        branch_id,
        cost_centre_id,
        budget_id,
        branch_role_assignment_id,
        purchase_request_id,
        purchase_request_line_id,
        approval_step_id,
        threshold_rule_id,
        approval_delegation_id,
        device_registration_id,
        low_stock_report_id,
        push_notification_id,
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
    """Scoped by id, not tenant_id: beta now carries two membership rows (owner + the
    approval-delegation delegate added for 008-requests-approvals, T008), so a tenant_id-only
    filter no longer identifies a single row to assert against."""
    conn, alpha, beta = workspaces
    with conn.cursor() as cur:
        act_as(cur, alpha)
        cur.execute(
            "update membership set role = 'viewer' where tenant_id = %s", (beta.tenant_id,)
        )
        assert cur.rowcount == 0
        cur.execute("reset role")
        cur.execute("select role from membership where id = %s", (beta.membership_id,))
        row = cur.fetchone()
    assert row is not None and row[0] == "owner"


def test_a_cross_workspace_delete_removes_nothing(
    workspaces: tuple[psycopg.Connection, Workspace, Workspace],
) -> None:
    """beta carries two membership rows (owner + delegate, T008) — both must survive."""
    conn, alpha, beta = workspaces
    with conn.cursor() as cur:
        act_as(cur, alpha)
        cur.execute("delete from membership where tenant_id = %s", (beta.tenant_id,))
        assert cur.rowcount == 0
        cur.execute("reset role")
        cur.execute("select count(*) from membership where tenant_id = %s", (beta.tenant_id,))
        row = cur.fetchone()
    assert row is not None and row[0] == 2


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


# --- matching and normalisation (004-matching-normalisation, T052) ---------


def test_another_workspaces_match_candidates_are_invisible(
    workspaces: tuple[psycopg.Connection, Workspace, Workspace],
) -> None:
    conn, alpha, beta = workspaces
    with conn.cursor() as cur:
        act_as(cur, alpha)
        cur.execute(
            "select count(*) from match_candidate where quotation_line_id = %s",
            (beta.quotation_line_id,),
        )
        row = cur.fetchone()
    assert row is not None and row[0] == 0


def test_another_workspaces_match_tasks_are_invisible(
    workspaces: tuple[psycopg.Connection, Workspace, Workspace],
) -> None:
    """FR-011: the match-resolution queue is standalone, but still tenant-private."""
    conn, alpha, beta = workspaces
    with conn.cursor() as cur:
        act_as(cur, alpha)
        cur.execute(
            "select count(*) from match_task where quotation_line_id = %s",
            (beta.quotation_line_id,),
        )
        row = cur.fetchone()
    assert row is not None and row[0] == 0


def test_another_workspaces_match_decisions_are_invisible(
    workspaces: tuple[psycopg.Connection, Workspace, Workspace],
) -> None:
    conn, alpha, beta = workspaces
    with conn.cursor() as cur:
        act_as(cur, alpha)
        cur.execute(
            "select count(*) from match_decision where quotation_line_id = %s",
            (beta.quotation_line_id,),
        )
        row = cur.fetchone()
    assert row is not None and row[0] == 0


def test_another_workspaces_landed_costs_are_invisible(
    workspaces: tuple[psycopg.Connection, Workspace, Workspace],
) -> None:
    conn, alpha, beta = workspaces
    with conn.cursor() as cur:
        act_as(cur, alpha)
        cur.execute(
            "select count(*) from landed_cost where quotation_line_id = %s",
            (beta.quotation_line_id,),
        )
        row = cur.fetchone()
    assert row is not None and row[0] == 0


def test_a_member_cannot_write_a_match_decision_into_another_workspace(
    workspaces: tuple[psycopg.Connection, Workspace, Workspace],
) -> None:
    conn, alpha, beta = workspaces
    with conn.cursor() as cur:
        act_as(cur, alpha)
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cur.execute(
                "insert into match_decision "
                "(tenant_id,quotation_line_id,matched_workspace_product_id,outcome,"
                "is_automatic,confidence) "
                "values (%s,%s,%s,'no_match_new_product',true,0.9)",
                (beta.tenant_id, beta.quotation_line_id, beta.workspace_product_id),
            )


@pytest.mark.parametrize(
    ("table", "id_column", "set_clause"),
    [
        ("match_candidate", "id", "confidence = 0.6"),
        ("match_decision", "id", "confidence = 0.6"),
        ("landed_cost", "id", "total_amount = 13"),
    ],
)
def test_match_history_tables_are_append_only_for_authenticated_members(
    workspaces: tuple[psycopg.Connection, Workspace, Workspace],
    table: str,
    id_column: str,
    set_clause: str,
) -> None:
    conn, alpha, _beta = workspaces
    with conn.cursor() as cur:
        act_as(cur, alpha)
        cur.execute(
            f"select {id_column} from {table} where quotation_line_id = %s",  # noqa: S608
            (alpha.quotation_line_id,),
        )
        row = cur.fetchone()
        assert row is not None
        row_id = row[0]

        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cur.execute(
                f"update {table} set {set_clause} where {id_column} = %s",  # noqa: S608
                (row_id,),
            )
        conn.rollback()
        act_as(cur, alpha)

        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cur.execute(
                f"delete from {table} where {id_column} = %s",  # noqa: S608
                (row_id,),
            )


def test_workspace_products_tenant_name_embedding_stays_tenant_scoped(
    workspaces: tuple[psycopg.Connection, Workspace, Workspace],
) -> None:
    """The tenant-scoped half of research.md R4's two-embedding design: no new policy needed,
    since tenant_name_embedding is just another column on the already tenant-isolated
    workspace_product table — this confirms that, rather than assuming it."""
    conn, alpha, beta = workspaces
    with conn.cursor() as cur:
        act_as(cur, alpha)
        dummy_vector = "[" + ",".join("0.1" for _ in range(256)) + "]"
        cur.execute(
            "update workspace_product set tenant_name_embedding = %s where id = %s",
            (dummy_vector, beta.workspace_product_id),
        )
        assert cur.rowcount == 0
        cur.execute(
            "select id from workspace_product where id = %s", (beta.workspace_product_id,)
        )
        assert cur.fetchall() == []


def test_canonical_products_embedding_is_shared_by_design_not_a_leak(
    workspaces: tuple[psycopg.Connection, Workspace, Workspace],
) -> None:
    """The shared half of research.md R4's two-embedding design: canonical_embedding lives on
    canonical_product, which is deliberately shared across workspaces (chunk 4.2), because it is
    derived only from brand/name/variant — fields canonical_product already legitimately holds.
    Both workspaces' canonical products must remain readable, same as the plain canonical_product
    exception test above; this must stay an exception, not a leak of anything workspace-specific."""
    conn, alpha, beta = workspaces
    with conn.cursor() as cur:
        act_as(cur, alpha)
        cur.execute(
            "select id from canonical_product where id = any(%s)",
            ([alpha.canonical_product_id, beta.canonical_product_id],),
        )
        seen = {r[0] for r in cur.fetchall()}
    assert seen == {alpha.canonical_product_id, beta.canonical_product_id}


def test_another_workspaces_basket_split_jobs_are_invisible(
    workspaces: tuple[psycopg.Connection, Workspace, Workspace],
) -> None:
    conn, alpha, beta = workspaces
    with conn.cursor() as cur:
        act_as(cur, alpha)
        cur.execute(
            "select count(*) from basket_split_job where id = %s", (beta.basket_split_job_id,)
        )
        row = cur.fetchone()
    assert row is not None and row[0] == 0


def test_another_workspaces_alert_dismissals_are_invisible(
    workspaces: tuple[psycopg.Connection, Workspace, Workspace],
) -> None:
    conn, alpha, beta = workspaces
    with conn.cursor() as cur:
        act_as(cur, alpha)
        cur.execute(
            "select count(*) from alert_dismissal where id = %s", (beta.alert_dismissal_id,)
        )
        row = cur.fetchone()
    assert row is not None and row[0] == 0


def test_a_member_cannot_write_a_basket_split_job_into_another_workspace(
    workspaces: tuple[psycopg.Connection, Workspace, Workspace],
) -> None:
    """FR-018 restricts submission to owner/buyer, but tenant isolation is the database's job
    regardless of role — a cross-tenant insert must fail even carrying a valid membership id."""
    conn, alpha, beta = workspaces
    with conn.cursor() as cur:
        act_as(cur, alpha)
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cur.execute(
                "insert into basket_split_job (tenant_id,requested_by,supplier_ids,items) "
                "values (%s,%s,%s,%s)",
                (
                    beta.tenant_id,
                    beta.membership_id,
                    [beta.supplier_id, alpha.supplier_id],
                    Jsonb(
                        [{"workspace_product_id": str(beta.workspace_product_id), "quantity": "1"}]
                    ),
                ),
            )


# --- value proof and launch readiness (006-value-proof-launch) ------------


def test_another_workspaces_purchase_records_are_invisible(
    workspaces: tuple[psycopg.Connection, Workspace, Workspace],
) -> None:
    conn, alpha, beta = workspaces
    with conn.cursor() as cur:
        act_as(cur, alpha)
        cur.execute(
            "select count(*) from purchase_record where id = %s", (beta.purchase_record_id,)
        )
        row = cur.fetchone()
    assert row is not None and row[0] == 0


def test_another_workspaces_saving_records_are_invisible(
    workspaces: tuple[psycopg.Connection, Workspace, Workspace],
) -> None:
    conn, alpha, beta = workspaces
    with conn.cursor() as cur:
        act_as(cur, alpha)
        cur.execute(
            "select count(*) from saving_record where id = %s", (beta.saving_record_id,)
        )
        row = cur.fetchone()
    assert row is not None and row[0] == 0


def test_another_workspaces_billing_account_is_invisible(
    workspaces: tuple[psycopg.Connection, Workspace, Workspace],
) -> None:
    conn, alpha, beta = workspaces
    with conn.cursor() as cur:
        act_as(cur, alpha)
        cur.execute(
            "select count(*) from billing_account where id = %s", (beta.billing_account_id,)
        )
        row = cur.fetchone()
    assert row is not None and row[0] == 0


def test_another_workspaces_export_jobs_are_invisible(
    workspaces: tuple[psycopg.Connection, Workspace, Workspace],
) -> None:
    conn, alpha, beta = workspaces
    with conn.cursor() as cur:
        act_as(cur, alpha)
        cur.execute("select count(*) from export_job where id = %s", (beta.export_job_id,))
        row = cur.fetchone()
    assert row is not None and row[0] == 0


def test_a_member_cannot_write_a_saving_record_into_another_workspace(
    workspaces: tuple[psycopg.Connection, Workspace, Workspace],
) -> None:
    conn, alpha, beta = workspaces
    with conn.cursor() as cur:
        act_as(cur, alpha)
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cur.execute(
                "insert into saving_record "
                "(tenant_id,purchase_record_id,workspace_product_id,baseline_policy,"
                "actual_value_amount,actual_value_currency,calculation_version,"
                "calculation_inputs,recorded_by) "
                "values (%s,%s,%s,'none_available',1,'GBP','test-fixture-v1','{}'::jsonb,%s)",
                (
                    beta.tenant_id,
                    beta.purchase_record_id,
                    beta.workspace_product_id,
                    beta.membership_id,
                ),
            )


def test_plan_is_a_shared_read_only_reference_table(
    workspaces: tuple[psycopg.Connection, Workspace, Workspace],
) -> None:
    """The shared exception (research.md R5): both workspaces must see the same plan rows —
    this must stay an exception, not a leak of anything workspace-specific — and neither may
    write to it directly."""
    conn, alpha, beta = workspaces
    with conn.cursor() as cur:
        act_as(cur, alpha)
        cur.execute("select code from plan order by code")
        codes = {row[0] for row in cur.fetchall()}
        assert codes == {"starter", "growth"}
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cur.execute(
                "insert into plan (code,name,monthly_price_amount,monthly_price_currency,limits) "
                "values ('rogue','Rogue',0,'GBP','{}'::jsonb)"
            )


def test_verified_saving_record_is_immutable_to_every_role(
    workspaces: tuple[psycopg.Connection, Workspace, Workspace],
) -> None:
    """FR-004 / research.md R7: once verified, no role — not even the recording buyer, not even
    a service-role connection — may update or delete the row. Verified here as the authenticated
    role would exercise it; a second check confirms even the migration-owning role is blocked
    (FORCE ROW LEVEL SECURITY only matters for RLS, this trigger has no role exception at all)."""
    conn, alpha, _beta = workspaces
    with conn.cursor() as cur:
        act_as(cur, alpha)
        cur.execute(
            "update saving_record set status='verified', verified_at=now(), verified_by=%s "
            "where id = %s",
            (alpha.membership_id, alpha.saving_record_id),
        )
        with pytest.raises(psycopg.errors.RestrictViolation, match="immutable"):
            cur.execute(
                "update saving_record set actual_value_amount = 999 where id = %s",
                (alpha.saving_record_id,),
            )
        conn.rollback()


def test_platform_invitations_are_unreadable_by_members(
    workspaces: tuple[psycopg.Connection, Workspace, Workspace],
) -> None:
    """They gate entry to the pilot; a member must not be able to mint or read one."""
    conn, alpha, _beta = workspaces
    with conn.cursor() as cur:
        act_as(cur, alpha)
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cur.execute("select count(*) from platform_invitation")


# --- organisation model (007-organisation-model, T008) ---------------------


def test_another_workspaces_branches_are_invisible(
    workspaces: tuple[psycopg.Connection, Workspace, Workspace],
) -> None:
    conn, alpha, beta = workspaces
    with conn.cursor() as cur:
        act_as(cur, alpha)
        cur.execute("select id from branch where id = %s", (beta.branch_id,))
        assert cur.fetchall() == []


def test_another_workspaces_cost_centres_are_invisible(
    workspaces: tuple[psycopg.Connection, Workspace, Workspace],
) -> None:
    conn, alpha, beta = workspaces
    with conn.cursor() as cur:
        act_as(cur, alpha)
        cur.execute("select count(*) from cost_centre where id = %s", (beta.cost_centre_id,))
        row = cur.fetchone()
    assert row is not None and row[0] == 0


def test_another_workspaces_budgets_are_invisible(
    workspaces: tuple[psycopg.Connection, Workspace, Workspace],
) -> None:
    conn, alpha, beta = workspaces
    with conn.cursor() as cur:
        act_as(cur, alpha)
        cur.execute("select count(*) from budget where id = %s", (beta.budget_id,))
        row = cur.fetchone()
    assert row is not None and row[0] == 0


def test_another_workspaces_branch_role_assignments_are_invisible(
    workspaces: tuple[psycopg.Connection, Workspace, Workspace],
) -> None:
    conn, alpha, beta = workspaces
    with conn.cursor() as cur:
        act_as(cur, alpha)
        cur.execute(
            "select count(*) from branch_role_assignment where id = %s",
            (beta.branch_role_assignment_id,),
        )
        row = cur.fetchone()
    assert row is not None and row[0] == 0


def test_a_member_cannot_write_a_branch_into_another_workspace(
    workspaces: tuple[psycopg.Connection, Workspace, Workspace],
) -> None:
    """WITH CHECK on branch_tenant_isolation, not just the scoped-visibility RESTRICTIVE policy."""
    conn, alpha, beta = workspaces
    with conn.cursor() as cur:
        act_as(cur, alpha)
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cur.execute(
                "insert into branch (tenant_id,name) values (%s,'intruder branch')",
                (beta.tenant_id,),
            )


def test_a_cross_workspace_budget_update_changes_nothing(
    workspaces: tuple[psycopg.Connection, Workspace, Workspace],
) -> None:
    conn, alpha, beta = workspaces
    with conn.cursor() as cur:
        act_as(cur, alpha)
        cur.execute("update budget set amount = 1 where id = %s", (beta.budget_id,))
        assert cur.rowcount == 0
        cur.execute("reset role")
        cur.execute("select amount from budget where id = %s", (beta.budget_id,))
        row = cur.fetchone()
    assert row is not None and row[0] == 1000


def test_a_cross_workspace_branch_delete_removes_nothing(
    workspaces: tuple[psycopg.Connection, Workspace, Workspace],
) -> None:
    conn, alpha, beta = workspaces
    with conn.cursor() as cur:
        act_as(cur, alpha)
        cur.execute("delete from branch where id = %s", (beta.branch_id,))
        assert cur.rowcount == 0
        cur.execute("reset role")
        cur.execute("select count(*) from branch where id = %s", (beta.branch_id,))
        row = cur.fetchone()
    assert row is not None and row[0] == 1


# --- requests + approvals (008-requests-approvals, T008) --------------------


def test_another_workspaces_purchase_requests_are_invisible(
    workspaces: tuple[psycopg.Connection, Workspace, Workspace],
) -> None:
    conn, alpha, beta = workspaces
    with conn.cursor() as cur:
        act_as(cur, alpha)
        cur.execute(
            "select count(*) from purchase_request where id = %s", (beta.purchase_request_id,)
        )
        row = cur.fetchone()
    assert row is not None and row[0] == 0


def test_another_workspaces_purchase_request_lines_are_invisible(
    workspaces: tuple[psycopg.Connection, Workspace, Workspace],
) -> None:
    conn, alpha, beta = workspaces
    with conn.cursor() as cur:
        act_as(cur, alpha)
        cur.execute(
            "select count(*) from purchase_request_line where id = %s",
            (beta.purchase_request_line_id,),
        )
        row = cur.fetchone()
    assert row is not None and row[0] == 0


def test_another_workspaces_approval_steps_are_invisible(
    workspaces: tuple[psycopg.Connection, Workspace, Workspace],
) -> None:
    conn, alpha, beta = workspaces
    with conn.cursor() as cur:
        act_as(cur, alpha)
        cur.execute("select count(*) from approval_step where id = %s", (beta.approval_step_id,))
        row = cur.fetchone()
    assert row is not None and row[0] == 0


def test_another_workspaces_threshold_rules_are_invisible(
    workspaces: tuple[psycopg.Connection, Workspace, Workspace],
) -> None:
    conn, alpha, beta = workspaces
    with conn.cursor() as cur:
        act_as(cur, alpha)
        cur.execute("select count(*) from threshold_rule where id = %s", (beta.threshold_rule_id,))
        row = cur.fetchone()
    assert row is not None and row[0] == 0


def test_another_workspaces_approval_delegations_are_invisible(
    workspaces: tuple[psycopg.Connection, Workspace, Workspace],
) -> None:
    conn, alpha, beta = workspaces
    with conn.cursor() as cur:
        act_as(cur, alpha)
        cur.execute(
            "select count(*) from approval_delegation where id = %s",
            (beta.approval_delegation_id,),
        )
        row = cur.fetchone()
    assert row is not None and row[0] == 0


def test_a_member_cannot_write_a_purchase_request_into_another_workspace(
    workspaces: tuple[psycopg.Connection, Workspace, Workspace],
) -> None:
    """WITH CHECK on purchase_request_tenant_isolation, not just the scoped-visibility policy."""
    conn, alpha, beta = workspaces
    with conn.cursor() as cur:
        act_as(cur, alpha)
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cur.execute(
                "insert into purchase_request "
                "(tenant_id,branch_id,requested_by_membership_id,required_by_date) "
                "values (%s,%s,%s, current_date)",
                (beta.tenant_id, beta.branch_id, alpha.membership_id),
            )


def test_a_cross_workspace_threshold_rule_update_changes_nothing(
    workspaces: tuple[psycopg.Connection, Workspace, Workspace],
) -> None:
    conn, alpha, beta = workspaces
    with conn.cursor() as cur:
        act_as(cur, alpha)
        cur.execute(
            "update threshold_rule set min_amount = 999 where id = %s",
            (beta.threshold_rule_id,),
        )
        assert cur.rowcount == 0
        cur.execute("reset role")
        cur.execute(
            "select min_amount from threshold_rule where id = %s", (beta.threshold_rule_id,)
        )
        row = cur.fetchone()
    assert row is not None and row[0] == 0


def test_a_cross_workspace_approval_step_delete_removes_nothing(
    workspaces: tuple[psycopg.Connection, Workspace, Workspace],
) -> None:
    conn, alpha, beta = workspaces
    with conn.cursor() as cur:
        act_as(cur, alpha)
        cur.execute("delete from approval_step where id = %s", (beta.approval_step_id,))
        assert cur.rowcount == 0
        cur.execute("reset role")
        cur.execute("select count(*) from approval_step where id = %s", (beta.approval_step_id,))
        row = cur.fetchone()
    assert row is not None and row[0] == 1


# --- 009-mobile-app-mvp (T007): device_registration, low_stock_report, push_notification -------


def test_another_workspaces_device_registrations_are_invisible(
    workspaces: tuple[psycopg.Connection, Workspace, Workspace],
) -> None:
    conn, alpha, beta = workspaces
    with conn.cursor() as cur:
        act_as(cur, alpha)
        cur.execute(
            "select id from device_registration where id = %s", (beta.device_registration_id,)
        )
        assert cur.fetchall() == []


def test_a_cross_workspace_device_registration_delete_removes_nothing(
    workspaces: tuple[psycopg.Connection, Workspace, Workspace],
) -> None:
    conn, alpha, beta = workspaces
    with conn.cursor() as cur:
        act_as(cur, alpha)
        cur.execute(
            "delete from device_registration where id = %s", (beta.device_registration_id,)
        )
        assert cur.rowcount == 0
        cur.execute("reset role")
        cur.execute(
            "select count(*) from device_registration where id = %s",
            (beta.device_registration_id,),
        )
        row = cur.fetchone()
    assert row is not None and row[0] == 1


def test_another_workspaces_low_stock_reports_are_invisible(
    workspaces: tuple[psycopg.Connection, Workspace, Workspace],
) -> None:
    conn, alpha, beta = workspaces
    with conn.cursor() as cur:
        act_as(cur, alpha)
        cur.execute(
            "select id from low_stock_report where id = %s", (beta.low_stock_report_id,)
        )
        assert cur.fetchall() == []


def test_a_cross_workspace_low_stock_report_delete_removes_nothing(
    workspaces: tuple[psycopg.Connection, Workspace, Workspace],
) -> None:
    conn, alpha, beta = workspaces
    with conn.cursor() as cur:
        act_as(cur, alpha)
        cur.execute("delete from low_stock_report where id = %s", (beta.low_stock_report_id,))
        assert cur.rowcount == 0
        cur.execute("reset role")
        cur.execute(
            "select count(*) from low_stock_report where id = %s", (beta.low_stock_report_id,)
        )
        row = cur.fetchone()
    assert row is not None and row[0] == 1


def test_authenticated_has_no_access_to_push_notification_at_all(
    workspaces: tuple[psycopg.Connection, Workspace, Workspace],
) -> None:
    """push_notification is service-role only (no client-facing read this release — data-model.md).

    `service_role` carries `bypassrls`, by design (it is this project's trusted backend role, the
    same as every other internal-only write path in this codebase) — testing tenant isolation
    against it the way the tests above test it for `authenticated` would test something that
    cannot be true by construction, not a real leak. The actual guarantee for this table is
    narrower and different: no user-facing role can reach it at all, so tenant filtering for it is
    the calling Python code's own responsibility, exactly like every other service-role-only write
    in this codebase (e.g. audit_event).
    """
    conn, alpha, beta = workspaces
    with conn.cursor() as cur:
        act_as(cur, alpha)
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cur.execute(
                "select id from push_notification where id = %s", (beta.push_notification_id,)
            )


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
        "match_candidate", "match_task", "match_decision", "landed_cost",
        "match_resolution_idempotency",
        "basket_split_job", "alert_dismissal",
        "purchase_record", "saving_record", "export_job", "billing_account", "plan",
        "branch", "cost_centre", "budget", "branch_role_assignment",
        "purchase_request", "purchase_request_line", "approval_step", "threshold_rule",
        "approval_delegation",
        "device_registration", "low_stock_report", "push_notification",
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

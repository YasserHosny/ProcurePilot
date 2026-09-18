"""Cross-tenant and cross-branch isolation for R2.5 reporting — task T008 (FR-019, FR-004).

Three layers, matching how the surfaces arrive:

1. Database-level proofs over the R2.5 migrations — report_schedule and digest_subscription
   RLS, the widened export_job, the per-period idempotency unique index, and the four
   tenant-pinned reader functions. These run now: the migrations are on this branch.

2. Router-level cross-read proofs against the real reports router. The import is deferred
   into the test body, so until the backend lane lands `modules/reports` (T011/T012) these
   are red for the right reason — the module does not exist — and they go green later in
   this wave. Each carries a positive control (the owning member CAN read the row) so a
   merely missing route can never satisfy them: a missing route 404s, and 404 is exactly
   what the cross-tenant case must prove, so only the pair of assertions pins the truth.

3. The scheduler's own claim-hardening tests (Wave 17, T016) are written against the real
   module in that lane; what T008 owns at the storage layer — the per-period idempotency
   unique index every scheduler behaviour leans on — is proven here now. The rendered digest
   view's branch proof lands with T024; the storage-level guarantee it will rest on (the
   readers honour the subscription's branch filter) is proven here now.

Worker hardening that is testable today is tested today: the export worker's payload is
already refused when it names the wrong tenant (FR-007 outcome), and a purged (expired)
artifact already resolves as not found on download (FR-005/FR-014).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import psycopg
import pytest
from fastapi import FastAPI
from psycopg.types.json import Jsonb

from integration.catalogue_helpers import (
    TEST_DATABASE_URL,
    Workspace,
    act_as,
    make_workspace,
    make_workspace_product,
    reset_role,
)
from integration.quotation_helpers import (
    ensure_quotation_reference_data,
    make_document,
    make_line,
    make_quotation,
    make_supplier,
)
from integration.smart_compare_helpers import (
    cleanup_workspace,
    member_from_workspace,
    settings_for_test_db,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is not set; needs a Postgres with the migrations applied",
)

PERIOD_START = "2026-09-07"


@dataclass(frozen=True)
class ReportingTenant:
    """One tenant and the R2.5 marker rows only that tenant should ever see."""

    workspace: Workspace
    branch_member: Workspace
    schedule_id: UUID
    subscription_id: UUID
    scheduled_job_id: UUID
    branch_id: UUID
    other_branch_id: UUID
    purchase_id: UUID
    saving_id: UUID
    landed_cost_id: UUID
    branch_a_job_id: UUID
    branch_b_job_id: UUID


def make_reporting_tenant(cur: psycopg.Cursor, label: str) -> ReportingTenant:
    # Sequential construction on one cursor: the previous tenant's helpers leave the
    # connection acting as `authenticated`, and ensure_quotation_reference_data would
    # faithfully restore that role — so reset to postgres explicitly, every time.
    reset_role(cur)
    ensure_quotation_reference_data(cur)
    workspace = make_workspace(cur, label)

    # The branch-scoped member is created FIRST, while the connection still holds the
    # postgres role: auth.users is owner-only and the helpers below leave the connection
    # acting as `authenticated`.
    branch_user_id, branch_membership_id = uuid4(), uuid4()
    cur.execute(
        "insert into auth.users (id,email) values (%s,%s)",
        (branch_user_id, f"{label}-branch@example.test"),
    )
    cur.execute(
        """
        insert into membership (id,tenant_id,user_id,email,role,is_active_workspace)
        values (%s, %s, %s, %s, 'branch_manager', false)
        """,
        (branch_membership_id, workspace.tenant_id, branch_user_id, f"{label}-branch@example.test"),
    )

    supplier_id = make_supplier(cur, workspace, name=f"{label} Reporting Supplier")
    product_id = make_workspace_product(cur, workspace, name=f"{label} Reporting Product")

    # Offer lineage: document -> reviewed quotation -> line -> match decision -> landed cost
    # with a validity window inside the reader horizon.
    document_id = make_document(cur, workspace)
    quotation_id = make_quotation(
        cur,
        workspace,
        document_id=document_id,
        supplier_id=supplier_id,
        status="reviewed",
        arithmetic_status="reconciled",
    )
    line_id = make_line(cur, workspace, quotation_id)
    act_as(cur, workspace)
    match_decision_id, landed_cost_id = uuid4(), uuid4()
    cur.execute(
        """
        insert into match_decision
          (id, tenant_id, quotation_line_id, matched_workspace_product_id,
           outcome, is_automatic, confidence)
        values (%s, %s, %s, %s, 'no_match_new_product', true, 0.95)
        """,
        (match_decision_id, workspace.tenant_id, line_id, product_id),
    )
    cur.execute(
        """
        insert into landed_cost
          (id, tenant_id, quotation_line_id, match_decision_id, quantity,
           normalised_base_quantity, base_unit, unit_price_amount, unit_price_currency,
           vat_amount, vat_currency, delivery_fee_amount, delivery_fee_currency,
           discount_amount, discount_currency, other_charges_amount, other_charges_currency,
           total_amount, total_currency, raw_inputs, rule_version, valid_from, valid_to)
        values (%s, %s, %s, %s, 10, 30, 'kg', 10, 'GBP',
                2, 'GBP', 0, 'GBP', 0, 'GBP', 0, 'GBP',
                12, 'GBP', '{}'::jsonb, 'landed-cost-v1',
                now() - interval '2 days', now() + interval '3 days')
        """,
        (landed_cost_id, workspace.tenant_id, line_id, match_decision_id),
    )

    # Branches and the attribution chain: purchase -> landed_cost -> request line -> request
    # -> branch. The purchase is attributed to branch_id only, never other_branch_id.
    branch_id, other_branch_id, cost_centre_id = uuid4(), uuid4(), uuid4()
    purchase_id, saving_id, purchase_request_id, request_line_id = (
        uuid4(),
        uuid4(),
        uuid4(),
        uuid4(),
    )
    yesterday = datetime.now(UTC) - timedelta(days=1)
    cur.execute(
        "insert into branch (id,tenant_id,name,region) values (%s,%s,%s,'GB')",
        (branch_id, workspace.tenant_id, f"{label} Branch A"),
    )
    cur.execute(
        "insert into branch (id,tenant_id,name,region) values (%s,%s,%s,'GB')",
        (other_branch_id, workspace.tenant_id, f"{label} Branch B"),
    )
    cur.execute(
        "insert into cost_centre (id,tenant_id,name,code,branch_id) values (%s,%s,%s,%s,%s)",
        (cost_centre_id, workspace.tenant_id, f"{label} CC", f"{label}-cc", branch_id),
    )
    cur.execute(
        """
        insert into purchase_request
          (id, tenant_id, branch_id, cost_centre_id, requested_by_membership_id,
           required_by_date)
        values (%s, %s, %s, %s, %s, current_date + interval '7 days')
        """,
        (
            purchase_request_id,
            workspace.tenant_id,
            branch_id,
            cost_centre_id,
            workspace.membership_id,
        ),
    )
    cur.execute(
        """
        insert into purchase_request_line
          (id, tenant_id, purchase_request_id, workspace_product_id, quantity,
           estimated_unit_price_amount, estimated_unit_price_currency,
           estimated_unit_price_source_landed_cost_id)
        values (%s, %s, %s, %s, 10, 10, 'GBP', %s)
        """,
        (
            request_line_id,
            workspace.tenant_id,
            purchase_request_id,
            product_id,
            landed_cost_id,
        ),
    )
    cur.execute(
        """
        insert into purchase_record
          (id, tenant_id, workspace_product_id, supplier_id, landed_cost_id, recorded_by,
           quantity, base_unit, unit_price_amount, unit_price_currency,
           total_paid_amount, total_paid_currency, delivery_result, recorded_at)
        values (%s, %s, %s, %s, %s, %s, 10, 'kg', 10, 'GBP', 100, 'GBP', 'delivered', %s)
        """,
        (
            purchase_id,
            workspace.tenant_id,
            product_id,
            supplier_id,
            landed_cost_id,
            workspace.membership_id,
            yesterday,
        ),
    )
    cur.execute(
        """
        insert into saving_record
          (id, tenant_id, purchase_record_id, workspace_product_id, supplier_id, status,
           baseline_policy, baseline_unit_price_amount, baseline_unit_price_currency,
           baseline_value_amount, baseline_value_currency, actual_value_amount,
           actual_value_currency, delta_amount, delta_currency, calculation_version,
           calculation_inputs, recorded_by, recorded_at, verified_by, verified_at)
        values (%s, %s, %s, %s, %s, 'verified', 'last_paid', 12, 'GBP',
                120, 'GBP', 100, 'GBP', 20, 'GBP', 'isolation-fixture-v1',
                '{}'::jsonb, %s, %s, %s, %s)
        """,
        (
            saving_id,
            workspace.tenant_id,
            purchase_id,
            product_id,
            supplier_id,
            workspace.membership_id,
            yesterday,
            workspace.membership_id,
            yesterday,
        ),
    )

    # The R2.5 marker rows themselves: one schedule, one subscription, one scheduled
    # artifact (exercising every widened export_job column), and two branch-filtered
    # completed artifacts for the FR-004 listing proof.
    schedule_id, subscription_id, scheduled_job_id = uuid4(), uuid4(), uuid4()
    cur.execute(
        """
        insert into report_schedule
          (id, tenant_id, created_by_membership_id, kind, format, filters, filters_digest,
           weekday, status, next_run_at, rule_version)
        values (%s, %s, %s, 'savings_ledger', 'xlsx', %s, %s, 0, 'active',
                now() - interval '1 hour', 'isolation-fixture-v1')
        """,
        (
            schedule_id,
            workspace.tenant_id,
            workspace.membership_id,
            Jsonb({"supplier_id": None, "branch_id": None}),
            f"{label}-schedule-digest",
        ),
    )
    cur.execute(
        """
        insert into digest_subscription
          (id, tenant_id, membership_id, kind, locale, filters, filters_digest, channel,
           status, next_run_at)
        values (%s, %s, %s, 'weekly_digest', 'en', %s, %s, 'in_app', 'active',
                now() - interval '1 hour')
        """,
        (
            subscription_id,
            workspace.tenant_id,
            workspace.membership_id,
            Jsonb({"branch_id": None}),
            f"{label}-digest-filters",
        ),
    )
    cur.execute(
        """
        insert into export_job
          (id, tenant_id, requested_by, kind, format, filters, status, schedule_id, locale,
           rule_version, schedule_snapshot, storage_bucket, storage_path, row_count,
           completed_at)
        values (%s, %s, %s, 'savings_ledger', 'xlsx', %s, 'completed', %s, 'ar',
                'isolation-fixture-v1', %s, 'exports', %s, 1, now())
        """,
        (
            scheduled_job_id,
            workspace.tenant_id,
            workspace.membership_id,
            Jsonb({"period_start": PERIOD_START, "supplier_id": None, "branch_id": None}),
            schedule_id,
            Jsonb({"kind": "savings_ledger", "format": "xlsx"}),
            f"{workspace.tenant_id}/reports/{scheduled_job_id}.xlsx",
        ),
    )
    branch_a_job_id, branch_b_job_id = uuid4(), uuid4()
    for job_id, branch in (
        (branch_a_job_id, branch_id),
        (branch_b_job_id, other_branch_id),
    ):
        cur.execute(
            """
            insert into export_job
              (id, tenant_id, requested_by, kind, format, filters, status,
               storage_bucket, storage_path, row_count, completed_at)
            values (%s, %s, %s, 'spend_by_supplier', 'csv', %s, 'completed',
                    'exports', %s, 1, now())
            """,
            (
                job_id,
                workspace.tenant_id,
                workspace.membership_id,
                Jsonb(
                    {
                        "period_start": PERIOD_START,
                        "supplier_id": None,
                        "branch_id": str(branch),
                    }
                ),
                f"{workspace.tenant_id}/reports/{job_id}.csv",
            ),
        )

    # The branch assignment itself: branch_manager scoped to branch A only. Same tenant,
    # different person — the within-tenant FR-004 case.
    cur.execute(
        "insert into branch_role_assignment (id,tenant_id,membership_id,branch_id) "
        "values (%s,%s,%s,%s)",
        (uuid4(), workspace.tenant_id, branch_membership_id, branch_id),
    )

    return ReportingTenant(
        workspace=workspace,
        branch_member=Workspace(
            tenant_id=workspace.tenant_id,
            user_id=branch_user_id,
            membership_id=branch_membership_id,
            role="branch_manager",
            label=f"{label}-branch",
        ),
        schedule_id=schedule_id,
        subscription_id=subscription_id,
        scheduled_job_id=scheduled_job_id,
        branch_id=branch_id,
        other_branch_id=other_branch_id,
        purchase_id=purchase_id,
        saving_id=saving_id,
        landed_cost_id=landed_cost_id,
        branch_a_job_id=branch_a_job_id,
        branch_b_job_id=branch_b_job_id,
    )


@pytest.fixture
def reporting_tenants() -> Iterator[tuple[ReportingTenant, ReportingTenant]]:
    """Two unrelated businesses with marker reporting rows, committed for router reads."""
    with psycopg.connect(TEST_DATABASE_URL or "") as conn:
        with conn.cursor() as cur:
            alpha = make_reporting_tenant(cur, "r25-alpha")
            beta = make_reporting_tenant(cur, "r25-beta")
        conn.commit()
    try:
        yield alpha, beta
    finally:
        # cleanup_workspace(alpha.workspace) deletes the tenant (cascading away the branch
        # member's membership row) and that workspace's own auth.users row — but never the
        # SEPARATE auth.users row make_reporting_tenant() inserts directly for the branch
        # member (branch_user_id), which has no FK path back to tenant. Left orphaned with a
        # fixed, non-random email, this leaks across test runs: the real Supabase auth.users
        # schema enforces a unique index on email (unlike this test suite's own lightweight
        # stand-in), so the next test to build a reporting tenant fails outright on a duplicate
        # key. alpha.branch_member is already a full Workspace for exactly this reason — reuse
        # the same cleanup_workspace call on it; it's a no-op on the (already-deleted) tenant
        # and just deletes the one auth.users row that would otherwise leak (issue #21).
        cleanup_workspace(alpha.workspace)
        cleanup_workspace(alpha.branch_member)
        cleanup_workspace(beta.workspace)
        cleanup_workspace(beta.branch_member)


# --- layer 1: RLS on the new tables -----------------------------------------


def test_another_workspaces_schedules_are_invisible(
    reporting_tenants: tuple[ReportingTenant, ReportingTenant],
) -> None:
    alpha, beta = reporting_tenants
    with psycopg.connect(TEST_DATABASE_URL or "") as conn:
        with conn.cursor() as cur:
            act_as(cur, alpha.workspace)
            cur.execute("select id from report_schedule")
            ids = {row[0] for row in cur.fetchall()}
    assert alpha.schedule_id in ids
    assert beta.schedule_id not in ids


def test_another_workspaces_subscriptions_are_invisible(
    reporting_tenants: tuple[ReportingTenant, ReportingTenant],
) -> None:
    alpha, beta = reporting_tenants
    with psycopg.connect(TEST_DATABASE_URL or "") as conn:
        with conn.cursor() as cur:
            act_as(cur, alpha.workspace)
            cur.execute("select id from digest_subscription")
            ids = {row[0] for row in cur.fetchall()}
    assert alpha.subscription_id in ids
    assert beta.subscription_id not in ids


def test_another_workspaces_artifacts_are_invisible(
    reporting_tenants: tuple[ReportingTenant, ReportingTenant],
) -> None:
    alpha, beta = reporting_tenants
    with psycopg.connect(TEST_DATABASE_URL or "") as conn:
        with conn.cursor() as cur:
            act_as(cur, alpha.workspace)
            cur.execute("select id from export_job")
            ids = {row[0] for row in cur.fetchall()}
    assert alpha.scheduled_job_id in ids
    assert beta.scheduled_job_id not in ids


def test_a_member_cannot_write_another_workspaces_schedule(
    reporting_tenants: tuple[ReportingTenant, ReportingTenant],
) -> None:
    """WITH CHECK, not just USING — a write-then-cannot-read row must never be creatable."""
    alpha, beta = reporting_tenants
    with psycopg.connect(TEST_DATABASE_URL or "") as conn:
        with conn.cursor() as cur:
            act_as(cur, alpha.workspace)
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                cur.execute(
                    """
                    insert into report_schedule
                      (tenant_id, created_by_membership_id, kind, format, filters,
                       filters_digest, weekday, next_run_at)
                    values (%s, %s, 'savings_ledger', 'xlsx', '{}'::jsonb,
                            'intruder-digest', 0, now())
                    """,
                    (beta.workspace.tenant_id, alpha.workspace.membership_id),
                )


def test_a_member_cannot_write_another_workspaces_subscription(
    reporting_tenants: tuple[ReportingTenant, ReportingTenant],
) -> None:
    alpha, beta = reporting_tenants
    with psycopg.connect(TEST_DATABASE_URL or "") as conn:
        with conn.cursor() as cur:
            act_as(cur, alpha.workspace)
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                cur.execute(
                    """
                    insert into digest_subscription
                      (tenant_id, membership_id, filters, filters_digest, next_run_at)
                    values (%s, %s, '{}'::jsonb, 'intruder-digest', now())
                    """,
                    (beta.workspace.tenant_id, beta.workspace.membership_id),
                )


def test_duplicate_scheduled_artifact_for_the_same_period_is_refused(
    reporting_tenants: tuple[ReportingTenant, ReportingTenant],
) -> None:
    """FR-006 at the storage layer: the per-period unique partial index is the guarantee the
    scheduler (T016) will lean on — a replayed or raced tick cannot insert a second artifact
    for the same schedule and period, whatever the worker code does."""
    alpha, _beta = reporting_tenants
    with psycopg.connect(TEST_DATABASE_URL or "") as conn:
        with conn.cursor() as cur:
            with pytest.raises(psycopg.errors.UniqueViolation):
                cur.execute(
                    """
                    insert into export_job
                      (tenant_id, requested_by, kind, format, filters, status, schedule_id)
                    values (%s, %s, 'savings_ledger', 'xlsx', %s, 'queued', %s)
                    """,
                    (
                        alpha.workspace.tenant_id,
                        alpha.workspace.membership_id,
                        Jsonb(
                            {
                                "period_start": PERIOD_START,
                                "supplier_id": None,
                                "branch_id": None,
                            }
                        ),
                        alpha.schedule_id,
                    ),
                )


# --- layer 1: the tenant-pinned reader functions -----------------------------


def test_savings_reader_pinned_to_tenant_a_excludes_tenant_b(
    reporting_tenants: tuple[ReportingTenant, ReportingTenant],
) -> None:
    alpha, beta = reporting_tenants
    with psycopg.connect(TEST_DATABASE_URL or "") as conn:
        with conn.cursor() as cur:
            cur.execute(
                "select saving_id from reporting_savings_for_period(%s, %s, %s, null, null)",
                (alpha.workspace.tenant_id, "2026-01-01", "2026-12-31"),
            )
            ids = {row[0] for row in cur.fetchall()}
    assert alpha.saving_id in ids
    assert beta.saving_id not in ids


def test_purchases_reader_pinned_to_tenant_a_excludes_tenant_b(
    reporting_tenants: tuple[ReportingTenant, ReportingTenant],
) -> None:
    alpha, beta = reporting_tenants
    with psycopg.connect(TEST_DATABASE_URL or "") as conn:
        with conn.cursor() as cur:
            cur.execute(
                "select purchase_record_id from reporting_purchases_for_period"
                "(%s, %s, %s, null, null)",
                (alpha.workspace.tenant_id, "2026-01-01", "2026-12-31"),
            )
            ids = {row[0] for row in cur.fetchall()}
    assert alpha.purchase_id in ids
    assert beta.purchase_id not in ids


def test_alert_snapshot_reader_pinned_to_tenant_a_excludes_tenant_b(
    reporting_tenants: tuple[ReportingTenant, ReportingTenant],
) -> None:
    """The alert snapshot returns SOURCE rows (the landed-cost lineage), so the marker is the
    landed_cost row itself — the exact input the Wave 17 Python conditions will consume."""
    alpha, beta = reporting_tenants
    with psycopg.connect(TEST_DATABASE_URL or "") as conn:
        with conn.cursor() as cur:
            cur.execute(
                "select landed_cost_id from reporting_alert_snapshot(%s, %s, %s, null)",
                (alpha.workspace.tenant_id, "2026-01-01", "2026-12-31"),
            )
            ids = {row[0] for row in cur.fetchall()}
    assert alpha.landed_cost_id in ids
    assert beta.landed_cost_id not in ids


def test_validity_expiring_reader_pinned_to_tenant_a_excludes_tenant_b(
    reporting_tenants: tuple[ReportingTenant, ReportingTenant],
) -> None:
    alpha, beta = reporting_tenants
    now = datetime.now(UTC)
    with psycopg.connect(TEST_DATABASE_URL or "") as conn:
        with conn.cursor() as cur:
            cur.execute(
                "select landed_cost_id from reporting_validity_expiring(%s, %s, 7, null)",
                (alpha.workspace.tenant_id, now),
            )
            ids = {row[0] for row in cur.fetchall()}
    assert alpha.landed_cost_id in ids
    assert beta.landed_cost_id not in ids


def test_branch_guard_raises_for_another_tenants_branch(
    reporting_tenants: tuple[ReportingTenant, ReportingTenant],
) -> None:
    """The readers' shared guard: a branch that is not an active branch of the pinned tenant
    raises instead of being treated as "no filter" — a wrong-tenant branch id must never
    silently widen a report."""
    alpha, beta = reporting_tenants
    with psycopg.connect(TEST_DATABASE_URL or "") as conn:
        with conn.cursor() as cur:
            # The guard raises with errcode 22023 (invalid_parameter_value) — the code is
            # deliberate, so the test pins it rather than accepting any raise.
            with pytest.raises(psycopg.errors.InvalidParameterValue):
                cur.execute(
                    "select reporting_assert_branch_visible(%s, %s)",
                    (alpha.workspace.tenant_id, beta.branch_id),
                )


def test_branch_filter_excludes_other_branch_rows_in_readers(
    reporting_tenants: tuple[ReportingTenant, ReportingTenant],
) -> None:
    """The branch-A/branch-B reader case: alpha's purchase is attributed (via its request
    lineage) to branch A only, so a branch-B filter sees nothing — and an unattributed row
    would be excluded under either filter rather than guessed into a branch."""
    alpha, _beta = reporting_tenants
    with psycopg.connect(TEST_DATABASE_URL or "") as conn:
        with conn.cursor() as cur:
            cur.execute(
                "select count(*) from reporting_savings_for_period(%s, %s, %s, null, %s)",
                (alpha.workspace.tenant_id, "2026-01-01", "2026-12-31", alpha.branch_id),
            )
            own_branch_count = cur.fetchone()[0]
            cur.execute(
                "select count(*) from reporting_savings_for_period(%s, %s, %s, null, %s)",
                (
                    alpha.workspace.tenant_id,
                    "2026-01-01",
                    "2026-12-31",
                    alpha.other_branch_id,
                ),
            )
            other_branch_count = cur.fetchone()[0]
    assert own_branch_count == 1
    assert other_branch_count == 0


def test_digest_content_rests_on_branch_filtered_readers(
    reporting_tenants: tuple[ReportingTenant, ReportingTenant],
) -> None:
    """Storage-level guarantee the Wave 17 digest render (T024) will rest on: a subscription
    filtered to branch B can only be rendered from branch-B reader rows. The rendered-view
    proof itself lands with T024."""
    alpha, _beta = reporting_tenants
    with psycopg.connect(TEST_DATABASE_URL or "") as conn:
        with conn.cursor() as cur:
            cur.execute(
                "select count(*) from reporting_purchases_for_period(%s, %s, %s, null, %s)",
                (
                    alpha.workspace.tenant_id,
                    "2026-01-01",
                    "2026-12-31",
                    alpha.other_branch_id,
                ),
            )
            count = cur.fetchone()[0]
    assert count == 0


# --- layer 1: worker and purge hardening, testable today ---------------------


def test_export_worker_refuses_a_tenant_job_mismatch_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FR-007 outcome: the queue payload is an untrusted hint — a payload naming beta's
    tenant against alpha's job is refused, and no artifact appears for either tenant. Today
    the refusal rides on RLS (the update under beta's claims finds no row); T017 replaces
    the mechanism with an explicit re-derive-and-refuse while keeping this outcome."""
    from procurepilot_api.workers import export_worker

    settings = settings_for_test_db(monkeypatch)
    from integration.smart_compare_helpers import committed_smart_context

    with committed_smart_context("r25-mismatch-alpha") as alpha:
        with committed_smart_context("r25-mismatch-beta") as beta:
            from procurepilot_api.modules.exports import service as export_service_module
            from procurepilot_api.modules.exports.service import ExportService

            monkeypatch.setattr(
                export_service_module,
                "_enqueue_export_job",
                lambda *_args, **_kwargs: None,
            )

            class FakeAuditWriter:
                def record(self, event: object, bearer_token: str | None = None) -> None:
                    return None

            monkeypatch.setattr(
                export_service_module, "get_audit_writer", lambda: FakeAuditWriter()
            )
            from integration.value_proof_helpers import export_request

            job = ExportService(settings).create_job(member=alpha.member, payload=export_request())
            monkeypatch.setattr(export_worker, "get_settings", lambda: settings)

            with pytest.raises(RuntimeError):
                export_worker.process_export_job(
                    {"job_id": str(job.id), "tenant_id": str(beta.workspace.tenant_id)}
                )

            with psycopg.connect(
                TEST_DATABASE_URL or "", row_factory=psycopg.rows.dict_row
            ) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "select status, storage_path from export_job where id = %s", (job.id,)
                    )
                    row = cur.fetchone()
    assert row["status"] == "queued"
    assert row["storage_path"] is None


def test_purged_artifact_download_returns_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FR-005/FR-014: once retention purges an artifact (status flipped to expired, storage
    cleared), a previously issued link resolves as not found — the download endpoint refuses
    anything that is not a completed artifact with storage."""
    settings = settings_for_test_db(monkeypatch)
    from procurepilot_api.errors import NotFoundError
    from procurepilot_api.modules.exports.service import ExportService

    with psycopg.connect(TEST_DATABASE_URL or "") as conn:
        with conn.cursor() as cur:
            alpha = make_workspace(cur, "r25-purged")
            job_id = uuid4()
            cur.execute(
                """
                insert into export_job
                  (id, tenant_id, requested_by, kind, format, filters, status,
                   storage_bucket, storage_path, download_url, row_count, completed_at)
                values (%s, %s, %s, 'savings_ledger', 'xlsx', '{}'::jsonb, 'expired',
                        null, null, null, 5, now())
                """,
                (job_id, alpha.tenant_id, alpha.membership_id),
            )
        conn.commit()
    try:
        with pytest.raises(NotFoundError):
            ExportService(settings).create_download_url(
                member=member_from_workspace(alpha),
                job_id=job_id,
                bearer_token="caller-token",
            )
    finally:
        cleanup_workspace(alpha)


# --- layer 2: router-level cross-reads (red until T012 lands) ----------------


def _reports_app(monkeypatch: pytest.MonkeyPatch, member: object) -> FastAPI:
    """The real application with the real reports router, authenticated as `member`.

    Deferred import: until modules/reports exists (T012) this raises ModuleNotFoundError
    inside the test — red for the right reason, green the moment the lane lands."""
    from procurepilot_api.deps import current_member
    from procurepilot_api.main import create_app

    app = create_app(settings_for_test_db(monkeypatch))
    app.dependency_overrides[current_member] = lambda: member
    return app


def test_cross_tenant_schedule_read_returns_not_found(
    monkeypatch: pytest.MonkeyPatch,
    reporting_tenants: tuple[ReportingTenant, ReportingTenant],
) -> None:
    from fastapi.testclient import TestClient

    alpha, beta = reporting_tenants

    owner_client = TestClient(
        _reports_app(monkeypatch, member_from_workspace(alpha.workspace)),
        raise_server_exceptions=False,
    )
    own = owner_client.get(f"/api/v1/reports/schedules/{alpha.schedule_id}")
    assert own.status_code == 200, (
        f"positive control failed: the owning member must read their own schedule "
        f"(got {own.status_code}; is the reports router wired into main.py?)"
    )

    intruder_client = TestClient(
        _reports_app(monkeypatch, member_from_workspace(beta.workspace)),
        raise_server_exceptions=False,
    )
    cross = intruder_client.get(f"/api/v1/reports/schedules/{alpha.schedule_id}")
    assert cross.status_code == 404
    assert cross.json()["code"]


def test_branch_scoped_member_sees_only_own_branch_artifacts(
    monkeypatch: pytest.MonkeyPatch,
    reporting_tenants: tuple[ReportingTenant, ReportingTenant],
) -> None:
    """FR-004: a branch_manager assigned to branch A sees branch A's artifacts and NOT
    branch B's — and unfiltered artifacts remain visible to every member."""
    from fastapi.testclient import TestClient

    alpha, _beta = reporting_tenants

    branch_client = TestClient(
        _reports_app(monkeypatch, member_from_workspace(alpha.branch_member)),
        raise_server_exceptions=False,
    )
    response = branch_client.get("/api/v1/reports/artifacts?limit=100")
    assert response.status_code == 200, (
        f"positive control failed: the artifacts listing must answer (got "
        f"{response.status_code}; body={response.text})"
    )
    ids = {item["id"] for item in response.json()["items"]}

    assert str(alpha.branch_a_job_id) in ids
    assert str(alpha.branch_b_job_id) not in ids
    # No branch filter on the artifact means no branch restriction on the listing.
    assert str(alpha.scheduled_job_id) in ids


# --- layer 3: scheduler claim hardening (Wave 17) ----------------------------
#
# The scheduler's own hardening tests (due-row claim via FOR UPDATE SKIP LOCKED, crash-after-
# upload recovery, duplicate RQ replay) are written against the real module in T016's lane —
# they need its actual entrypoint, which does not exist yet. What T008 owns at the storage
# layer is already proven above: the per-period unique partial index (test_duplicate_
# scheduled_artifact_for_the_same_period_is_refused) is the guarantee every scheduler
# behaviour leans on, whatever the worker code does.

"""Purchase request integration tests — T016 (008-requests-approvals, US1).

Proves at the database level: draft creation, status transitions, the paired-nullability
constraints (estimated total, line estimates), approval_step constraints (paired decision
fields, one-per-request unique), cascading deletes, and FK enforcement.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import psycopg
import pytest

from integration.catalogue_helpers import (
    TEST_DATABASE_URL,
    Workspace,
    act_as,
    connection,
    make_workspace,
    make_workspace_product,
)

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL not set; needs Postgres with R2.1 migrations",
)


@pytest.fixture
def conn() -> object:
    yield from connection()


def _make_branch(
    cur: psycopg.Cursor, workspace: Workspace
) -> UUID:
    branch_id = uuid4()
    cur.execute(
        "insert into branch (id,tenant_id,name,region) "
        "values (%s,%s,'Test Branch','GB')",
        (branch_id, workspace.tenant_id),
    )
    return branch_id


def _make_request(
    cur: psycopg.Cursor,
    workspace: Workspace,
    branch_id: UUID,
    *,
    status: str = "draft",
) -> UUID:
    request_id = uuid4()
    cur.execute(
        "insert into purchase_request "
        "(id,tenant_id,branch_id,requested_by_membership_id,"
        "required_by_date,status) "
        "values (%s,%s,%s,%s, current_date + interval '7 days', %s)",
        (
            request_id,
            workspace.tenant_id,
            branch_id,
            workspace.membership_id,
            status,
        ),
    )
    return request_id


def _add_line_no_estimate(
    cur: psycopg.Cursor,
    workspace: Workspace,
    request_id: UUID,
    product_id: UUID,
) -> UUID:
    line_id = uuid4()
    cur.execute(
        "insert into purchase_request_line "
        "(id,tenant_id,purchase_request_id,"
        "workspace_product_id,quantity) "
        "values (%s,%s,%s,%s,10)",
        (line_id, workspace.tenant_id, request_id, product_id),
    )
    return line_id


# ── draft creation ────────────────────────────────────────────────────


def test_a_draft_request_is_visible_to_its_own_workspace(
    conn: object,
) -> None:
    with conn.cursor() as cur:
        ws = make_workspace(cur, "pr-draft-visible")
        act_as(cur, ws)
        branch_id = _make_branch(cur, ws)
        request_id = _make_request(cur, ws, branch_id)
        cur.execute(
            "select status from purchase_request where id = %s",
            (request_id,),
        )
        assert cur.fetchone() == ("draft",)


def test_a_draft_request_accepts_lines_without_estimates(
    conn: object,
) -> None:
    with conn.cursor() as cur:
        ws = make_workspace(cur, "pr-draft-lines")
        act_as(cur, ws)
        branch_id = _make_branch(cur, ws)
        product_id = make_workspace_product(cur, ws, name="Widget")
        request_id = _make_request(cur, ws, branch_id)
        line_id = _add_line_no_estimate(cur, ws, request_id, product_id)
        cur.execute(
            "select estimated_unit_price_amount, "
            "estimated_unit_price_currency, "
            "estimated_unit_price_source_landed_cost_id "
            "from purchase_request_line where id = %s",
            (line_id,),
        )
        row = cur.fetchone()
        assert row == (None, None, None)


def test_a_draft_line_has_no_estimated_at(conn: object) -> None:
    with conn.cursor() as cur:
        ws = make_workspace(cur, "pr-draft-no-estimated-at")
        act_as(cur, ws)
        branch_id = _make_branch(cur, ws)
        product_id = make_workspace_product(cur, ws, name="Widget")
        request_id = _make_request(cur, ws, branch_id)
        line_id = _add_line_no_estimate(cur, ws, request_id, product_id)
        cur.execute(
            "select estimated_at from purchase_request_line "
            "where id = %s",
            (line_id,),
        )
        assert cur.fetchone() == (None,)


# ── estimate constraints ──────────────────────────────────────────────


def test_line_estimate_paired_nullability_rejects_partial_estimate(
    conn: object,
) -> None:
    with conn.cursor() as cur:
        ws = make_workspace(cur, "pr-line-paired")
        act_as(cur, ws)
        branch_id = _make_branch(cur, ws)
        product_id = make_workspace_product(cur, ws, name="Widget")
        request_id = _make_request(cur, ws, branch_id)
        with pytest.raises(psycopg.errors.CheckViolation):
            cur.execute(
                "insert into purchase_request_line "
                "(id,tenant_id,purchase_request_id,"
                "workspace_product_id,quantity,"
                "estimated_unit_price_amount) "
                "values (%s,%s,%s,%s,10,25.5)",
                (uuid4(), ws.tenant_id, request_id, product_id),
            )


def test_request_estimated_total_paired_nullability(
    conn: object,
) -> None:
    with conn.cursor() as cur:
        ws = make_workspace(cur, "pr-total-paired")
        act_as(cur, ws)
        branch_id = _make_branch(cur, ws)
        request_id = _make_request(cur, ws, branch_id)
        with pytest.raises(psycopg.errors.CheckViolation):
            cur.execute(
                "update purchase_request "
                "set estimated_total_amount = 100 "
                "where id = %s",
                (request_id,),
            )


# ── status transitions ───────────────────────────────────────────────


def test_submit_sets_status_and_submitted_at(conn: object) -> None:
    with conn.cursor() as cur:
        ws = make_workspace(cur, "pr-submit")
        act_as(cur, ws)
        branch_id = _make_branch(cur, ws)
        request_id = _make_request(cur, ws, branch_id)
        cur.execute(
            "update purchase_request "
            "set status = 'submitted', submitted_at = now() "
            "where id = %s returning status, submitted_at",
            (request_id,),
        )
        row = cur.fetchone()
        assert row[0] == "submitted"
        assert row[1] is not None


def test_freeze_sets_estimated_at_on_lines(conn: object) -> None:
    with conn.cursor() as cur:
        ws = make_workspace(cur, "pr-freeze")
        act_as(cur, ws)
        branch_id = _make_branch(cur, ws)
        product_id = make_workspace_product(cur, ws, name="Widget")
        request_id = _make_request(cur, ws, branch_id)
        line_id = _add_line_no_estimate(cur, ws, request_id, product_id)
        cur.execute(
            "update purchase_request_line set estimated_at = now() "
            "where id = %s returning estimated_at",
            (line_id,),
        )
        assert cur.fetchone()[0] is not None


def test_withdraw_from_draft(conn: object) -> None:
    with conn.cursor() as cur:
        ws = make_workspace(cur, "pr-withdraw-draft")
        act_as(cur, ws)
        branch_id = _make_branch(cur, ws)
        request_id = _make_request(cur, ws, branch_id)
        cur.execute(
            "update purchase_request "
            "set status = 'withdrawn', withdrawn_at = now() "
            "where id = %s returning status",
            (request_id,),
        )
        assert cur.fetchone() == ("withdrawn",)


def test_withdraw_from_submitted(conn: object) -> None:
    with conn.cursor() as cur:
        ws = make_workspace(cur, "pr-withdraw-submitted")
        act_as(cur, ws)
        branch_id = _make_branch(cur, ws)
        request_id = _make_request(
            cur, ws, branch_id, status="submitted"
        )
        cur.execute(
            "update purchase_request "
            "set status = 'withdrawn', withdrawn_at = now() "
            "where id = %s returning status",
            (request_id,),
        )
        assert cur.fetchone() == ("withdrawn",)


# ── approval_step constraints ─────────────────────────────────────────


def test_approval_step_decision_fields_paired_rejects_pending_with_decided(
    conn: object,
) -> None:
    with conn.cursor() as cur:
        ws = make_workspace(cur, "pr-step-paired-pending")
        act_as(cur, ws)
        branch_id = _make_branch(cur, ws)
        request_id = _make_request(
            cur, ws, branch_id, status="submitted"
        )
        with pytest.raises(psycopg.errors.CheckViolation):
            cur.execute(
                "insert into approval_step "
                "(id,tenant_id,purchase_request_id,"
                "assigned_membership_id,source,status,"
                "decided_by_membership_id,decided_at) "
                "values (%s,%s,%s,%s,'owner_fallback','pending',"
                "%s,now())",
                (
                    uuid4(),
                    ws.tenant_id,
                    request_id,
                    ws.membership_id,
                    ws.membership_id,
                ),
            )


def test_approval_step_decision_fields_paired_rejects_approved_without_decided(
    conn: object,
) -> None:
    with conn.cursor() as cur:
        ws = make_workspace(cur, "pr-step-paired-approved")
        act_as(cur, ws)
        branch_id = _make_branch(cur, ws)
        request_id = _make_request(
            cur, ws, branch_id, status="submitted"
        )
        with pytest.raises(psycopg.errors.CheckViolation):
            cur.execute(
                "insert into approval_step "
                "(id,tenant_id,purchase_request_id,"
                "assigned_membership_id,source,status) "
                "values (%s,%s,%s,%s,'owner_fallback','approved')",
                (
                    uuid4(),
                    ws.tenant_id,
                    request_id,
                    ws.membership_id,
                ),
            )


def test_approval_step_accepts_approved_with_decided(
    conn: object,
) -> None:
    with conn.cursor() as cur:
        ws = make_workspace(cur, "pr-step-valid-approved")
        act_as(cur, ws)
        branch_id = _make_branch(cur, ws)
        request_id = _make_request(
            cur, ws, branch_id, status="submitted"
        )
        step_id = uuid4()
        cur.execute(
            "insert into approval_step "
            "(id,tenant_id,purchase_request_id,"
            "assigned_membership_id,source,status,"
            "decided_by_membership_id,decided_at) "
            "values (%s,%s,%s,%s,'owner_fallback','approved',"
            "%s,now())",
            (
                step_id,
                ws.tenant_id,
                request_id,
                ws.membership_id,
                ws.membership_id,
            ),
        )
        cur.execute(
            "select status from approval_step where id = %s",
            (step_id,),
        )
        assert cur.fetchone() == ("approved",)


def test_approval_step_one_per_request(conn: object) -> None:
    with conn.cursor() as cur:
        ws = make_workspace(cur, "pr-step-unique")
        act_as(cur, ws)
        branch_id = _make_branch(cur, ws)
        request_id = _make_request(
            cur, ws, branch_id, status="submitted"
        )
        cur.execute(
            "insert into approval_step "
            "(id,tenant_id,purchase_request_id,"
            "assigned_membership_id,source,status) "
            "values (%s,%s,%s,%s,'owner_fallback','pending')",
            (uuid4(), ws.tenant_id, request_id, ws.membership_id),
        )
        with pytest.raises(psycopg.errors.UniqueViolation):
            cur.execute(
                "insert into approval_step "
                "(id,tenant_id,purchase_request_id,"
                "assigned_membership_id,source,status) "
                "values (%s,%s,%s,%s,'threshold_match','pending')",
                (
                    uuid4(),
                    ws.tenant_id,
                    request_id,
                    ws.membership_id,
                ),
            )


# ── cascade ──────────────────────────────────────────────────────────


def test_deleting_a_request_cascades_to_lines_and_steps(
    conn: object,
) -> None:
    with conn.cursor() as cur:
        ws = make_workspace(cur, "pr-cascade")
        act_as(cur, ws)
        branch_id = _make_branch(cur, ws)
        product_id = make_workspace_product(cur, ws, name="Widget")
        request_id = _make_request(
            cur, ws, branch_id, status="submitted"
        )
        line_id = _add_line_no_estimate(
            cur, ws, request_id, product_id
        )
        step_id = uuid4()
        cur.execute(
            "insert into approval_step "
            "(id,tenant_id,purchase_request_id,"
            "assigned_membership_id,source,status) "
            "values (%s,%s,%s,%s,'owner_fallback','pending')",
            (step_id, ws.tenant_id, request_id, ws.membership_id),
        )
        cur.execute(
            "delete from purchase_request where id = %s",
            (request_id,),
        )
        cur.execute(
            "select count(*) from purchase_request_line "
            "where id = %s",
            (line_id,),
        )
        assert cur.fetchone() == (0,)
        cur.execute(
            "select count(*) from approval_step where id = %s",
            (step_id,),
        )
        assert cur.fetchone() == (0,)


# ── FK constraints ───────────────────────────────────────────────────


def test_request_requires_valid_branch(conn: object) -> None:
    with conn.cursor() as cur:
        ws = make_workspace(cur, "pr-fk-branch")
        act_as(cur, ws)
        with pytest.raises(psycopg.errors.ForeignKeyViolation):
            cur.execute(
                "insert into purchase_request "
                "(id,tenant_id,branch_id,"
                "requested_by_membership_id,required_by_date) "
                "values (%s,%s,%s,%s, current_date + interval '7 days')",
                (uuid4(), ws.tenant_id, uuid4(), ws.membership_id),
            )


def test_line_requires_valid_workspace_product(
    conn: object,
) -> None:
    with conn.cursor() as cur:
        ws = make_workspace(cur, "pr-fk-product")
        act_as(cur, ws)
        branch_id = _make_branch(cur, ws)
        request_id = _make_request(cur, ws, branch_id)
        with pytest.raises(psycopg.errors.ForeignKeyViolation):
            cur.execute(
                "insert into purchase_request_line "
                "(id,tenant_id,purchase_request_id,"
                "workspace_product_id,quantity) "
                "values (%s,%s,%s,%s,10)",
                (uuid4(), ws.tenant_id, request_id, uuid4()),
            )


# ── service-layer guard boundaries ──────────────────────────────────
# FR-003 (zero-lines), FR-004 (no-edit-after-submit), and withdraw-
# blocked-from-terminal are service.py guards, not DB constraints.
# Tests below verify the DB permits these transitions, confirming the
# service as the single enforcement point.


def test_db_allows_submit_with_no_lines(conn: object) -> None:
    with conn.cursor() as cur:
        ws = make_workspace(cur, "pr-fr003-boundary")
        act_as(cur, ws)
        branch_id = _make_branch(cur, ws)
        request_id = _make_request(cur, ws, branch_id)
        cur.execute(
            "update purchase_request "
            "set status = 'submitted', submitted_at = now() "
            "where id = %s returning status",
            (request_id,),
        )
        assert cur.fetchone() == ("submitted",)


def test_db_allows_update_of_submitted_request(
    conn: object,
) -> None:
    with conn.cursor() as cur:
        ws = make_workspace(cur, "pr-fr004-boundary")
        act_as(cur, ws)
        branch_id = _make_branch(cur, ws)
        request_id = _make_request(
            cur, ws, branch_id, status="submitted"
        )
        cur.execute(
            "update purchase_request "
            "set required_by_date = current_date + interval '30 days' "
            "where id = %s returning required_by_date",
            (request_id,),
        )
        assert cur.fetchone() is not None


def test_db_allows_withdraw_from_approved(conn: object) -> None:
    with conn.cursor() as cur:
        ws = make_workspace(cur, "pr-withdraw-approved-boundary")
        act_as(cur, ws)
        branch_id = _make_branch(cur, ws)
        request_id = _make_request(
            cur, ws, branch_id, status="approved"
        )
        cur.execute(
            "update purchase_request "
            "set status = 'withdrawn', withdrawn_at = now() "
            "where id = %s returning status",
            (request_id,),
        )
        assert cur.fetchone() == ("withdrawn",)


def test_db_allows_withdraw_from_rejected(conn: object) -> None:
    with conn.cursor() as cur:
        ws = make_workspace(cur, "pr-withdraw-rejected-boundary")
        act_as(cur, ws)
        branch_id = _make_branch(cur, ws)
        request_id = _make_request(
            cur, ws, branch_id, status="rejected"
        )
        cur.execute(
            "update purchase_request "
            "set status = 'withdrawn', withdrawn_at = now() "
            "where id = %s returning status",
            (request_id,),
        )

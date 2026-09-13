"""Purchase request integration tests — T016 (008-requests-approvals, US1).

Proves at the database level: draft creation, status transitions, the paired-nullability
constraints (estimated total, line estimates), approval_step constraints (paired decision
fields, one-per-request unique), cascading deletes, and FK enforcement.
"""

from __future__ import annotations

from datetime import date, timedelta
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg import sql

from integration.catalogue_helpers import (
    TEST_DATABASE_URL,
    Workspace,
    act_as,
    connection,
    make_workspace,
    make_workspace_product,
    reset_role,
)
from integration.quotation_helpers import (
    PsycopgSupabaseClient,
    PsycopgTableQuery,
    _adapt_value,
    _Response,
)
from procurepilot_api.deps import CurrentMember
from procurepilot_api.errors import PermissionDeniedError
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.requests import service as requests_service_module
from procurepilot_api.modules.requests.schemas import (
    PurchaseRequestCreate,
    PurchaseRequestLineInput,
    PurchaseRequestUpdate,
)
from procurepilot_api.modules.requests.service import RequestsService
from procurepilot_api.modules.requests.valuation import LineEstimate

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
    requested_by_membership_id: UUID | None = None,
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
            requested_by_membership_id or workspace.membership_id,
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


# ── branch write authorization (create_request & update_request) ──────


def _make_member(
    cur: psycopg.Cursor, tenant_id: UUID, label: str, role: str
) -> Workspace:
    user_id, membership_id = uuid4(), uuid4()
    cur.execute(
        "insert into auth.users (id,email) values (%s,%s)",
        (user_id, f"{label}@example.test"),
    )
    cur.execute(
        "insert into membership (id,tenant_id,user_id,email,role,is_active_workspace) "
        "values (%s,%s,%s,%s,%s,true)",
        (membership_id, tenant_id, user_id, f"{label}@example.test", role),
    )
    return Workspace(tenant_id, user_id, membership_id, role, label)


def _assign_branch(
    cur: psycopg.Cursor, workspace: Workspace, member: Workspace, branch_id: UUID
) -> None:
    cur.execute(
        "insert into branch_role_assignment (id,tenant_id,membership_id,branch_id) "
        "values (%s,%s,%s,%s)",
        (uuid4(), workspace.tenant_id, member.membership_id, branch_id),
    )


def _current_member(workspace: Workspace, member_ws: Workspace) -> CurrentMember:
    return CurrentMember(
        membership_id=member_ws.membership_id,
        tenant_id=workspace.tenant_id,
        user_id=member_ws.user_id,
        email=f"{member_ws.label}@example.test",
        role=MemberRole(member_ws.role),
    )


class _TestTableQuery(PsycopgTableQuery):
    def insert(
        self, payload: dict[str, object] | list[dict[str, object]]
    ) -> _TestTableQuery:
        self._operation = "insert"
        self._payload = payload  # type: ignore[assignment]
        return self

    def _execute_insert(self) -> object:
        if self._payload is None:
            raise AssertionError("insert payload is required")
        if isinstance(self._payload, list):
            if not self._payload:
                return _Response([])
            keys = list(self._payload[0])
            query = sql.SQL("insert into {} ({}) values {} returning *").format(
                sql.Identifier(self._table),
                sql.SQL(",").join(sql.Identifier(key) for key in keys),
                sql.SQL(",").join(
                    sql.SQL("({})").format(
                        sql.SQL(",").join(sql.Placeholder() for _ in keys)
                    )
                    for _ in self._payload
                ),
            )
            params = [
                _adapt_value(key, row[key])
                for row in self._payload
                for key in keys
            ]
            return _Response(self._fetch(query, params))
        return super()._execute_insert()


class _TestSupabaseClient(PsycopgSupabaseClient):
    def table(self, table: str) -> _TestTableQuery:
        return _TestTableQuery(self._conn, table)


def _service(
    conn: psycopg.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> RequestsService:
    service = RequestsService()
    monkeypatch.setattr(
        requests_service_module,
        "authenticated_client",
        lambda _settings, _token: _TestSupabaseClient(conn),
    )
    monkeypatch.setattr(
        service,
        "_estimate_products",
        lambda product_ids: [
            LineEstimate(
                unit_price_amount=None,
                unit_price_currency=None,
                source_landed_cost_id=None,
            )
            for _ in product_ids
        ],
    )
    monkeypatch.setattr(service, "_budget_status_for", lambda _client, _row: None)
    monkeypatch.setattr(service, "_record", lambda **kwargs: None)
    return service


def test_create_request_rejects_unassigned_branch_for_scoped_member(
    conn: psycopg.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    with conn.cursor() as cur:
        owner = make_workspace(cur, "pr-auth-create-denied")
        requester = _make_member(
            cur, owner.tenant_id, "pr-create-denied-req", "branch_manager"
        )
        branch_a = _make_branch(cur, owner)
        branch_b = _make_branch(cur, owner)
        _assign_branch(cur, owner, requester, branch_a)
        product_id = make_workspace_product(cur, owner, name="Paper")
        reset_role(cur)
    conn.commit()

    service = _service(conn, monkeypatch)
    payload = PurchaseRequestCreate(
        branch_id=branch_b,
        required_by_date=date.today() + timedelta(days=7),
        lines=[
            PurchaseRequestLineInput(
                workspace_product_id=product_id,
                quantity="5.000000",
            )
        ],
    )
    with pytest.raises(PermissionDeniedError) as exc:
        service.create_request(
            bearer_token="token",
            member=_current_member(owner, requester),
            payload=payload,
        )

    assert exc.value.status_code == 403
    assert exc.value.details == {"reason": "branch_not_assigned"}


def test_create_request_allows_assigned_branch_for_scoped_member(
    conn: psycopg.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    with conn.cursor() as cur:
        owner = make_workspace(cur, "pr-auth-create-allowed")
        requester = _make_member(
            cur, owner.tenant_id, "pr-create-allowed-req", "branch_manager"
        )
        branch_a = _make_branch(cur, owner)
        _branch_b = _make_branch(cur, owner)
        _assign_branch(cur, owner, requester, branch_a)
        product_id = make_workspace_product(cur, owner, name="Pens")
        reset_role(cur)
    conn.commit()

    service = _service(conn, monkeypatch)
    payload = PurchaseRequestCreate(
        branch_id=branch_a,
        required_by_date=date.today() + timedelta(days=7),
        lines=[
            PurchaseRequestLineInput(
                workspace_product_id=product_id,
                quantity="3.000000",
            )
        ],
    )
    created_request, created = service.create_request(
        bearer_token="token",
        member=_current_member(owner, requester),
        payload=payload,
    )

    assert created is True
    assert created_request.branch_id == branch_a
    assert created_request.status == "draft"
    assert created_request.requested_by_membership_id == requester.membership_id


def test_create_request_allows_any_branch_for_owner_and_unscoped_member(
    conn: psycopg.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    with conn.cursor() as cur:
        owner = make_workspace(cur, "pr-auth-unscoped")
        unscoped_member = _make_member(
            cur, owner.tenant_id, "pr-unscoped-member", "branch_manager"
        )
        branch = _make_branch(cur, owner)
        product_id = make_workspace_product(cur, owner, name="Staples")
        reset_role(cur)
    conn.commit()

    service = _service(conn, monkeypatch)

    # Owner can create request against any branch without an assignment
    owner_cm = CurrentMember(
        membership_id=owner.membership_id,
        tenant_id=owner.tenant_id,
        user_id=owner.user_id,
        email="owner@example.test",
        role=MemberRole.owner,
    )
    owner_payload = PurchaseRequestCreate(
        branch_id=branch,
        required_by_date=date.today() + timedelta(days=7),
        lines=[
            PurchaseRequestLineInput(
                workspace_product_id=product_id,
                quantity="1.000000",
            )
        ],
    )
    owner_req, created = service.create_request(
        bearer_token="token",
        member=owner_cm,
        payload=owner_payload,
    )
    assert created is True
    assert owner_req.branch_id == branch

    # Unscoped member (zero assignments) can create request against any branch
    unscoped_cm = _current_member(owner, unscoped_member)
    unscoped_payload = PurchaseRequestCreate(
        branch_id=branch,
        required_by_date=date.today() + timedelta(days=7),
        lines=[
            PurchaseRequestLineInput(
                workspace_product_id=product_id,
                quantity="2.000000",
            )
        ],
    )
    unscoped_req, created = service.create_request(
        bearer_token="token",
        member=unscoped_cm,
        payload=unscoped_payload,
    )
    assert created is True
    assert unscoped_req.branch_id == branch


def test_update_request_branch_authorization(
    conn: psycopg.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    with conn.cursor() as cur:
        owner = make_workspace(cur, "pr-auth-update")
        requester = _make_member(
            cur, owner.tenant_id, "pr-update-req", "branch_manager"
        )
        branch_a = _make_branch(cur, owner)
        branch_b = _make_branch(cur, owner)
        _assign_branch(cur, owner, requester, branch_a)
        product_id = make_workspace_product(cur, owner, name="Folders")
        reset_role(cur)
        request_id = _make_request(
            cur,
            owner,
            branch_a,
            status="draft",
            requested_by_membership_id=requester.membership_id,
        )
        _add_line_no_estimate(cur, owner, request_id, product_id)
    conn.commit()

    service = _service(conn, monkeypatch)
    requester_cm = _current_member(owner, requester)

    # 1. Changing branch_id to unassigned branch B raises PermissionDeniedError (403)
    patch_b = PurchaseRequestUpdate(branch_id=branch_b)
    with pytest.raises(PermissionDeniedError) as exc:
        service.update_request(
            bearer_token="token",
            member=requester_cm,
            request_id=request_id,
            patch=patch_b,
        )

    assert exc.value.status_code == 403
    assert exc.value.details == {"reason": "branch_not_assigned"}

    # 2. A patch that does not touch branch_id (only required_by_date) succeeds
    new_date = date.today() + timedelta(days=14)
    patch_date = PurchaseRequestUpdate(required_by_date=new_date)
    updated = service.update_request(
        bearer_token="token",
        member=requester_cm,
        request_id=request_id,
        patch=patch_date,
    )
    assert updated.required_by_date == new_date
    assert updated.branch_id == branch_a


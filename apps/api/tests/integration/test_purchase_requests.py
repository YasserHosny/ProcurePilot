"""Purchase request integration tests — T016 (008-requests-approvals, US1).

Proves at the database level: draft creation, status transitions, the paired-nullability
constraints (estimated total, line estimates), approval_step constraints (paired decision
fields, one-per-request unique), cascading deletes, and FK enforcement.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
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
from procurepilot_api.errors import (
    ConflictError,
    PermissionDeniedError,
    UnprocessableEntityError,
)
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


def _make_branch(cur: psycopg.Cursor, workspace: Workspace) -> UUID:
    branch_id = uuid4()
    cur.execute(
        "insert into branch (id,tenant_id,name,region) values (%s,%s,'Test Branch','GB')",
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
            "select estimated_at from purchase_request_line where id = %s",
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
                "update purchase_request set estimated_total_amount = 100 where id = %s",
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
        request_id = _make_request(cur, ws, branch_id, status="submitted")
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
        request_id = _make_request(cur, ws, branch_id, status="submitted")
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
        request_id = _make_request(cur, ws, branch_id, status="submitted")
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
        request_id = _make_request(cur, ws, branch_id, status="submitted")
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
        request_id = _make_request(cur, ws, branch_id, status="submitted")
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
        request_id = _make_request(cur, ws, branch_id, status="submitted")
        line_id = _add_line_no_estimate(cur, ws, request_id, product_id)
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
            "select count(*) from purchase_request_line where id = %s",
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
        request_id = _make_request(cur, ws, branch_id, status="submitted")
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
        request_id = _make_request(cur, ws, branch_id, status="approved")
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
        request_id = _make_request(cur, ws, branch_id, status="rejected")
        cur.execute(
            "update purchase_request "
            "set status = 'withdrawn', withdrawn_at = now() "
            "where id = %s returning status",
            (request_id,),
        )


# ── branch write authorization (create_request & update_request) ──────


def _make_member(cur: psycopg.Cursor, tenant_id: UUID, label: str, role: str) -> Workspace:
    user_id, membership_id = uuid4(), uuid4()
    email = f"{label}-{user_id.hex[:8]}@example.test"
    cur.execute(
        "insert into auth.users (id,email) values (%s,%s)",
        (user_id, email),
    )
    cur.execute(
        "insert into membership (id,tenant_id,user_id,email,role,is_active_workspace) "
        "values (%s,%s,%s,%s,%s,true)",
        (membership_id, tenant_id, user_id, email, role),
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
    def insert(self, payload: dict[str, object] | list[dict[str, object]]) -> _TestTableQuery:
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
                    sql.SQL("({})").format(sql.SQL(",").join(sql.Placeholder() for _ in keys))
                    for _ in self._payload
                ),
            )
            params = [_adapt_value(key, row[key]) for row in self._payload for key in keys]
            return _Response(self._fetch(query, params))
        return super()._execute_insert()


class _TestSupabaseClient(PsycopgSupabaseClient):
    def table(self, table: str) -> _TestTableQuery:
        return _TestTableQuery(
            self._conn, table, service_role=self._service_role, claims=self._claims
        )


def _service(
    conn: psycopg.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> RequestsService:
    service = RequestsService()
    monkeypatch.setattr(
        requests_service_module,
        "authenticated_client",
        lambda _settings, token: _TestSupabaseClient(
            conn, claims=token if (token and token.startswith("{")) else None
        ),
    )
    monkeypatch.setattr(
        service,
        "_estimate_products",
        lambda product_ids, **_kw: [
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
        requester = _make_member(cur, owner.tenant_id, "pr-create-denied-req", "branch_manager")
        branch_a = _make_branch(cur, owner)
        branch_b = _make_branch(cur, owner)
        _assign_branch(cur, owner, requester, branch_a)
        product_id = make_workspace_product(cur, owner, name="Paper")
        reset_role(cur)
    conn.commit()

    service = _service(conn, monkeypatch)
    payload = PurchaseRequestCreate(
        branch_id=branch_b,
        required_by_date=datetime.now(UTC).date() + timedelta(days=7),
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
        requester = _make_member(cur, owner.tenant_id, "pr-create-allowed-req", "branch_manager")
        branch_a = _make_branch(cur, owner)
        _branch_b = _make_branch(cur, owner)
        _assign_branch(cur, owner, requester, branch_a)
        product_id = make_workspace_product(cur, owner, name="Pens")
        reset_role(cur)
    conn.commit()

    service = _service(conn, monkeypatch)
    payload = PurchaseRequestCreate(
        branch_id=branch_a,
        required_by_date=datetime.now(UTC).date() + timedelta(days=7),
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
        unscoped_member = _make_member(cur, owner.tenant_id, "pr-unscoped-member", "branch_manager")
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
        required_by_date=datetime.now(UTC).date() + timedelta(days=7),
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
        required_by_date=datetime.now(UTC).date() + timedelta(days=7),
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
        requester = _make_member(cur, owner.tenant_id, "pr-update-req", "branch_manager")
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


# ── atomicity and validation integration tests (PPS-184 / PPS-186) ────


def _make_cost_centre(
    cur: psycopg.Cursor, workspace: Workspace, branch_id: UUID | None = None
) -> UUID:
    cc_id = uuid4()
    cur.execute(
        "insert into cost_centre (id, tenant_id, code, name, branch_id) "
        "values (%s, %s, %s, 'Test Cost Centre', %s)",
        (cc_id, workspace.tenant_id, f"CC-{cc_id.hex[:6]}", branch_id),
    )
    return cc_id


def test_create_request_atomicity_line_failure_leaves_no_header(
    conn: psycopg.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    with conn.cursor() as cur:
        owner = make_workspace(cur, "pr-atom-create")
        branch = _make_branch(cur, owner)
        product_id = make_workspace_product(cur, owner, name="Widgets")
        reset_role(cur)
        cur.execute(
            "select count(*) from purchase_request where tenant_id = %s",
            (owner.tenant_id,),
        )
        count_before = cur.fetchone()[0]
    conn.commit()

    service = _service(conn, monkeypatch)
    # Simulate a failure during line insertion inside the transaction
    monkeypatch.setattr(
        service,
        "_insert_lines_db",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            UnprocessableEntityError(details={"reason": "database_constraint"})
        ),
    )

    payload = PurchaseRequestCreate(
        branch_id=branch,
        required_by_date=datetime.now(UTC).date() + timedelta(days=7),
        lines=[PurchaseRequestLineInput(workspace_product_id=product_id, quantity="10.000000")],
    )

    with pytest.raises(UnprocessableEntityError):
        service.create_request(
            bearer_token="token",
            member=_current_member(owner, owner),
            payload=payload,
        )

    with conn.cursor() as cur:
        reset_role(cur)
        cur.execute(
            "select count(*) from purchase_request where tenant_id = %s",
            (owner.tenant_id,),
        )
        count_after = cur.fetchone()[0]
    assert count_after == count_before, "Failed create must leave NO purchase_request header row"


def test_update_request_atomicity_invalid_line_leaves_original_lines(
    conn: psycopg.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    with conn.cursor() as cur:
        owner = make_workspace(cur, "pr-atom-update")
        branch = _make_branch(cur, owner)
        product_a = make_workspace_product(cur, owner, name="Prod A")
        product_b = make_workspace_product(cur, owner, name="Prod B")
        reset_role(cur)
        request_id = _make_request(cur, owner, branch, status="draft")
        line_id = _add_line_no_estimate(cur, owner, request_id, product_a)
    conn.commit()

    service = _service(conn, monkeypatch)
    # Simulate a failure during new line insertion inside update transaction
    monkeypatch.setattr(
        service,
        "_insert_lines_db",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            UnprocessableEntityError(details={"reason": "database_constraint"})
        ),
    )

    patch = PurchaseRequestUpdate(
        lines=[PurchaseRequestLineInput(workspace_product_id=product_b, quantity="20.000000")]
    )

    with pytest.raises(UnprocessableEntityError):
        service.update_request(
            bearer_token="token",
            member=_current_member(owner, owner),
            request_id=request_id,
            patch=patch,
        )

    with conn.cursor() as cur:
        reset_role(cur)
        cur.execute(
            "select id, workspace_product_id from purchase_request_line "
            "where purchase_request_id = %s",
            (request_id,),
        )
        lines = cur.fetchall()
        assert len(lines) == 1
        assert lines[0][0] == line_id
        assert lines[0][1] == product_a, "Original lines must remain intact after update failure"


def test_concurrent_update_vs_withdraw_loser_gets_conflict(
    conn: psycopg.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    import threading
    from concurrent.futures import ThreadPoolExecutor

    with conn.cursor() as cur:
        owner = make_workspace(cur, "pr-conc-upd-wth")
        branch = _make_branch(cur, owner)
        product_id = make_workspace_product(cur, owner, name="Prod C")
        reset_role(cur)
        request_id = _make_request(cur, owner, branch, status="draft")
        _add_line_no_estimate(cur, owner, request_id, product_id)
    conn.commit()

    thread_state = threading.local()

    def client_factory(_settings: object, token: str) -> _TestSupabaseClient:
        return _TestSupabaseClient(
            thread_state.conn, claims=token if (token and token.startswith("{")) else owner.claims()
        )

    monkeypatch.setattr(requests_service_module, "authenticated_client", client_factory)

    service = RequestsService()
    monkeypatch.setattr(service, "_budget_status_for", lambda _client, _row: None)
    monkeypatch.setattr(service, "_record", lambda **kwargs: None)
    monkeypatch.setattr(
        service,
        "_estimate_products",
        lambda product_ids, **_kw: [
            LineEstimate(
                unit_price_amount=None,
                unit_price_currency=None,
                source_landed_cost_id=None,
            )
            for _ in product_ids
        ],
    )

    barrier = threading.Barrier(2)
    results: dict[str, object] = {}

    def do_withdraw() -> None:
        thread_state.conn = psycopg.connect(TEST_DATABASE_URL or "", prepare_threshold=None)
        try:
            with thread_state.conn.cursor() as cur:
                act_as(cur, owner)
            barrier.wait()
            res = service.withdraw_request(
                bearer_token=owner.claims(),
                member=_current_member(owner, owner),
                request_id=request_id,
            )
            results["withdraw"] = res
        except Exception as exc:
            results["withdraw"] = exc
        finally:
            thread_state.conn.close()

    def do_update() -> None:
        thread_state.conn = psycopg.connect(TEST_DATABASE_URL or "", prepare_threshold=None)
        try:
            with thread_state.conn.cursor() as cur:
                act_as(cur, owner)
            barrier.wait()
            patch = PurchaseRequestUpdate(
                lines=[
                    PurchaseRequestLineInput(workspace_product_id=product_id, quantity="9.000000")
                ]
            )
            res = service.update_request(
                bearer_token=owner.claims(),
                member=_current_member(owner, owner),
                request_id=request_id,
                patch=patch,
            )
            results["update"] = res
        except Exception as exc:
            results["update"] = exc
        finally:
            thread_state.conn.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(do_withdraw)
        f2 = executor.submit(do_update)
        f1.result()
        f2.result()

    # Exactly one must succeed, and the loser must get ConflictError (not_draft)
    withdraw_res = results.get("withdraw")
    update_res = results.get("update")

    # Invariant: withdraw always succeeds (draft is a valid state to withdraw from).
    assert not isinstance(withdraw_res, Exception), f"Withdraw unexpectedly failed: {withdraw_res}"

    conn.rollback()
    with conn.cursor() as cur:
        act_as(cur, owner)
        cur.execute(
            "select status, withdrawn_at from purchase_request where id = %s",
            (request_id,),
        )
        row = cur.fetchone()
        assert row is not None
        status, withdrawn_at = row
        assert status == "withdrawn"
        assert withdrawn_at is not None

        cur.execute(
            "select quantity from purchase_request_line where purchase_request_id = %s",
            (request_id,),
        )
        line_rows = cur.fetchall()
        assert len(line_rows) == 1
        qty = line_rows[0][0]

    # Deterministic invariant for every order:
    # 1. If withdraw committed first: update is rejected with 409 not_draft; lines intact (10).
    # 2. If update committed first while draft: update succeeds (9), then withdraw succeeds;
    #    final state is withdrawn.
    if isinstance(update_res, ConflictError):
        assert update_res.status_code == 409
        assert update_res.details == {"reason": "not_draft"}
        assert Decimal(str(qty)) == Decimal("10")
    else:
        assert not isinstance(update_res, Exception), f"Update unexpectedly failed: {update_res}"
        assert Decimal(str(qty)) == Decimal("9.000000")


def test_concurrent_update_vs_submit_loser_gets_conflict(
    conn: psycopg.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    import threading
    from concurrent.futures import ThreadPoolExecutor

    with conn.cursor() as cur:
        owner = make_workspace(cur, "pr-conc-upd-sub")
        branch = _make_branch(cur, owner)
        product_id = make_workspace_product(cur, owner, name="Prod D")
        reset_role(cur)
        request_id = _make_request(cur, owner, branch, status="draft")
        _add_line_no_estimate(cur, owner, request_id, product_id)
    conn.commit()

    thread_state = threading.local()

    def client_factory(_settings: object, token: str) -> _TestSupabaseClient:
        return _TestSupabaseClient(
            thread_state.conn, claims=token if (token and token.startswith("{")) else owner.claims()
        )

    monkeypatch.setattr(requests_service_module, "authenticated_client", client_factory)

    service = RequestsService()
    monkeypatch.setattr(service, "_budget_status_for", lambda _client, _row: None)
    monkeypatch.setattr(service, "_record", lambda **kwargs: None)
    monkeypatch.setattr(
        service,
        "_fetch_owner_membership_id",
        lambda _client: owner.membership_id,
    )
    monkeypatch.setattr(
        service,
        "_estimate_products",
        lambda product_ids, **_kw: [
            LineEstimate(
                unit_price_amount=None,
                unit_price_currency=None,
                source_landed_cost_id=None,
            )
            for _ in product_ids
        ],
    )

    barrier = threading.Barrier(2)
    results: dict[str, object] = {}

    def do_submit() -> None:
        thread_state.conn = psycopg.connect(TEST_DATABASE_URL or "", prepare_threshold=None)
        try:
            with thread_state.conn.cursor() as cur:
                act_as(cur, owner)
            barrier.wait()
            res = service.submit_request(
                bearer_token=owner.claims(),
                member=_current_member(owner, owner),
                request_id=request_id,
            )
            results["submit"] = res
        except Exception as exc:
            results["submit"] = exc
        finally:
            thread_state.conn.close()

    def do_update() -> None:
        thread_state.conn = psycopg.connect(TEST_DATABASE_URL or "", prepare_threshold=None)
        try:
            with thread_state.conn.cursor() as cur:
                act_as(cur, owner)
            barrier.wait()
            patch = PurchaseRequestUpdate(
                lines=[
                    PurchaseRequestLineInput(workspace_product_id=product_id, quantity="9.000000")
                ]
            )
            res = service.update_request(
                bearer_token=owner.claims(),
                member=_current_member(owner, owner),
                request_id=request_id,
                patch=patch,
            )
            results["update"] = res
        except Exception as exc:
            results["update"] = exc
        finally:
            thread_state.conn.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(do_submit)
        f2 = executor.submit(do_update)
        f1.result()
        f2.result()

    submit_res = results.get("submit")
    update_res = results.get("update")

    # Invariant: submit always succeeds (draft is a valid state to submit from).
    assert not isinstance(submit_res, Exception), f"Submit unexpectedly failed: {submit_res}"

    conn.rollback()
    with conn.cursor() as cur:
        act_as(cur, owner)
        cur.execute(
            "select status, submitted_at from purchase_request where id = %s",
            (request_id,),
        )
        row = cur.fetchone()
        assert row is not None
        status, submitted_at = row
        assert status == "submitted"
        assert submitted_at is not None

        cur.execute(
            "select quantity from purchase_request_line where purchase_request_id = %s",
            (request_id,),
        )
        line_rows = cur.fetchall()
        assert len(line_rows) == 1
        qty = line_rows[0][0]

        cur.execute(
            "select status from approval_step where purchase_request_id = %s",
            (request_id,),
        )
        step_row = cur.fetchone()
        assert step_row is not None
        assert step_row[0] == "pending"

    # Deterministic invariant for every order:
    # 1. If submit committed first: update is rejected with 409 not_draft; lines intact (10).
    # 2. If update committed first while draft: update succeeds (9), then submit succeeds;
    #    final state is submitted.
    if isinstance(update_res, ConflictError):
        assert update_res.status_code == 409
        assert update_res.details == {"reason": "not_draft"}
        assert Decimal(str(qty)) == Decimal("10")
    else:
        assert not isinstance(update_res, Exception), f"Update unexpectedly failed: {update_res}"
        assert Decimal(str(qty)) == Decimal("9.000000")


def test_validation_rejects_past_date(
    conn: psycopg.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    with conn.cursor() as cur:
        owner = make_workspace(cur, "pr-val-past-date")
        branch = _make_branch(cur, owner)
        product_id = make_workspace_product(cur, owner, name="Prod")
        reset_role(cur)
        cur.execute(
            "select count(*) from purchase_request where tenant_id = %s",
            (owner.tenant_id,),
        )
        count_before = cur.fetchone()[0]
    conn.commit()

    service = _service(conn, monkeypatch)
    past_date = datetime.now(UTC).date() - timedelta(days=2)
    payload = PurchaseRequestCreate(
        branch_id=branch,
        required_by_date=past_date,
        lines=[PurchaseRequestLineInput(workspace_product_id=product_id, quantity="1.000000")],
    )

    with pytest.raises(UnprocessableEntityError) as exc_info:
        service.create_request(
            bearer_token="token",
            member=_current_member(owner, owner),
            payload=payload,
        )

    assert exc_info.value.status_code == 422
    assert exc_info.value.details == {
        "field": "required_by_date",
        "reason": "required_by_in_the_past",
    }

    with conn.cursor() as cur:
        reset_role(cur)
        cur.execute(
            "select count(*) from purchase_request where tenant_id = %s",
            (owner.tenant_id,),
        )
        assert cur.fetchone()[0] == count_before, "Nothing must be written on validation failure"


def test_validation_rejects_duplicate_product(
    conn: psycopg.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    with conn.cursor() as cur:
        owner = make_workspace(cur, "pr-val-dup-prod")
        branch = _make_branch(cur, owner)
        product_id = make_workspace_product(cur, owner, name="Prod")
        reset_role(cur)
        cur.execute(
            "select count(*) from purchase_request where tenant_id = %s",
            (owner.tenant_id,),
        )
        count_before = cur.fetchone()[0]
    conn.commit()

    service = _service(conn, monkeypatch)
    payload = PurchaseRequestCreate(
        branch_id=branch,
        required_by_date=datetime.now(UTC).date() + timedelta(days=7),
        lines=[
            PurchaseRequestLineInput(workspace_product_id=product_id, quantity="1.000000"),
            PurchaseRequestLineInput(workspace_product_id=product_id, quantity="2.000000"),
        ],
    )

    with pytest.raises(UnprocessableEntityError) as exc_info:
        service.create_request(
            bearer_token="token",
            member=_current_member(owner, owner),
            payload=payload,
        )

    assert exc_info.value.status_code == 422
    assert exc_info.value.details == {
        "field": "lines[1].workspace_product_id",
        "reason": "duplicate_product",
    }

    with conn.cursor() as cur:
        reset_role(cur)
        cur.execute(
            "select count(*) from purchase_request where tenant_id = %s",
            (owner.tenant_id,),
        )
        assert cur.fetchone()[0] == count_before


def test_validation_rejects_cost_centre_not_found(
    conn: psycopg.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    with conn.cursor() as cur:
        owner = make_workspace(cur, "pr-val-cc-notfound")
        branch = _make_branch(cur, owner)
        product_id = make_workspace_product(cur, owner, name="Prod")
        reset_role(cur)
        cur.execute(
            "select count(*) from purchase_request where tenant_id = %s",
            (owner.tenant_id,),
        )
        count_before = cur.fetchone()[0]
    conn.commit()

    service = _service(conn, monkeypatch)
    payload = PurchaseRequestCreate(
        branch_id=branch,
        cost_centre_id=uuid4(),
        required_by_date=datetime.now(UTC).date() + timedelta(days=7),
        lines=[PurchaseRequestLineInput(workspace_product_id=product_id, quantity="1.000000")],
    )

    with pytest.raises(UnprocessableEntityError) as exc_info:
        service.create_request(
            bearer_token="token",
            member=_current_member(owner, owner),
            payload=payload,
        )

    assert exc_info.value.status_code == 422
    assert exc_info.value.details == {
        "field": "cost_centre_id",
        "reason": "cost_centre_not_found",
    }

    with conn.cursor() as cur:
        reset_role(cur)
        cur.execute(
            "select count(*) from purchase_request where tenant_id = %s",
            (owner.tenant_id,),
        )
        assert cur.fetchone()[0] == count_before


def test_validation_rejects_cost_centre_branch_mismatch(
    conn: psycopg.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    with conn.cursor() as cur:
        owner = make_workspace(cur, "pr-val-cc-mismatch")
        branch_a = _make_branch(cur, owner)
        branch_b = _make_branch(cur, owner)
        product_id = make_workspace_product(cur, owner, name="Prod")
        cc_b = _make_cost_centre(cur, owner, branch_id=branch_b)
        reset_role(cur)
        cur.execute(
            "select count(*) from purchase_request where tenant_id = %s",
            (owner.tenant_id,),
        )
        count_before = cur.fetchone()[0]
    conn.commit()

    service = _service(conn, monkeypatch)
    payload = PurchaseRequestCreate(
        branch_id=branch_a,
        cost_centre_id=cc_b,
        required_by_date=datetime.now(UTC).date() + timedelta(days=7),
        lines=[PurchaseRequestLineInput(workspace_product_id=product_id, quantity="1.000000")],
    )

    with pytest.raises(UnprocessableEntityError) as exc_info:
        service.create_request(
            bearer_token="token",
            member=_current_member(owner, owner),
            payload=payload,
        )

    assert exc_info.value.status_code == 422
    assert exc_info.value.details == {
        "field": "cost_centre_id",
        "reason": "cost_centre_branch_mismatch",
    }

    with conn.cursor() as cur:
        reset_role(cur)
        cur.execute(
            "select count(*) from purchase_request where tenant_id = %s",
            (owner.tenant_id,),
        )
        assert cur.fetchone()[0] == count_before


def test_validation_rejects_quantity_zero(
    conn: psycopg.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    with conn.cursor() as cur:
        owner = make_workspace(cur, "pr-val-qty-zero")
        branch = _make_branch(cur, owner)
        product_id = make_workspace_product(cur, owner, name="Prod")
        reset_role(cur)
        cur.execute(
            "select count(*) from purchase_request where tenant_id = %s",
            (owner.tenant_id,),
        )
        count_before = cur.fetchone()[0]
    conn.commit()

    service = _service(conn, monkeypatch)
    payload = PurchaseRequestCreate(
        branch_id=branch,
        required_by_date=datetime.now(UTC).date() + timedelta(days=7),
        lines=[PurchaseRequestLineInput(workspace_product_id=product_id, quantity="0")],
    )

    with pytest.raises(UnprocessableEntityError) as exc_info:
        service.create_request(
            bearer_token="token",
            member=_current_member(owner, owner),
            payload=payload,
        )

    assert exc_info.value.status_code == 422
    assert exc_info.value.details == {
        "field": "lines[0].quantity",
        "reason": "quantity_not_positive",
    }

    with conn.cursor() as cur:
        reset_role(cur)
        cur.execute(
            "select count(*) from purchase_request where tenant_id = %s",
            (owner.tenant_id,),
        )
        assert cur.fetchone()[0] == count_before, "No header must remain when quantity is 0"


def test_validation_rejects_unknown_product(
    conn: psycopg.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A product id that is not in the caller's workspace is rejected as not found."""
    with conn.cursor() as cur:
        owner_a = make_workspace(cur, "pr-val-foreign-a")
        branch_a = _make_branch(cur, owner_a)
        owner_b = make_workspace(cur, "pr-val-foreign-b")
        foreign_product_id = make_workspace_product(cur, owner_b, name="Foreign Prod")
        reset_role(cur)
        cur.execute(
            "select count(*) from purchase_request where tenant_id = %s",
            (owner_a.tenant_id,),
        )
        count_before = cur.fetchone()[0]
    conn.commit()

    service = _service(conn, monkeypatch)
    payload = PurchaseRequestCreate(
        branch_id=branch_a,
        required_by_date=datetime.now(UTC).date() + timedelta(days=7),
        lines=[
            PurchaseRequestLineInput(
                workspace_product_id=foreign_product_id,
                quantity="1.000000",
            )
        ],
    )

    with pytest.raises(UnprocessableEntityError) as exc_info:
        service.create_request(
            bearer_token=owner_a.claims(),
            member=_current_member(owner_a, owner_a),
            payload=payload,
        )

    assert exc_info.value.status_code == 422
    assert exc_info.value.details == {
        "field": "lines[0].workspace_product_id",
        "reason": "product_not_found",
    }

    with conn.cursor() as cur:
        reset_role(cur)
        cur.execute(
            "select count(*) from purchase_request where tenant_id = %s",
            (owner_a.tenant_id,),
        )
        assert cur.fetchone()[0] == count_before


def test_create_and_update_happy_paths_preserve_response_shapes(
    conn: psycopg.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    with conn.cursor() as cur:
        owner = make_workspace(cur, "pr-happy-shapes")
        branch = _make_branch(cur, owner)
        cc_id = _make_cost_centre(cur, owner, branch_id=branch)
        product_1 = make_workspace_product(cur, owner, name="Prod 1")
        product_2 = make_workspace_product(cur, owner, name="Prod 2")
        reset_role(cur)
    conn.commit()

    service = _service(conn, monkeypatch)
    owner_cm = _current_member(owner, owner)

    # 1. Create request
    create_payload = PurchaseRequestCreate(
        branch_id=branch,
        cost_centre_id=cc_id,
        required_by_date=datetime.now(UTC).date() + timedelta(days=10),
        lines=[
            PurchaseRequestLineInput(workspace_product_id=product_1, quantity="2.000000"),
            PurchaseRequestLineInput(workspace_product_id=product_2, quantity="4.000000"),
        ],
    )
    req, created = service.create_request(
        bearer_token="token",
        member=owner_cm,
        payload=create_payload,
    )
    assert created is True
    assert req.branch_id == branch
    assert req.cost_centre_id == cc_id
    assert req.status == "draft"
    assert len(req.lines) == 2

    # 2. Update request
    new_required_date = datetime.now(UTC).date() + timedelta(days=15)
    update_payload = PurchaseRequestUpdate(
        required_by_date=new_required_date,
        lines=[PurchaseRequestLineInput(workspace_product_id=product_1, quantity="5.000000")],
    )
    updated_req = service.update_request(
        bearer_token="token",
        member=owner_cm,
        request_id=req.id,
        patch=update_payload,
    )
    assert updated_req.id == req.id
    assert updated_req.required_by_date == new_required_date
    assert len(updated_req.lines) == 1
    assert updated_req.lines[0].quantity == "5.000000"

    # 3. Submit request
    monkeypatch.setattr(
        service,
        "_fetch_owner_membership_id",
        lambda _client: owner.membership_id,
    )
    submitted_req = service.submit_request(
        bearer_token="token",
        member=owner_cm,
        request_id=req.id,
    )
    assert submitted_req.id == req.id
    assert submitted_req.status == "submitted"
    assert submitted_req.approval_step is not None
    assert submitted_req.approval_step.status == "pending"


# ── Idempotent replay before validation tests (PR #414 review finding) ────


def test_idempotent_replay_survives_clock_moved_past_midnight(
    conn: psycopg.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    with conn.cursor() as cur:
        owner = make_workspace(cur, "pr-replay-midnight")
        branch = _make_branch(cur, owner)
        product = make_workspace_product(cur, owner, name="Prod Midnight")
        reset_role(cur)
    conn.commit()

    service = _service(conn, monkeypatch)
    owner_cm = _current_member(owner, owner)

    today = datetime.now(UTC).date()
    idempotency_key = uuid4()
    payload = PurchaseRequestCreate(
        branch_id=branch,
        required_by_date=today,
        lines=[PurchaseRequestLineInput(workspace_product_id=product, quantity="3.000000")],
    )

    req1, created1 = service.create_request(
        bearer_token=owner.claims(),
        member=owner_cm,
        payload=payload,
        idempotency_key=idempotency_key,
    )
    assert created1 is True

    # Move clock past midnight
    class FakeDateTime(datetime):
        _mock_now = datetime.now(UTC) + timedelta(days=1)

        @classmethod
        def now(cls, tz: object = None) -> datetime:
            assert cls._mock_now is not None
            return cls._mock_now

    monkeypatch.setattr(requests_service_module, "datetime", FakeDateTime)

    # Retry the same payload and key after midnight: must return 200 replay (created=False)
    req2, created2 = service.create_request(
        bearer_token=owner.claims(),
        member=owner_cm,
        payload=payload,
        idempotency_key=idempotency_key,
    )
    assert created2 is False
    assert req2.id == req1.id

    # Exactly one purchase_request row and one set of lines exist in DB
    with conn.cursor() as cur:
        act_as(cur, owner)
        cur.execute(
            "select count(*) from purchase_request where id = %s",
            (req1.id,),
        )
        assert cur.fetchone()[0] == 1
        cur.execute(
            "select count(*) from purchase_request_line where purchase_request_id = %s",
            (req1.id,),
        )
        assert cur.fetchone()[0] == 1


def test_idempotent_replay_with_invalid_payload_replays_while_new_key_rejected(
    conn: psycopg.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    with conn.cursor() as cur:
        owner = make_workspace(cur, "pr-replay-invalid")
        branch = _make_branch(cur, owner)
        product = make_workspace_product(cur, owner, name="Prod Invalid")
        reset_role(cur)
    conn.commit()

    service = _service(conn, monkeypatch)
    owner_cm = _current_member(owner, owner)

    today = datetime.now(UTC).date()
    idempotency_key = uuid4()
    valid_payload = PurchaseRequestCreate(
        branch_id=branch,
        required_by_date=today + timedelta(days=2),
        lines=[PurchaseRequestLineInput(workspace_product_id=product, quantity="1.000000")],
    )

    req1, created1 = service.create_request(
        bearer_token=owner.claims(),
        member=owner_cm,
        payload=valid_payload,
        idempotency_key=idempotency_key,
    )
    assert created1 is True

    # Same key with payload that is now invalid (past date)
    invalid_payload = PurchaseRequestCreate(
        branch_id=branch,
        required_by_date=today - timedelta(days=5),
        lines=[PurchaseRequestLineInput(workspace_product_id=product, quantity="1.000000")],
    )

    # Replay with same key must succeed and replay original
    req2, created2 = service.create_request(
        bearer_token=owner.claims(),
        member=owner_cm,
        payload=invalid_payload,
        idempotency_key=idempotency_key,
    )
    assert created2 is False
    assert req2.id == req1.id

    # A NEW key with that invalid payload returns 422 required_by_in_the_past and writes nothing
    new_key = uuid4()
    with pytest.raises(UnprocessableEntityError) as exc_info:
        service.create_request(
            bearer_token=owner.claims(),
            member=owner_cm,
            payload=invalid_payload,
            idempotency_key=new_key,
        )
    assert exc_info.value.status_code == 422
    assert exc_info.value.details == {
        "field": "required_by_date",
        "reason": "required_by_in_the_past",
    }

    with conn.cursor() as cur:
        act_as(cur, owner)
        cur.execute(
            "select count(*) from purchase_request where idempotency_key = %s",
            (str(new_key),),
        )
        assert cur.fetchone()[0] == 0


def test_idempotent_replay_skips_validation_of_products_and_cost_centre(
    conn: psycopg.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    with conn.cursor() as cur:
        owner = make_workspace(cur, "pr-replay-spy")
        branch = _make_branch(cur, owner)
        cc_id = _make_cost_centre(cur, owner, branch_id=branch)
        product = make_workspace_product(cur, owner, name="Prod Spy")
        reset_role(cur)
    conn.commit()

    service = _service(conn, monkeypatch)
    owner_cm = _current_member(owner, owner)

    key = uuid4()
    payload = PurchaseRequestCreate(
        branch_id=branch,
        cost_centre_id=cc_id,
        required_by_date=datetime.now(UTC).date() + timedelta(days=3),
        lines=[PurchaseRequestLineInput(workspace_product_id=product, quantity="2.000000")],
    )

    req1, created1 = service.create_request(
        bearer_token=owner.claims(),
        member=owner_cm,
        payload=payload,
        idempotency_key=key,
    )
    assert created1 is True

    # Spies for validation calls
    validate_products_calls = 0
    orig_validate_products = service._validate_products_exist

    def spy_validate_products(*args: object, **kwargs: object) -> None:
        nonlocal validate_products_calls
        validate_products_calls += 1
        return orig_validate_products(*args, **kwargs)

    validate_cost_centre_calls = 0
    orig_validate_cost_centre = service._validate_cost_centre_branch

    def spy_validate_cost_centre(*args: object, **kwargs: object) -> None:
        nonlocal validate_cost_centre_calls
        validate_cost_centre_calls += 1
        return orig_validate_cost_centre(*args, **kwargs)

    monkeypatch.setattr(service, "_validate_products_exist", spy_validate_products)
    monkeypatch.setattr(service, "_validate_cost_centre_branch", spy_validate_cost_centre)

    # Replay
    req2, created2 = service.create_request(
        bearer_token=owner.claims(),
        member=owner_cm,
        payload=payload,
        idempotency_key=key,
    )
    assert created2 is False
    assert req2.id == req1.id

    # Neither validation method should be called during replay
    assert validate_products_calls == 0, f"Expected 0 calls, got {validate_products_calls}"
    assert validate_cost_centre_calls == 0, f"Expected 0 calls, got {validate_cost_centre_calls}"


def test_idempotent_key_does_not_replay_across_different_tenants(
    conn: psycopg.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    with conn.cursor() as cur:
        owner_1 = make_workspace(cur, "pr-replay-t1")
        branch_1 = _make_branch(cur, owner_1)
        product_1 = make_workspace_product(cur, owner_1, name="Prod T1")

        owner_2 = make_workspace(cur, "pr-replay-t2")
        branch_2 = _make_branch(cur, owner_2)
        product_2 = make_workspace_product(cur, owner_2, name="Prod T2")
        reset_role(cur)
    conn.commit()

    service = _service(conn, monkeypatch)
    owner_1_cm = _current_member(owner_1, owner_1)
    owner_2_cm = _current_member(owner_2, owner_2)

    shared_key = uuid4()

    # Tenant 1 creates a request with shared_key
    payload_1 = PurchaseRequestCreate(
        branch_id=branch_1,
        required_by_date=datetime.now(UTC).date() + timedelta(days=5),
        lines=[PurchaseRequestLineInput(workspace_product_id=product_1, quantity="1.000000")],
    )
    req_t1, created_t1 = service.create_request(
        bearer_token=owner_1.claims(),
        member=owner_1_cm,
        payload=payload_1,
        idempotency_key=shared_key,
    )
    assert created_t1 is True

    # Tenant 2 creates a request with the SAME key
    payload_2 = PurchaseRequestCreate(
        branch_id=branch_2,
        required_by_date=datetime.now(UTC).date() + timedelta(days=6),
        lines=[PurchaseRequestLineInput(workspace_product_id=product_2, quantity="2.000000")],
    )
    req_t2, created_t2 = service.create_request(
        bearer_token=owner_2.claims(),
        member=owner_2_cm,
        payload=payload_2,
        idempotency_key=shared_key,
    )
    # Tenant 2 must NOT replay Tenant 1's request; it must create its own request normally
    assert created_t2 is True
    assert req_t2.id != req_t1.id

    with conn.cursor() as cur:
        act_as(cur, owner_1)
        cur.execute("select tenant_id from purchase_request where id = %s", (req_t1.id,))
        assert cur.fetchone()[0] == owner_1.tenant_id
        act_as(cur, owner_2)
        cur.execute("select tenant_id from purchase_request where id = %s", (req_t2.id,))
        assert cur.fetchone()[0] == owner_2.tenant_id

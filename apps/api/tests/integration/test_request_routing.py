"""Request routing integration coverage — task T031.

The pure resolver is already covered in unit tests. These checks exercise the submit path that
uses it: request estimates are frozen, an approval step is created for the resolved assignee, and
the pending queue returns the same routed step. Owner fallback also has to emit the escalation
audit event.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Literal
from uuid import UUID, uuid4

import psycopg
import pytest
from pydantic import SecretStr

from integration.catalogue_helpers import (
    TEST_DATABASE_URL,
    Workspace,
    connection,
    delete_tenant_scoped_rows,
    make_workspace,
    make_workspace_product,
    reset_role,
)
from integration.quotation_helpers import PsycopgSupabaseClient, PsycopgTableQuery
from procurepilot_api.config import Settings
from procurepilot_api.deps import CurrentMember
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.requests.routing import DelegationRow, ThresholdRuleRow
from procurepilot_api.modules.requests.schemas import ApprovalStepSource
from procurepilot_api.modules.requests.service import RequestsService
from procurepilot_api.modules.requests.valuation import LineEstimate
from procurepilot_api.shared.audit import AuditEventCreate

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL not set; requires a migrated database",
)


@pytest.fixture
def conn() -> Iterator[psycopg.Connection]:
    yield from connection()


def _test_settings() -> Settings:
    return Settings(
        API_HOST="127.0.0.1",
        API_PORT=8000,
        API_ENV="local",
        API_LOG_LEVEL="error",
        API_CORS_ORIGINS="http://localhost:4200",
        SUPABASE_URL="http://localhost:54321",
        SUPABASE_ANON_KEY=SecretStr("anon"),
        SUPABASE_SERVICE_ROLE_KEY=SecretStr("service"),
        SUPABASE_JWT_AUDIENCE="authenticated",
        SUPABASE_JWT_ISSUER="http://localhost:54321/auth/v1",
        DATABASE_URL=SecretStr(TEST_DATABASE_URL or os.environ.get("TEST_DATABASE_URL", "")),
        PLATFORM_INVITATION_TTL_DAYS=7,
        MEMBER_INVITATION_TTL_DAYS=7,
        RATE_LIMIT_AUTH="100/minute",
        WEB_API_BASE_URL="http://localhost:8000/api/v1",
        WEB_DEFAULT_LOCALE="en",
    )


class _TestTableQuery(PsycopgTableQuery):
    pass


class _TestSupabaseClient(PsycopgSupabaseClient):
    def __init__(
        self,
        conn: psycopg.Connection,
        *,
        service_role: bool = False,
        claims: str | None = None,
    ) -> None:
        super().__init__(conn, service_role=service_role, claims=claims)
        self.request_row: dict[str, object] = {}

    def table(self, table: str) -> _TestTableQuery:
        return _TestTableQuery(
            self._conn, table, service_role=self._service_role, claims=self._claims
        )


class FakeAuditWriter:
    def __init__(self) -> None:
        self.actions: list[str] = []

    def record(self, event: AuditEventCreate, *, bearer_token: str) -> None:
        self.actions.append(str(event.action))


def _make_member(cur: psycopg.Cursor, tenant_id: UUID, label: str, role: str) -> Workspace:
    reset_role(cur)
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


def _make_branch(cur: psycopg.Cursor, workspace: Workspace) -> UUID:
    branch_id = uuid4()
    cur.execute(
        "insert into branch (id,tenant_id,name,region) values (%s,%s,'Branch','GB')",
        (branch_id, workspace.tenant_id),
    )
    return branch_id


def _cleanup(
    conn: psycopg.Connection,
    owner: Workspace,
    extra_members: list[Workspace] | None = None,
) -> None:
    with conn.cursor() as cur:
        cur.execute("reset role")
        cur.execute("set local session_replication_role = replica")
        delete_tenant_scoped_rows(cur, owner.tenant_id)
        cur.execute("delete from tenant where id = %s", (owner.tenant_id,))
        cur.execute("delete from auth.users where id = %s", (owner.user_id,))
        for m in extra_members or []:
            cur.execute("delete from auth.users where id = %s", (m.user_id,))
        conn.commit()


def threshold_rule(
    *,
    branch_id: UUID | None,
    min_amount: str,
    max_amount: str | None,
    approver_id: UUID,
) -> ThresholdRuleRow:
    return ThresholdRuleRow(
        id=uuid4(),
        branch_id=branch_id,
        min_amount=Decimal(min_amount),
        max_amount=Decimal(max_amount) if max_amount is not None else None,
        currency="GBP",
        approver_membership_id=approver_id,
    )


def active_delegation(*, delegator_id: UUID, delegate_id: UUID) -> DelegationRow:
    return DelegationRow(
        id=uuid4(),
        delegator_membership_id=delegator_id,
        delegate_membership_id=delegate_id,
        starts_on=datetime.now(UTC).date() - timedelta(days=2),
        ends_on=datetime.now(UTC).date() + timedelta(days=2),
        created_at=datetime.now(UTC),
    )


def build_service(
    conn: psycopg.Connection,
    monkeypatch: pytest.MonkeyPatch,
    *,
    owner: Workspace,
    branch_id: UUID,
    product_id: UUID,
    rules: list[ThresholdRuleRow],
    delegations: list[DelegationRow] | None = None,
    removed_membership_ids: set[UUID] | None = None,
    audit: FakeAuditWriter | None = None,
) -> tuple[RequestsService, _TestSupabaseClient, CurrentMember, UUID]:
    request_id = uuid4()
    with conn.cursor() as cur:
        cur.execute(
            "insert into purchase_request ("
            " id, tenant_id, branch_id, requested_by_membership_id, required_by_date, status"
            ") values (%s, %s, %s, %s, %s, 'draft')",
            (
                request_id,
                owner.tenant_id,
                branch_id,
                owner.membership_id,
                datetime.now(UTC).date() + timedelta(days=7),
            ),
        )
        cur.execute(
            "insert into purchase_request_line ("
            " id, tenant_id, purchase_request_id, workspace_product_id, quantity, position"
            ") values (%s, %s, %s, %s, 5, 0)",
            (uuid4(), owner.tenant_id, request_id, product_id),
        )
        reset_role(cur)
    conn.commit()

    service = RequestsService()
    service._settings = _test_settings()
    client = _TestSupabaseClient(conn, claims=owner.claims())
    client.request_row = {"branch_id": str(branch_id)}

    member = CurrentMember(
        tenant_id=owner.tenant_id,
        membership_id=owner.membership_id,
        user_id=owner.user_id,
        email=f"{owner.label}@example.test",
        role=MemberRole.owner,
    )

    monkeypatch.setattr(
        "procurepilot_api.modules.requests.service.authenticated_client",
        lambda _settings, token: _TestSupabaseClient(
            conn, claims=token if (token and token.startswith("{")) else owner.claims()
        ),
    )
    monkeypatch.setattr(
        service,
        "_estimate_products",
        lambda _ids, **_kw: [LineEstimate(Decimal("60.0000"), "GBP", None)],
    )
    monkeypatch.setattr(service, "_fetch_threshold_rules", lambda _client: rules)
    monkeypatch.setattr(
        service,
        "_fetch_active_delegations",
        lambda _client, *, as_of: delegations or [],
    )
    monkeypatch.setattr(
        service,
        "_fetch_removed_membership_ids",
        lambda _client: removed_membership_ids or set(),
    )
    monkeypatch.setattr(service, "_fetch_owner_membership_id", lambda _client: owner.membership_id)
    monkeypatch.setattr(service, "_budget_status_for", lambda _client, _row: None)
    monkeypatch.setattr(
        "procurepilot_api.modules.requests.service.get_audit_writer",
        lambda: audit if audit is not None else FakeAuditWriter(),
    )

    return service, client, member, request_id


def submit_and_fetch_pending(
    service: RequestsService,
    member: CurrentMember,
    request_id: UUID,
) -> tuple[ApprovalStepSource, UUID]:
    claims_token = (
        f'{{"sub":"{member.user_id}","tenant_id":"{member.tenant_id}","role":"authenticated"}}'
    )
    submitted = service.submit_request(
        bearer_token=claims_token,
        member=member,
        request_id=request_id,
    )
    pending = service.list_pending_approvals(
        bearer_token=claims_token,
        member=member,
    )

    assert submitted.approval_step is not None
    assert pending.items[0].approval_step is not None
    assert pending.items[0].approval_step.id == submitted.approval_step.id
    return submitted.approval_step.source, submitted.approval_step.assigned_membership_id


@pytest.mark.parametrize(
    ("branch_rule", "expected_source"),
    [(True, "threshold_match"), (False, "threshold_match")],
)
def test_submitted_request_routes_to_matching_threshold_approver(
    conn: psycopg.Connection,
    monkeypatch: pytest.MonkeyPatch,
    branch_rule: bool,
    expected_source: Literal["threshold_match"],
) -> None:
    with conn.cursor() as cur:
        owner = make_workspace(cur, "req-routing")
        branch_id = _make_branch(cur, owner)
        product_id = make_workspace_product(cur, owner, name="Routing Widget")
        branch_approver = _make_member(cur, owner.tenant_id, "branch-appr", "approver")
        tenant_approver = _make_member(cur, owner.tenant_id, "tenant-appr", "approver")
    conn.commit()

    extra_members = [branch_approver, tenant_approver]
    try:
        rules = [
            threshold_rule(
                branch_id=None,
                min_amount="0",
                max_amount="1000",
                approver_id=tenant_approver.membership_id,
            )
        ]
        if branch_rule:
            rules.append(
                threshold_rule(
                    branch_id=branch_id,
                    min_amount="0",
                    max_amount="1000",
                    approver_id=branch_approver.membership_id,
                )
            )

        service, client, member, request_id = build_service(
            conn,
            monkeypatch,
            owner=owner,
            branch_id=branch_id,
            product_id=product_id,
            rules=rules,
        )

        source, assignee_id = submit_and_fetch_pending(service, member, request_id)

        assert source == expected_source
        assert assignee_id == (
            branch_approver.membership_id if branch_rule else tenant_approver.membership_id
        )
    finally:
        _cleanup(conn, owner, extra_members)


def test_active_delegation_redirects_the_threshold_resolved_assignee(
    conn: psycopg.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with conn.cursor() as cur:
        owner = make_workspace(cur, "req-delegation")
        branch_id = _make_branch(cur, owner)
        product_id = make_workspace_product(cur, owner, name="Routing Widget")
        approver = _make_member(cur, owner.tenant_id, "approver", "approver")
        delegate = _make_member(cur, owner.tenant_id, "delegate", "buyer")
    conn.commit()

    extra_members = [approver, delegate]
    try:
        rules = [
            threshold_rule(
                branch_id=None,
                min_amount="0",
                max_amount="1000",
                approver_id=approver.membership_id,
            )
        ]
        service, _client, member, request_id = build_service(
            conn,
            monkeypatch,
            owner=owner,
            branch_id=branch_id,
            product_id=product_id,
            rules=rules,
            delegations=[
                active_delegation(
                    delegator_id=approver.membership_id,
                    delegate_id=delegate.membership_id,
                )
            ],
        )

        source, assignee_id = submit_and_fetch_pending(service, member, request_id)

        assert source == "delegate"
        assert assignee_id == delegate.membership_id
    finally:
        _cleanup(conn, owner, extra_members)


def test_owner_fallback_records_escalation_when_no_rule_matches(
    conn: psycopg.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with conn.cursor() as cur:
        owner = make_workspace(cur, "req-fallback")
        branch_id = _make_branch(cur, owner)
        product_id = make_workspace_product(cur, owner, name="Routing Widget")
    conn.commit()

    try:
        audit = FakeAuditWriter()
        service, _client, member, request_id = build_service(
            conn,
            monkeypatch,
            owner=owner,
            branch_id=branch_id,
            product_id=product_id,
            rules=[],
            audit=audit,
        )

        source, assignee_id = submit_and_fetch_pending(service, member, request_id)

        assert source == "owner_fallback"
        assert assignee_id == member.membership_id
        # The escalation event still goes through the (post-commit) audit writer; the submitted
        # event is now written inside the submit transaction, straight to audit_event, so it is
        # read back from the table instead of the fake writer.
        assert audit.actions == ["requests.approval_step_escalated"]
        with conn.cursor() as cur:
            reset_role(cur)
            cur.execute(
                "select count(*) from audit_event where tenant_id = %s and action = %s",
                (owner.tenant_id, "requests.purchase_request_submitted"),
            )
            assert cur.fetchone()[0] == 1
    finally:
        _cleanup(conn, owner)

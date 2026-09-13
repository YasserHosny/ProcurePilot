from __future__ import annotations

from uuid import UUID, uuid4

import psycopg
import pytest

from integration.catalogue_helpers import (
    TEST_DATABASE_URL,
    Workspace,
    connection,
    make_workspace,
    make_workspace_product,
    reset_role,
)
from integration.quotation_helpers import PsycopgSupabaseClient
from procurepilot_api.deps import CurrentMember
from procurepilot_api.errors import ConflictError, PermissionDeniedError
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.requests import service as requests_service_module
from procurepilot_api.modules.requests.schemas import DeliveryConfirmationCreate
from procurepilot_api.modules.requests.service import RequestsService

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL not set; needs Postgres with R2.3 migrations",
)


@pytest.fixture
def conn() -> psycopg.Connection:
    yield from connection()


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


def _make_branch(cur: psycopg.Cursor, workspace: Workspace, label: str) -> UUID:
    branch_id = uuid4()
    cur.execute(
        "insert into branch (id,tenant_id,name,region) values (%s,%s,%s,'GB')",
        (branch_id, workspace.tenant_id, label),
    )
    return branch_id


def _make_request(
    cur: psycopg.Cursor,
    workspace: Workspace,
    branch_id: UUID,
    requester: Workspace,
    *,
    status: str = "ordered",
) -> UUID:
    request_id = uuid4()
    cur.execute(
        "insert into purchase_request "
        "(id,tenant_id,branch_id,requested_by_membership_id,required_by_date,status) "
        "values (%s,%s,%s,%s,current_date + interval '7 days',%s)",
        (
            request_id,
            workspace.tenant_id,
            branch_id,
            requester.membership_id,
            status,
        ),
    )
    return request_id


def _add_line(
    cur: psycopg.Cursor,
    workspace: Workspace,
    request_id: UUID,
    *,
    quantity: str,
    name: str,
) -> UUID:
    product_id = make_workspace_product(cur, workspace, name=name)
    reset_role(cur)
    line_id = uuid4()
    cur.execute(
        "insert into purchase_request_line "
        "(id,tenant_id,purchase_request_id,workspace_product_id,quantity) "
        "values (%s,%s,%s,%s,%s)",
        (
            line_id,
            workspace.tenant_id,
            request_id,
            product_id,
            quantity,
        ),
    )
    return line_id


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


def _payload(lines: list[tuple[UUID, str]]) -> DeliveryConfirmationCreate:
    return DeliveryConfirmationCreate(
        lines=[
            {
                "purchase_request_line_id": line_id,
                "quantity_received": quantity,
            }
            for line_id, quantity in lines
        ]
    )


def _service(
    conn: psycopg.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[RequestsService, list[dict[str, object]]]:
    service = RequestsService()
    recorded: list[dict[str, object]] = []
    monkeypatch.setattr(
        requests_service_module,
        "authenticated_client",
        lambda _settings, _token: PsycopgSupabaseClient(conn),
    )
    monkeypatch.setattr(service, "_budget_status_for", lambda _client, _row: None)
    monkeypatch.setattr(
        service, "_record", lambda **kwargs: recorded.append(kwargs)
    )
    return service, recorded


def test_full_quantity_delivery_marks_delivered_without_discrepancy(
    conn: psycopg.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    with conn.cursor() as cur:
        owner = make_workspace(cur, "delivery-full")
        requester = _make_member(
            cur, owner.tenant_id, "delivery-full-requester", "branch_manager"
        )
        receiver = _make_member(
            cur, owner.tenant_id, "delivery-full-receiver", "approver"
        )
        branch_id = _make_branch(cur, owner, "Delivery Full")
        _assign_branch(cur, owner, receiver, branch_id)
        request_id = _make_request(cur, owner, branch_id, requester)
        line_a = _add_line(
            cur, owner, request_id, quantity="10.000000", name="Flour"
        )
        line_b = _add_line(
            cur, owner, request_id, quantity="4.500000", name="Oil"
        )
    conn.commit()

    service, recorded = _service(conn, monkeypatch)
    result = service.confirm_delivery(
        bearer_token="token",
        member=_current_member(owner, receiver),
        request_id=request_id,
        payload=_payload([(line_a, "10.000000"), (line_b, "4.500000")]),
    )

    assert result.status == "delivered"
    assert result.has_delivery_discrepancy is False
    assert result.delivered_at is not None
    assert result.delivery_confirmed_by_membership_id == receiver.membership_id
    assert [row["action"] for row in recorded] == ["requests.delivery_confirmed"]

    with conn.cursor() as cur:
        cur.execute(
            "select status, has_delivery_discrepancy, "
            "delivery_confirmed_by_membership_id, delivered_at "
            "from purchase_request where id = %s",
            (request_id,),
        )
        status, discrepancy, confirmed_by, delivered_at = cur.fetchone()
        assert (status, discrepancy, str(confirmed_by)) == (
            "delivered",
            False,
            str(receiver.membership_id),
        )
        assert delivered_at is not None


def test_short_quantity_records_exact_line_quantities_and_discrepancy(
    conn: psycopg.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    with conn.cursor() as cur:
        owner = make_workspace(cur, "delivery-short")
        requester = _make_member(
            cur, owner.tenant_id, "delivery-short-requester", "branch_manager"
        )
        receiver = _make_member(
            cur, owner.tenant_id, "delivery-short-receiver", "approver"
        )
        branch_id = _make_branch(cur, owner, "Delivery Short")
        _assign_branch(cur, owner, receiver, branch_id)
        request_id = _make_request(cur, owner, branch_id, requester)
        line_a = _add_line(
            cur, owner, request_id, quantity="10.000000", name="Rice"
        )
        line_b = _add_line(
            cur, owner, request_id, quantity="8.000000", name="Sugar"
        )
    conn.commit()

    service, _recorded = _service(conn, monkeypatch)
    result = service.confirm_delivery(
        bearer_token="token",
        member=_current_member(owner, receiver),
        request_id=request_id,
        payload=_payload([(line_a, "7.000000"), (line_b, "8.000000")]),
    )

    assert result.has_delivery_discrepancy is True
    assert {str(line.id): line.quantity_received for line in result.lines} == {
        str(line_a): "7.000000",
        str(line_b): "8.000000",
    }

    with conn.cursor() as cur:
        cur.execute(
            "select has_delivery_discrepancy from purchase_request where id = %s",
            (request_id,),
        )
        assert cur.fetchone() == (True,)
        cur.execute(
            "select id, quantity_received from purchase_request_line "
            "where purchase_request_id = %s order by id",
            (request_id,),
        )
        received = {str(row[0]): str(row[1]) for row in cur.fetchall()}
        assert received == {
            str(line_a): "7.000000",
            str(line_b): "8.000000",
        }


def test_not_ordered_request_refuses_with_not_ordered_conflict(
    conn: psycopg.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    with conn.cursor() as cur:
        owner = make_workspace(cur, "delivery-not-ordered")
        branch_id = _make_branch(cur, owner, "Delivery Submitted")
        request_id = _make_request(cur, owner, branch_id, owner, status="submitted")
        line_id = _add_line(cur, owner, request_id, quantity="3.000000", name="Tea")
    conn.commit()

    service, _recorded = _service(conn, monkeypatch)
    with pytest.raises(ConflictError) as exc:
        service.confirm_delivery(
            bearer_token="token",
            member=_current_member(owner, owner),
            request_id=request_id,
            payload=_payload([(line_id, "3.000000")]),
        )

    assert exc.value.status_code == 409
    assert exc.value.details == {"reason": "not_ordered"}


def test_visible_different_branch_without_write_scope_refuses_with_403(
    conn: psycopg.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    with conn.cursor() as cur:
        owner = make_workspace(cur, "delivery-forbidden")
        requester = _make_member(
            cur,
            owner.tenant_id,
            "delivery-forbidden-requester",
            "branch_manager",
        )
        receiver = _make_member(
            cur, owner.tenant_id, "delivery-forbidden-receiver", "approver"
        )
        requested_branch = _make_branch(cur, owner, "Requested Branch")
        assigned_branch = _make_branch(cur, owner, "Assigned Branch")
        _assign_branch(cur, owner, receiver, assigned_branch)
        request_id = _make_request(cur, owner, requested_branch, requester)
        line_id = _add_line(
            cur, owner, request_id, quantity="3.000000", name="Beans"
        )
    conn.commit()

    service, _recorded = _service(conn, monkeypatch)
    with pytest.raises(PermissionDeniedError) as exc:
        service.confirm_delivery(
            bearer_token="token",
            member=_current_member(owner, receiver),
            request_id=request_id,
            payload=_payload([(line_id, "3.000000")]),
        )

    assert exc.value.status_code == 403
    assert exc.value.details == {"reason": "branch_not_assigned"}


def test_requester_without_branch_assignment_can_confirm_own_order(
    conn: psycopg.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    with conn.cursor() as cur:
        owner = make_workspace(cur, "delivery-requester")
        requester = _make_member(
            cur, owner.tenant_id, "delivery-requester-own", "branch_manager"
        )
        branch_id = _make_branch(cur, owner, "Requester Branch")
        request_id = _make_request(cur, owner, branch_id, requester)
        line_id = _add_line(
            cur, owner, request_id, quantity="12.000000", name="Coffee"
        )
    conn.commit()

    service, _recorded = _service(conn, monkeypatch)
    result = service.confirm_delivery(
        bearer_token="token",
        member=_current_member(owner, requester),
        request_id=request_id,
        payload=_payload([(line_id, "12.000000")]),
    )

    assert result.status == "delivered"
    assert result.delivery_confirmed_by_membership_id == requester.membership_id

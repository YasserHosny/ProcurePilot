"""T007: split context follows request visibility and is fetched once per page."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID, uuid4

import psycopg
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from psycopg import sql

from integration.catalogue_helpers import TEST_DATABASE_URL, Workspace, make_workspace, reset_role
from integration.quotation_helpers import PsycopgSupabaseClient, PsycopgTableQuery, _Response
from integration.test_purchase_requests import _current_member, _make_branch, _make_member
from procurepilot_api.deps import bearer_token, current_member
from procurepilot_api.errors import AppError, NotFoundError, app_error_handler
from procurepilot_api.modules.requests import service as service_module
from procurepilot_api.modules.requests.router import router
from procurepilot_api.modules.requests.service import RequestsService, get_requests_service

pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="TEST_DATABASE_URL not set")


class GroupQuery(PsycopgTableQuery):
    """Exercise the to-one PostgREST embedding with a real RLS-protected SQL join.

    The shared adapter ignores select columns/embeddings, so translate this one relation
    explicitly. Neither the group nor its requests is read outside authenticated_scope.
    """

    def select(self, columns: str = "*") -> GroupQuery:
        assert "purchase_request_request_group_fkey" in columns
        super().select(columns)
        return self

    def _execute_select(self) -> object:
        where, params = self._where_sql()
        query = sql.SQL(
            "select pr.*, row_to_json(g) as request_group from purchase_request pr "
            "left join purchase_request_group g "
            "on g.tenant_id = pr.tenant_id and g.id = pr.request_group_id"
        )
        if where is not None:
            # All filters in this query belong to purchase_request; qualify to avoid
            # ambiguity with the group's tenant_id.
            for column in ("tenant_id", "request_group_id"):
                where = sql.SQL(
                    where.as_string(self._conn).replace(f'"{column}"', f'pr."{column}"')
                )
            query += sql.SQL(" where ") + where
        return _Response(self._fetch(query, params))


@dataclass
class Seed:
    ws: Workspace
    branch: UUID
    rfq: UUID
    group: UUID
    requests: list[UUID]
    ordinary: UUID


@pytest.fixture
def conn() -> Iterator[psycopg.Connection]:
    with psycopg.connect(TEST_DATABASE_URL or "", prepare_threshold=None) as connection:
        yield connection
        connection.rollback()


def seed(conn: psycopg.Connection, *, count: int = 2, totals: bool = True) -> Seed:
    with conn.cursor() as cur:
        ws = make_workspace(cur, "group-read")
        branch = _make_branch(cur, ws)
        rfq, job, group, ordinary = (uuid4() for _ in range(4))
        cur.execute(
            "insert into rfq (id,tenant_id,created_by_membership_id,status,needed_by_date,"
            "idempotency_key) values (%s,%s,%s,'converted',current_date+7,%s)",
            (rfq, ws.tenant_id, ws.membership_id, uuid4()),
        )
        cur.execute(
            "insert into basket_split_job (id,tenant_id,requested_by,supplier_ids,items,status) "
            "values (%s,%s,%s,array[gen_random_uuid(),gen_random_uuid()],'[]','queued')",
            (job, ws.tenant_id, ws.membership_id),
        )
        cur.execute(
            "insert into purchase_request_group (id,tenant_id,rfq_id,basket_split_job_id,"
            "branch_id,combined_total_amount,combined_total_currency,best_single_total_amount,"
            "best_single_total_currency,saving_amount,saving_currency,idempotency_key,"
            "created_by_membership_id) values (%s,%s,%s,%s,%s,4063,'GBP',%s,%s,%s,%s,%s,%s)",
            (
                group,
                ws.tenant_id,
                rfq,
                job,
                branch,
                4137 if totals else None,
                "GBP" if totals else None,
                74 if totals else None,
                "GBP" if totals else None,
                uuid4(),
                ws.membership_id,
            ),
        )
        # Insert backwards, with tied timestamps for the first pair; neither insertion
        # order nor sorting on id alone is the required (created_at, id) order.
        ids = sorted((uuid4() for _ in range(count)), reverse=True)
        ids[:2] = sorted(ids[:2])
        for i in reversed(range(count)):
            cur.execute(
                "insert into purchase_request (id,tenant_id,branch_id,requested_by_membership_id,"
                "required_by_date,status,request_group_id,created_at) "
                "values (%s,%s,%s,%s,current_date+7,'submitted',%s,"
                "'2026-10-01'::timestamptz + %s * interval '1 second')",
                (ids[i], ws.tenant_id, branch, ws.membership_id, group, max(0, i - 1)),
            )
        cur.execute(
            "insert into purchase_request (id,tenant_id,branch_id,requested_by_membership_id,"
            "required_by_date,status) values (%s,%s,%s,%s,current_date+7,'submitted')",
            (ordinary, ws.tenant_id, branch, ws.membership_id),
        )
        for request in [*ids, ordinary]:
            cur.execute(
                "insert into approval_step (tenant_id,purchase_request_id,assigned_membership_id,"
                "source,status) values (%s,%s,%s,'threshold_match','pending')",
                (ws.tenant_id, request, ws.membership_id),
            )
    conn.commit()
    return Seed(ws, branch, rfq, group, ids, ordinary)


@contextmanager
def api_as(
    conn: psycopg.Connection, monkeypatch: pytest.MonkeyPatch, ws: Workspace
) -> Iterator[tuple[TestClient, RequestsService, list[str]]]:
    queries: list[str] = []

    class Client(PsycopgSupabaseClient):
        def table(self, name: str) -> PsycopgTableQuery:
            query = super().table(name)
            if name == "purchase_request":
                # Only the group batch uses a relation embedding. Ordinary reads retain
                # the shared adapter so a missing enrichment still fails on assertions.
                original_select = query.select

                def select(columns: str = "*") -> PsycopgTableQuery:
                    if "purchase_request_request_group_fkey" in columns:
                        queries.append("group")
                        return GroupQuery(conn, name, claims=ws.claims()).select(columns)
                    return original_select(columns)

                query.select = select
            return query

    # Raw SQL paths use the real database and verified-member claims. Count only the new
    # group enrichment: pre-existing per-request budget/source reads are outside T007.
    original_connect = service_module.db.connect

    class Cursor(psycopg.Cursor):
        def execute(self, query: object, params: object = None, **kwargs: object) -> Cursor:
            if "purchase_request_group" in str(query):
                queries.append("group")
            return super().execute(query, params, **kwargs)

    def connect(*args: object, **kwargs: object) -> psycopg.Connection:
        return original_connect(*args, cursor_factory=Cursor, **kwargs)

    monkeypatch.setattr(service_module.db, "connect", connect)
    monkeypatch.setattr(
        service_module, "authenticated_client", lambda *_: Client(conn, claims=ws.claims())
    )
    service = RequestsService()
    app = FastAPI()
    app.add_exception_handler(AppError, app_error_handler)
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[current_member] = lambda: _current_member(ws, ws)
    app.dependency_overrides[bearer_token] = lambda: "token"
    app.dependency_overrides[get_requests_service] = lambda: service
    with TestClient(app) as client:
        yield client, service, queries


def assert_group(
    body: dict[str, object],
    data: Seed,
    position: int,
    *,
    visible: list[UUID] | None = None,
    totals: bool = True,
) -> None:
    ids = data.requests if visible is None else visible
    group = body["request_group"]
    assert group is not None
    assert group["id"] == str(data.group)
    assert group["rfq_id"] == str(data.rfq)
    assert group["position"] == position
    assert group["size"] == len(ids)
    assert group["sibling_request_ids"] == [str(id_) for id_ in ids if str(id_) != body["id"]]
    for field, amount in (
        ("combined_total", "4063"),
        ("best_single_total", "4137"),
        ("saving", "74"),
    ):
        if not totals and field != "combined_total":
            assert group[field] is None
        else:
            assert group[field]["currency"] == "GBP"
            assert Decimal(group[field]["amount"]) == Decimal(amount)


def test_get_and_member_read_return_positions_siblings_and_currency(
    conn: psycopg.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    data = seed(conn)
    with api_as(conn, monkeypatch, data.ws) as (client, service, _queries):
        for position, request_id in enumerate(data.requests, 1):
            response = client.get(f"/api/v1/requests/{request_id}")
            assert response.status_code == 200, response.text
            assert_group(response.json(), data, position)
            member_read = service.get_request(
                bearer_token="token",
                member=_current_member(data.ws, data.ws),
                request_id=request_id,
            )
            assert_group(member_read.model_dump(mode="json"), data, position)
        assert client.get(f"/api/v1/requests/{data.ordinary}").json()["request_group"] is None


@pytest.mark.parametrize(
    "path", ["/requests", "/approvals/pending", "/requests?eligible_for_order=true"]
)
@pytest.mark.parametrize("count", [2, 8])
def test_lists_batch_group_context_and_keep_ordinary_requests_null(
    conn: psycopg.Connection, monkeypatch: pytest.MonkeyPatch, path: str, count: int
) -> None:
    data = seed(conn, count=count)
    if "eligible_for_order" in path:
        with conn.cursor() as cur:
            reset_role(cur)
            cur.execute(
                "update purchase_request set status='approved' where tenant_id=%s",
                (data.ws.tenant_id,),
            )
            cur.execute(
                "update approval_step set status='approved', decided_by_membership_id=%s, "
                "decided_at=now() where tenant_id=%s",
                (data.ws.membership_id, data.ws.tenant_id),
            )
        conn.commit()
    with api_as(conn, monkeypatch, data.ws) as (client, _service, queries):
        response = client.get("/api/v1" + path)
        assert response.status_code == 200, response.text
        items = {item["id"]: item for item in response.json()["items"]}
        for position, request_id in enumerate(data.requests, 1):
            assert_group(items[str(request_id)], data, position)
        assert items[str(data.ordinary)]["request_group"] is None
        assert queries == ["group"], "group enrichment must cost one query regardless of page size"
        queries.clear()
        # A page containing one request still includes siblings outside the page.
        page = client.get("/api/v1" + path, params={"limit": 1}).json()
        if page["items"][0]["id"] != str(data.ordinary):
            body = page["items"][0]
            assert_group(body, data, data.requests.index(UUID(body["id"])) + 1)


def test_nullable_comparison_totals(
    conn: psycopg.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    data = seed(conn, totals=False)
    with api_as(conn, monkeypatch, data.ws) as (client, _service, _queries):
        assert_group(
            client.get(f"/api/v1/requests/{data.requests[0]}").json(), data, 1, totals=False
        )


def test_other_tenant_cannot_get_or_enumerate_the_requests(
    conn: psycopg.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    data = seed(conn)
    with conn.cursor() as cur:
        stranger = make_workspace(cur, "group-read-stranger")
    conn.commit()
    with api_as(conn, monkeypatch, stranger) as (client, service, _queries):
        for request in data.requests:
            response = client.get(f"/api/v1/requests/{request}")
            assert response.status_code == 404, response.text
        for path in ("/requests", "/approvals/pending", "/requests?eligible_for_order=true"):
            response = client.get("/api/v1" + path)
            assert response.status_code == 200, response.text
            assert response.json()["items"] == []
        with pytest.raises(NotFoundError):
            service.get_request(
                bearer_token="token",
                member=_current_member(stranger, stranger),
                request_id=data.requests[0],
            )


@pytest.mark.parametrize("role", ["buyer", "approver"])
def test_branch_limited_member_counts_only_rls_visible_siblings(
    conn: psycopg.Connection, monkeypatch: pytest.MonkeyPatch, role: str
) -> None:
    data = seed(conn)
    with conn.cursor() as cur:
        reset_role(cur)
        member = _make_member(cur, data.ws.tenant_id, f"group-{role}-{uuid4().hex[:8]}", role)
        other_branch = _make_branch(cur, data.ws)
        cur.execute(
            "insert into branch_role_assignment (tenant_id,membership_id,branch_id) "
            "values (%s,%s,%s)",
            (data.ws.tenant_id, member.membership_id, data.branch),
        )
        cur.execute(
            "update approval_step set assigned_membership_id=%s where tenant_id=%s",
            (member.membership_id, data.ws.tenant_id),
        )
    conn.commit()
    with api_as(conn, monkeypatch, member) as (client, _service, _queries):
        # Normal invariant: every request uses the group's branch, so both are visible.
        assert_group(client.get(f"/api/v1/requests/{data.requests[0]}").json(), data, 1)
        with conn.cursor() as cur:
            reset_role(cur)
            # Deliberately violate the service invariant to prove no read widens RLS.
            cur.execute(
                "update purchase_request set branch_id=%s where id=%s",
                (other_branch, data.requests[0]),
            )
        conn.commit()
        assert client.get(f"/api/v1/requests/{data.requests[0]}").status_code == 404
        assert_group(
            client.get(f"/api/v1/requests/{data.requests[1]}").json(),
            data,
            1,
            visible=[data.requests[1]],
        )
        for path in ("/requests", "/approvals/pending"):
            items = client.get("/api/v1" + path).json()["items"]
            assert str(data.requests[0]) not in [item["id"] for item in items]
            body = next(item for item in items if item["id"] == str(data.requests[1]))
            assert_group(body, data, 1, visible=[data.requests[1]])


def test_an_rls_hidden_group_leaves_a_visible_request_with_null_context(
    conn: psycopg.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    data = seed(conn)
    with conn.cursor() as cur:
        # A temporary restrictive policy exercises the hidden-group case without changing
        # the production schema; the fixture rolls this DDL back after the test.
        cur.execute(
            sql.SQL(
                "create policy group_read_hidden on purchase_request_group "
                "as restrictive for select to authenticated using (id <> {})"
            ).format(sql.Literal(data.group))
        )
    with api_as(conn, monkeypatch, data.ws) as (client, _service, _queries):
        response = client.get(f"/api/v1/requests/{data.requests[0]}")
        assert response.status_code == 200, response.text
        assert response.json()["request_group"] is None
        items = client.get("/api/v1/requests").json()["items"]
        assert len(items) == 3
        assert all(item["request_group"] is None for item in items)

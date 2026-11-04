"""PPS-193: request list filters use real rows and authenticated database RLS."""

from collections.abc import Iterator
from dataclasses import dataclass
from uuid import UUID, uuid4

import psycopg
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from integration.catalogue_helpers import (
    TEST_DATABASE_URL,
    Workspace,
    make_workspace,
    make_workspace_product,
    reset_role,
)
from integration.quotation_helpers import make_quotation, make_supplier
from integration.test_purchase_requests import (
    _add_line_no_estimate,
    _assign_branch,
    _current_member,
    _make_branch,
    _make_member,
    _make_request,
    _service,
)
from procurepilot_api.deps import bearer_token, current_member
from procurepilot_api.errors import register_exception_handlers
from procurepilot_api.modules.requests.router import router
from procurepilot_api.modules.requests.service import (
    RequestsService,
    _encode_cursor,
    get_requests_service,
)

pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="TEST_DATABASE_URL not set")


@dataclass
class Seed:
    conn: psycopg.Connection
    ws: Workspace
    branch: UUID
    ids: list[str]
    foreign: str


@pytest.fixture(scope="module")
def data() -> Iterator[Seed]:
    with psycopg.connect(TEST_DATABASE_URL or "", prepare_threshold=None) as conn:
        with conn.cursor() as cur:
            ws = make_workspace(cur, "p169b-list")
            branch = _make_branch(cur, ws)
            other = _make_member(cur, ws.tenant_id, "p169b-other", "owner")
            product = make_workspace_product(cur, ws, name="Ordinary")
            special = make_workspace_product(cur, ws, name="Arabic أرز Product")
            reset_role(cur)
            ids = []
            for i in range(6):
                request = _make_request(
                    cur,
                    ws,
                    branch,
                    status="submitted" if i < 4 else "draft",
                    requested_by_membership_id=(ws if i % 2 == 0 else other).membership_id,
                )
                ids.append(str(request))
                line = _add_line_no_estimate(cur, ws, request, special if i == 4 else product)
                cur.execute(
                    "update purchase_request_line set note=%s where id=%s",
                    (
                        [
                            "Needle 50%",
                            "needle under_score",
                            r"NEEDLE back\slash",
                            "needle",
                            "plain",
                            "plain",
                        ][i],
                        line,
                    ),
                )
                cur.execute(
                    "update purchase_request set created_at='2026-10-01'::timestamptz + "
                    "%s * interval '1 day', required_by_date=current_date+%s, "
                    "estimated_total_amount=%s, estimated_total_currency=%s where id=%s",
                    (
                        i // 2,
                        [8, 8, 9, 9, 7, 7][i],
                        None if i >= 4 else (i // 2 + 1) * 10,
                        None if i >= 4 else ("GBP" if i % 2 else "USD"),
                        request,
                    ),
                )
            supplier = make_supplier(cur, ws, "Fresh الوفرة Supplier")
            quote = make_quotation(cur, ws, supplier_id=supplier)
            reset_role(cur)
            rfq, recipient, response = uuid4(), uuid4(), uuid4()
            cur.execute(
                "insert into rfq (id,tenant_id,created_by_membership_id,idempotency_key,"
                "needed_by_date,status) "
                "values (%s,%s,%s,%s,current_date+7,'converted')",
                (rfq, ws.tenant_id, ws.membership_id, uuid4()),
            )
            cur.execute(
                "insert into rfq_recipient (id,tenant_id,rfq_id,supplier_id,status) "
                "values (%s,%s,%s,%s,'sent')",
                (recipient, ws.tenant_id, rfq, supplier),
            )
            cur.execute(
                "insert into rfq_response (id,tenant_id,rfq_recipient_id,quotation_id) "
                "values (%s,%s,%s,%s)",
                (response, ws.tenant_id, recipient, quote),
            )
            cur.execute(
                "update purchase_request set source_rfq_response_id=%s where id=%s",
                (response, ids[0]),
            )
            foreign_ws = make_workspace(cur, "p169b-foreign")
            foreign_branch = _make_branch(cur, foreign_ws)
            foreign_product = make_workspace_product(cur, foreign_ws, name="Needle Fresh الوفرة")
            reset_role(cur)
            foreign = _make_request(cur, foreign_ws, foreign_branch)
            _add_line_no_estimate(cur, foreign_ws, foreign, foreign_product)
        conn.commit()
        yield Seed(conn, ws, branch, ids, str(foreign))
        conn.rollback()


@pytest.fixture
def client(data: Seed, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    service = _service(data.conn, monkeypatch)
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[current_member] = lambda: _current_member(data.ws, data.ws)
    app.dependency_overrides[bearer_token] = data.ws.claims
    app.dependency_overrides[get_requests_service] = lambda: service
    with TestClient(app) as test_client:
        yield test_client


def listing(client: TestClient, **params: object) -> dict:
    response = client.get("/api/v1/requests", params=params)
    assert response.status_code == 200, response.text
    return response.json()


def ids(body: dict) -> list[str]:
    return [item["id"] for item in body["items"]]


@pytest.mark.parametrize(
    "sort",
    [
        "created_desc",
        "created_asc",
        "required_by_asc",
        "required_by_desc",
        "total_desc",
        "total_asc",
    ],
)
def test_sort_total_order(client: TestClient, data: Seed, sort: str) -> None:
    groups = [data.ids[i : i + 2] for i in range(0, 6, 2)]
    if sort == "created_desc":
        groups.reverse()
    elif sort == "required_by_asc":
        groups = [groups[2], groups[0], groups[1]]
    elif sort == "required_by_desc":
        groups = [groups[1], groups[0], groups[2]]
    elif sort == "total_desc":
        groups = [groups[1], groups[0], groups[2]]
    expected = [value for group in groups for value in sorted(group)]
    assert ids(listing(client, sort=sort)) == expected
    first = listing(client, sort=sort, limit=3)
    second = listing(client, sort=sort, limit=3, cursor=first["next_cursor"])
    assert ids(first) + ids(second) == expected
    assert second["next_cursor"] is None


@pytest.mark.parametrize(
    ("q", "indices"),
    [
        ("Fresh", [0]),
        ("الوفرة", [0]),
        ("sUpPlIeR", [0]),
        ("أرز", [4]),
        ("pRoDuCt", [4]),
        ("  nEeDlE  ", [0, 1, 2, 3]),
        ("50%", [0]),
        ("%", [0]),
        ("_", [1]),
        ("under_score", [1]),
        ("\\", [2]),
        ("absent", []),
        (" " + "x" * 100 + " ", []),
    ],
)
def test_search(client: TestClient, data: Seed, q: str, indices: list[int]) -> None:
    assert set(ids(listing(client, q=q))) == {data.ids[i] for i in indices}


@pytest.mark.parametrize(
    ("params", "field"),
    [
        ({"sort": "unknown"}, "sort"),
        ({"q": "x" * 101}, "q"),
        ({"q": "   "}, "q"),
        ({"q": ""}, "q"),
        ({"limit": 0}, "limit"),
        ({"limit": -1}, "limit"),
        ({"limit": 101}, "limit"),
    ],
)
def test_validation(client: TestClient, params: dict, field: str) -> None:
    response = client.get("/api/v1/requests", params=params)
    assert response.status_code == 422, response.text
    assert response.json()["details"][0]["field"] == field
    assert response.json()["details"][0]["reason"]


def test_mine(client: TestClient, data: Seed) -> None:
    assert set(ids(listing(client, mine="true"))) == set(data.ids[::2])
    assert set(ids(listing(client, mine="false"))) == set(data.ids)


def test_combined_paging(client: TestClient, data: Seed) -> None:
    params = dict(
        status="submitted",
        q="needle",
        sort="total_desc",
        limit=2,
        branch_id=str(data.branch),
        mine="false",
    )
    first = listing(client, **params)
    assert first["next_cursor"]
    second = listing(client, **params, cursor=first["next_cursor"])
    assert ids(first) + ids(second) == sorted(data.ids[2:4]) + sorted(data.ids[:2])
    assert second["next_cursor"] is None
    assert ids(listing(client, **{**params, "mine": "true"})) == [data.ids[2], data.ids[0]]


def test_search_tenant_isolation(client: TestClient, data: Seed) -> None:
    assert data.foreign not in ids(listing(client, q="Needle"))
    assert ids(listing(client, q="Needle Fresh الوفرة")) == []


def test_default_unchanged(client: TestClient, data: Seed, monkeypatch: pytest.MonkeyPatch) -> None:
    def unexpected_sql(*args: object, **kwargs: object) -> None:
        pytest.fail("The default list must retain the pre-change PostgREST path")

    monkeypatch.setattr(RequestsService, "_list_request_rows_sql", unexpected_sql)
    # Pre-change contract: all six tenant requests, newest first, ascending id on ties.
    expected = [value for start in (4, 2, 0) for value in sorted(data.ids[start : start + 2])]
    body = listing(client)
    assert ids(body) == expected
    assert body["next_cursor"] is None


@dataclass
class EligibleSeed:
    conn: psycopg.Connection
    ws: Workspace
    member: Workspace
    branch: UUID
    visible: list[str]
    hidden: str
    foreign: str


@pytest.fixture(scope="module")
def eligible_data() -> Iterator[EligibleSeed]:
    with psycopg.connect(TEST_DATABASE_URL or "", prepare_threshold=None) as conn:
        with conn.cursor() as cur:
            ws = make_workspace(cur, "p169-parity")
            member = _make_member(cur, ws.tenant_id, "p169-scoped", "branch_manager")
            branch = _make_branch(cur, ws)
            hidden_branch = _make_branch(cur, ws)
            _assign_branch(cur, ws, member, branch)
            foreign_ws = make_workspace(cur, "p169-parity-foreign")
            foreign_branch = _make_branch(cur, foreign_ws)
            requests = []
            for tenant, request_branch in (
                (ws, branch),
                (ws, branch),
                (ws, hidden_branch),
                (foreign_ws, foreign_branch),
            ):
                product = make_workspace_product(cur, tenant, name="Parity product")
                reset_role(cur)
                request = _make_request(
                    cur,
                    tenant,
                    request_branch,
                    status="approved",
                    requested_by_membership_id=(
                        member.membership_id if request_branch == branch else tenant.membership_id
                    ),
                )
                requests.append(str(request))
                # Both product names and both notes match: EXISTS must not duplicate rows.
                for _ in range(2):
                    line = _add_line_no_estimate(cur, tenant, request, product)
                    cur.execute(
                        "update purchase_request_line set note='Parity note' where id=%s",
                        (line,),
                    )
                cur.execute(
                    "insert into approval_step (tenant_id,purchase_request_id,"
                    "assigned_membership_id,source,status,decided_by_membership_id,decided_at) "
                    "values (%s,%s,%s,'owner_fallback','approved',%s,now())",
                    (tenant.tenant_id, request, tenant.membership_id, tenant.membership_id),
                )
        conn.commit()
        yield EligibleSeed(conn, ws, member, branch, requests[:2], requests[2], requests[3])
        conn.rollback()


@pytest.fixture
def eligible_client(
    eligible_data: EligibleSeed, monkeypatch: pytest.MonkeyPatch
) -> Iterator[TestClient]:
    data = eligible_data
    service = _service(data.conn, monkeypatch)
    # Exercise real enrichment rather than the generic helper's budget stub.
    monkeypatch.setattr(
        service, "_budget_status_for", RequestsService._budget_status_for.__get__(service)
    )
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[current_member] = lambda: _current_member(data.ws, data.member)
    app.dependency_overrides[bearer_token] = data.member.claims
    app.dependency_overrides[get_requests_service] = lambda: service
    with TestClient(app) as test_client:
        yield test_client


@pytest.mark.parametrize(
    "params",
    [
        {"sort": "created_asc"},
        {"mine": "true"},
        {"q": "Parity"},
        {"status": "approved"},
        {"branch_id": "assigned"},
    ],
)
def test_eligible_item_parity(
    eligible_client: TestClient, eligible_data: EligibleSeed, params: dict
) -> None:
    bare = listing(eligible_client, eligible_for_order="true")
    if "branch_id" in params:
        params = {"branch_id": str(eligible_data.branch)}
    filtered = listing(eligible_client, eligible_for_order="true", **params)
    assert set(ids(bare)) == set(eligible_data.visible)
    assert sorted(bare["items"], key=lambda item: item["id"]) == sorted(
        filtered["items"], key=lambda item: item["id"]
    )


@pytest.mark.parametrize(
    "params",
    [
        {"q": "Parity"},
        {"sort": "created_asc"},
        {"mine": "true"},
        {"eligible_for_order": "true"},
        {"eligible_for_order": "true", "q": "Parity", "sort": "created_asc", "mine": "true"},
    ],
)
def test_branch_scoped_member_isolation(
    eligible_client: TestClient, eligible_data: EligibleSeed, params: dict
) -> None:
    # The other branch has an approved, matching owner-created request. Own requests
    # intentionally bypass branch scope under the existing requester-always RLS rule.
    result = ids(listing(eligible_client, **params))
    assert set(result) == set(eligible_data.visible)
    assert eligible_data.hidden not in result
    assert eligible_data.foreign not in result


@pytest.mark.parametrize("q", ["Parity product", "Parity note"])
def test_multiple_matching_lines_appear_once(
    eligible_client: TestClient, eligible_data: EligibleSeed, q: str
) -> None:
    body = listing(eligible_client, q=q, sort="created_asc")
    assert set(ids(body)) == set(eligible_data.visible)
    assert len(body["items"]) == len(eligible_data.visible)
    assert all(len(item["lines"]) == 2 for item in body["items"])


def test_search_pages_beyond_2000_matches(client: TestClient, data: Seed) -> None:
    """The search predicate must apply before paging, without truncating matching IDs."""
    with data.conn.cursor() as cur:
        reset_role(cur)
        product = make_workspace_product(cur, data.ws, name="Bulk search product")
        cur.execute(
            "insert into purchase_request (tenant_id,branch_id,requested_by_membership_id,"
            "required_by_date,status,created_at) "
            "select %s,%s,%s,current_date+7,'draft','2026-10-01'::timestamptz "
            "from generate_series(1,2001) returning id",
            (data.ws.tenant_id, data.branch, data.ws.membership_id),
        )
        bulk_ids = sorted(str(row[0]) for row in cur.fetchall())
        cur.execute(
            "insert into purchase_request_line "
            "(tenant_id,purchase_request_id,workspace_product_id,quantity,note) "
            "select %s,id,%s,1,'bulk-only-needle' from purchase_request where id=any(%s::uuid[])",
            (data.ws.tenant_id, product, bulk_ids),
        )
    data.conn.commit()
    try:
        first = listing(client, q="bulk-only-needle", sort="created_asc", limit=1)
        assert ids(first) == bulk_ids[:1]
        assert first["next_cursor"] == _encode_cursor(1)
        last = listing(
            client,
            q="bulk-only-needle",
            sort="created_asc",
            limit=1,
            cursor=_encode_cursor(2000),
        )
        assert ids(last) == bulk_ids[-1:]
        assert last["next_cursor"] is None
    finally:
        data.conn.rollback()
        with data.conn.cursor() as cur:
            reset_role(cur)
            cur.execute("delete from purchase_request where id=any(%s::uuid[])", (bulk_ids,))
        data.conn.commit()

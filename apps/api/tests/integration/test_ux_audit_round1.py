"""Round-1 UX audit fixes (PPS-89): RFQ responses, request line order, RFQ validation."""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, timedelta
from uuid import UUID, uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient

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
    make_extracted_quotation,
    make_supplier,
)
from integration.smart_compare_helpers import committed_smart_context, member_from_workspace
from integration.test_order_tracking import _app as _orders_app
from integration.test_order_tracking import _base_order_payload, _setup_approved_request
from integration.test_purchase_requests import (
    _current_member,
    _make_branch,
    _make_member,
    _service,
)
from procurepilot_api import db
from procurepilot_api.config import get_settings
from procurepilot_api.deps import current_member
from procurepilot_api.main import app
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.orders import service as orders_service_module
from procurepilot_api.modules.requests import service as requests_service_module
from procurepilot_api.modules.requests.schemas import (
    PurchaseRequestCreate,
    PurchaseRequestLineInput,
)
from procurepilot_api.modules.rfq import service as rfq_module
from procurepilot_api.modules.rfq.service import RfqService, get_rfq_service

pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="TEST_DATABASE_URL required")


@pytest.fixture
def committing_conn() -> Iterator[psycopg.Connection]:
    """Commits, and cleans its tenants up afterwards (catalogue_helpers.connection)."""
    yield from connection()


@contextmanager
def rolled_back() -> Iterator[psycopg.Connection]:
    with db.connect(TEST_DATABASE_URL or "") as conn:
        yield conn
        conn.rollback()


@contextmanager
def api_as(
    monkeypatch: pytest.MonkeyPatch, conn: psycopg.Connection, ws: Workspace
) -> Iterator[TestClient]:
    @contextmanager
    def auth_db(*_: object) -> Iterator[psycopg.Connection]:
        yield conn

    monkeypatch.setattr(rfq_module, "_authenticated_db", auth_db)
    app.dependency_overrides[current_member] = lambda: _current_member(ws, ws)
    app.dependency_overrides[get_rfq_service] = lambda: RfqService(settings=get_settings())
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _quote_line(
    cur: psycopg.Cursor,
    ws: Workspace,
    quotation_id: UUID,
    number: int,
    text: str,
    product: UUID | None,
) -> None:
    line_id = uuid4()
    cur.execute(
        "insert into quotation_line "
        "(id,tenant_id,quotation_id,line_number,original_text,quantity,pack_count,unit_size,"
        "pack_unit,unit_price_amount,unit_price_currency) "
        "values (%s,%s,%s,%s,%s,2,1,10,'kilogram',12,'GBP')",
        (line_id, ws.tenant_id, quotation_id, number, text),
    )
    if product is not None:
        candidate_id = uuid4()
        cur.execute(
            "insert into match_candidate "
            "(id,tenant_id,quotation_line_id,candidate_workspace_product_id,confidence,reasons,"
            "rank,scoring_version) values (%s,%s,%s,%s,0.9,'{}'::jsonb,1,'test-fixture-v1')",
            (candidate_id, ws.tenant_id, line_id, product),
        )
        cur.execute(
            "insert into match_decision "
            "(tenant_id,quotation_line_id,matched_workspace_product_id,selected_match_candidate_id,"
            "outcome,is_automatic,decided_by,confidence) "
            "values (%s,%s,%s,%s,'same_product',false,%s,1)",
            (ws.tenant_id, line_id, product, candidate_id, ws.membership_id),
        )


def test_rfq_responses_show_the_suppliers_text_in_rfq_line_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """RFQ-H2: unmatched lines were only "Pending Match" and lines came in the supplier's order."""
    with rolled_back() as db_conn:
        with db_conn.cursor() as cur:
            ws = make_workspace(cur, "ux-r1-responses")
            rice = make_workspace_product(cur, ws, name="Rice bag 10 kg")
            oil = make_workspace_product(cur, ws, name="Oil tin 18 L")
            quote = make_extracted_quotation(cur, ws)  # one unmatched line: "Tomatoes case 10 kg"
            act_as(cur, ws)
            _quote_line(cur, ws, quote.quotation_id, 2, "زيت دوار الشمس تنكة 18 لتر", oil)
            _quote_line(cur, ws, quote.quotation_id, 3, "أرز بسمتي كيس 10 كجم", rice)
            cur.execute("reset role")
            rfq_id, recipient_id = uuid4(), uuid4()
            cur.execute(
                "insert into rfq "
                "(id,tenant_id,created_by_membership_id,idempotency_key,needed_by_date,status) "
                "values (%s,%s,%s,gen_random_uuid(),current_date+7,'responded')",
                (rfq_id, ws.tenant_id, ws.membership_id),
            )
            for position, product in enumerate((rice, oil)):
                cur.execute(
                    "insert into rfq_line "
                    "(tenant_id,rfq_id,workspace_product_id,quantity,position) "
                    "values (%s,%s,%s,2,%s)",
                    (ws.tenant_id, rfq_id, product, position),
                )
            cur.execute(
                "insert into rfq_recipient (id,tenant_id,rfq_id,supplier_id,status) values "
                "(%s,%s,%s,%s,'sent')",
                (recipient_id, ws.tenant_id, rfq_id, quote.supplier_id),
            )
            cur.execute(
                "insert into rfq_response (tenant_id,rfq_recipient_id,quotation_id) "
                "values (%s,%s,%s)",
                (ws.tenant_id, recipient_id, quote.quotation_id),
            )
            act_as(cur, ws)

        with api_as(monkeypatch, db_conn, ws) as client:
            response = client.get(f"/api/v1/rfq/{rfq_id}/responses")

    assert response.status_code == 200, response.text
    item = response.json()["items"][0]
    assert item["quotation_id"] == str(quote.quotation_id)
    assert [(line["original_text"], line["pending_match"]) for line in item["lines"]] == [
        ("أرز بسمتي كيس 10 كجم", False),
        ("زيت دوار الشمس تنكة 18 لتر", False),
        ("Tomatoes case 10 kg", True),
    ]


def test_a_request_keeps_its_lines_in_the_order_they_were_given(
    committing_conn: psycopg.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R1-M1: lines of one save share created_at, so reads came back in uuid order."""
    with committing_conn.cursor() as cur:
        owner = make_workspace(cur, "ux-r1-line-order")
        branch = _make_branch(cur, owner)
        products = [
            make_workspace_product(cur, owner, name=name)
            for name in (
                "Rice bag 10 kg",
                "Oil tin 18 L",
                "Sugar bag 10 kg",
                "Flour bag 45 kg",
                "Eggs 30",
            )
        ]
        reset_role(cur)
    committing_conn.commit()

    service = _service(committing_conn, monkeypatch)
    member = _current_member(owner, owner)
    created, _ = service.create_request(
        bearer_token="token",
        member=member,
        payload=PurchaseRequestCreate(
            branch_id=branch,
            required_by_date=date.today() + timedelta(days=7),
            lines=[
                PurchaseRequestLineInput(workspace_product_id=p, quantity=str(n + 1))
                for n, p in enumerate(products)
            ],
        ),
    )
    committing_conn.commit()
    # The member path reads with its own connection (it is what orders use to build a PO).
    read_back = service.get_request(bearer_token="token", member=member, request_id=created.id)

    assert [line.workspace_product_id for line in created.lines] == products
    assert [line.workspace_product_id for line in read_back.lines] == products


def _rfq_fixture(cur: psycopg.Cursor, name: str) -> tuple[Workspace, UUID, UUID, UUID]:
    ws = make_workspace(cur, name)
    rice = make_workspace_product(cur, ws, name="Rice bag 10 kg")
    oil = make_workspace_product(cur, ws, name="Oil tin 18 L")
    supplier = make_supplier(cur, ws)
    cur.execute(
        "update supplier set contact_email = 'quotes@supplier.example' where id = %s", (supplier,)
    )
    return ws, rice, oil, supplier


@pytest.mark.parametrize(
    ("days_ahead", "same_product_twice", "reason"),
    [(-1, False, "needed_by_in_past"), (7, True, "duplicate_product")],
)
@pytest.mark.parametrize("method", ["create", "update"])
def test_an_rfq_cannot_ask_for_a_past_date_or_the_same_product_twice(
    monkeypatch: pytest.MonkeyPatch,
    method: str,
    days_ahead: int,
    same_product_twice: bool,
    reason: str,
) -> None:
    """RFQ-M1, RFQ-M2: a needed-by date in the past and a repeated product were both saved."""
    with rolled_back() as db_conn:
        with db_conn.cursor() as cur:
            ws, rice, oil, supplier = _rfq_fixture(cur, "ux-r1-rfq-validation")
        valid = {
            "lines": [
                {"workspace_product_id": str(rice), "quantity": "20"},
                {"workspace_product_id": str(oil), "quantity": "10"},
            ],
            "recipient_supplier_ids": [str(supplier)],
            "needed_by_date": str(date.today() + timedelta(days=7)),
        }
        invalid = {
            **valid,
            "needed_by_date": str(date.today() + timedelta(days=days_ahead)),
            "lines": valid["lines"]
            + (
                [{"workspace_product_id": str(rice), "quantity": "5"}] if same_product_twice else []
            ),
        }
        with api_as(monkeypatch, db_conn, ws) as client:
            if method == "create":
                response = client.post(
                    "/api/v1/rfq", json=invalid, headers={"Idempotency-Key": str(uuid4())}
                )
            else:
                created = client.post(
                    "/api/v1/rfq", json=valid, headers={"Idempotency-Key": str(uuid4())}
                )
                assert created.status_code == 201, created.text
                rfq_id = created.json()["rfq"]["id"]
                response = client.put(
                    f"/api/v1/rfq/{rfq_id}", json=invalid, headers={"Idempotency-Key": str(uuid4())}
                )

    assert response.status_code == 422, response.text
    assert response.json()["details"]["reason"] == reason


@pytest.mark.parametrize("method", ["create", "update"])
def test_a_retry_after_midnight_returns_the_rfq_it_already_saved(
    monkeypatch: pytest.MonkeyPatch, method: str
) -> None:
    """Review finding: the past-date check ran before the idempotent replay lookup, so a retry of
    a save that committed with today's date, arriving after midnight, got 422 needed_by_in_past
    instead of the RFQ that already exists."""
    today = date.today()
    with rolled_back() as db_conn:
        with db_conn.cursor() as cur:
            ws, rice, oil, supplier = _rfq_fixture(cur, "ux-r1-rfq-midnight")
        body = {
            "lines": [
                {"workspace_product_id": str(rice), "quantity": "20"},
                {"workspace_product_id": str(oil), "quantity": "10"},
            ],
            "recipient_supplier_ids": [str(supplier)],
            "needed_by_date": str(today),
        }
        key = str(uuid4())
        with api_as(monkeypatch, db_conn, ws) as client:
            if method == "create":
                first = client.post("/api/v1/rfq", json=body, headers={"Idempotency-Key": key})
            else:
                created = client.post(
                    "/api/v1/rfq",
                    json={**body, "needed_by_date": str(today + timedelta(days=7))},
                    headers={"Idempotency-Key": str(uuid4())},
                )
                assert created.status_code == 201, created.text
                rfq_id = created.json()["rfq"]["id"]
                first = client.put(
                    f"/api/v1/rfq/{rfq_id}", json=body, headers={"Idempotency-Key": key}
                )
            assert first.status_code in (200, 201), first.text

            class _Tomorrow(date):
                @classmethod
                def today(cls) -> date:
                    return today + timedelta(days=1)

            monkeypatch.setattr(rfq_module, "date", _Tomorrow)
            if method == "create":
                retry = client.post("/api/v1/rfq", json=body, headers={"Idempotency-Key": key})
            else:
                retry = client.put(
                    f"/api/v1/rfq/{rfq_id}", json=body, headers={"Idempotency-Key": key}
                )
            # A new save with the same date and a fresh key is refused, as before.
            fresh = client.post(
                "/api/v1/rfq", json=body, headers={"Idempotency-Key": str(uuid4())}
            )

    assert retry.status_code == first.status_code, retry.text
    assert retry.json()["rfq"]["id"] == first.json()["rfq"]["id"]
    assert fresh.status_code == 422
    assert fresh.json()["details"]["reason"] == "needed_by_in_past"


def test_a_draft_whose_needed_by_date_has_passed_is_not_sent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """RFQ-M1: a draft saved earlier could still be emailed to suppliers with a past date."""
    with rolled_back() as db_conn:
        with db_conn.cursor() as cur:
            ws, rice, _oil, supplier = _rfq_fixture(cur, "ux-r1-rfq-send-past")
            rfq_id = uuid4()
            cur.execute(
                "insert into rfq "
                "(id,tenant_id,created_by_membership_id,idempotency_key,needed_by_date,status) "
                "values (%s,%s,%s,gen_random_uuid(),current_date-1,'draft')",
                (rfq_id, ws.tenant_id, ws.membership_id),
            )
            cur.execute(
                "insert into rfq_line (tenant_id,rfq_id,workspace_product_id,quantity) "
                "values (%s,%s,%s,20)",
                (ws.tenant_id, rfq_id, rice),
            )
            cur.execute(
                "insert into rfq_recipient (tenant_id,rfq_id,supplier_id,status) "
                "values (%s,%s,%s,'draft')",
                (ws.tenant_id, rfq_id, supplier),
            )
        with api_as(monkeypatch, db_conn, ws) as client:
            response = client.post(
                f"/api/v1/rfq/{rfq_id}/send", headers={"Idempotency-Key": str(uuid4())}
            )

    assert response.status_code == 422, response.text
    assert response.json()["details"]["reason"] == "needed_by_in_past"


def test_a_request_prepared_from_an_rfq_names_its_supplier_and_source(
    committing_conn: psycopg.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R1-H4: request, requests list and approval row never said which supplier or RFQ."""
    with committing_conn.cursor() as cur:
        ws = make_workspace(cur, "ux-r1-request-source")
        branch = _make_branch(cur, ws)
        quote = make_extracted_quotation(cur, ws)
        act_as(cur, ws)
        cur.execute(
            "update supplier set name = 'الوفرة للمواد الغذائية' where id = %s",
            (quote.supplier_id,),
        )
        reset_role(cur)
        rfq_id, recipient_id, response_id, request_id = uuid4(), uuid4(), uuid4(), uuid4()
        cur.execute(
            "insert into rfq "
            "(id,tenant_id,created_by_membership_id,idempotency_key,needed_by_date,status) "
            "values (%s,%s,%s,gen_random_uuid(),current_date+7,'converted')",
            (rfq_id, ws.tenant_id, ws.membership_id),
        )
        cur.execute(
            "insert into rfq_recipient (id,tenant_id,rfq_id,supplier_id,status) "
            "values (%s,%s,%s,%s,'sent')",
            (recipient_id, ws.tenant_id, rfq_id, quote.supplier_id),
        )
        cur.execute(
            "insert into rfq_response (id,tenant_id,rfq_recipient_id,quotation_id) "
            "values (%s,%s,%s,%s)",
            (response_id, ws.tenant_id, recipient_id, quote.quotation_id),
        )
        cur.execute(
            "insert into purchase_request (id,tenant_id,branch_id,requested_by_membership_id,"
            "required_by_date,status,source_rfq_response_id) "
            "values (%s,%s,%s,%s,current_date+7,'draft',%s)",
            (request_id, ws.tenant_id, branch, ws.membership_id, response_id),
        )
    committing_conn.commit()

    service = _service(committing_conn, monkeypatch)
    member = _current_member(ws, ws)
    expected = {
        "rfq_id": rfq_id,
        "rfq_response_id": response_id,
        "quotation_id": quote.quotation_id,
        "supplier_id": quote.supplier_id,
        "supplier_name": "الوفرة للمواد الغذائية",
    }

    detail = service.get_request(bearer_token="token", request_id=request_id)
    by_member = service.get_request(bearer_token="token", member=member, request_id=request_id)
    # List as the owner, under RLS: the superuser test client would page through every tenant's
    # requests in the shared test database and could miss this one.
    monkeypatch.setattr(
        requests_service_module,
        "authenticated_client",
        lambda _settings, _token: PsycopgSupabaseClient(committing_conn, claims=ws.claims()),
    )
    listed = service.list_requests(bearer_token="token", member=member).items

    for request in (detail, by_member, next(r for r in listed if r.id == request_id)):
        assert request.source is not None
        assert request.source.model_dump() == expected


def test_an_approver_sees_the_supplier_of_a_request_prepared_from_an_rfq(
    committing_conn: psycopg.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Review finding: RFQ tables are readable only by owners, buyers and the RFQ's creator, so a
    source read through them left the supplier blank for the approver deciding the request."""
    with committing_conn.cursor() as cur:
        ws = make_workspace(cur, "ux-r1-approver-source")
        branch = _make_branch(cur, ws)
        quote = make_extracted_quotation(cur, ws)
        act_as(cur, ws)
        cur.execute(
            "update supplier set name = 'الذهبي للتموين' where id = %s", (quote.supplier_id,)
        )
        reset_role(cur)
        approver = _make_member(cur, ws.tenant_id, f"approver-{uuid4().hex[:8]}", "approver")
        rfq_id, recipient_id, response_id, request_id = uuid4(), uuid4(), uuid4(), uuid4()
        cur.execute(
            "insert into rfq "
            "(id,tenant_id,created_by_membership_id,idempotency_key,needed_by_date,status) "
            "values (%s,%s,%s,gen_random_uuid(),current_date+7,'converted')",
            (rfq_id, ws.tenant_id, ws.membership_id),
        )
        cur.execute(
            "insert into rfq_recipient (id,tenant_id,rfq_id,supplier_id,status) "
            "values (%s,%s,%s,%s,'sent')",
            (recipient_id, ws.tenant_id, rfq_id, quote.supplier_id),
        )
        cur.execute(
            "insert into rfq_response (id,tenant_id,rfq_recipient_id,quotation_id) "
            "values (%s,%s,%s,%s)",
            (response_id, ws.tenant_id, recipient_id, quote.quotation_id),
        )
        cur.execute(
            "insert into purchase_request (id,tenant_id,branch_id,requested_by_membership_id,"
            "required_by_date,status,source_rfq_response_id) "
            "values (%s,%s,%s,%s,current_date+7,'submitted',%s)",
            (request_id, ws.tenant_id, branch, ws.membership_id, response_id),
        )
        cur.execute(
            "insert into approval_step "
            "(tenant_id,purchase_request_id,assigned_membership_id,source,status) "
            "values (%s,%s,%s,'threshold_match','pending')",
            (ws.tenant_id, request_id, approver.membership_id),
        )
    committing_conn.commit()

    service = _service(committing_conn, monkeypatch)
    # Read as the approver, under row-level security, not as the test superuser.
    monkeypatch.setattr(
        requests_service_module,
        "authenticated_client",
        lambda _settings, _token: PsycopgSupabaseClient(committing_conn, claims=approver.claims()),
    )
    approver_member = _current_member(ws, approver)
    expected_supplier = ("الذهبي للتموين", quote.supplier_id, quote.quotation_id, rfq_id)

    pending = service.list_pending_approvals(bearer_token="token", member=approver_member).items
    detail = service.get_request(
        bearer_token="token", member=approver_member, request_id=request_id
    )
    row = next(r for r in pending if r.id == request_id)
    for request in (row, detail):
        assert request.source is not None
        assert (
            request.source.supplier_name,
            request.source.supplier_id,
            request.source.quotation_id,
            request.source.rfq_id,
        ) == expected_supplier


def test_a_purchase_order_names_its_supplier(monkeypatch: pytest.MonkeyPatch) -> None:
    """R1-H3: PO-000004's page never showed «الوفرة»; order cards had no supplier either."""
    with committed_smart_context("ux-r1-po-supplier") as context:
        member = member_from_workspace(context.workspace, role=MemberRole.owner)
        app = _orders_app(monkeypatch, member)
        client = TestClient(app, raise_server_exceptions=False)
        supplier_id = context.supplier_ids[0]
        with psycopg.connect(TEST_DATABASE_URL or "") as conn:
            req_id, line_id = _setup_approved_request(conn, context.workspace, context.product_id)
            with conn.cursor() as cur:
                cur.execute("select name from supplier where id = %s", (supplier_id,))
                supplier_name = cur.fetchone()[0]

        created = client.post(
            "/api/v1/orders",
            json=_base_order_payload(supplier_id, req_id, line_id, context.product_id),
            headers={"Idempotency-Key": str(uuid4())},
        )
        assert created.status_code == 201, created.text
        order_id = created.json()["id"]
        # Reads go through PostgREST; serve them from the test database as this workspace.
        with psycopg.connect(TEST_DATABASE_URL or "", autocommit=True) as read_conn:
            monkeypatch.setattr(
                orders_service_module,
                "authenticated_client",
                lambda *_: PsycopgSupabaseClient(read_conn, claims=context.workspace.claims()),
            )
            detail = client.get(f"/api/v1/orders/{order_id}")
            listed = client.get("/api/v1/orders")

    assert created.json()["supplier_name"] == supplier_name
    assert detail.status_code == 200, detail.text
    assert detail.json()["order"]["supplier_name"] == supplier_name
    assert next(o for o in listed.json()["items"] if o["id"] == order_id)["supplier_name"] == (
        supplier_name
    )


def test_a_request_source_snapshot_cannot_be_forged() -> None:
    """The snapshot is derived from source_rfq_response_id on every write, so a member who names
    another supplier gets the response's supplier, and clearing the response clears the source."""
    with rolled_back() as conn, conn.cursor() as cur:
        ws = make_workspace(cur, "ux-r1-source-forge")
        branch = _make_branch(cur, ws)
        quote = make_extracted_quotation(cur, ws)
        other_supplier = make_supplier(cur, ws, name="Somebody Else")
        reset_role(cur)
        rfq_id, recipient_id, response_id = uuid4(), uuid4(), uuid4()
        cur.execute(
            "insert into rfq "
            "(id,tenant_id,created_by_membership_id,idempotency_key,needed_by_date,status) "
            "values (%s,%s,%s,gen_random_uuid(),current_date+7,'responded')",
            (rfq_id, ws.tenant_id, ws.membership_id),
        )
        cur.execute(
            "insert into rfq_recipient (id,tenant_id,rfq_id,supplier_id,status) "
            "values (%s,%s,%s,%s,'sent')",
            (recipient_id, ws.tenant_id, rfq_id, quote.supplier_id),
        )
        cur.execute(
            "insert into rfq_response (id,tenant_id,rfq_recipient_id,quotation_id) "
            "values (%s,%s,%s,%s)",
            (response_id, ws.tenant_id, recipient_id, quote.quotation_id),
        )
        act_as(cur, ws)
        cur.execute(
            "insert into purchase_request (tenant_id,branch_id,requested_by_membership_id,"
            "required_by_date,status,source_rfq_response_id,source_supplier_id) "
            "values (%s,%s,%s,current_date+7,'draft',%s,%s) "
            "returning id, source_rfq_id, source_quotation_id, source_supplier_id",
            (ws.tenant_id, branch, ws.membership_id, response_id, other_supplier),
        )
        request_id, snap_rfq, snap_quote, snap_supplier = cur.fetchone()
        assert (snap_rfq, snap_quote, snap_supplier) == (
            rfq_id,
            quote.quotation_id,
            quote.supplier_id,
        )
        cur.execute(
            "update purchase_request set source_rfq_response_id = null where id = %s "
            "returning source_rfq_id, source_quotation_id, source_supplier_id",
            (request_id,),
        )
        assert cur.fetchone() == (None, None, None)

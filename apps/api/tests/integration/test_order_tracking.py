"""API integration tests for order tracking and draft creation from requests (T001)."""

from __future__ import annotations

import concurrent.futures
from decimal import Decimal
from uuid import UUID, uuid4

import psycopg
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from integration.catalogue_helpers import TEST_DATABASE_URL, Workspace, act_as
from integration.quotation_helpers import PsycopgSupabaseClient
from integration.smart_compare_helpers import (
    committed_smart_context,
    member_from_workspace,
    settings_for_test_db,
)
from procurepilot_api.deps import bearer_token, current_member
from procurepilot_api.main import create_app
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.orders import service as orders_service
from procurepilot_api.modules.requests import service as requests_service

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is not set; needs a migrated local Postgres",
)


@pytest.fixture(autouse=True)
def _fresh_mutation_limiter() -> None:
    # Several tests here make five or more order mutations from one client within a minute.
    from procurepilot_api.shared.rate_limit import mutation_limiter

    mutation_limiter.reset()


def _app(monkeypatch: pytest.MonkeyPatch, member: object) -> FastAPI:
    settings = settings_for_test_db(monkeypatch)
    app = create_app(settings)
    app.dependency_overrides[current_member] = lambda: member
    app.dependency_overrides[bearer_token] = lambda: "test-token"
    return app


def _setup_approved_request(
    conn: psycopg.Connection, ws: Workspace, product_id: UUID
) -> tuple[UUID, UUID]:
    branch_id = uuid4()
    request_id = uuid4()
    line_id = uuid4()
    step_id = uuid4()

    with conn.cursor() as cur:
        cur.execute(
            "insert into branch (id,tenant_id,name,region) values (%s,%s,'Test Branch','GB')",
            (branch_id, ws.tenant_id),
        )
        cur.execute(
            "insert into purchase_request ("
            "id,tenant_id,branch_id,requested_by_membership_id,"
            "required_by_date,status,submitted_at) "
            "values (%s,%s,%s,%s,current_date + interval '7 days', 'ordered', now())",
            (request_id, ws.tenant_id, branch_id, ws.membership_id),
        )
        cur.execute(
            "insert into purchase_request_line ("
            "id,tenant_id,purchase_request_id,workspace_product_id,quantity,"
            "estimated_unit_price_amount,estimated_unit_price_currency) "
            "values (%s,%s,%s,%s,10,15.00,'USD')",
            (line_id, ws.tenant_id, request_id, product_id),
        )
        cur.execute(
            "insert into approval_step "
            "(id,tenant_id,purchase_request_id,assigned_membership_id,source,status,"
            "decided_by_membership_id,decided_at) "
            "values (%s,%s,%s,%s,'owner_fallback','approved',%s,now())",
            (step_id, ws.tenant_id, request_id, ws.membership_id, ws.membership_id),
        )
        conn.commit()
    return request_id, line_id


def _base_order_payload(
    supplier_id: UUID, req_id: UUID, line_id: UUID, product_id: UUID, qty: str = "5"
) -> dict[str, object]:
    amount_str = f"{Decimal(qty) * Decimal('12.50'):.2f}"
    return {
        "order_number": f"PO-{uuid4().hex[:8]}",
        "supplier_id": str(supplier_id),
        "order_date": "2026-09-30",
        "source_kind": "manual",
        "source_reference": f"test:{uuid4().hex[:8]}",
        "source_request_id": str(req_id),
        "total": {"amount": amount_str, "currency": "USD"},
        "tax": {"amount": "0.00", "currency": "USD"},
        "lines": [
            {
                "line_number": 1,
                "workspace_product_id": str(product_id),
                "description": "Test product",
                "ordered_quantity": qty,
                "base_unit": "each",
                "unit_price": {"amount": "12.50", "currency": "USD"},
                "tax": {"amount": "0.00", "currency": "USD"},
                "line_total": {"amount": amount_str, "currency": "USD"},
                "source_request_line_id": str(line_id),
            }
        ],
    }


def test_create_draft_from_approved_request(monkeypatch: pytest.MonkeyPatch) -> None:
    with committed_smart_context("order-draft") as context:
        member = member_from_workspace(context.workspace, role=MemberRole.owner)
        app = _app(monkeypatch, member)
        client = TestClient(app, raise_server_exceptions=False)

        with psycopg.connect(TEST_DATABASE_URL) as conn:
            req_id, line_id = _setup_approved_request(conn, context.workspace, context.product_id)

        payload = _base_order_payload(context.supplier_ids[0], req_id, line_id, context.product_id)

        headers = {"Idempotency-Key": str(uuid4())}
        res = client.post("/api/v1/orders", json=payload, headers=headers)

        assert res.status_code == 201, res.text
        data = res.json()
        assert data["status"] == "draft"
        assert data["source_request_id"] == str(req_id)
        assert data["total"]["amount"] == "62.50"

        with psycopg.connect(TEST_DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute("select status from purchase_request where id = %s", (req_id,))
                assert cur.fetchone()[0] == "ordered"


def test_request_withdrawn_after_approval_cannot_become_an_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with committed_smart_context("order-withdrawn") as context:
        member = member_from_workspace(context.workspace, role=MemberRole.owner)
        app = _app(monkeypatch, member)
        client = TestClient(app, raise_server_exceptions=False)

        with psycopg.connect(TEST_DATABASE_URL) as conn:
            req_id, line_id = _setup_approved_request(conn, context.workspace, context.product_id)
            with conn.cursor() as cur:
                cur.execute(
                    "update purchase_request set status = 'withdrawn', withdrawn_at = now() "
                    "where id = %s",
                    (req_id,),
                )
            conn.commit()

        eligible = client.get("/api/v1/requests", params={"eligible_for_order": "true"})
        assert eligible.status_code == 200, eligible.text
        assert str(req_id) not in {item["id"] for item in eligible.json()["items"]}

        payload = _base_order_payload(context.supplier_ids[0], req_id, line_id, context.product_id)
        res = client.post("/api/v1/orders", json=payload, headers={"Idempotency-Key": str(uuid4())})
        assert res.status_code == 422, res.text
        assert res.json()["details"]["reason"] == "request_not_approved"


def test_approved_request_list_item_can_create_and_edit_linked_draft_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with committed_smart_context("order-request-edit") as context:
        member = member_from_workspace(context.workspace, role=MemberRole.owner)
        app = _app(monkeypatch, member)
        client = TestClient(app, raise_server_exceptions=False)

        with psycopg.connect(TEST_DATABASE_URL) as conn:
            req_id, line_id = _setup_approved_request(conn, context.workspace, context.product_id)

            act_as(conn, context.workspace)
            monkeypatch.setattr(
                requests_service,
                "authenticated_client",
                lambda _settings, _bearer_token: PsycopgSupabaseClient(conn),
            )

            res_requests = client.get("/api/v1/requests")
            assert res_requests.status_code == 200, res_requests.text
            listed = {item["id"]: item for item in res_requests.json()["items"]}
            assert listed[str(req_id)]["status"] == "ordered"
            assert listed[str(req_id)]["approval_step"]["status"] == "approved"

        payload = _base_order_payload(context.supplier_ids[0], req_id, line_id, context.product_id)
        res_create = client.post(
            "/api/v1/orders", json=payload, headers={"Idempotency-Key": str(uuid4())}
        )
        assert res_create.status_code == 201, res_create.text
        order = res_create.json()
        assert order["source_request_id"] == str(req_id)
        assert order["lines"][0]["source_request_line_id"] == str(line_id)

        edit_payload = _base_order_payload(
            context.supplier_ids[0], req_id, line_id, context.product_id, qty="7"
        )
        edit_payload["order_number"] = order["order_number"]
        res_edit = client.put(
            f"/api/v1/orders/{order['id']}",
            json=edit_payload,
            headers={"Idempotency-Key": str(uuid4())},
        )
        assert res_edit.status_code == 200, res_edit.text
        edited = res_edit.json()
        assert edited["source_request_id"] == str(req_id)
        assert edited["lines"][0]["source_request_line_id"] == str(line_id)
        assert edited["lines"][0]["ordered_quantity"] == "7.000000"


def test_request_list_says_whether_anything_is_left_to_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with committed_smart_context("order-request-remaining") as context:
        member = member_from_workspace(context.workspace, role=MemberRole.owner)
        client = TestClient(_app(monkeypatch, member), raise_server_exceptions=False)

        with psycopg.connect(TEST_DATABASE_URL) as conn:
            req_id, line_id = _setup_approved_request(conn, context.workspace, context.product_id)

        def assert_remaining(expected: bool) -> None:
            with psycopg.connect(TEST_DATABASE_URL) as conn:
                act_as(conn, context.workspace)
                monkeypatch.setattr(
                    requests_service,
                    "authenticated_client",
                    lambda _settings, _bearer_token: PsycopgSupabaseClient(conn),
                )
                response = client.get("/api/v1/requests")
                assert response.status_code == 200, response.text
                listed = {item["id"]: item for item in response.json()["items"]}
                assert listed[str(req_id)]["has_quantity_to_order"] is expected

        assert_remaining(True)
        for quantity, expected in (("4", True), ("6", False)):
            response = client.post(
                "/api/v1/orders",
                json=_base_order_payload(
                    context.supplier_ids[0], req_id, line_id, context.product_id, qty=quantity
                ),
                headers={"Idempotency-Key": str(uuid4())},
            )
            assert response.status_code == 201, response.text
            order_id = response.json()["id"]
            assert_remaining(expected)

        response = client.post(
            f"/api/v1/orders/{order_id}/cancel",
            headers={"Idempotency-Key": str(uuid4())},
        )
        assert response.status_code == 200, response.text
        assert_remaining(True)


def test_reject_ordered_status_without_approval_proof(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with committed_smart_context("order-no-approval") as context:
        member = member_from_workspace(context.workspace, role=MemberRole.owner)
        app = _app(monkeypatch, member)
        client = TestClient(app, raise_server_exceptions=False)

        branch_id = uuid4()
        req_id = uuid4()
        line_id = uuid4()
        with psycopg.connect(TEST_DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "insert into branch (id,tenant_id,name,region) "
                    "values (%s,%s,'Test Branch','GB')",
                    (branch_id, context.workspace.tenant_id),
                )
                cur.execute(
                    "insert into purchase_request ("
                    "id,tenant_id,branch_id,requested_by_membership_id,"
                    "required_by_date,status,submitted_at) "
                    "values (%s,%s,%s,%s,current_date + interval '7 days', 'ordered', now())",
                    (
                        req_id,
                        context.workspace.tenant_id,
                        branch_id,
                        context.workspace.membership_id,
                    ),
                )
                cur.execute(
                    "insert into purchase_request_line "
                    "(id,tenant_id,purchase_request_id,workspace_product_id,quantity) "
                    "values (%s,%s,%s,%s,10)",
                    (line_id, context.workspace.tenant_id, req_id, context.product_id),
                )
                conn.commit()

        payload = _base_order_payload(context.supplier_ids[0], req_id, line_id, context.product_id)

        res = client.post("/api/v1/orders", json=payload, headers={"Idempotency-Key": str(uuid4())})
        assert res.status_code in (
            400,
            422,
            403,
        ), f"Should reject because no approval_step exists: {res.text}"


def test_idempotent_draft_editing_and_allocation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with committed_smart_context("order-edit") as context:
        member = member_from_workspace(context.workspace, role=MemberRole.owner)
        app = _app(monkeypatch, member)
        client = TestClient(app, raise_server_exceptions=False)

        with psycopg.connect(TEST_DATABASE_URL) as conn:
            req_id, line_id = _setup_approved_request(conn, context.workspace, context.product_id)

        payload = _base_order_payload(context.supplier_ids[0], req_id, line_id, context.product_id)
        headers = {"Idempotency-Key": str(uuid4())}
        res_create = client.post("/api/v1/orders", json=payload, headers=headers)

        assert res_create.status_code == 201, res_create.text
        order_id = res_create.json()["id"]

        edit_payload = _base_order_payload(
            context.supplier_ids[0], req_id, line_id, context.product_id, qty="8"
        )
        edit_headers = {"Idempotency-Key": str(uuid4())}
        res_edit1 = client.put(
            f"/api/v1/orders/{order_id}", json=edit_payload, headers=edit_headers
        )
        assert res_edit1.status_code == 200, res_edit1.text

        res_edit2 = client.put(
            f"/api/v1/orders/{order_id}", json=edit_payload, headers=edit_headers
        )
        assert res_edit2.status_code == 200, res_edit2.text

        over_payload = _base_order_payload(
            context.supplier_ids[0], req_id, line_id, context.product_id, qty="11"
        )
        res_over = client.put(
            f"/api/v1/orders/{order_id}",
            json=over_payload,
            headers={"Idempotency-Key": str(uuid4())},
        )
        assert res_over.status_code in (
            400,
            409,
            422,
        ), "Should reject over-allocation"


def test_allocations_list_the_requests_purchase_orders(monkeypatch: pytest.MonkeyPatch) -> None:
    with committed_smart_context("order-allocation-list") as context:
        member = member_from_workspace(context.workspace, role=MemberRole.owner)
        client = TestClient(_app(monkeypatch, member), raise_server_exceptions=False)

        with psycopg.connect(TEST_DATABASE_URL) as conn:
            req_id, line_id = _setup_approved_request(conn, context.workspace, context.product_id)

        allocation_url = f"/api/v1/orders/allocations?source_request_id={req_id}"
        initial = client.get(allocation_url)
        assert initial.status_code == 200, initial.text
        assert initial.json()["orders"] == []
        assert Decimal(initial.json()["lines"][0]["remaining_quantity"]) == Decimal("10")

        expected_orders: list[dict[str, str]] = []
        for quantity, remaining in (("4", "6"), ("6", "0")):
            payload = _base_order_payload(
                context.supplier_ids[0], req_id, line_id, context.product_id, qty=quantity
            )
            created = client.post(
                "/api/v1/orders", json=payload, headers={"Idempotency-Key": str(uuid4())}
            )
            assert created.status_code == 201, created.text
            order = created.json()
            expected_orders.append(
                {"id": order["id"], "order_number": order["order_number"], "status": "draft"}
            )
            allocation = client.get(allocation_url)
            assert allocation.status_code == 200, allocation.text
            assert allocation.json()["orders"] == expected_orders
            assert Decimal(allocation.json()["lines"][0]["remaining_quantity"]) == Decimal(
                remaining
            )

        over = client.post(
            "/api/v1/orders",
            json=_base_order_payload(
                context.supplier_ids[0], req_id, line_id, context.product_id, qty="1"
            ),
            headers={"Idempotency-Key": str(uuid4())},
        )
        assert over.status_code == 409, over.text
        assert over.json()["details"]["reason"] == "quantity_exceeds_allocation"

        cancelled = client.post(
            f"/api/v1/orders/{expected_orders[0]['id']}/cancel",
            headers={"Idempotency-Key": str(uuid4())},
        )
        assert cancelled.status_code == 200, cancelled.text
        allocation = client.get(allocation_url)
        assert allocation.status_code == 200, allocation.text
        assert allocation.json()["orders"] == expected_orders[1:]


def test_stale_edit_idempotency_retry_does_not_overwrite_newer_edit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with committed_smart_context("order-stale-edit") as context:
        member = member_from_workspace(context.workspace, role=MemberRole.owner)
        app = _app(monkeypatch, member)
        client = TestClient(app, raise_server_exceptions=False)

        with psycopg.connect(TEST_DATABASE_URL) as conn:
            req_id, line_id = _setup_approved_request(conn, context.workspace, context.product_id)

        payload = _base_order_payload(context.supplier_ids[0], req_id, line_id, context.product_id)
        res_create = client.post(
            "/api/v1/orders", json=payload, headers={"Idempotency-Key": str(uuid4())}
        )
        assert res_create.status_code == 201, res_create.text
        order_id = res_create.json()["id"]

        key_first = str(uuid4())
        first_payload = _base_order_payload(
            context.supplier_ids[0], req_id, line_id, context.product_id, qty="6"
        )
        first_payload["order_number"] = payload["order_number"]
        res_first = client.put(
            f"/api/v1/orders/{order_id}",
            json=first_payload,
            headers={"Idempotency-Key": key_first},
        )
        assert res_first.status_code == 200, res_first.text

        second_payload = _base_order_payload(
            context.supplier_ids[0], req_id, line_id, context.product_id, qty="7"
        )
        second_payload["order_number"] = payload["order_number"]
        res_second = client.put(
            f"/api/v1/orders/{order_id}",
            json=second_payload,
            headers={"Idempotency-Key": str(uuid4())},
        )
        assert res_second.status_code == 200, res_second.text
        assert res_second.json()["lines"][0]["ordered_quantity"] == "7.000000"

        stale_retry = client.put(
            f"/api/v1/orders/{order_id}",
            json=first_payload,
            headers={"Idempotency-Key": key_first},
        )
        assert stale_retry.status_code == 200, stale_retry.text
        assert stale_retry.json()["lines"][0]["ordered_quantity"] == "7.000000"


def test_create_order_replay_after_submit_uses_create_idempotency_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with committed_smart_context("order-create-submit-replay") as context:
        member = member_from_workspace(context.workspace, role=MemberRole.owner)
        app = _app(monkeypatch, member)
        client = TestClient(app, raise_server_exceptions=False)

        payload = _base_order_payload(context.supplier_ids[0], uuid4(), uuid4(), context.product_id)
        payload.pop("source_request_id")
        payload["lines"][0].pop("source_request_line_id")
        create_key = str(uuid4())

        res_create = client.post(
            "/api/v1/orders", json=payload, headers={"Idempotency-Key": create_key}
        )
        assert res_create.status_code == 201, res_create.text
        order_id = res_create.json()["id"]

        res_submit = client.post(
            f"/api/v1/orders/{order_id}/submit",
            headers={"Idempotency-Key": str(uuid4())},
        )
        assert res_submit.status_code == 200, res_submit.text

        replay = client.post(
            "/api/v1/orders", json=payload, headers={"Idempotency-Key": create_key}
        )
        assert replay.status_code == 200, replay.text
        assert replay.json()["id"] == order_id


def test_concurrent_allocation_limits(monkeypatch: pytest.MonkeyPatch) -> None:
    with committed_smart_context("order-concurrent") as context:
        member = member_from_workspace(context.workspace, role=MemberRole.owner)

        with psycopg.connect(TEST_DATABASE_URL) as conn:
            req_id, line_id = _setup_approved_request(conn, context.workspace, context.product_id)

        payload1 = _base_order_payload(
            context.supplier_ids[0], req_id, line_id, context.product_id, qty="8"
        )
        payload2 = _base_order_payload(
            context.supplier_ids[1], req_id, line_id, context.product_id, qty="8"
        )

        app1 = _app(monkeypatch, member)
        client1 = TestClient(app1, raise_server_exceptions=False)
        app2 = _app(monkeypatch, member)
        client2 = TestClient(app2, raise_server_exceptions=False)

        def make_request(payload: dict, local_client: TestClient) -> int:
            headers = {"Idempotency-Key": str(uuid4())}
            res = local_client.post("/api/v1/orders", json=payload, headers=headers)
            return res.status_code

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            future1 = executor.submit(make_request, payload1, client1)
            future2 = executor.submit(make_request, payload2, client2)
            results = {future1.result(), future2.result()}

        assert 201 in results, "At least one request should succeed"
        assert results != {201}, "Should reject over-allocation concurrently"


def test_cancellation_releases_unreceived_quantity_but_retains_receipts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with committed_smart_context("order-cancel") as context:
        member = member_from_workspace(context.workspace, role=MemberRole.owner)
        app = _app(monkeypatch, member)
        client = TestClient(app, raise_server_exceptions=False)

        with psycopg.connect(TEST_DATABASE_URL) as conn:
            req_id, line_id = _setup_approved_request(conn, context.workspace, context.product_id)

        payload = _base_order_payload(
            context.supplier_ids[0], req_id, line_id, context.product_id, qty="10"
        )
        res_create = client.post(
            "/api/v1/orders", json=payload, headers={"Idempotency-Key": str(uuid4())}
        )
        assert res_create.status_code == 201, res_create.text
        order = res_create.json()
        order_id = order["id"]
        order_line_id = order["lines"][0]["id"]

        # Insert a real receipt for 4 items directly into DB
        with psycopg.connect(TEST_DATABASE_URL) as conn:
            with conn.cursor() as cur:
                receipt_id = uuid4()
                cur.execute(
                    """
                    insert into delivery_receipt (
                        id,tenant_id,purchase_order_id,receipt_reference,
                        receipt_date,received_by,source_kind,source_reference
                    )
                    values (%s,%s,%s,'GRN-1',current_date,%s,'manual','test-grn')
                    """,
                    (
                        receipt_id,
                        context.workspace.tenant_id,
                        order_id,
                        context.workspace.membership_id,
                    ),
                )
                cur.execute(
                    """
                    insert into delivery_receipt_line (
                        id,tenant_id,delivery_receipt_id,purchase_order_id,
                        purchase_order_line_id,received_quantity
                    )
                    values (%s,%s,%s,%s,%s,4)
                    """,
                    (
                        uuid4(),
                        context.workspace.tenant_id,
                        receipt_id,
                        order_id,
                        order_line_id,
                    ),
                )
                conn.commit()

        res_cancel = client.post(
            f"/api/v1/orders/{order_id}/cancel",
            headers={"Idempotency-Key": str(uuid4())},
        )
        assert res_cancel.status_code == 200, res_cancel.text

        res_alloc = client.get(f"/api/v1/orders/allocations?source_request_id={req_id}")
        assert res_alloc.status_code == 200, res_alloc.text

        data = res_alloc.json()
        lines = {item["source_request_line_id"]: item for item in data.get("lines", [])}
        assert Decimal(str(lines[str(line_id)]["remaining_quantity"])) == Decimal("6.00")

        with psycopg.connect(TEST_DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "select sum(received_quantity) from delivery_receipt_line "
                    "join delivery_receipt on delivery_receipt_id = delivery_receipt.id "
                    "where delivery_receipt.purchase_order_id = %s",
                    (order_id,),
                )
                assert cur.fetchone()[0] == Decimal("4")


def test_confirmation_and_receipts_advance_stored_order_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Spec 016 US1: submitted -> confirmed -> partially_received -> received, stored."""
    with (
        committed_smart_context("order-status") as context,
        psycopg.connect(TEST_DATABASE_URL, autocommit=True) as reader,
    ):
        member = member_from_workspace(context.workspace, role=MemberRole.owner)
        client = TestClient(_app(monkeypatch, member), raise_server_exceptions=False)
        # Evidence endpoints read the order through PostgREST; serve that from Postgres as
        # the tenant so RLS still applies.
        monkeypatch.setattr(
            orders_service,
            "authenticated_client",
            lambda _settings, _bearer_token: PsycopgSupabaseClient(
                reader, claims=context.workspace.claims()
            ),
        )

        with psycopg.connect(TEST_DATABASE_URL) as conn:
            req_id, line_id = _setup_approved_request(conn, context.workspace, context.product_id)

        payload = _base_order_payload(
            context.supplier_ids[0], req_id, line_id, context.product_id, qty="10"
        )
        created = client.post(
            "/api/v1/orders", json=payload, headers={"Idempotency-Key": str(uuid4())}
        )
        assert created.status_code == 201, created.text
        order_id = created.json()["id"]
        order_line_id = created.json()["lines"][0]["id"]

        def stored_status() -> str:
            with psycopg.connect(TEST_DATABASE_URL) as conn, conn.cursor() as cur:
                cur.execute("select status::text from purchase_order where id = %s", (order_id,))
                return str(cur.fetchone()[0])

        def receive(quantity: str, reference: str, key: str | None = None) -> dict[str, object]:
            res = client.post(
                f"/api/v1/orders/{order_id}/receipts",
                json={
                    "receipt_reference": reference,
                    "receipt_date": "2026-10-01",
                    "source_reference": f"test:{reference}",
                    "lines": [
                        {"purchase_order_line_id": order_line_id, "received_quantity": quantity}
                    ],
                },
                headers={"Idempotency-Key": key or str(uuid4())},
            )
            assert res.status_code == 200, res.text
            return res.json()

        submitted = client.post(
            f"/api/v1/orders/{order_id}/submit", headers={"Idempotency-Key": str(uuid4())}
        )
        assert submitted.status_code == 200, submitted.text
        assert stored_status() == "submitted"

        confirmation_key = str(uuid4())
        confirmation_body = {
            "supplier_reference": "SO-1",
            "confirmed_at": "2026-09-30T10:00:00Z",
            "source_reference": "test:so-1",
            "lines": [{"purchase_order_line_id": order_line_id, "confirmed_quantity": "10"}],
        }
        confirmed = client.post(
            f"/api/v1/orders/{order_id}/confirmations",
            json=confirmation_body,
            headers={"Idempotency-Key": confirmation_key},
        )
        assert confirmed.status_code == 200, confirmed.text
        assert confirmed.json()["order"]["status"] == "confirmed"
        assert confirmed.json()["lifecycle"]["status"] == "confirmed"
        assert stored_status() == "confirmed"

        first_receipt_key = str(uuid4())
        partial = receive("4", "GRN-1", first_receipt_key)
        assert partial["order"]["status"] == "partially_received"
        assert stored_status() == "partially_received"
        # A retried receipt is the same receipt: still 4 received, not 8.
        retried = receive("4", "GRN-1", first_receipt_key)
        assert len(retried["receipts"]) == 1
        assert Decimal(str(retried["lifecycle"]["lines"][0]["received"]["quantity"])) == 4

        # Replaying the confirmation after a delivery must not move the order backwards.
        replay = client.post(
            f"/api/v1/orders/{order_id}/confirmations",
            json=confirmation_body,
            headers={"Idempotency-Key": confirmation_key},
        )
        assert replay.status_code == 200, replay.text
        assert stored_status() == "partially_received"

        complete = receive("6", "GRN-2")
        assert complete["order"]["status"] == "received"
        assert complete["lifecycle"]["status"] == "received"
        assert stored_status() == "received"

        refused = client.post(
            f"/api/v1/orders/{order_id}/cancel", headers={"Idempotency-Key": str(uuid4())}
        )
        assert refused.status_code == 409, refused.text
        assert refused.json()["details"]["reason"] == "order_not_cancellable"

        with psycopg.connect(TEST_DATABASE_URL) as conn, conn.cursor() as cur:
            cur.execute(
                "select count(*) from audit_event where action = %s and tenant_id = %s",
                ("orders.purchase_order_status_changed", context.workspace.tenant_id),
            )
            assert cur.fetchone()[0] == 3


def test_cross_tenant_and_role_rejections(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with (
        committed_smart_context("order-tenant-a") as context_a,
        committed_smart_context("order-tenant-b") as context_b,
    ):
        with psycopg.connect(TEST_DATABASE_URL) as conn:
            req_id_a, line_id_a = _setup_approved_request(
                conn, context_a.workspace, context_a.product_id
            )

        member_b = member_from_workspace(context_b.workspace, role=MemberRole.owner)
        app_b = _app(monkeypatch, member_b)
        client_b = TestClient(app_b, raise_server_exceptions=False)

        payload_b = _base_order_payload(
            context_b.supplier_ids[0], req_id_a, line_id_a, context_a.product_id
        )
        res_b = client_b.post(
            "/api/v1/orders", json=payload_b, headers={"Idempotency-Key": str(uuid4())}
        )
        assert res_b.status_code == 404, (
            f"Cross-tenant request reference should return 404, got {res_b.status_code}"
        )

        member_viewer = member_from_workspace(context_a.workspace, role=MemberRole.viewer)
        app_a_viewer = _app(monkeypatch, member_viewer)
        client_a_viewer = TestClient(app_a_viewer, raise_server_exceptions=False)

        payload_viewer = _base_order_payload(
            context_a.supplier_ids[0], req_id_a, line_id_a, context_a.product_id
        )
        res_viewer = client_a_viewer.post(
            "/api/v1/orders", json=payload_viewer, headers={"Idempotency-Key": str(uuid4())}
        )
        assert res_viewer.status_code == 403, "Viewer should not be allowed to create drafts"

        member_a = member_from_workspace(context_a.workspace, role=MemberRole.owner)
        app_a = _app(monkeypatch, member_a)
        client_a = TestClient(app_a, raise_server_exceptions=False)

        invalid_line_payload = _base_order_payload(
            context_a.supplier_ids[0], req_id_a, uuid4(), context_a.product_id
        )
        res_invalid = client_a.post(
            "/api/v1/orders", json=invalid_line_payload, headers={"Idempotency-Key": str(uuid4())}
        )
        assert res_invalid.status_code in (
            400,
            404,
            422,
        ), "Should reject missing/invalid source_request_line_id"


def test_database_rejects_line_from_different_source_request() -> None:
    with committed_smart_context("order-line-integrity") as context:
        with psycopg.connect(TEST_DATABASE_URL) as conn:
            req_id_a, _line_id_a = _setup_approved_request(
                conn, context.workspace, context.product_id
            )
            _req_id_b, line_id_b = _setup_approved_request(
                conn, context.workspace, context.product_id
            )
            order_id = uuid4()
            with conn.cursor() as cur:
                cur.execute(
                    "insert into purchase_order (id,tenant_id,order_number,supplier_id,"
                    "order_date,total_amount,total_currency,tax_amount,tax_currency,"
                    "source_reference,created_by,source_request_id) "
                    "values (%s,%s,%s,%s,current_date,10,'USD',0,'USD','test',%s,%s)",
                    (
                        order_id,
                        context.workspace.tenant_id,
                        f"PO-INTEGRITY-{uuid4().hex[:8]}",
                        context.supplier_ids[0],
                        context.workspace.membership_id,
                        req_id_a,
                    ),
                )
                with pytest.raises(psycopg.errors.ForeignKeyViolation):
                    cur.execute(
                        "insert into purchase_order_line (tenant_id,purchase_order_id,"
                        "line_number,workspace_product_id,description,ordered_quantity,"
                        "base_unit,unit_price_amount,unit_price_currency,tax_amount,"
                        "tax_currency,line_total_amount,line_total_currency,"
                        "source_request_id,source_request_line_id) "
                        "values (%s,%s,1,%s,'wrong request line',1,'each',10,'USD',"
                        "0,'USD',10,'USD',%s,%s)",
                        (
                            context.workspace.tenant_id,
                            order_id,
                            context.product_id,
                            req_id_a,
                            line_id_b,
                        ),
                    )


def test_order_pack_snapshot_survives_catalogue_changes_and_refreshes_on_draft_edit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with committed_smart_context("order-pack-snapshot") as context:
        member = member_from_workspace(context.workspace, role=MemberRole.owner)
        client = TestClient(_app(monkeypatch, member), raise_server_exceptions=False)
        with psycopg.connect(TEST_DATABASE_URL) as conn:
            act_as(conn, context.workspace)
            with conn.cursor() as cur:
                cur.execute(
                    "update pack_definition set pack_count = 1, unit_size = 0.5 "
                    "where tenant_id = %s and workspace_product_id = %s",
                    (context.workspace.tenant_id, context.product_id),
                )
            conn.commit()

        payload = _base_order_payload(context.supplier_ids[0], uuid4(), uuid4(), context.product_id)
        payload.pop("source_request_id")
        payload["lines"][0].pop("source_request_line_id")
        created = client.post(
            "/api/v1/orders", json=payload, headers={"Idempotency-Key": str(uuid4())}
        )
        assert created.status_code == 201, created.text
        order = created.json()
        assert order["lines"][0]["pack_base_quantity"] == "0.500000"

        with psycopg.connect(TEST_DATABASE_URL) as conn:
            act_as(conn, context.workspace)
            with conn.cursor() as cur:
                cur.execute(
                    "update pack_definition set unit_size = 2 "
                    "where tenant_id = %s and workspace_product_id = %s",
                    (context.workspace.tenant_id, context.product_id),
                )
                cur.execute(
                    "select pack_base_quantity from purchase_order_line "
                    "where tenant_id = %s and purchase_order_id = %s",
                    (context.workspace.tenant_id, order["id"]),
                )
                assert cur.fetchone()[0] == Decimal("0.500000")
            conn.commit()

        edited = client.put(
            f"/api/v1/orders/{order['id']}",
            json=payload,
            headers={"Idempotency-Key": str(uuid4())},
        )
        assert edited.status_code == 200, edited.text
        assert edited.json()["lines"][0]["pack_base_quantity"] == "2.000000"


def test_po_creation_rechecks_request_after_concurrent_withdrawal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from procurepilot_api import db
    from procurepilot_api.modules.requests.schemas import PurchaseRequest
    from procurepilot_api.modules.requests.service import RequestsService

    with committed_smart_context("order-withdraw-race") as context:
        member = member_from_workspace(context.workspace, role=MemberRole.owner)
        app = _app(monkeypatch, member)
        with db.connect(TEST_DATABASE_URL or "") as conn:
            req_id, line_id = _setup_approved_request(conn, context.workspace, context.product_id)

        validate = RequestsService.validate_approved_request_for_order

        def withdraw_after_validation(self: RequestsService, **kwargs: object) -> PurchaseRequest:
            request = validate(self, **kwargs)
            with db.connect(TEST_DATABASE_URL or "") as conn:
                with conn.cursor() as cur:
                    act_as(cur, context.workspace)
                    cur.execute(
                        "update purchase_request set status='withdrawn', withdrawn_at=now() "
                        "where id=%s",
                        (req_id,),
                    )
            return request

        monkeypatch.setattr(
            RequestsService, "validate_approved_request_for_order", withdraw_after_validation
        )
        payload = _base_order_payload(context.supplier_ids[0], req_id, line_id, context.product_id)
        response = TestClient(app).post(
            "/api/v1/orders", json=payload, headers={"Idempotency-Key": str(uuid4())}
        )
        assert response.status_code == 409, response.text
        assert response.json()["details"]["reason"] == "request_not_approved"
        with db.connect(TEST_DATABASE_URL or "") as conn:
            count = conn.execute(
                "select count(*) from purchase_order where source_request_id=%s", (req_id,)
            ).fetchone()[0]
            assert count == 0


def test_retried_linked_create_that_used_all_remaining_quantity_returns_the_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """P-183: a lost response must not turn the retry into «quantity exceeds allocation»."""
    with committed_smart_context("order-create-replay") as context:
        member = member_from_workspace(context.workspace, role=MemberRole.owner)
        client = TestClient(_app(monkeypatch, member), raise_server_exceptions=False)
        with psycopg.connect(TEST_DATABASE_URL) as conn:
            req_id, line_id = _setup_approved_request(conn, context.workspace, context.product_id)
        payload = _base_order_payload(
            context.supplier_ids[0], req_id, line_id, context.product_id, qty="10"
        )
        key = str(uuid4())
        first = client.post("/api/v1/orders", json=payload, headers={"Idempotency-Key": key})
        assert first.status_code == 201, first.text

        retry = client.post("/api/v1/orders", json=payload, headers={"Idempotency-Key": key})

        assert retry.status_code == 200, retry.text
        assert retry.json()["id"] == first.json()["id"]


def test_linked_draft_can_move_to_another_approved_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """P-183: changing the source request must not trip the line foreign key."""
    with committed_smart_context("order-relink") as context:
        member = member_from_workspace(context.workspace, role=MemberRole.owner)
        client = TestClient(_app(monkeypatch, member), raise_server_exceptions=False)
        with psycopg.connect(TEST_DATABASE_URL) as conn:
            req_a, line_a = _setup_approved_request(conn, context.workspace, context.product_id)
            req_b, line_b = _setup_approved_request(conn, context.workspace, context.product_id)
        payload = _base_order_payload(
            context.supplier_ids[0], req_a, line_a, context.product_id, qty="4"
        )
        created = client.post(
            "/api/v1/orders", json=payload, headers={"Idempotency-Key": str(uuid4())}
        )
        assert created.status_code == 201, created.text

        moved = _base_order_payload(
            context.supplier_ids[0], req_b, line_b, context.product_id, qty="4"
        )
        moved["order_number"] = created.json()["order_number"]
        res = client.put(
            f"/api/v1/orders/{created.json()['id']}",
            json=moved,
            headers={"Idempotency-Key": str(uuid4())},
        )

        assert res.status_code == 200, res.text
        assert res.json()["source_request_id"] == str(req_b)
        assert res.json()["lines"][0]["source_request_line_id"] == str(line_b)


def _manual_payload(supplier_id: UUID, number: str, qty: str, price: str) -> dict[str, object]:
    total = f"{Decimal(qty) * Decimal(price):.2f}"
    return {
        "order_number": number,
        "supplier_id": str(supplier_id),
        "order_date": "2026-09-30",
        "source_kind": "manual",
        "source_reference": f"test:{number}",
        "total": {"amount": total, "currency": "USD"},
        "tax": {"amount": "0.00", "currency": "USD"},
        "lines": [
            {
                "line_number": 1,
                "description": "Manual line",
                "ordered_quantity": qty,
                "base_unit": "each",
                "unit_price": {"amount": price, "currency": "USD"},
                "tax": {"amount": "0.00", "currency": "USD"},
                "line_total": {"amount": total, "currency": "USD"},
            }
        ],
    }


def test_order_list_filters_searches_sorts_and_counts(monkeypatch: pytest.MonkeyPatch) -> None:
    """P-182: the list answers search, status, supplier, date, sort and total count."""
    with committed_smart_context("order-list") as context:
        member = member_from_workspace(context.workspace, role=MemberRole.owner)
        client = TestClient(_app(monkeypatch, member), raise_server_exceptions=False)
        one, two = context.supplier_ids[0], context.supplier_ids[1]
        ids: dict[str, str] = {}
        for number, supplier, qty, price in (
            ("PO-ALPHA-1", one, "2", "10.00"),
            ("PO-BRAVO-2", two, "10", "10.00"),
            ("PO-CHARLIE-3", two, "1", "10.00"),
        ):
            res = client.post(
                "/api/v1/orders",
                json=_manual_payload(supplier, number, qty, price),
                headers={"Idempotency-Key": str(uuid4())},
            )
            assert res.status_code == 201, res.text
            ids[number] = res.json()["id"]
        submitted = client.post(
            f"/api/v1/orders/{ids['PO-BRAVO-2']}/submit",
            headers={"Idempotency-Key": str(uuid4())},
        )
        assert submitted.status_code == 200, submitted.text

        def numbers(**params: object) -> list[str]:
            res = client.get("/api/v1/orders", params=params)
            assert res.status_code == 200, res.text
            return [item["order_number"] for item in res.json()["items"]]

        assert sorted(numbers()) == ["PO-ALPHA-1", "PO-BRAVO-2", "PO-CHARLIE-3"]
        assert numbers(q="alpha") == ["PO-ALPHA-1"]
        assert sorted(numbers(q="Supplier 2")) == ["PO-BRAVO-2", "PO-CHARLIE-3"]
        assert numbers(status="submitted") == ["PO-BRAVO-2"]
        assert sorted(numbers(status="draft,submitted")) == sorted(ids)
        assert sorted(numbers(status="all")) == sorted(ids)
        assert sorted(numbers(supplier_id=str(two))) == ["PO-BRAVO-2", "PO-CHARLIE-3"]
        assert numbers(date_from="2026-10-01") == []
        assert len(numbers(date_from="2026-09-30", date_to="2026-09-30")) == 3
        assert numbers(sort="total", dir="asc") == ["PO-CHARLIE-3", "PO-ALPHA-1", "PO-BRAVO-2"]
        assert numbers(sort="total", dir="desc") == ["PO-BRAVO-2", "PO-ALPHA-1", "PO-CHARLIE-3"]
        assert numbers(sort="order_number", dir="asc") == [
            "PO-ALPHA-1",
            "PO-BRAVO-2",
            "PO-CHARLIE-3",
        ]

        first = client.get(
            "/api/v1/orders", params={"limit": 2, "sort": "order_number", "dir": "asc"}
        )
        assert first.json()["total_count"] == 3
        second = client.get(
            "/api/v1/orders",
            params={
                "limit": 2,
                "sort": "order_number",
                "dir": "asc",
                "cursor": first.json()["next_cursor"],
            },
        )
        listed = [i["order_number"] for i in first.json()["items"] + second.json()["items"]]
        assert listed == ["PO-ALPHA-1", "PO-BRAVO-2", "PO-CHARLIE-3"]
        assert second.json()["next_cursor"] is None
        assert first.json()["items"][0]["supplier_name"]
        assert len(first.json()["items"][0]["lines"]) == 1


def _serve_postgrest_from_postgres(
    monkeypatch: pytest.MonkeyPatch, reader: psycopg.Connection, workspace: Workspace
) -> None:
    """Evidence endpoints read through PostgREST; serve that from Postgres as the tenant."""
    monkeypatch.setattr(
        orders_service,
        "authenticated_client",
        lambda _settings, _bearer_token: PsycopgSupabaseClient(reader, claims=workspace.claims()),
    )


def _evidence_bodies(order_line_id: str) -> tuple[dict[str, object], dict[str, object]]:
    receipt = {
        "receipt_reference": "GRN-P180",
        "receipt_date": "2026-10-01",
        "source_reference": "test:grn-p180",
        "lines": [{"purchase_order_line_id": order_line_id, "received_quantity": "3"}],
    }
    confirmation = {
        "supplier_reference": "SO-P180",
        "confirmed_at": "2026-09-30T10:00:00Z",
        "source_reference": "test:so-p180",
        "lines": [{"purchase_order_line_id": order_line_id, "confirmed_quantity": "10"}],
    }
    return receipt, confirmation


def test_receipt_that_received_nothing_is_rejected_and_leaves_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """P-180: a delivery receipt with every quantity zero must not move the order."""
    with (
        committed_smart_context("order-zero-receipt") as context,
        psycopg.connect(TEST_DATABASE_URL, autocommit=True) as reader,
    ):
        _serve_postgrest_from_postgres(monkeypatch, reader, context.workspace)
        member = member_from_workspace(context.workspace, role=MemberRole.owner)
        client = TestClient(_app(monkeypatch, member), raise_server_exceptions=False)
        with psycopg.connect(TEST_DATABASE_URL) as conn:
            req_id, line_id = _setup_approved_request(conn, context.workspace, context.product_id)
        payload = _base_order_payload(
            context.supplier_ids[0], req_id, line_id, context.product_id, qty="10"
        )
        created = client.post(
            "/api/v1/orders", json=payload, headers={"Idempotency-Key": str(uuid4())}
        )
        assert created.status_code == 201, created.text
        order_id = created.json()["id"]
        order_line_id = created.json()["lines"][0]["id"]
        submitted = client.post(
            f"/api/v1/orders/{order_id}/submit", headers={"Idempotency-Key": str(uuid4())}
        )
        assert submitted.status_code == 200, submitted.text

        receipt, _ = _evidence_bodies(order_line_id)
        receipt["lines"] = [{"purchase_order_line_id": order_line_id, "received_quantity": "0"}]
        res = client.post(
            f"/api/v1/orders/{order_id}/receipts",
            json=receipt,
            headers={"Idempotency-Key": str(uuid4())},
        )

        assert res.status_code == 422, res.text
        with psycopg.connect(TEST_DATABASE_URL) as conn, conn.cursor() as cur:
            cur.execute("select status::text from purchase_order where id = %s", (order_id,))
            assert cur.fetchone()[0] == "submitted"
            cur.execute(
                "select count(*) from delivery_receipt where purchase_order_id = %s", (order_id,)
            )
            assert cur.fetchone()[0] == 0


@pytest.mark.parametrize("state", ["draft", "cancelled"])
def test_evidence_is_refused_on_draft_and_cancelled_orders(
    monkeypatch: pytest.MonkeyPatch, state: str
) -> None:
    """P-180: receipts and confirmations only belong to orders that were sent."""
    with (
        committed_smart_context(f"order-evidence-{state}") as context,
        psycopg.connect(TEST_DATABASE_URL, autocommit=True) as reader,
    ):
        _serve_postgrest_from_postgres(monkeypatch, reader, context.workspace)
        member = member_from_workspace(context.workspace, role=MemberRole.owner)
        client = TestClient(_app(monkeypatch, member), raise_server_exceptions=False)
        with psycopg.connect(TEST_DATABASE_URL) as conn:
            req_id, line_id = _setup_approved_request(conn, context.workspace, context.product_id)
        payload = _base_order_payload(
            context.supplier_ids[0], req_id, line_id, context.product_id, qty="10"
        )
        created = client.post(
            "/api/v1/orders", json=payload, headers={"Idempotency-Key": str(uuid4())}
        )
        assert created.status_code == 201, created.text
        order_id = created.json()["id"]
        order_line_id = created.json()["lines"][0]["id"]
        if state == "cancelled":
            cancelled = client.post(
                f"/api/v1/orders/{order_id}/cancel", headers={"Idempotency-Key": str(uuid4())}
            )
            assert cancelled.status_code == 200, cancelled.text

        receipt, confirmation = _evidence_bodies(order_line_id)
        for path, body in (("receipts", receipt), ("confirmations", confirmation)):
            res = client.post(
                f"/api/v1/orders/{order_id}/{path}",
                json=body,
                headers={"Idempotency-Key": str(uuid4())},
            )
            assert res.status_code == 409, (path, res.text)
            assert res.json()["details"]["reason"] == "order_not_open_for_evidence"
        with psycopg.connect(TEST_DATABASE_URL) as conn, conn.cursor() as cur:
            cur.execute("select status::text from purchase_order where id = %s", (order_id,))
            assert cur.fetchone()[0] == state
            cur.execute(
                "select (select count(*) from delivery_receipt where purchase_order_id = %s)"
                " + (select count(*) from supplier_confirmation where purchase_order_id = %s)",
                (order_id, order_id),
            )
            assert cur.fetchone()[0] == 0


@pytest.mark.parametrize("path", ["receipts", "confirmations"])
def test_retried_evidence_after_the_order_was_cancelled_replays_instead_of_refusing(
    monkeypatch: pytest.MonkeyPatch, path: str
) -> None:
    """P-180: a lost response must stay retryable even if the order was cancelled meanwhile."""
    with (
        committed_smart_context(f"order-replay-{path}") as context,
        psycopg.connect(TEST_DATABASE_URL, autocommit=True) as reader,
    ):
        _serve_postgrest_from_postgres(monkeypatch, reader, context.workspace)
        member = member_from_workspace(context.workspace, role=MemberRole.owner)
        client = TestClient(_app(monkeypatch, member), raise_server_exceptions=False)
        with psycopg.connect(TEST_DATABASE_URL) as conn:
            req_id, line_id = _setup_approved_request(conn, context.workspace, context.product_id)
        payload = _base_order_payload(
            context.supplier_ids[0], req_id, line_id, context.product_id, qty="10"
        )
        created = client.post(
            "/api/v1/orders", json=payload, headers={"Idempotency-Key": str(uuid4())}
        )
        assert created.status_code == 201, created.text
        order_id = created.json()["id"]
        order_line_id = created.json()["lines"][0]["id"]
        submitted = client.post(
            f"/api/v1/orders/{order_id}/submit", headers={"Idempotency-Key": str(uuid4())}
        )
        assert submitted.status_code == 200, submitted.text
        receipt, confirmation = _evidence_bodies(order_line_id)
        body = receipt if path == "receipts" else confirmation
        key = str(uuid4())
        first = client.post(
            f"/api/v1/orders/{order_id}/{path}", json=body, headers={"Idempotency-Key": key}
        )
        assert first.status_code == 200, first.text
        cancelled = client.post(
            f"/api/v1/orders/{order_id}/cancel", headers={"Idempotency-Key": str(uuid4())}
        )
        assert cancelled.status_code == 200, cancelled.text

        retry = client.post(
            f"/api/v1/orders/{order_id}/{path}", json=body, headers={"Idempotency-Key": key}
        )

        assert retry.status_code == 200, retry.text
        assert retry.json()["order"]["status"] == "cancelled"
        table = "delivery_receipt" if path == "receipts" else "supplier_confirmation"
        with psycopg.connect(TEST_DATABASE_URL) as conn, conn.cursor() as cur:
            cur.execute(f"select count(*) from {table} where purchase_order_id = %s", (order_id,))
            assert cur.fetchone()[0] == 1


def test_order_list_paging_is_stable_when_an_order_is_created_between_pages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PPS-206: an offset cursor repeated a row when something newer was inserted."""
    with committed_smart_context("order-keyset") as context:
        member = member_from_workspace(context.workspace, role=MemberRole.owner)
        client = TestClient(_app(monkeypatch, member), raise_server_exceptions=False)
        supplier = context.supplier_ids[0]

        def create(number: str, qty: str = "1") -> None:
            res = client.post(
                "/api/v1/orders",
                json=_manual_payload(supplier, number, qty, "10.00"),
                headers={"Idempotency-Key": str(uuid4())},
            )
            assert res.status_code == 201, res.text

        for number in ("PO-K1", "PO-K2", "PO-K3"):
            create(number)

        first = client.get("/api/v1/orders", params={"limit": 2})  # newest first: K3, K2
        assert [i["order_number"] for i in first.json()["items"]] == ["PO-K3", "PO-K2"]

        create("PO-K4")  # newer than everything already shown

        second = client.get(
            "/api/v1/orders", params={"limit": 2, "cursor": first.json()["next_cursor"]}
        )
        assert [i["order_number"] for i in second.json()["items"]] == ["PO-K1"]
        assert second.json()["next_cursor"] is None


@pytest.mark.parametrize(
    ("sort", "direction", "expected"),
    [
        ("order_number", "asc", ["PO-S1", "PO-S2", "PO-S3"]),
        ("order_number", "desc", ["PO-S3", "PO-S2", "PO-S1"]),
        ("total", "asc", ["PO-S3", "PO-S1", "PO-S2"]),
        ("order_date", "desc", ["PO-S3", "PO-S2", "PO-S1"]),
    ],
)
def test_order_list_keyset_paging_follows_every_sort(
    monkeypatch: pytest.MonkeyPatch, sort: str, direction: str, expected: list[str]
) -> None:
    with committed_smart_context(f"order-keyset-{sort.replace('_', '-')}-{direction}") as context:
        member = member_from_workspace(context.workspace, role=MemberRole.owner)
        client = TestClient(_app(monkeypatch, member), raise_server_exceptions=False)
        for number, qty, order_date in (
            ("PO-S1", "2", "2026-09-01"),
            ("PO-S2", "9", "2026-09-02"),
            ("PO-S3", "1", "2026-09-03"),
        ):
            payload = _manual_payload(context.supplier_ids[0], number, qty, "10.00")
            payload["order_date"] = order_date
            res = client.post(
                "/api/v1/orders", json=payload, headers={"Idempotency-Key": str(uuid4())}
            )
            assert res.status_code == 201, res.text

        seen: list[str] = []
        cursor: str | None = None
        for _ in range(5):
            params: dict[str, object] = {"limit": 1, "sort": sort, "dir": direction}
            if cursor:
                params["cursor"] = cursor
            page = client.get("/api/v1/orders", params=params).json()
            seen += [i["order_number"] for i in page["items"]]
            cursor = page["next_cursor"]
            if cursor is None:
                break
        assert seen == expected


def test_order_list_refuses_a_cursor_from_another_sort_or_a_garbled_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with committed_smart_context("order-keyset-bad") as context:
        member = member_from_workspace(context.workspace, role=MemberRole.owner)
        client = TestClient(_app(monkeypatch, member), raise_server_exceptions=False)
        for number in ("PO-B1", "PO-B2"):
            client.post(
                "/api/v1/orders",
                json=_manual_payload(context.supplier_ids[0], number, "1", "10.00"),
                headers={"Idempotency-Key": str(uuid4())},
            )
        page = client.get("/api/v1/orders", params={"limit": 1, "sort": "order_number"}).json()

        other_sort = client.get(
            "/api/v1/orders", params={"limit": 1, "cursor": page["next_cursor"]}
        )
        garbled = client.get("/api/v1/orders", params={"cursor": "not-a-cursor"})

        assert other_sort.status_code == 422, other_sort.text
        assert garbled.status_code == 422, garbled.text


def test_a_short_receipt_keeps_its_line_note(monkeypatch: pytest.MonkeyPatch) -> None:
    """PPS-212: a reason for a short or damaged delivery is stored and shown with the receipt."""
    with (
        committed_smart_context("order-receipt-note") as context,
        psycopg.connect(TEST_DATABASE_URL, autocommit=True) as reader,
    ):
        _serve_postgrest_from_postgres(monkeypatch, reader, context.workspace)
        member = member_from_workspace(context.workspace, role=MemberRole.owner)
        client = TestClient(_app(monkeypatch, member), raise_server_exceptions=False)
        with psycopg.connect(TEST_DATABASE_URL) as conn:
            req_id, line_id = _setup_approved_request(conn, context.workspace, context.product_id)
        payload = _base_order_payload(
            context.supplier_ids[0], req_id, line_id, context.product_id, qty="10"
        )
        created = client.post(
            "/api/v1/orders", json=payload, headers={"Idempotency-Key": str(uuid4())}
        )
        assert created.status_code == 201, created.text
        order_id = created.json()["id"]
        order_line_id = created.json()["lines"][0]["id"]
        client.post(f"/api/v1/orders/{order_id}/submit", headers={"Idempotency-Key": str(uuid4())})

        receipt, _ = _evidence_bodies(order_line_id)
        receipt["lines"] = [
            {
                "purchase_order_line_id": order_line_id,
                "received_quantity": "3",
                "note": "  Short: the supplier ran out; two cartons arrived crushed ",
            }
        ]
        res = client.post(
            f"/api/v1/orders/{order_id}/receipts",
            json=receipt,
            headers={"Idempotency-Key": str(uuid4())},
        )
        assert res.status_code == 200, res.text
        expected = "Short: the supplier ran out; two cartons arrived crushed"
        assert res.json()["receipts"][0]["lines"][0]["note"] == expected

        fetched = client.get(f"/api/v1/orders/{order_id}")
        assert fetched.json()["receipts"][0]["lines"][0]["note"] == expected


def test_an_order_from_a_split_names_the_split_job_it_came_from(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PPS-212: the order page can link back to the basket split that produced its request."""
    with (
        committed_smart_context("order-split-link") as context,
        psycopg.connect(TEST_DATABASE_URL, autocommit=True) as reader,
    ):
        _serve_postgrest_from_postgres(monkeypatch, reader, context.workspace)
        member = member_from_workspace(context.workspace, role=MemberRole.owner)
        client = TestClient(_app(monkeypatch, member), raise_server_exceptions=False)
        with psycopg.connect(TEST_DATABASE_URL) as conn:
            req_id, line_id = _setup_approved_request(conn, context.workspace, context.product_id)
        payload = _base_order_payload(
            context.supplier_ids[0], req_id, line_id, context.product_id, qty="10"
        )
        created = client.post(
            "/api/v1/orders", json=payload, headers={"Idempotency-Key": str(uuid4())}
        )
        assert created.status_code == 201, created.text
        order_id = created.json()["id"]
        assert client.get(f"/api/v1/orders/{order_id}").json()["source_split_job_id"] is None

        job_id, group_id = uuid4(), uuid4()
        with psycopg.connect(TEST_DATABASE_URL) as conn, conn.cursor() as cur:
            # The group's own rows (RFQ, job) are not what this proves; skip their foreign keys.
            cur.execute("set local session_replication_role = replica")
            cur.execute(
                "insert into purchase_request_group (id,tenant_id,rfq_id,basket_split_job_id,"
                "branch_id,combined_total_amount,combined_total_currency,idempotency_key,"
                "created_by_membership_id) select %s,%s,%s,%s,branch_id,1,'USD',%s,%s "
                "from purchase_request where id = %s",
                (
                    group_id,
                    context.workspace.tenant_id,
                    uuid4(),
                    job_id,
                    uuid4(),
                    context.workspace.membership_id,
                    req_id,
                ),
            )
            cur.execute(
                "update purchase_request set request_group_id = %s where id = %s",
                (group_id, req_id),
            )
            conn.commit()

        fetched = client.get(f"/api/v1/orders/{order_id}")
        assert fetched.status_code == 200, fetched.text
        assert fetched.json()["source_split_job_id"] == str(job_id)

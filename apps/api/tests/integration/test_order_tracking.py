"""API integration tests for order tracking and draft creation from requests (T001)."""

from __future__ import annotations

import concurrent.futures
from decimal import Decimal
from uuid import UUID, uuid4

import psycopg
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from integration.catalogue_helpers import TEST_DATABASE_URL, Workspace
from integration.smart_compare_helpers import (
    committed_smart_context,
    member_from_workspace,
    settings_for_test_db,
)
from procurepilot_api.deps import bearer_token, current_member
from procurepilot_api.main import create_app
from procurepilot_api.modules.auth.jwt import MemberRole

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is not set; needs a migrated local Postgres",
)


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


def test_approved_request_list_item_can_create_and_edit_linked_draft_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with committed_smart_context("order-request-edit") as context:
        member = member_from_workspace(context.workspace, role=MemberRole.owner)
        app = _app(monkeypatch, member)
        client = TestClient(app, raise_server_exceptions=False)

        with psycopg.connect(TEST_DATABASE_URL) as conn:
            req_id, line_id = _setup_approved_request(conn, context.workspace, context.product_id)

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

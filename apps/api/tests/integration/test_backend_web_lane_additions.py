"""DB-backed coverage for additive APIs consumed by the web approval/PO/matching lane."""

from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from integration.catalogue_helpers import (
    TEST_DATABASE_URL,
    act_as,
)
from integration.quotation_helpers import (
    PsycopgSupabaseClient,
    ensure_quotation_reference_data,
    make_document,
    make_line,
    make_quotation,
)
from integration.smart_compare_helpers import (
    committed_smart_context,
    member_from_workspace,
    settings_for_test_db,
)
from procurepilot_api.deps import CurrentMember, bearer_token, current_member
from procurepilot_api.main import create_app
from procurepilot_api.modules.matching import service as matching_module
from procurepilot_api.modules.matching.service import MatchingService
from procurepilot_api.modules.requests import service as requests_module
from procurepilot_api.modules.rfq.service import RfqService

pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="TEST_DATABASE_URL is required")


def _app(monkeypatch: pytest.MonkeyPatch, member: CurrentMember) -> FastAPI:
    settings = settings_for_test_db(monkeypatch)
    app = create_app(settings)
    app.dependency_overrides[current_member] = lambda: member
    app.dependency_overrides[bearer_token] = lambda: "test-token"
    return app


def _add_branch(cur: object, workspace: object, name: str) -> UUID:
    branch_id = uuid4()
    cur.execute(
        "insert into branch (id,tenant_id,name,region) values (%s,%s,%s,'GB')",
        (branch_id, workspace.tenant_id, name),
    )
    return branch_id


def test_approval_queue_includes_requester_email_and_branch_budget_reasons(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with committed_smart_context("web-approval-budget", supplier_count=1) as context:
        member = member_from_workspace(context.workspace)
        with pytest.importorskip("psycopg").connect(TEST_DATABASE_URL) as conn:
            with conn.cursor() as cur:
                branches = [_add_branch(cur, context.workspace, f"Branch {i}") for i in range(2)]
                budget_id = uuid4()
                act_as(cur, context.workspace)
                cur.execute(
                    "insert into budget (id,tenant_id,amount,currency,period,period_start,scope,branch_id,created_by) "  # noqa: E501
                    "values (%s,%s,380000,'GBP','monthly','2026-10-01','branch',%s,%s)",
                    (
                        budget_id,
                        context.workspace.tenant_id,
                        branches[0],
                        context.workspace.membership_id,
                    ),
                )
                request_ids = [uuid4(), uuid4()]
                for request_id, branch_id in zip(request_ids, branches, strict=True):
                    cur.execute(
                        "insert into purchase_request (id,tenant_id,branch_id,requested_by_membership_id,"  # noqa: E501
                        "required_by_date,status,estimated_total_amount,estimated_total_currency) "
                        "values (%s,%s,%s,%s,'2026-10-10','submitted',100,'GBP')",
                        (
                            request_id,
                            context.workspace.tenant_id,
                            branch_id,
                            context.workspace.membership_id,
                        ),
                    )
                    cur.execute(
                        "insert into approval_step (tenant_id,purchase_request_id,assigned_membership_id,source,status) "  # noqa: E501
                        "values (%s,%s,%s,'owner_fallback','pending')",
                        (context.workspace.tenant_id, request_id, context.workspace.membership_id),
                    )
            client = PsycopgSupabaseClient(conn, claims=context.workspace.claims())
            monkeypatch.setattr(requests_module, "authenticated_client", lambda *_: client)
            result = requests_module.RequestsService(
                settings_for_test_db(monkeypatch)
            ).list_pending_approvals(bearer_token="test-token", member=member)
            by_id = {item.id: item for item in result.items}
            assert (
                by_id[request_ids[0]].requester_email
                == context.workspace.label + "-owner@example.test"
            )
            assert by_id[request_ids[0]].budget_status is not None
            assert by_id[request_ids[0]].budget_status.status == "within"
            assert by_id[request_ids[1]].budget_status is not None
            assert by_id[request_ids[1]].budget_status.status == "no_budget"
            assert by_id[request_ids[1]].budget_status.reason_code == "no_budget_for_branch"


def test_prepare_request_uses_rfq_needed_by_date_and_returns_draft_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with committed_smart_context("web-rfq-prepare", supplier_count=1) as context:
        settings = settings_for_test_db(monkeypatch)
        member = member_from_workspace(context.workspace)
        branch_id = uuid4()
        rfq_id, recipient_id, response_id = uuid4(), uuid4(), uuid4()
        quote_id = uuid4()
        with pytest.importorskip("psycopg").connect(TEST_DATABASE_URL) as conn:
            with conn.cursor() as cur:
                ensure_quotation_reference_data(cur)
                act_as(cur, context.workspace)
                cur.execute(
                    "insert into branch (id,tenant_id,name,region) values (%s,%s,'Maadi','GB')",
                    (branch_id, context.workspace.tenant_id),
                )
                doc_id = make_document(cur, context.workspace)
                quote_id = make_quotation(
                    cur,
                    context.workspace,
                    document_id=doc_id,
                    supplier_id=context.supplier_ids[0],
                    status="reviewed",
                    arithmetic_status="reconciled",
                )
                line_id = make_line(cur, context.workspace, quote_id)
                cur.execute(
                    "insert into rfq (id,tenant_id,created_by_membership_id,status,needed_by_date,idempotency_key) values (%s,%s,%s,'sent','2026-12-19',%s)",  # noqa: E501
                    (rfq_id, context.workspace.tenant_id, context.workspace.membership_id, uuid4()),
                )
                cur.execute(
                    "insert into rfq_line (tenant_id,rfq_id,workspace_product_id,quantity) values (%s,%s,%s,2)",  # noqa: E501
                    (context.workspace.tenant_id, rfq_id, context.product_id),
                )
                cur.execute(
                    "insert into rfq_recipient (id,tenant_id,rfq_id,supplier_id,status) values (%s,%s,%s,%s,'sent')",  # noqa: E501
                    (recipient_id, context.workspace.tenant_id, rfq_id, context.supplier_ids[0]),
                )
                # Responses are recorded by the ingestion worker as service_role (20261018000009).
                cur.execute("set local role service_role")
                cur.execute(
                    "insert into rfq_response (id,tenant_id,rfq_recipient_id,quotation_id) values (%s,%s,%s,%s)",  # noqa: E501
                    (response_id, context.workspace.tenant_id, recipient_id, quote_id),
                )
                cur.execute("set local role authenticated")
                cur.execute(
                    "insert into match_decision (tenant_id,quotation_line_id,matched_workspace_product_id,outcome,is_automatic,confidence) values (%s,%s,%s,'no_match_new_product',true,0.99)",  # noqa: E501
                    (context.workspace.tenant_id, line_id, context.product_id),
                )
            conn.commit()
            client = PsycopgSupabaseClient(conn, claims=context.workspace.claims())
            monkeypatch.setattr(requests_module, "authenticated_client", lambda *_: client)
            monkeypatch.setattr(
                requests_module.RequestsService, "_record", lambda *_args, **_kwargs: None
            )

            def insert_lines(
                _service: object,
                client: PsycopgSupabaseClient,
                *,
                tenant_id: str,
                request_id: str,
                payload_lines: list[object],
                estimates: list[object],
            ) -> list[dict[str, object]]:
                del estimates
                rows: list[dict[str, object]] = []
                for line in payload_lines:
                    rows.extend(
                        client.table("purchase_request_line")
                        .insert(
                            {
                                "tenant_id": tenant_id,
                                "purchase_request_id": request_id,
                                "workspace_product_id": str(line.workspace_product_id),
                                "quantity": line.quantity,
                            }
                        )
                        .execute()
                        .data
                    )
                return rows

            monkeypatch.setattr(requests_module.RequestsService, "_insert_lines", insert_lines)
            response = RfqService(settings).prepare_request(
                bearer_token="test-token",
                member=member,
                rfq_id=rfq_id,
                rfq_response_id=response_id,
                branch_id=branch_id,
                required_by_date=date(2026, 11, 1),
                idempotency_key=uuid4(),
            )
            assert response.purchase_request_id
            assert response.status == "draft"
            with conn.cursor() as cur:
                cur.execute(
                    "select required_by_date from purchase_request where id=%s",
                    (response.purchase_request_id,),
                )
                assert cur.fetchone()[0] == date(2026, 12, 19)


def test_orders_next_number_supplier_prefill_and_duplicate_number_conflict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with committed_smart_context("web-orders-prefill", supplier_count=1) as context:
        member = member_from_workspace(context.workspace)
        app = _app(monkeypatch, member)
        client = TestClient(app, raise_server_exceptions=False)
        branch_id, request_id, rfq_id, recipient_id, response_id = (uuid4() for _ in range(5))
        pending_request_id = uuid4()
        withdrawn_request_id = uuid4()
        with pytest.importorskip("psycopg").connect(TEST_DATABASE_URL) as conn:
            with conn.cursor() as cur:
                act_as(cur, context.workspace)
                cur.execute(
                    "insert into branch (id,tenant_id,name,region) values (%s,%s,'Order branch','GB')",  # noqa: E501
                    (branch_id, context.workspace.tenant_id),
                )
                cur.execute(
                    "insert into rfq (id,tenant_id,created_by_membership_id,status,needed_by_date,idempotency_key) values (%s,%s,%s,'converted','2026-12-01',%s)",  # noqa: E501
                    (rfq_id, context.workspace.tenant_id, context.workspace.membership_id, uuid4()),
                )
                cur.execute(
                    "insert into rfq_recipient (id,tenant_id,rfq_id,supplier_id,status) values (%s,%s,%s,%s,'sent')",  # noqa: E501
                    (recipient_id, context.workspace.tenant_id, rfq_id, context.supplier_ids[0]),
                )
                quote_id = make_quotation(
                    cur,
                    context.workspace,
                    document_id=make_document(cur, context.workspace),
                    supplier_id=context.supplier_ids[0],
                )
                # Responses are recorded by the ingestion worker as service_role (20261018000009).
                cur.execute("set local role service_role")
                cur.execute(
                    "insert into rfq_response (id,tenant_id,rfq_recipient_id,quotation_id) values (%s,%s,%s,%s)",  # noqa: E501
                    (response_id, context.workspace.tenant_id, recipient_id, quote_id),
                )
                cur.execute("set local role authenticated")
                cur.execute(
                    "insert into purchase_request (id,tenant_id,branch_id,requested_by_membership_id,required_by_date,status,source_rfq_response_id) values (%s,%s,%s,%s,'2026-12-01','ordered',%s)",  # noqa: E501
                    (
                        request_id,
                        context.workspace.tenant_id,
                        branch_id,
                        context.workspace.membership_id,
                        response_id,
                    ),
                )
                cur.execute(
                    "insert into approval_step (tenant_id,purchase_request_id,"
                    "assigned_membership_id,"
                    "source,status,decided_by_membership_id,decided_at) "
                    "values (%s,%s,%s,'owner_fallback','approved',%s,now())",
                    (
                        context.workspace.tenant_id,
                        request_id,
                        context.workspace.membership_id,
                        context.workspace.membership_id,
                    ),
                )
                cur.execute(
                    "insert into purchase_request (id,tenant_id,branch_id,"
                    "requested_by_membership_id,"
                    "required_by_date,status) values (%s,%s,%s,%s,'2026-12-01','submitted')",
                    (
                        pending_request_id,
                        context.workspace.tenant_id,
                        branch_id,
                        context.workspace.membership_id,
                    ),
                )
                # Approved, then withdrawn: the approved step stays, but it must not be orderable.
                cur.execute(
                    "insert into purchase_request (id,tenant_id,branch_id,"
                    "requested_by_membership_id,required_by_date,status,withdrawn_at) "
                    "values (%s,%s,%s,%s,'2026-12-01','withdrawn',now())",
                    (
                        withdrawn_request_id,
                        context.workspace.tenant_id,
                        branch_id,
                        context.workspace.membership_id,
                    ),
                )
                cur.execute(
                    "insert into approval_step (tenant_id,purchase_request_id,"
                    "assigned_membership_id,"
                    "source,status,decided_by_membership_id,decided_at) "
                    "values (%s,%s,%s,'owner_fallback','approved',%s,now())",
                    (
                        context.workspace.tenant_id,
                        withdrawn_request_id,
                        context.workspace.membership_id,
                        context.workspace.membership_id,
                    ),
                )
                cur.execute(
                    "insert into purchase_order (tenant_id,order_number,supplier_id,status,order_date,total_amount,total_currency,tax_amount,tax_currency,source_kind,source_reference,created_by,create_idempotency_key) values (%s,'PO-000009',%s,'draft',current_date,1,'GBP',0,'GBP','manual','fixture',%s,%s)",  # noqa: E501
                    (
                        context.workspace.tenant_id,
                        context.supplier_ids[0],
                        context.workspace.membership_id,
                        uuid4(),
                    ),
                )
            conn.commit()
            next_number = client.get("/api/v1/orders/next-number")
            assert next_number.status_code == 200
            assert next_number.json() == {"order_number": "PO-000010"}
            prefill = client.get(
                "/api/v1/orders/request-prefill", params={"source_request_id": str(request_id)}
            )
            assert prefill.status_code == 200, prefill.text
            assert prefill.json()["supplier"] == {
                "id": str(context.supplier_ids[0]),
                "name": "web-orders-prefill Supplier 1",
            }
            eligible = client.get("/api/v1/requests", params={"eligible_for_order": "true"})
            assert eligible.status_code == 200, eligible.text
            assert str(request_id) in {item["id"] for item in eligible.json()["items"]}
            assert str(pending_request_id) not in {item["id"] for item in eligible.json()["items"]}
            pending_prefill = client.get(
                "/api/v1/orders/request-prefill",
                params={"source_request_id": str(pending_request_id)},
            )
            assert pending_prefill.status_code == 422
            assert pending_prefill.json()["details"]["reason"] == "request_not_approved"
            eligible_ids = {item["id"] for item in eligible.json()["items"]}
            assert str(withdrawn_request_id) not in eligible_ids
            withdrawn_prefill = client.get(
                "/api/v1/orders/request-prefill",
                params={"source_request_id": str(withdrawn_request_id)},
            )
            assert withdrawn_prefill.status_code == 422
            assert withdrawn_prefill.json()["details"]["reason"] == "request_not_approved"
            product_id = context.product_id
            payload = {
                "order_number": "PO-000009",
                "supplier_id": str(context.supplier_ids[0]),
                "order_date": "2026-10-17",
                "source_kind": "manual",
                "source_reference": "duplicate-test",
                "total": {"amount": "1.00", "currency": "GBP"},
                "tax": {"amount": "0.00", "currency": "GBP"},
                "lines": [
                    {
                        "line_number": 1,
                        "workspace_product_id": str(product_id),
                        "description": "Product",
                        "ordered_quantity": "1",
                        "base_unit": "litre",
                        "unit_price": {"amount": "1.00", "currency": "GBP"},
                        "tax": {"amount": "0.00", "currency": "GBP"},
                        "line_total": {"amount": "1.00", "currency": "GBP"},
                    }
                ],
            }
            result = client.post(
                "/api/v1/orders", json=payload, headers={"Idempotency-Key": str(uuid4())}
            )
            assert result.status_code == 409
            assert result.json()["details"]["reason"] == "order_number_exists"


def test_resolved_match_task_has_product_and_next_open_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with committed_smart_context("web-match-next", supplier_count=1) as context:
        settings = settings_for_test_db(monkeypatch)
        member = member_from_workspace(context.workspace)
        with pytest.importorskip("psycopg").connect(TEST_DATABASE_URL) as conn:
            with conn.cursor() as cur:
                ensure_quotation_reference_data(cur)
                supplier_id = context.supplier_ids[0]
                quote_id = make_quotation(
                    cur,
                    context.workspace,
                    document_id=make_document(cur, context.workspace),
                    supplier_id=supplier_id,
                    status="reviewed",
                    arithmetic_status="reconciled",
                )
                first_line_id = make_line(cur, context.workspace, quote_id)
                second_line_id = uuid4()
                cur.execute(
                    "insert into quotation_line (id,tenant_id,quotation_id,line_number,original_text,quantity,pack_count,unit_size,pack_unit,unit_price_amount,unit_price_currency) values (%s,%s,%s,2,'Second item',2,1,10,'kilogram',12,'GBP')",  # noqa: E501
                    (second_line_id, context.workspace.tenant_id, quote_id),
                )
                line_ids = [first_line_id, second_line_id]
                act_as(cur, context.workspace)
                resolved_task, open_task = uuid4(), uuid4()
                cur.execute(
                    "insert into match_decision (tenant_id,quotation_line_id,matched_workspace_product_id,outcome,is_automatic,decided_by,confidence) values (%s,%s,%s,'no_match_new_product',false,%s,0.9)",  # noqa: E501
                    (
                        context.workspace.tenant_id,
                        line_ids[0],
                        context.product_id,
                        context.workspace.membership_id,
                    ),
                )
                cur.execute(
                    "insert into match_task (id,tenant_id,quotation_line_id,status,priority,reason,resolved_at) values (%s,%s,%s,'resolved','normal','low_confidence',now())",  # noqa: E501
                    (resolved_task, context.workspace.tenant_id, line_ids[0]),
                )
                cur.execute(
                    "insert into match_task (id,tenant_id,quotation_line_id,status,priority,reason) values (%s,%s,%s,'open','normal','no_candidate')",  # noqa: E501
                    (open_task, context.workspace.tenant_id, line_ids[1]),
                )
            conn.commit()
            db_client = PsycopgSupabaseClient(conn, claims=context.workspace.claims())
            monkeypatch.setattr(matching_module, "authenticated_client", lambda *_: db_client)
            service = MatchingService(settings)
            task_row = {
                "id": resolved_task,
                "quotation_line_id": line_ids[0],
                "status": "resolved",
                "priority": "normal",
                "reason": "low_confidence",
                "created_at": datetime.now(UTC),
                "resolved_at": datetime.now(UTC),
            }
            task = service._task(db_client, task_row)  # noqa: SLF001
            assert task.matched_product is not None
            assert task.matched_product.id == context.product_id
            from procurepilot_api.modules.matching.router import next_match_task

            next_item = next_match_task(
                "test-token", member, service, exclude_task_id=resolved_task
            )
            assert next_item.next_task_id == open_task
            assert next_item.next_quotation_line_id == line_ids[1]

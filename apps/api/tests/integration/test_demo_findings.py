"""Regression coverage using isolated, rollback-only workspaces."""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from decimal import Decimal
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient

from integration.catalogue_helpers import TEST_DATABASE_URL, act_as, make_workspace
from integration.quotation_helpers import (
    PsycopgSupabaseClient,
    make_extracted_quotation,
    make_review_task,
)
from integration.test_purchase_requests import (
    _current_member,
    _make_branch,
    _make_member,
    _make_request,
)
from procurepilot_api import db
from procurepilot_api.config import get_settings
from procurepilot_api.deps import bearer_token, current_member
from procurepilot_api.main import app
from procurepilot_api.modules.quotations import confirmation_service as confirmation_module
from procurepilot_api.modules.quotations import review_service as review_module
from procurepilot_api.modules.quotations import service as quotation_module
from procurepilot_api.modules.quotations.confirmation_service import QuotationConfirmationService
from procurepilot_api.modules.quotations.review_service import QuotationReviewService
from procurepilot_api.modules.quotations.schemas import QuotationReviewPatch
from procurepilot_api.modules.quotations.service import QuotationService
from procurepilot_api.modules.requests import service as requests_module
from procurepilot_api.modules.requests.budget_status import BudgetRow
from procurepilot_api.modules.requests.service import RequestsService, get_requests_service
from procurepilot_api.modules.rfq import service as rfq_module
from procurepilot_api.modules.rfq.service import RfqService, get_rfq_service
from procurepilot_api.shared.audit import AuditEventCreate

pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="TEST_DATABASE_URL required")


class NoopAudit:
    def record(self, event: AuditEventCreate, bearer_token: str | None = None) -> None:
        del event, bearer_token


@pytest.mark.parametrize("initial_task", ["open", "resolved", "missing"])
@pytest.mark.parametrize("via_patch", [False, True])
@pytest.mark.parametrize("decision", ["authorise", "refuse"])
def test_in_review_remains_in_inbox_until_human_decision(
    monkeypatch: pytest.MonkeyPatch, via_patch: bool, decision: str, initial_task: str
) -> None:
    with next_connection() as conn:
        with conn.cursor() as cur:
            ws = make_workspace(cur, "demo25")
            quote = make_extracted_quotation(cur, ws)
            cur.execute(
                "update quotation set status='in_review' where id=%s", (quote.quotation_id,)
            )
            if initial_task != "missing":
                make_review_task(cur, ws, quote.quotation_id, reason="low_confidence")
                if initial_task == "resolved":
                    cur.execute(
                        "update review_task set status='resolved', resolved_at=now() "
                        "where quotation_id=%s",
                        (quote.quotation_id,),
                    )
            act_as(cur, ws)
        client = PsycopgSupabaseClient(conn)
        for module in (quotation_module, review_module, confirmation_module):
            monkeypatch.setattr(module, "authenticated_client", lambda *_: client)
            monkeypatch.setattr(module, "get_audit_writer", NoopAudit)
        member = _current_member(ws, ws)
        if via_patch:
            QuotationReviewService().apply_review_patch(
                bearer_token="test",
                member=member,
                quotation_id=quote.quotation_id,
                patch=QuotationReviewPatch(reviewer_notes="Checked"),
            )
        tasks = QuotationService().list_review_tasks(bearer_token="test").items
        task = next((task for task in tasks if task.quotation_id == quote.quotation_id), None)
        assert task is not None
        assert (task.status, task.reason, task.priority) == ("open", "ready_to_authorise", "low")
        with conn.cursor() as cur:
            cur.execute("select status from quotation where id=%s", (quote.quotation_id,))
            assert cur.fetchone() == ("in_review",)
        if decision == "authorise":
            QuotationConfirmationService().confirm(
                bearer_token="test",
                member=member,
                quotation_id=quote.quotation_id,
                payload=None,
            )
        else:
            QuotationReviewService().refuse_quotation(
                bearer_token="test",
                member=member,
                quotation_id=quote.quotation_id,
                reason=None,
            )
        assert all(
            task.quotation_id != quote.quotation_id
            for task in QuotationService().list_review_tasks(bearer_token="test").items
        )
        with conn.cursor() as cur:
            cur.execute(
                "select status from review_task where quotation_id=%s", (quote.quotation_id,)
            )
            assert all(row == ("resolved",) for row in cur.fetchall())


@contextmanager
def next_connection() -> Iterator[psycopg.Connection]:
    with db.connect(TEST_DATABASE_URL or "") as conn:
        yield conn
        conn.rollback()


def test_refused_rfq_reply_api_keeps_status_and_response(monkeypatch: pytest.MonkeyPatch) -> None:
    with next_connection() as conn:
        with conn.cursor() as cur:
            ws = make_workspace(cur, "demo26")
            quote = make_extracted_quotation(cur, ws)
            cur.execute("update quotation set status='refused' where id=%s", (quote.quotation_id,))
            cur.execute("delete from quotation_line where quotation_id=%s", (quote.quotation_id,))
            cur.execute("reset role")
            rfq_id, recipient_id, response_id = uuid4(), uuid4(), uuid4()
            cur.execute(
                "insert into rfq "
                "(id,tenant_id,created_by_membership_id,idempotency_key,needed_by_date,status) "
                "values (%s,%s,%s,gen_random_uuid(),current_date+7,'sent')",
                (rfq_id, ws.tenant_id, ws.membership_id),
            )
            cur.execute(
                "insert into rfq_recipient (id,tenant_id,rfq_id,supplier_id,status) values "
                "(%s,%s,%s,%s,'sent')",
                (recipient_id, ws.tenant_id, rfq_id, quote.supplier_id),
            )
            cur.execute(
                "insert into rfq_response (id,tenant_id,rfq_recipient_id,quotation_id) values "
                "(%s,%s,%s,%s)",
                (response_id, ws.tenant_id, recipient_id, quote.quotation_id),
            )
            act_as(cur, ws)

        @contextmanager
        def auth_db(*_: object) -> Iterator[psycopg.Connection]:
            yield conn

        monkeypatch.setattr(rfq_module, "_authenticated_db", auth_db)
        app.dependency_overrides[current_member] = lambda: _current_member(ws, ws)
        app.dependency_overrides[get_rfq_service] = lambda: RfqService(settings=get_settings())
        try:
            response = TestClient(app).get(f"/api/v1/rfq/{rfq_id}/responses")
            assert response.status_code == 200, response.text
            item = response.json()["items"][0]
            assert item["id"] == str(response_id)
            assert item["quotation_status"] == "refused"
            assert item["lines"] == []
        finally:
            app.dependency_overrides.clear()


@pytest.mark.parametrize(
    ("actor", "po_status", "expected"),
    [
        ("requester", None, 200),
        ("owner", None, 200),
        ("other", None, 403),
        ("requester", "draft", 409),
        ("requester", "cancelled", 200),
    ],
)
def test_ordered_withdrawal_api_and_committed_spend(
    monkeypatch: pytest.MonkeyPatch, actor: str, po_status: str | None, expected: int
) -> None:
    with next_connection() as conn:
        with conn.cursor() as cur:
            ws = make_workspace(cur, "demo30")
            requester = _make_member(cur, ws.tenant_id, f"requester-{uuid4()}", "buyer")
            other = _make_member(cur, ws.tenant_id, f"other-{uuid4()}", "buyer")
            act_as(cur, ws)
            branch = _make_branch(cur, ws)
            quote = make_extracted_quotation(cur, ws)
            request_id = _make_request(
                cur,
                ws,
                branch,
                status="ordered",
                requested_by_membership_id=requester.membership_id,
            )
            cur.execute(
                "update purchase_request set estimated_total_amount=100, "
                "estimated_total_currency='GBP', required_by_date=current_date where id=%s",
                (request_id,),
            )
            if po_status:
                cur.execute(
                    "insert into purchase_order "
                    "(tenant_id,order_number,supplier_id,status,order_date,total_amount,"
                    "total_currency,tax_currency,source_reference,created_by,source_request_id) "
                    "values (%s,%s,%s,%s,current_date,100,'GBP','GBP',%s,%s,%s)",
                    (
                        ws.tenant_id,
                        str(uuid4()),
                        quote.supplier_id,
                        po_status,
                        str(uuid4()),
                        ws.membership_id,
                        request_id,
                    ),
                )
            who = {"requester": requester, "owner": ws, "other": other}[actor]
            act_as(cur, who)
        client = PsycopgSupabaseClient(conn)
        service = RequestsService()
        monkeypatch.setattr(requests_module, "authenticated_client", lambda *_: client)
        monkeypatch.setattr(requests_module, "get_audit_writer", NoopAudit)

        @contextmanager
        def borrow_connection(*_: object) -> Iterator[psycopg.Connection]:
            yield conn

        monkeypatch.setattr(requests_module.db, "connect", borrow_connection)
        audit = []
        monkeypatch.setattr(service, "_record", lambda **kwargs: audit.append(kwargs))
        budget = BudgetRow(
            id=uuid4(),
            amount=Decimal("1000"),
            currency="GBP",
            period="monthly",
            period_start=date.today().replace(day=1),
            scope="branch",
            branch_id=branch,
            cost_centre_id=None,
        )
        before = sum(row.amount for row in service._fetch_committed_spend_rows(client, budget))
        assert before == 100
        app.dependency_overrides[current_member] = lambda: _current_member(ws, who)
        app.dependency_overrides[bearer_token] = lambda: "test"
        app.dependency_overrides[get_requests_service] = lambda: service
        try:
            response = TestClient(app).post(f"/api/v1/requests/{request_id}/withdraw")
            assert response.status_code == expected, response.text
            if expected == 200:
                assert response.json()["status"] == "withdrawn"
                assert response.json()["withdrawn_at"]
                assert (
                    sum(row.amount for row in service._fetch_committed_spend_rows(client, budget))
                    == 0
                )
                assert audit[0]["action"] == "requests.purchase_request_withdrawn"
                assert audit[0]["target"]["previous_status"] == "ordered"
            elif expected == 409:
                assert response.json()["details"]["reason"] == "purchase_order_exists"
            else:
                assert response.json()["details"]["reason"] == "not_requester"
        finally:
            app.dependency_overrides.clear()

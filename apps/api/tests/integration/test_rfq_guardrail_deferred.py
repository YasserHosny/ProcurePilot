"""Deferred guardrail evaluation race and candidate/baseline integration coverage."""

from __future__ import annotations

import os
import sys
import threading
import uuid
from datetime import date
from decimal import Decimal
from typing import Any

import psycopg
import pytest

sys.path.append(os.path.dirname(__file__))

from test_rfq_service_e2e import (  # noqa: E402
    _FakeAuthenticatedClient,
    _seed_rfq_and_responses,
    _seed_tenant,
)

from procurepilot_api.config import Settings, get_settings
from procurepilot_api.deps import CurrentMember
from procurepilot_api.errors import UnprocessableEntityError
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.ingestion.orchestrator import _evaluate_guardrails_for_rfq
from procurepilot_api.modules.quotations.review_service import QuotationReviewService
from procurepilot_api.modules.quotations.service import QuotationService
from procurepilot_api.modules.rfq.service import RfqService

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is not set; needs Postgres with the migrations applied",
)


def _baseline_and_guardrail(
    cur: psycopg.Cursor[Any],
    *,
    tenant_id: uuid.UUID,
    membership_id: uuid.UUID,
    rfq_id: uuid.UUID,
    variance: str = "0.2500",
) -> tuple[uuid.UUID, list[uuid.UUID]]:
    cur.execute("select id, workspace_product_id from rfq_line where rfq_id = %s", (rfq_id,))
    products = [row[1] for row in cur.fetchall()]
    for product_id, price in zip(products, (Decimal("15"), Decimal("25")), strict=True):
        doc_id, quotation_id, line_id, decision_id = (uuid.uuid4() for _ in range(4))
        cur.execute(
            "insert into document "
            "(id,tenant_id,storage_bucket,storage_path,mime_type,content_hash,created_by) "
            "values (%s,%s,'quotation-documents',%s,'application/pdf',%s,%s)",
            (
                doc_id,
                tenant_id,
                f"tenants/{tenant_id}/quotations/{doc_id}/history.pdf",
                f"history-{doc_id}",
                membership_id,
            ),
        )
        cur.execute(
            "insert into quotation "
            "(id,tenant_id,document_id,supplier_id,currency,status) "
            "values (%s,%s,%s,(select supplier_id from rfq_recipient where rfq_id=%s limit 1),"
            "'GBP','reviewed')",
            (quotation_id, tenant_id, doc_id, rfq_id),
        )
        cur.execute(
            "insert into quotation_line "
            "(id,tenant_id,quotation_id,line_number,original_text,quantity,"
            "unit_price_amount,unit_price_currency) values (%s,%s,%s,1,'history',1,%s,'GBP')",
            (line_id, tenant_id, quotation_id, price),
        )
        cur.execute(
            "insert into match_decision "
            "(id,tenant_id,quotation_line_id,matched_workspace_product_id,outcome,"
            "is_automatic,confidence) values (%s,%s,%s,%s,'no_match_new_product',true,1)",
            (decision_id, tenant_id, line_id, product_id),
        )
        cur.execute(
            "insert into landed_cost "
            "(id,tenant_id,quotation_line_id,match_decision_id,quantity,"
            "normalised_base_quantity,base_unit,unit_price_amount,unit_price_currency,"
            "vat_amount,vat_currency,delivery_fee_amount,delivery_fee_currency,"
            "discount_amount,discount_currency,other_charges_amount,other_charges_currency,"
            "total_amount,total_currency,raw_inputs,rule_version,valid_from) "
            "values (%s,%s,%s,%s,1,1,'each',%s,'GBP',0,'GBP',0,'GBP',0,'GBP',0,'GBP',"
            "%s,'GBP','{}','v1',now())",
            (uuid.uuid4(), tenant_id, line_id, decision_id, price, price),
        )

    branch_id = uuid.uuid4()
    cur.execute(
        "insert into branch (id,tenant_id,name) values (%s,%s,'Guardrail test branch')",
        (branch_id, tenant_id),
    )
    guardrail_id = uuid.uuid4()
    cur.execute(
        "insert into auto_preparation_guardrail "
        "(id,tenant_id,created_by_membership_id,default_branch_id,max_order_value_amount,"
        "max_order_value_currency,min_response_count,max_price_variance_pct,enabled) "
        "values (%s,%s,%s,%s,1000,'GBP',1,%s,true)",
        (guardrail_id, tenant_id, membership_id, branch_id, Decimal(variance)),
    )
    return guardrail_id, products


def _set_response_prices(
    cur: psycopg.Cursor[Any], response_id: uuid.UUID, prices: tuple[int, int]
) -> None:
    cur.execute("select quotation_id from rfq_response where id = %s", (response_id,))
    quotation_id = cur.fetchone()[0]
    cur.execute(
        "update quotation_line set unit_price_amount = %s "
        "where quotation_id = %s and line_number = 1",
        (prices[0], quotation_id),
    )
    cur.execute(
        "update quotation_line set unit_price_amount = %s "
        "where quotation_id = %s and line_number = 2",
        (prices[1], quotation_id),
    )


def _make_fixture() -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID]:
    settings = get_settings()
    with psycopg.connect(settings.database_url.get_secret_value(), prepare_threshold=None) as conn:
        with conn.cursor() as cur:
            tenant_id, user_id, membership_id = _seed_tenant(cur, email_suffix=uuid.uuid4().hex)
            rfq_id, response_a, response_b, _ = _seed_rfq_and_responses(
                cur, tenant_id, membership_id
            )
            guardrail_id, _ = _baseline_and_guardrail(
                cur,
                tenant_id=tenant_id,
                membership_id=membership_id,
                rfq_id=rfq_id,
            )
        conn.commit()
    return tenant_id, user_id, membership_id, rfq_id, response_a, response_b


def _thread_local_requests_client(
    monkeypatch: pytest.MonkeyPatch, tenant_id: uuid.UUID, user_id: uuid.UUID
) -> list[psycopg.Connection[Any]]:
    from procurepilot_api.modules.requests import service as requests_service_module
    from procurepilot_api.modules.requests.valuation import LineEstimate

    local = threading.local()
    connections: list[psycopg.Connection[Any]] = []
    lock = threading.Lock()

    def client(_settings: object, _token: str) -> _FakeAuthenticatedClient:
        conn = getattr(local, "conn", None)
        if conn is None:
            conn = psycopg.connect(get_settings().database_url.get_secret_value(), autocommit=True)
            with conn.cursor() as cur:
                cur.execute("set role authenticated")
                cur.execute(
                    "select set_config('request.jwt.claims', %s, false)",
                    (
                        f'{{"sub":"{user_id}","tenant_id":"{tenant_id}","role":"authenticated","member_role":"owner"}}',
                    ),
                )
            local.conn = conn
            with lock:
                connections.append(conn)
        return _FakeAuthenticatedClient(conn)

    monkeypatch.setattr(requests_service_module, "authenticated_client", client)
    monkeypatch.setattr(
        requests_service_module.RequestsService,
        "_estimate_products",
        lambda self, product_ids: [
            LineEstimate(
                unit_price_amount=None, unit_price_currency=None, source_landed_cost_id=None
            )
            for _ in product_ids
        ],
    )
    monkeypatch.setattr(
        requests_service_module.RequestsService, "_record", lambda self, **kwargs: None
    )
    return connections


def _complete_response(
    settings: Settings,
    *,
    tenant_id: uuid.UUID,
    rfq_id: uuid.UUID,
    response_id: uuid.UUID,
) -> None:
    """Add the missing real match to the fixture's initially pending response."""
    with psycopg.connect(settings.database_url.get_secret_value()) as conn:
        with conn.cursor() as cur:
            cur.execute("select quotation_id from rfq_response where id = %s", (response_id,))
            quotation_id = cur.fetchone()[0]
            cur.execute(
                "select id from quotation_line where quotation_id = %s and line_number = 2",
                (quotation_id,),
            )
            line_id = cur.fetchone()[0]
            cur.execute(
                "select workspace_product_id from rfq_line where rfq_id = %s "
                "order by created_at limit 2 offset 1",
                (rfq_id,),
            )
            product_id = cur.fetchone()[0]
            cur.execute(
                "insert into match_decision "
                "(id,tenant_id,quotation_line_id,matched_workspace_product_id,outcome,"
                "is_automatic,confidence) values (%s,%s,%s,%s,'no_match_new_product',true,1)",
                (uuid.uuid4(), tenant_id, line_id, product_id),
            )
        conn.commit()


def _quotation_id(settings: Settings, response_id: uuid.UUID) -> uuid.UUID:
    with psycopg.connect(settings.database_url.get_secret_value()) as conn:
        with conn.cursor() as cur:
            cur.execute("select quotation_id from rfq_response where id = %s", (response_id,))
            return cur.fetchone()[0]


def _wire_quotation_lifecycle_services(
    monkeypatch: pytest.MonkeyPatch,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    membership_id: uuid.UUID,
) -> None:
    """Use the real quotation services while backing their authenticated client with psycopg."""
    from procurepilot_api.modules.quotations import review_service
    from procurepilot_api.modules.quotations import service as quotation_service

    conn = psycopg.connect(get_settings().database_url.get_secret_value(), autocommit=True)
    with conn.cursor() as cur:
        cur.execute("set role authenticated")
        cur.execute(
            "select set_config('request.jwt.claims', %s, false)",
            (
                f'{{"sub":"{user_id}","tenant_id":"{tenant_id}",'
                f'"role":"authenticated","member_role":"owner"}}',
            ),
        )
    def client(_settings: object, _token: str) -> _FakeAuthenticatedClient:
        return _FakeAuthenticatedClient(conn)

    monkeypatch.setattr(quotation_service, "authenticated_client", client)
    monkeypatch.setattr(review_service, "authenticated_client", client)
    monkeypatch.setattr(quotation_service, "get_audit_writer", lambda: _NoopAuditWriter())
    monkeypatch.setattr(review_service, "get_audit_writer", lambda: _NoopAuditWriter())


class _NoopAuditWriter:
    def record(self, *args: object, **kwargs: object) -> None:
        return None


def _member(
    tenant_id: uuid.UUID, user_id: uuid.UUID, membership_id: uuid.UUID
) -> CurrentMember:
    return CurrentMember(
        membership_id=membership_id,
        tenant_id=tenant_id,
        user_id=user_id,
        email="rfq-e2e@example.test",
        role=MemberRole.owner,
    )


def _latest_guardrail_job(
    settings: Settings, tenant_id: uuid.UUID, quotation_id: uuid.UUID
) -> dict[str, object]:
    with psycopg.connect(settings.database_url.get_secret_value()) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "select id, tenant_id, job_type, status, payload, attempts, max_attempts "
                "from ingestion_jobs where tenant_id = %s and job_type = 'guardrail_eval' "
                "and payload->>'quotation_id' = %s order by created_at desc limit 1",
                (tenant_id, str(quotation_id)),
            )
            row = cur.fetchone()
    assert row is not None
    return dict(
        zip(
            ("id", "tenant_id", "job_type", "status", "payload", "attempts", "max_attempts"),
            row,
            strict=True,
        )
    )


def _process_enqueued_guardrail_job(
    settings: Settings, tenant_id: uuid.UUID, quotation_id: uuid.UUID
) -> str:
    from procurepilot_api.workers.email_ingestion_worker import _process_job

    return _process_job(settings, _latest_guardrail_job(settings, tenant_id, quotation_id))


def _event_response_id(settings: Settings, tenant_id: uuid.UUID) -> uuid.UUID | None:
    with psycopg.connect(settings.database_url.get_secret_value()) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "select rfq_response_id from auto_preparation_event "
                "where tenant_id = %s order by created_at desc limit 1",
                (tenant_id,),
            )
            row = cur.fetchone()
    return row[0] if row else None


def test_archived_cheapest_response_is_never_chosen(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    tenant_id, user_id, membership_id, rfq_id, response_a, response_b = _make_fixture()
    _complete_response(settings, tenant_id=tenant_id, rfq_id=rfq_id, response_id=response_b)
    _set_response_prices_on_fixture(settings, response_a, (14, 25), response_b, (16, 30))
    _thread_local_requests_client(monkeypatch, tenant_id, user_id)
    _wire_quotation_lifecycle_services(
        monkeypatch, tenant_id=tenant_id, user_id=user_id, membership_id=membership_id
    )

    member = _member(tenant_id, user_id, membership_id)
    archived_quotation_id = _quotation_id(settings, response_a)
    QuotationService(settings).archive_quotation(
        bearer_token="unused-token", member=member, quotation_id=archived_quotation_id
    )

    with pytest.raises(UnprocessableEntityError) as exc:
        RfqService(settings).prepare_request(
            bearer_token="unused-token",
            member=member,
            rfq_id=rfq_id,
            rfq_response_id=response_a,
            branch_id=uuid.uuid4(),
            required_by_date=date.today(),
            idempotency_key=uuid.uuid4(),
        )
    assert exc.value.details == {"reason": "quotation_archived"}

    assert (
        _process_enqueued_guardrail_job(settings, tenant_id, archived_quotation_id)
        == "completed"
    )
    assert _event_response_id(settings, tenant_id) == response_b


@pytest.mark.parametrize("unblock_action", ["refuse", "archive"])
def test_refusing_or_archiving_blocking_response_unblocks_guardrail(
    monkeypatch: pytest.MonkeyPatch, unblock_action: str
) -> None:
    settings = get_settings()
    tenant_id, user_id, membership_id, rfq_id, response_a, response_b = _make_fixture()
    _set_response_prices_on_fixture(settings, response_a, (16, 30), response_b, (14, 25))
    _thread_local_requests_client(monkeypatch, tenant_id, user_id)
    _wire_quotation_lifecycle_services(
        monkeypatch, tenant_id=tenant_id, user_id=user_id, membership_id=membership_id
    )

    response_b_quotation_id = _quotation_id(settings, response_b)
    with psycopg.connect(settings.database_url.get_secret_value()) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "update quotation set status = 'in_review' where id = %s",
                (response_b_quotation_id,),
            )
        conn.commit()

    member = _member(tenant_id, user_id, membership_id)
    if unblock_action == "refuse":
        QuotationReviewService(settings).refuse_quotation(
            bearer_token="unused-token",
            member=member,
            quotation_id=response_b_quotation_id,
            reason="not selected",
        )
    else:
        QuotationService(settings).archive_quotation(
            bearer_token="unused-token", member=member, quotation_id=response_b_quotation_id
        )

    assert (
        _process_enqueued_guardrail_job(settings, tenant_id, response_b_quotation_id)
        == "completed"
    )
    assert _event_response_id(settings, tenant_id) == response_a


def test_archived_response_does_not_count_toward_minimum_response_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = get_settings()
    tenant_id, user_id, membership_id, rfq_id, response_a, response_b = _make_fixture()
    _complete_response(settings, tenant_id=tenant_id, rfq_id=rfq_id, response_id=response_b)
    _set_response_prices_on_fixture(settings, response_a, (16, 30), response_b, (14, 25))
    _thread_local_requests_client(monkeypatch, tenant_id, user_id)
    _wire_quotation_lifecycle_services(
        monkeypatch, tenant_id=tenant_id, user_id=user_id, membership_id=membership_id
    )

    with psycopg.connect(settings.database_url.get_secret_value()) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "update auto_preparation_guardrail set min_response_count = 2 "
                "where tenant_id = %s",
                (tenant_id,),
            )
        conn.commit()

    archived_quotation_id = _quotation_id(settings, response_b)
    QuotationService(settings).archive_quotation(
        bearer_token="unused-token",
        member=_member(tenant_id, user_id, membership_id),
        quotation_id=archived_quotation_id,
    )
    assert (
        _process_enqueued_guardrail_job(settings, tenant_id, archived_quotation_id)
        == "completed"
    )
    assert _event_response_id(settings, tenant_id) is None


def test_concurrent_evaluations_fire_once(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    tenant_id, user_id, membership_id, rfq_id, response_a, _ = _make_fixture()
    _thread_local_requests_client(monkeypatch, tenant_id, user_id)

    with psycopg.connect(settings.database_url.get_secret_value()) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "update quotation set status = 'refused' where id = "
                "(select response.quotation_id from rfq_response response "
                "join rfq_recipient recipient on recipient.id = response.rfq_recipient_id "
                "where recipient.rfq_id = %s and response.id <> %s)",
                (rfq_id, response_a),
            )
            cur.execute(
                "update quotation_line ql set unit_price_amount = 15.5 where ql.quotation_id = (select quotation_id from rfq_response where id = %s) and line_number = 1",  # noqa: E501
                (response_a,),
            )
            cur.execute(
                "update quotation_line ql set unit_price_amount = 25 where ql.quotation_id = (select quotation_id from rfq_response where id = %s) and line_number = 2",  # noqa: E501
                (response_a,),
            )
        conn.commit()

    barrier = threading.Barrier(2)
    errors: list[BaseException] = []

    def evaluate() -> None:
        try:
            with psycopg.connect(settings.database_url.get_secret_value()) as conn:
                with conn.cursor() as cur:
                    cur.execute("set lock_timeout = '3s'")
                    cur.execute("set statement_timeout = '3s'")
                barrier.wait(timeout=3)
                _evaluate_guardrails_for_rfq(settings, conn, tenant_id=tenant_id, rfq_id=rfq_id)
                conn.commit()
        except BaseException as exc:  # surfaced below; keeps both threads joinable
            errors.append(exc)

    threads = [threading.Thread(target=evaluate) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=8)
    assert all(not thread.is_alive() for thread in threads), "concurrent evaluation did not finish"
    assert not errors

    with psycopg.connect(settings.database_url.get_secret_value()) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "select count(*) from auto_preparation_event where tenant_id = %s", (tenant_id,)
            )
            assert cur.fetchone()[0] == 1
            cur.execute("select count(*) from purchase_request where tenant_id = %s", (tenant_id,))
            assert cur.fetchone()[0] == 1
            cur.execute(
                "select count(*) from purchase_request "
                "where tenant_id = %s and source_rfq_response_id = %s",
                (tenant_id, response_a),
            )
            assert cur.fetchone()[0] == 1
            cur.execute("select status from rfq where id = %s", (rfq_id,))
            assert cur.fetchone()[0] == "converted"


def test_pending_cheaper_response_blocks_then_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    tenant_id, user_id, membership_id, rfq_id, response_a, response_b = _make_fixture()
    _set_response_prices_on_fixture(settings, response_a, (16, 30), response_b, (14, 25))
    # No preparation should occur while response B is still pending, despite A being complete.
    with psycopg.connect(settings.database_url.get_secret_value()) as conn:
        _evaluate_guardrails_for_rfq(settings, conn, tenant_id=tenant_id, rfq_id=rfq_id)
        conn.commit()
        with conn.cursor() as cur:
            cur.execute(
                "select count(*) from auto_preparation_event where tenant_id = %s", (tenant_id,)
            )
            assert cur.fetchone()[0] == 0
            cur.execute("select status from rfq where id = %s", (rfq_id,))
            assert cur.fetchone()[0] == "responded"

    # Complete B's second match, then evaluate through the real preparation path.
    from test_rfq_service_e2e import _patch_requests_service_for_test

    _patch_requests_service_for_test(
        monkeypatch, tenant_id=tenant_id, user_id=user_id, membership_id=membership_id
    )
    with psycopg.connect(settings.database_url.get_secret_value()) as conn:
        with conn.cursor() as cur:
            cur.execute("select quotation_id from rfq_response where id = %s", (response_b,))
            quotation_id = cur.fetchone()[0]
            cur.execute(
                "select id from quotation_line where quotation_id = %s and line_number = 2",
                (quotation_id,),
            )
            line_id = cur.fetchone()[0]
            cur.execute(
                "select workspace_product_id from rfq_line where rfq_id = %s order by created_at limit 2 offset 1",  # noqa: E501
                (rfq_id,),
            )
            product_id = cur.fetchone()[0]
            cur.execute(
                "insert into match_decision (id,tenant_id,quotation_line_id,matched_workspace_product_id,outcome,is_automatic,confidence) values (%s,%s,%s,%s,'no_match_new_product',true,1)",  # noqa: E501
                (uuid.uuid4(), tenant_id, line_id, product_id),
            )
        conn.commit()
    with psycopg.connect(settings.database_url.get_secret_value()) as conn:
        _evaluate_guardrails_for_rfq(settings, conn, tenant_id=tenant_id, rfq_id=rfq_id)
        conn.commit()
        with conn.cursor() as cur:
            cur.execute(
                "select rfq_response_id from auto_preparation_event where tenant_id = %s",
                (tenant_id,),
            )
            assert cur.fetchone()[0] == response_b


def _set_response_prices_on_fixture(
    settings: Settings,
    response_a: uuid.UUID,
    prices_a: tuple[int, int],
    response_b: uuid.UUID,
    prices_b: tuple[int, int],
) -> None:
    with psycopg.connect(settings.database_url.get_secret_value()) as conn:
        with conn.cursor() as cur:
            _set_response_prices(cur, response_a, prices_a)
            _set_response_prices(cur, response_b, prices_b)
        conn.commit()


def test_candidate_landed_cost_is_excluded_from_baseline() -> None:
    settings = get_settings()
    tenant_id, _, membership_id, rfq_id, response_a, _ = _make_fixture()
    with psycopg.connect(settings.database_url.get_secret_value()) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "update quotation set status = 'refused' where id = "
                "(select response.quotation_id from rfq_response response "
                "join rfq_recipient recipient on recipient.id = response.rfq_recipient_id "
                "where recipient.rfq_id = %s and response.id <> %s)",
                (rfq_id, response_a),
            )
            _set_response_prices(cur, response_a, (1000, 1000))
            cur.execute("select quotation_id from rfq_response where id = %s", (response_a,))
            quotation_id = cur.fetchone()[0]
            cur.execute(
                "select id from quotation_line where quotation_id = %s order by line_number limit 1",  # noqa: E501
                (quotation_id,),
            )
            line_id = cur.fetchone()[0]
            cur.execute(
                "select id, workspace_product_id from rfq_line where rfq_id = %s order by created_at limit 1",  # noqa: E501
                (rfq_id,),
            )
            _, product_id = cur.fetchone()
            cur.execute("select id from match_decision where quotation_line_id = %s", (line_id,))
            decision_id = cur.fetchone()[0]
            cur.execute(
                "insert into landed_cost (id,tenant_id,quotation_line_id,match_decision_id,quantity,normalised_base_quantity,base_unit,unit_price_amount,unit_price_currency,vat_amount,vat_currency,delivery_fee_amount,delivery_fee_currency,discount_amount,discount_currency,other_charges_amount,other_charges_currency,total_amount,total_currency,raw_inputs,rule_version,valid_from) values (%s,%s,%s,%s,1,1,'each',1000,'GBP',0,'GBP',0,'GBP',0,'GBP',0,'GBP',1000,'GBP','{}','v1',now())",  # noqa: E501
                (uuid.uuid4(), tenant_id, line_id, decision_id),
            )
        conn.commit()
    with psycopg.connect(settings.database_url.get_secret_value()) as conn:
        _evaluate_guardrails_for_rfq(settings, conn, tenant_id=tenant_id, rfq_id=rfq_id)
        conn.commit()
        with conn.cursor() as cur:
            cur.execute(
                "select count(*) from auto_preparation_event where tenant_id = %s", (tenant_id,)
            )
            assert cur.fetchone()[0] == 0
            cur.execute("select status from rfq where id = %s", (rfq_id,))
            assert cur.fetchone()[0] == "responded"

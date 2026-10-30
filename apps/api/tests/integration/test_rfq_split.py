"""Spec 024 US1: RFQ → queued job → real solver, with round-1 evidence."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID, uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from httpx import Response
from psycopg.rows import dict_row

from integration.catalogue_helpers import TEST_DATABASE_URL, reset_role
from integration.fixtures.round1_rfq import Round1Rfq, round1_rfq
from integration.quotation_helpers import make_line, make_quotation, make_supplier
from integration.smart_compare_helpers import member_from_workspace, settings_for_test_db
from procurepilot_api.deps import bearer_token, current_member
from procurepilot_api.main import app
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.offers import basket_service

pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="TEST_DATABASE_URL is not set")


@pytest.fixture
def queue(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, object]]:
    settings_for_test_db(monkeypatch)
    queued = []

    def enqueue(_settings: object, row: dict[str, object], _member: object) -> None:
        with psycopg.connect(TEST_DATABASE_URL or "", prepare_threshold=None) as conn:
            assert conn.execute(
                "select status from basket_split_job where id=%s", (row["id"],)
            ).fetchone() == ("queued",)
        queued.append(row)

    monkeypatch.setattr(basket_service, "_enqueue_redis_job", enqueue)
    monkeypatch.setitem(app.dependency_overrides, bearer_token, lambda: "test-token")
    return queued


def _authenticate(
    monkeypatch: pytest.MonkeyPatch, fixture: Round1Rfq, role: MemberRole = MemberRole.buyer
) -> None:
    monkeypatch.setitem(
        app.dependency_overrides,
        current_member,
        lambda: member_from_workspace(fixture.workspace, role=role),
    )


def _post(fixture: Round1Rfq, key: UUID | None = None) -> Response:
    return TestClient(app).post(
        f"/api/v1/rfq/{fixture.rfq_id}/split", headers={"Idempotency-Key": str(key or uuid4())}
    )


def _add_unrelated_price(fixture: Round1Rfq) -> None:
    """Older quotation re-costed later: latest-price must never contaminate this RFQ."""
    with psycopg.connect(TEST_DATABASE_URL or "", prepare_threshold=None) as conn:
        with conn.cursor() as cur:
            quotation_id = make_quotation(
                cur, fixture.workspace, supplier_id=fixture.supplier_ids[0], status="reviewed"
            )
            cur.execute(
                "update quotation set currency='SAR',created_at=now()-interval '30 days' "
                "where id=%s",
                (quotation_id,),
            )
            line_id = make_line(cur, fixture.workspace, quotation_id)
            decision_id = uuid4()
            cur.execute(
                "insert into match_decision (id,tenant_id,quotation_line_id,"
                "matched_workspace_product_id,outcome,is_automatic,confidence) "
                "values (%s,%s,%s,%s,'no_match_new_product',true,1)",
                (decision_id, fixture.workspace.tenant_id, line_id, fixture.product_ids[0]),
            )
            reset_role(cur)
            cur.execute(
                """
                insert into landed_cost (tenant_id,quotation_line_id,match_decision_id,quantity,
                  normalised_base_quantity,base_unit,unit_price_amount,unit_price_currency,
                  vat_amount,vat_currency,delivery_fee_amount,delivery_fee_currency,discount_amount,
                  discount_currency,other_charges_currency,total_amount,total_currency,raw_inputs,
                  rule_version,valid_from,recorded_at)
                select tenant_id,%s,%s,quantity,normalised_base_quantity,base_unit,1,'SAR',0,'SAR',
                  0,'SAR',0,'SAR','SAR',quantity,'SAR',raw_inputs,rule_version,valid_from,
                  now()+interval '1 minute' from landed_cost where quotation_line_id in (
                    select ql.id from quotation_line ql join current_match_decision md
                    on md.quotation_line_id=ql.id where ql.quotation_id=%s
                    and md.matched_workspace_product_id=%s)
                """,
                (line_id, decision_id, fixture.quotation_ids[0], fixture.product_ids[0]),
            )
        conn.commit()


@pytest.mark.parametrize("unrelated_price", [False, True])
def test_round1_split_job_and_solver_total(
    monkeypatch: pytest.MonkeyPatch,
    queue: list[dict[str, object]],
    unrelated_price: bool,
) -> None:
    from procurepilot_optimiser_worker.repository import (
        load_advanced_optimisation_input,
        mark_completed,
        mark_running,
    )
    from procurepilot_optimiser_worker.solver import solve_advanced_basket

    with round1_rfq() as fixture:
        _authenticate(monkeypatch, fixture)
        if unrelated_price:
            _add_unrelated_price(fixture)
        key = uuid4()
        response = _post(fixture, key)
        assert response.status_code == 202, response.text
        body = response.json()
        assert body["rfq_id"] == str(fixture.rfq_id)
        assert body["status"] == "queued"
        assert set(body["supplier_ids"]) == set(map(str, fixture.supplier_ids))
        assert [Decimal(item["quantity"]) for item in body["items"]] == list(
            map(Decimal, [250, 108, 120, 360])
        )
        assert [item["workspace_product_id"] for item in body["items"]] == list(
            map(str, fixture.product_ids)
        )
        assert len(queue) == 1
        snapshot = queue[0]["request_snapshot"]["rfq"]
        assert snapshot["rfq_id"] == str(fixture.rfq_id)
        assert set(snapshot["price_quotation_ids"]) == set(map(str, fixture.quotation_ids))
        assert set(snapshot["rfq_response_ids"]) == set(map(str, fixture.response_ids))
        assert snapshot["pack_base_quantities"] == dict(
            zip(
                map(str, fixture.product_ids),
                ["10.000000", "18.000000", "10.000000", "45.000000"],
                strict=True,
            )
        )
        job_id = UUID(body["id"])
        with psycopg.connect(TEST_DATABASE_URL or "", prepare_threshold=None) as conn:
            data = load_advanced_optimisation_input(
                conn, job_id=job_id, tenant_id=fixture.workspace.tenant_id
            )
            result = solve_advanced_basket(input_payload=data)
            assert result.feasible
            assert result.total_landed_cost.currency == "SAR"
            assert Decimal(result.total_landed_cost.amount) == Decimal("4063.00")
            baselines = [
                Decimal(b.total_landed_cost.amount)
                for b in result.single_supplier_baselines
                if b.feasible
            ]
            assert sorted(baselines) == [Decimal("4137.00"), Decimal("4147.00")]
            assert min(baselines) - Decimal(result.total_landed_cost.amount) == Decimal("74.00")
            assert {
                a.supplier_id: Decimal(a.total_landed_cost.amount) for a in result.allocation
            } == dict(zip(fixture.supplier_ids, [Decimal(2773), Decimal(1290)], strict=True))
            mark_running(conn, job_id=job_id)
            mark_completed(conn, job_id=job_id, result=result.model_dump(mode="json"))
        result_response = TestClient(app).get(body["result_url"])
        assert result_response.status_code == 200, result_response.text
        assert Decimal(result_response.json()["result"]["total_landed_cost"]["amount"]) == Decimal(
            4063
        )
        replay = _post(fixture, key)
        assert replay.status_code == 202, replay.text
        assert replay.json()["id"] == body["id"]
        assert len(queue) == 1
        with psycopg.connect(
            TEST_DATABASE_URL or "", prepare_threshold=None, row_factory=dict_row
        ) as conn:
            events = conn.execute(
                "select target from audit_event where tenant_id=%s and "
                "action='offers.rfq_split_started'",
                (fixture.workspace.tenant_id,),
            ).fetchall()
            assert len(events) == 1
            assert set(events[0]["target"]["price_quotation_ids"]) == set(
                map(str, fixture.quotation_ids)
            )
            assert (
                conn.execute("select status from rfq where id=%s", (fixture.rfq_id,)).fetchone()[
                    "status"
                ]
                == "responded"
            )


@pytest.mark.parametrize("excluded_currency", ["SAR", "GBP"])
def test_unmatched_reply_is_excluded_with_two_eligible_replies(
    monkeypatch: pytest.MonkeyPatch,
    queue: list[dict[str, object]],
    excluded_currency: str,
) -> None:
    with round1_rfq() as fixture:
        _authenticate(monkeypatch, fixture)
        with psycopg.connect(TEST_DATABASE_URL or "", prepare_threshold=None) as conn:
            with conn.cursor() as cur:
                supplier_id = make_supplier(cur, fixture.workspace, name="Unmatched supplier")
                quotation_id = make_quotation(
                    cur, fixture.workspace, supplier_id=supplier_id, status="reviewed"
                )
                line_id = make_line(cur, fixture.workspace, quotation_id)
                cur.execute(
                    "update quotation set currency=%s where id=%s",
                    (excluded_currency, quotation_id),
                )
                cur.execute(
                    "update quotation_line set unit_price_currency=%s where id=%s",
                    (excluded_currency, line_id),
                )
                reset_role(cur)
                recipient_id, response_id = uuid4(), uuid4()
                cur.execute(
                    "insert into rfq_recipient (id,tenant_id,rfq_id,supplier_id,status) "
                    "values (%s,%s,%s,%s,'sent')",
                    (recipient_id, fixture.workspace.tenant_id, fixture.rfq_id, supplier_id),
                )
                cur.execute(
                    "insert into rfq_response (id,tenant_id,rfq_recipient_id,quotation_id) "
                    "values (%s,%s,%s,%s)",
                    (response_id, fixture.workspace.tenant_id, recipient_id, quotation_id),
                )
        response = _post(fixture)
        assert response.status_code == 202, response.text
        assert set(response.json()["supplier_ids"]) == set(map(str, fixture.supplier_ids))
        assert len(queue) == 1
        assert set(map(str, queue[0]["supplier_ids"])) == set(map(str, fixture.supplier_ids))
        snapshot = queue[0]["request_snapshot"]["rfq"]
        assert set(snapshot["price_quotation_ids"]) == set(map(str, fixture.quotation_ids))
        assert set(snapshot["rfq_response_ids"]) == set(map(str, fixture.response_ids))


@pytest.mark.parametrize(
    "reason,change",
    [
        ("not_enough_replies", "refused"),
        ("not_enough_replies", "pending"),
        ("not_enough_replies", "archived"),
        ("not_enough_replies", "unmatched"),
        ("mixed_currency", "currency"),
        ("rfq_already_converted", "converted"),
    ],
)
def test_ineligible_rfq_returns_409(
    monkeypatch: pytest.MonkeyPatch,
    queue: list,
    reason: str,
    change: str,
) -> None:
    with round1_rfq() as fixture:
        _authenticate(monkeypatch, fixture)
        with psycopg.connect(TEST_DATABASE_URL or "", prepare_threshold=None) as conn:
            if change in ("pending", "refused"):
                conn.execute(
                    "update quotation set status=%s where id=%s", (change, fixture.quotation_ids[1])
                )
            elif change == "archived":
                conn.execute(
                    "update quotation set deleted_at=now() where id=%s", (fixture.quotation_ids[1],)
                )
            elif change == "unmatched":
                with conn.cursor() as cur:
                    make_line(cur, fixture.workspace, fixture.quotation_ids[1])
            elif change == "currency":
                # Header currency alone also prevents a split, even if its lines say SAR.
                conn.execute(
                    "update quotation set currency='GBP' where id=%s", (fixture.quotation_ids[1],)
                )
            else:
                conn.execute("update rfq set status='converted' where id=%s", (fixture.rfq_id,))
        response = _post(fixture)
        assert response.status_code == 409, response.text
        assert response.json()["details"]["reason"] == reason
        if reason == "not_enough_replies":
            assert response.json()["details"] == {
                "reason": reason,
                "eligible": 1,
                "unmatched_quotation_ids": [str(fixture.quotation_ids[1])]
                if change == "unmatched"
                else [],
            }
        assert queue == []


def test_cross_tenant_returns_404(monkeypatch: pytest.MonkeyPatch, queue: list) -> None:
    with round1_rfq() as fixture, round1_rfq() as other:
        _authenticate(monkeypatch, other)
        response = _post(fixture)
        assert response.status_code == 404, response.text
        assert queue == []


def test_reader_cannot_split(monkeypatch: pytest.MonkeyPatch, queue: list) -> None:
    with round1_rfq() as fixture:
        _authenticate(monkeypatch, fixture, MemberRole.approver)
        response = _post(fixture)
        assert response.status_code == 403, response.text
        assert queue == []


def test_idempotency_key_required(monkeypatch: pytest.MonkeyPatch, queue: list) -> None:
    with round1_rfq() as fixture:
        _authenticate(monkeypatch, fixture)
        response = TestClient(app).post(f"/api/v1/rfq/{fixture.rfq_id}/split")
        assert response.status_code == 422, response.text
        assert queue == []


def test_same_key_cannot_replay_another_rfq(
    monkeypatch: pytest.MonkeyPatch,
    queue: list,
) -> None:
    with round1_rfq() as fixture:
        _authenticate(monkeypatch, fixture)
        key = uuid4()
        assert _post(fixture, key).status_code == 202
        with psycopg.connect(TEST_DATABASE_URL or "", prepare_threshold=None) as conn:
            other_id = conn.execute(
                "insert into rfq (tenant_id,created_by_membership_id,status,needed_by_date,"
                "idempotency_key) values (%s,%s,'responded',current_date+7,%s) returning id",
                (fixture.workspace.tenant_id, fixture.workspace.membership_id, uuid4()),
            ).fetchone()[0]
        response = TestClient(app).post(
            f"/api/v1/rfq/{other_id}/split", headers={"Idempotency-Key": str(key)}
        )
        assert response.status_code == 409, response.text
        assert response.json()["details"]["reason"] == "idempotency_key_reused"
        assert len(queue) == 1


def test_split_waits_for_conversion_then_refuses(
    monkeypatch: pytest.MonkeyPatch,
    queue: list,
) -> None:
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    from procurepilot_api.modules.rfq import service as rfq_service

    original_lock = rfq_service.lock_rfq_for_preparation
    entered = Event()

    def observed_lock(*args: object, **kwargs: object) -> str | None:
        entered.set()
        return original_lock(*args, **kwargs)

    with round1_rfq() as fixture:
        _authenticate(monkeypatch, fixture)
        with psycopg.connect(TEST_DATABASE_URL or "", prepare_threshold=None) as conn:
            with conn.cursor() as cur:
                original_lock(cur, tenant_id=fixture.workspace.tenant_id, rfq_id=fixture.rfq_id)
                cur.execute("update rfq set status='converted' where id=%s", (fixture.rfq_id,))
            monkeypatch.setattr(rfq_service, "lock_rfq_for_preparation", observed_lock)
            with ThreadPoolExecutor(max_workers=1) as executor:
                pending = executor.submit(_post, fixture)
                try:
                    assert entered.wait(5), "split never reached the preparation lock"
                    assert not pending.done()
                finally:
                    conn.commit()
                response = pending.result(timeout=10)
        assert response.status_code == 409, response.text
        assert response.json()["details"]["reason"] == "rfq_already_converted"
        assert queue == []


def test_archived_supplier_reply_is_left_out(
    monkeypatch: pytest.MonkeyPatch,
    queue: list[dict[str, object]],
) -> None:
    from procurepilot_optimiser_worker.repository import load_advanced_optimisation_input
    from procurepilot_optimiser_worker.solver import solve_advanced_basket

    with round1_rfq() as fixture:
        _authenticate(monkeypatch, fixture)
        with psycopg.connect(TEST_DATABASE_URL or "", prepare_threshold=None) as conn:
            with conn.cursor() as cur:
                archived_supplier_id = make_supplier(
                    cur, fixture.workspace, name="Archived supplier"
                )
                cur.execute(
                    "update supplier set status = 'archived' where id = %s",
                    (archived_supplier_id,),
                )
                quotation_id = make_quotation(
                    cur, fixture.workspace, supplier_id=archived_supplier_id, status="reviewed"
                )
                cur.execute("update quotation set currency = 'SAR' where id = %s", (quotation_id,))
                for position, product_id in enumerate(fixture.product_ids, 1):
                    line_id = uuid4()
                    cur.execute(
                        "insert into quotation_line "
                        "(id,tenant_id,quotation_id,line_number,original_text,quantity,pack_count,unit_size,"
                        "pack_unit,unit_price_amount,unit_price_currency) "
                        "values (%s,%s,%s,%s,'Item',10,1,1,'kilogram',100,'SAR')",
                        (line_id, fixture.workspace.tenant_id, quotation_id, position),
                    )
                    decision_id = uuid4()
                    cur.execute(
                        "insert into match_decision (id,tenant_id,quotation_line_id,"
                        "matched_workspace_product_id,outcome,is_automatic,confidence) "
                        "values (%s,%s,%s,%s,'no_match_new_product',true,1)",
                        (decision_id, fixture.workspace.tenant_id, line_id, product_id),
                    )
                reset_role(cur)
                recipient_id, response_id = uuid4(), uuid4()
                cur.execute(
                    "insert into rfq_recipient (id,tenant_id,rfq_id,supplier_id,status) "
                    "values (%s,%s,%s,%s,'sent')",
                    (
                        recipient_id,
                        fixture.workspace.tenant_id,
                        fixture.rfq_id,
                        archived_supplier_id,
                    ),
                )
                cur.execute(
                    "insert into rfq_response (id,tenant_id,rfq_recipient_id,quotation_id) "
                    "values (%s,%s,%s,%s)",
                    (response_id, fixture.workspace.tenant_id, recipient_id, quotation_id),
                )
            conn.commit()

        # Third supplier's reply is reviewed, but supplier is archived -> left out, returns 202
        response = _post(fixture)
        assert response.status_code == 202, response.text
        body = response.json()
        assert set(body["supplier_ids"]) == set(map(str, fixture.supplier_ids))
        assert len(queue) == 1

        # The round-1 split must still give SAR 4,063.00 / 4,137.00 / 74.00
        job_id = UUID(body["id"])
        with psycopg.connect(TEST_DATABASE_URL or "", prepare_threshold=None) as conn:
            data = load_advanced_optimisation_input(
                conn, job_id=job_id, tenant_id=fixture.workspace.tenant_id
            )
            result = solve_advanced_basket(input_payload=data)
            assert result.feasible
            assert result.total_landed_cost.currency == "SAR"
            assert Decimal(result.total_landed_cost.amount) == Decimal("4063.00")
            baselines = [
                Decimal(b.total_landed_cost.amount)
                for b in result.single_supplier_baselines
                if b.feasible
            ]
            assert sorted(baselines) == [Decimal("4137.00"), Decimal("4147.00")]
            assert min(baselines) - Decimal(result.total_landed_cost.amount) == Decimal("74.00")

        # With only one remaining active supplier -> 409 not_enough_replies
        with psycopg.connect(TEST_DATABASE_URL or "", prepare_threshold=None) as conn:
            conn.execute(
                "update supplier set status = 'archived' where id = %s",
                (fixture.supplier_ids[0],),
            )
            conn.commit()
        response_one = _post(fixture)
        assert response_one.status_code == 409, response_one.text
        assert response_one.json()["details"] == {
            "reason": "not_enough_replies",
            "eligible": 1,
            "unmatched_quotation_ids": [],
        }

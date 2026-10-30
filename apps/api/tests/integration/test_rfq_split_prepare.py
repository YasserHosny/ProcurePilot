"""Spec 024 US2: atomic split preparation, provenance and conversion races."""

from __future__ import annotations

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from decimal import Decimal
from threading import Barrier, Event, local
from uuid import UUID, uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from httpx import Response
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from integration.catalogue_helpers import TEST_DATABASE_URL
from integration.fixtures.round1_rfq import Round1Rfq, round1_rfq
from integration.test_rfq_service_e2e import _patch_requests_service_for_test
from integration.test_rfq_split import _authenticate, _post
from integration.test_rfq_split import queue as split_queue
from procurepilot_api.config import get_settings
from procurepilot_api.errors import ConflictError
from procurepilot_api.main import app
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.requests.service import RequestsService
from procurepilot_api.modules.requests.valuation import estimate_from_source_response
from procurepilot_api.modules.rfq.service import RfqService

queue = split_queue

pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="TEST_DATABASE_URL is not set")


@pytest.fixture(autouse=True)
def isolated_rate_limits() -> Iterator[None]:
    from procurepilot_api.shared.rate_limit import mutation_limiter

    mutation_limiter.reset()
    yield
    mutation_limiter.reset()


def _complete(fixture: Round1Rfq) -> UUID:
    from procurepilot_optimiser_worker.repository import (
        load_advanced_optimisation_input,
        mark_completed,
        mark_running,
    )
    from procurepilot_optimiser_worker.solver import solve_advanced_basket

    response = _post(fixture)
    assert response.status_code == 202, response.text
    job_id = UUID(response.json()["id"])
    with psycopg.connect(TEST_DATABASE_URL or "", prepare_threshold=None) as conn:
        data = load_advanced_optimisation_input(
            conn, job_id=job_id, tenant_id=fixture.workspace.tenant_id
        )
        result = solve_advanced_basket(input_payload=data)
        mark_running(conn, job_id=job_id)
        mark_completed(conn, job_id=job_id, result=result.model_dump(mode="json"))
    return job_id


def _prepare(
    fixture: Round1Rfq, job_id: UUID, key: UUID | None = None, **changes: object
) -> Response:
    return TestClient(app).post(
        f"/api/v1/baskets/{job_id}/prepare-requests",
        headers={"Idempotency-Key": str(key or uuid4())},
        json={
            "branch_id": str(fixture.branch_id),
            "required_by_date": str(date.today() + timedelta(days=9)),
            **changes,
        },
    )


def _assert_empty(fixture: Round1Rfq) -> None:
    with psycopg.connect(TEST_DATABASE_URL or "", prepare_threshold=None) as conn:
        assert (
            conn.execute(
                "select count(*) from purchase_request_group where tenant_id=%s",
                (fixture.workspace.tenant_id,),
            ).fetchone()[0]
            == 0
        )
        assert (
            conn.execute(
                "select count(*) from purchase_request where tenant_id=%s",
                (fixture.workspace.tenant_id,),
            ).fetchone()[0]
            == 0
        )
        assert (
            conn.execute("select status from rfq where id=%s", (fixture.rfq_id,)).fetchone()[0]
            == "responded"
        )


def test_round1_prepare_prices_snapshots_detail_and_replay(
    monkeypatch: pytest.MonkeyPatch, queue: list
) -> None:
    with round1_rfq() as fixture:
        _authenticate(monkeypatch, fixture)
        detail = TestClient(app).get(f"/api/v1/rfq/{fixture.rfq_id}").json()
        assert detail["converted_purchase_request_ids"] == []
        assert detail["request_group_id"] is None
        job_id = _complete(fixture)
        key = uuid4()
        with psycopg.connect(TEST_DATABASE_URL or "", prepare_threshold=None) as conn:
            cost_centre = conn.execute(
                "insert into cost_centre (tenant_id,name,code) values (%s,'Split "
                "centre','SPLIT') returning id",
                (fixture.workspace.tenant_id,),
            ).fetchone()[0]
        statements: list[str] = []
        execute = psycopg.Cursor.execute

        def observed_execute(
            cur: psycopg.Cursor, query: str, *args: object, **kwargs: object
        ) -> psycopg.Cursor:
            statements.append(" ".join(query.lower().split()))
            return execute(cur, query, *args, **kwargs)

        with monkeypatch.context() as tracing:
            tracing.setattr(psycopg.Cursor, "execute", observed_execute)
            response = _prepare(fixture, job_id, key, cost_centre_id=str(cost_centre))
        print(f"Preparation SQL statements: {len(statements)} (including role/claims setup)")
        assert len(statements) == 18
        assert sum(q.startswith("insert into purchase_request ") for q in statements) == 1
        assert sum(q.startswith("insert into purchase_request_line ") for q in statements) == 1
        assert response.status_code == 201, response.text
        body = response.json()
        assert len(body["purchase_request_ids"]) == 2
        replay = _prepare(fixture, job_id, key, cost_centre_id=str(cost_centre))
        assert replay.status_code == 200, replay.text
        assert replay.json() == body
        with psycopg.connect(
            TEST_DATABASE_URL or "", prepare_threshold=None, row_factory=dict_row
        ) as conn:
            group = conn.execute(
                "select * from purchase_request_group where id=%s", (body["request_group_id"],)
            ).fetchone()
            for field, amount in [
                ("combined_total", 4063),
                ("best_single_total", 4137),
                ("saving", 74),
            ]:
                assert group[field + "_amount"] == Decimal(amount)
                assert group[field + "_currency"] == "SAR"
            assert group["created_by_membership_id"] == fixture.member.membership_id
            rows = conn.execute(
                "select * from purchase_request where tenant_id=%s", (fixture.workspace.tenant_id,)
            ).fetchall()
            assert len(rows) == 2
            for row in rows:
                index = fixture.supplier_ids.index(row["source_supplier_id"])
                assert row["source_rfq_response_id"] == fixture.response_ids[index]
                assert row["source_rfq_id"] == fixture.rfq_id
                assert row["source_quotation_id"] == fixture.quotation_ids[index]
                assert row["request_group_id"] == UUID(body["request_group_id"])
                assert row["status"] == "draft"
                assert row["branch_id"] == fixture.branch_id
                assert row["cost_centre_id"] == cost_centre
                assert row["required_by_date"] == date.today() + timedelta(days=9)
                assert row["estimated_total_amount"] == [Decimal(2773), Decimal(1290)][index]
                assert row["estimated_total_currency"] == "SAR"
                assert not row["has_incomplete_estimate"]
                lines = conn.execute(
                    "select * from purchase_request_line where purchase_request_id=%s order by "
                    "position",
                    (row["id"],),
                ).fetchall()
                expected_products = [
                    fixture.product_ids[i] for i in ([0, 3] if index == 0 else [1, 2])
                ]
                assert [line["workspace_product_id"] for line in lines] == expected_products
                assert [line["position"] for line in lines] == [0, 1]
                estimates = estimate_from_source_response(
                    conn, rfq_response_id=fixture.response_ids[index], product_ids=expected_products
                )
                for line in lines:
                    estimate = estimates[line["workspace_product_id"]]
                    assert line["estimated_unit_price_amount"] == estimate.unit_price_amount
                    assert line["estimated_unit_price_currency"] == estimate.unit_price_currency
                    assert (
                        line["estimated_unit_price_source_landed_cost_id"]
                        == estimate.source_landed_cost_id
                    )
                    assert (
                        line["pack_base_quantity"]
                        == [10, 18, 10, 45][fixture.product_ids.index(line["workspace_product_id"])]
                    )
            events = conn.execute(
                "select target from audit_event where tenant_id=%s and "
                "action='requests.group_prepared'",
                (fixture.workspace.tenant_id,),
            ).fetchall()
            assert len(events) == 1
            assert set(events[0]["target"]["purchase_request_ids"]) == set(
                body["purchase_request_ids"]
            )
        detail_response = TestClient(app).get(f"/api/v1/rfq/{fixture.rfq_id}")
        assert detail_response.status_code == 200, detail_response.text
        detail = detail_response.json()
        assert detail["rfq"]["status"] == "converted"
        assert set(detail["converted_purchase_request_ids"]) == set(body["purchase_request_ids"])
        assert detail["request_group_id"] == body["request_group_id"]
        conflict = _prepare(fixture, job_id)
        assert conflict.status_code == 409
        assert conflict.json()["details"]["reason"] == "rfq_already_converted"
        assert set(conflict.json()["details"]["purchase_request_ids"]) == set(
            body["purchase_request_ids"]
        )


@pytest.mark.parametrize("pricing", ["rounded_pack_price", "delivery_fee"])
def test_prepare_and_submit_use_draft_totals_and_solver_saving(
    monkeypatch: pytest.MonkeyPatch, queue: list, pricing: str
) -> None:
    with round1_rfq() as fixture:
        _authenticate(monkeypatch, fixture)
        with psycopg.connect(TEST_DATABASE_URL or "", prepare_threshold=None) as conn:
            if pricing == "rounded_pack_price":
                # Three sugar packs cost 100 SAR: the draft's per-pack price is 33.3333.
                conn.execute(
                    "update rfq_line set quantity=3 where rfq_id=%s and workspace_product_id=%s",
                    (fixture.rfq_id, fixture.product_ids[2]),
                )
                conn.execute(
                    "update landed_cost set quantity=3,normalised_base_quantity=30,"
                    "total_amount=100 where quotation_line_id in "
                    "(select ql.id from quotation_line ql join current_match_decision md "
                    "on md.quotation_line_id=ql.id where ql.quotation_id=%s "
                    "and md.matched_workspace_product_id=%s)",
                    (fixture.quotation_ids[1], fixture.product_ids[2]),
                )
            else:
                conn.execute(
                    "insert into supplier_commercial_term "
                    "(tenant_id,supplier_id,delivery_fee_amount,delivery_fee_currency,"
                    "created_by_membership_id) values (%s,%s,10,'SAR',%s)",
                    (
                        fixture.member.tenant_id,
                        fixture.supplier_ids[0],
                        fixture.member.membership_id,
                    ),
                )
        job_id = _complete(fixture)
        with psycopg.connect(
            TEST_DATABASE_URL or "", prepare_threshold=None, row_factory=dict_row
        ) as conn:
            result = conn.execute(
                "select result from basket_split_job where id=%s", (job_id,)
            ).fetchone()["result"]
        solver_total = Decimal(result["total_landed_cost"]["amount"])
        best_single = min(
            Decimal(b["total_landed_cost"]["amount"])
            for b in result["single_supplier_baselines"]
            if b["feasible"] and b["total_landed_cost"]
        )
        if pricing == "delivery_fee":
            assert solver_total == Decimal("4073.00")
            assert any(c["kind"] == "delivery_fee" for c in result["applied_constraints"])
        response = _prepare(fixture, job_id)
        assert response.status_code == 201, response.text
        group_id = UUID(response.json()["request_group_id"])
        with psycopg.connect(
            TEST_DATABASE_URL or "", prepare_threshold=None, row_factory=dict_row
        ) as conn:
            group = conn.execute(
                "select * from purchase_request_group where id=%s", (group_id,)
            ).fetchone()
            drafts_total = conn.execute(
                "select sum(estimated_total_amount) as total from purchase_request "
                "where request_group_id=%s",
                (group_id,),
            ).fetchone()["total"]
            assert drafts_total == Decimal(
                "3742.9999" if pricing == "rounded_pack_price" else "4063.00"
            )
            assert drafts_total != solver_total
            assert group["combined_total_amount"] == drafts_total
            assert group["combined_total_currency"] == "SAR"
            assert group["best_single_total_amount"] == best_single
            assert group["best_single_total_currency"] == "SAR"
            assert group["saving_amount"] == max(Decimal(0), best_single - solver_total)
            assert group["saving_currency"] == "SAR"
            target = conn.execute(
                "select target from audit_event where tenant_id=%s "
                "and action='requests.group_prepared'",
                (fixture.member.tenant_id,),
            ).fetchone()["target"]
            assert Decimal(target["combined_total"]["amount"]) == drafts_total
            assert target["combined_total"]["currency"] == "SAR"
        submitted = RequestsService().submit_group(
            bearer_token="test-token",
            member=fixture.member,
            group_id=group_id,
            idempotency_key=uuid4(),
        )
        assert {str(r.id) for r in submitted} == set(response.json()["purchase_request_ids"])
        assert {r.status for r in submitted} == {"submitted"}
        assert all(r.request_group.combined_total.amount == str(drafts_total) for r in submitted)


@pytest.mark.parametrize(
    "change",
    [
        "new_reply",
        "refused",
        "inactive_supplier",
        "deleted",
        "unmatched",
        "rereviewed",
        "corrected_match",
        "replaced_cost",
        "fractional",
        "expired",
        "not_completed",
        "not_rfq",
    ],
)
def test_preparation_conflicts(monkeypatch: pytest.MonkeyPatch, queue: list, change: str) -> None:
    with round1_rfq() as fixture:
        _authenticate(monkeypatch, fixture)
        job_id = _complete(fixture)
        with psycopg.connect(
            TEST_DATABASE_URL or "", prepare_threshold=None, row_factory=dict_row
        ) as conn:
            if change == "new_reply":
                from integration.catalogue_helpers import reset_role
                from integration.quotation_helpers import make_line, make_quotation

                with conn.cursor() as cur:
                    quotation_id = make_quotation(
                        cur,
                        fixture.workspace,
                        supplier_id=fixture.supplier_ids[0],
                        status="reviewed",
                    )
                    line_id = make_line(cur, fixture.workspace, quotation_id)
                    reset_role(cur)
                    cur.execute("update quotation set currency='SAR' where id=%s", (quotation_id,))
                    cur.execute(
                        "insert into match_decision "
                        "(tenant_id,quotation_line_id,matched_workspace_product_id,outcome,"
                        "is_automatic,confidence) "
                        "values (%s,%s,%s,'no_match_new_product',true,1)",
                        (fixture.member.tenant_id, line_id, fixture.product_ids[0]),
                    )
                    cur.execute(
                        "insert into rfq_response (tenant_id,rfq_recipient_id,quotation_id) "
                        "select tenant_id,rfq_recipient_id,%s from rfq_response where id=%s",
                        (quotation_id, fixture.response_ids[0]),
                    )
            elif change == "refused":
                conn.execute(
                    "update quotation set status='refused' where id=%s", (fixture.quotation_ids[0],)
                )
            elif change == "inactive_supplier":
                conn.execute(
                    "update supplier set status='archived' where id=%s", (fixture.supplier_ids[0],)
                )
            elif change == "deleted":
                conn.execute(
                    "update quotation set deleted_at=now() where id=%s", (fixture.quotation_ids[0],)
                )
            elif change == "unmatched":
                from integration.quotation_helpers import make_line

                with conn.cursor() as cur:
                    make_line(cur, fixture.workspace, fixture.quotation_ids[0])
            elif change in ("rereviewed", "corrected_match", "replaced_cost"):
                if change != "replaced_cost":
                    conn.execute(
                        """
                        insert into match_decision
                          (tenant_id,quotation_line_id,matched_workspace_product_id,outcome,
                           is_automatic,confidence,supersedes_decision_id)
                        select tenant_id,quotation_line_id,matched_workspace_product_id,outcome,
                               is_automatic,confidence,id from current_match_decision
                        where tenant_id=%s
                        """,
                        (fixture.member.tenant_id,),
                    )
                if change in ("rereviewed", "replaced_cost"):
                    conn.execute(
                        """
                        insert into landed_cost
                          (tenant_id,quotation_line_id,match_decision_id,quantity,
                           normalised_base_quantity,base_unit,unit_price_amount,unit_price_currency,
                           vat_amount,vat_currency,delivery_fee_amount,delivery_fee_currency,
                           discount_amount,discount_currency,other_charges_amount,
                           other_charges_currency,total_amount,total_currency,raw_inputs,
                           rule_version,valid_from,recorded_at)
                        select lc.tenant_id,lc.quotation_line_id,md.id,quantity,
                               normalised_base_quantity,base_unit,unit_price_amount,
                               unit_price_currency,vat_amount,vat_currency,delivery_fee_amount,
                               delivery_fee_currency,discount_amount,discount_currency,
                               other_charges_amount,other_charges_currency,total_amount,
                               total_currency,raw_inputs,rule_version||%s,valid_from,
                               now()+interval '1 second'
                        from landed_cost lc join current_match_decision md
                          on md.quotation_line_id=lc.quotation_line_id
                        where lc.tenant_id=%s
                        """,
                        (
                            "-replacement" if change == "replaced_cost" else "",
                            fixture.member.tenant_id,
                        ),
                    )
            elif change == "expired":
                conn.execute(
                    "update quotation set issue_date=null,expiry_date=current_date-1 where id=%s",
                    (fixture.quotation_ids[0],),
                )
                conn.execute(
                    "update landed_cost set valid_from=now()-interval '2 days',"
                    "valid_to=now()-interval '1 day' where quotation_line_id in "
                    "(select id from quotation_line where quotation_id=%s)",
                    (fixture.quotation_ids[0],),
                )
            else:
                row = conn.execute(
                    "select result from basket_split_job where id=%s", (job_id,)
                ).fetchone()
                if change == "fractional":
                    row["result"]["allocation"][0]["lines"][0]["quantity"] = "255.000000"
                    conn.execute(
                        "update basket_split_job set result=%s where id=%s",
                        (Jsonb(row["result"]), job_id),
                    )
                elif change == "not_completed":
                    conn.execute(
                        "update basket_split_job set status='running',completed_at=null where "
                        "id=%s",
                        (job_id,),
                    )
                else:
                    conn.execute("update basket_split_job set rfq_id=null where id=%s", (job_id,))
        response = _prepare(fixture, job_id)
        reason = {
            "fractional": "allocation_not_whole_packs",
            "expired": "expired_quotation_unconfirmed",
            "not_completed": "split_not_completed",
            "not_rfq": "not_rfq_split",
        }.get(change, "split_stale")
        assert response.status_code == 409, response.text
        assert response.json()["details"]["reason"] == reason
        _assert_empty(fixture)
        if change == "expired":
            assert response.json()["details"]["quotation_ids"] == [str(fixture.quotation_ids[0])]
            confirmed = _prepare(
                fixture, job_id, confirm_expired_quotation_ids=[str(fixture.quotation_ids[0])]
            )
            assert confirmed.status_code == 201, confirmed.text


def test_second_insert_constraint_failure_rolls_everything_back(
    monkeypatch: pytest.MonkeyPatch, queue: list
) -> None:
    from procurepilot_api.modules.requests import service

    with round1_rfq() as fixture:
        _authenticate(monkeypatch, fixture)
        job_id = _complete(fixture)
        original = service._insert_group_requests

        def failing_insert(conn: psycopg.Connection, rows: list[dict[str, object]]) -> None:
            rows[1]["required_by_date"] = None  # Real NOT NULL failure in second batched row.
            return original(conn, rows)

        monkeypatch.setattr(service, "_insert_group_requests", failing_insert)
        response = _prepare(fixture, job_id)
        assert response.status_code == 503, response.text
        _assert_empty(fixture)
        with psycopg.connect(TEST_DATABASE_URL or "", prepare_threshold=None) as conn:
            assert (
                conn.execute(
                    "select count(*) from audit_event where tenant_id=%s and "
                    "action='requests.group_prepared'",
                    (fixture.workspace.tenant_id,),
                ).fetchone()[0]
                == 0
            )


@pytest.mark.parametrize("first", ["single", "split"])
def test_single_and_split_race_has_one_winner(
    monkeypatch: pytest.MonkeyPatch, queue: list, first: str
) -> None:
    from procurepilot_api.modules.offers.rfq_split import prepare_requests_from_split
    from procurepilot_api.modules.offers.schemas import SplitPrepareRequest
    from procurepilot_api.modules.rfq import service

    with round1_rfq() as fixture:
        _authenticate(monkeypatch, fixture)
        job_id = _complete(fixture)
        _patch_requests_service_for_test(
            monkeypatch,
            tenant_id=fixture.member.tenant_id,
            user_id=fixture.member.user_id,
            membership_id=fixture.member.membership_id,
        )
        barrier = Barrier(2)
        original = service.lock_rfq_for_preparation
        backend_pids = set()
        thread_kind = local()
        first_locked = Event()

        def observed_lock(cur: psycopg.Cursor, **kwargs: object) -> str | None:
            cur.execute("select pg_backend_pid() as pid")
            backend_pids.add(cur.fetchone()["pid"])
            barrier.wait(timeout=10)
            # Exercise both lock winners without replacing either preparation path.
            if thread_kind.kind == first:
                status = original(cur, **kwargs)
                first_locked.set()
                return status
            assert first_locked.wait(timeout=10)
            return original(cur, **kwargs)

        monkeypatch.setattr(service, "lock_rfq_for_preparation", observed_lock)

        # Both services use the shared function via its defining module.
        def run(kind: str) -> object:
            thread_kind.kind = kind
            try:
                if kind == "single":
                    return RfqService(get_settings()).prepare_request(
                        bearer_token="test",
                        member=fixture.member,
                        rfq_id=fixture.rfq_id,
                        rfq_response_id=fixture.response_ids[0],
                        branch_id=fixture.branch_id,
                        cost_centre_id=None,
                        required_by_date=date.today(),
                        idempotency_key=uuid4(),
                    )
                return prepare_requests_from_split(
                    member=fixture.member,
                    basket_id=job_id,
                    payload=SplitPrepareRequest(
                        branch_id=fixture.branch_id, required_by_date=date.today()
                    ),
                    idempotency_key=uuid4(),
                )
            except ConflictError as exc:
                return exc

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(run, [first, "split" if first == "single" else "single"]))
        assert len(backend_pids) == 2
        conflicts = [r for r in results if isinstance(r, ConflictError)]
        assert len(conflicts) == 1
        assert conflicts[0].status_code == 409
        assert conflicts[0].details["reason"] == "rfq_already_converted"
        detail = RfqService(get_settings()).get_detail(member=fixture.member, rfq_id=fixture.rfq_id)
        assert detail.rfq.status == "converted"
        assert len(detail.converted_purchase_request_ids) == (1 if first == "single" else 2)
        assert (detail.request_group_id is not None) == (
            len(detail.converted_purchase_request_ids) == 2
        )


def test_prepare_security_and_required_key(monkeypatch: pytest.MonkeyPatch, queue: list) -> None:
    with round1_rfq() as fixture, round1_rfq() as other:
        _authenticate(monkeypatch, fixture)
        job_id = _complete(fixture)
        _authenticate(monkeypatch, other)
        assert _prepare(other, job_id).status_code == 404
        _authenticate(monkeypatch, fixture, MemberRole.approver)
        assert _prepare(fixture, job_id).status_code == 403
        _authenticate(monkeypatch, fixture)
        assert (
            TestClient(app)
            .post(
                f"/api/v1/baskets/{job_id}/prepare-requests",
                json={"branch_id": str(fixture.branch_id), "required_by_date": str(date.today())},
            )
            .status_code
            == 422
        )


def test_destination_ids_are_tenant_scoped(monkeypatch: pytest.MonkeyPatch, queue: list) -> None:
    with round1_rfq() as fixture, round1_rfq() as other:
        _authenticate(monkeypatch, fixture)
        job_id = _complete(fixture)
        for changes in ({"branch_id": str(other.branch_id)}, {"cost_centre_id": str(uuid4())}):
            response = _prepare(fixture, job_id, **changes)
            assert response.status_code == 404, response.text
            _assert_empty(fixture)


def test_detail_only_reports_conversion_when_converted(
    monkeypatch: pytest.MonkeyPatch, queue: list
) -> None:
    with round1_rfq() as fixture:
        _authenticate(monkeypatch, fixture)
        with psycopg.connect(TEST_DATABASE_URL or "", prepare_threshold=None) as conn:
            request_id = conn.execute(
                "insert into purchase_request (tenant_id,branch_id,requested_by_membership_id,"
                "required_by_date,source_rfq_response_id) "
                "values (%s,%s,%s,current_date,%s) returning id",
                (
                    fixture.member.tenant_id,
                    fixture.branch_id,
                    fixture.member.membership_id,
                    fixture.response_ids[0],
                ),
            ).fetchone()[0]
        detail = RfqService(get_settings()).get_detail(member=fixture.member, rfq_id=fixture.rfq_id)
        assert detail.converted_purchase_request_ids == []
        assert detail.request_group_id is None
        with psycopg.connect(TEST_DATABASE_URL or "", prepare_threshold=None) as conn:
            conn.execute("update rfq set status='converted' where id=%s", (fixture.rfq_id,))
        detail = RfqService(get_settings()).get_detail(member=fixture.member, rfq_id=fixture.rfq_id)
        assert detail.converted_purchase_request_ids == [request_id]
        assert detail.request_group_id is None


def test_simultaneous_same_key_replays_after_waiting_for_lock(
    monkeypatch: pytest.MonkeyPatch, queue: list
) -> None:
    from procurepilot_api.modules.offers.rfq_split import prepare_requests_from_split
    from procurepilot_api.modules.offers.schemas import SplitPrepareRequest
    from procurepilot_api.modules.rfq import service

    with round1_rfq() as fixture:
        _authenticate(monkeypatch, fixture)
        job_id = _complete(fixture)
        key = uuid4()
        barrier = Barrier(2)
        original = service.lock_rfq_for_preparation

        def observed_lock(cur: psycopg.Cursor, **kwargs: object) -> str | None:
            barrier.wait(timeout=10)
            return original(cur, **kwargs)

        monkeypatch.setattr(service, "lock_rfq_for_preparation", observed_lock)

        def run(_index: int) -> tuple[object, bool]:
            return prepare_requests_from_split(
                member=fixture.member,
                basket_id=job_id,
                payload=SplitPrepareRequest(
                    branch_id=fixture.branch_id, required_by_date=date.today()
                ),
                idempotency_key=key,
            )

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(run, [0, 1]))
        assert sorted(created for _, created in results) == [False, True]
        assert results[0][0] == results[1][0]
        with psycopg.connect(TEST_DATABASE_URL or "", prepare_threshold=None) as conn:
            assert (
                conn.execute(
                    "select count(*) from purchase_request where tenant_id=%s",
                    (fixture.member.tenant_id,),
                ).fetchone()[0]
                == 2
            )
            assert (
                conn.execute(
                    "select count(*) from purchase_request_group where tenant_id=%s",
                    (fixture.member.tenant_id,),
                ).fetchone()[0]
                == 1
            )


def _copy_reply(
    fixture: Round1Rfq,
    *,
    supplier_id: UUID | None = None,
    product_ids: list[UUID] | None = None,
) -> UUID:
    """Another fully priced reply, learned after the original; retain its exact round-1 prices."""
    from integration.catalogue_helpers import reset_role
    from integration.quotation_helpers import make_quotation

    with psycopg.connect(TEST_DATABASE_URL or "", prepare_threshold=None) as conn:
        with conn.cursor() as cur:
            quotation_id = make_quotation(
                cur,
                fixture.workspace,
                supplier_id=supplier_id or fixture.supplier_ids[0],
                status="reviewed",
            )
            reset_role(cur)
            cur.execute("update quotation set currency='SAR' where id=%s", (quotation_id,))
            cur.execute(
                "select ql.id from quotation_line ql join current_match_decision md "
                "on md.quotation_line_id=ql.id where ql.quotation_id=%s "
                "and md.matched_workspace_product_id=any(%s) order by ql.line_number",
                (fixture.quotation_ids[0], product_ids or fixture.product_ids),
            )
            for (original_line_id,) in cur.fetchall():
                line_id, decision_id = uuid4(), uuid4()
                cur.execute(
                    """
                    insert into quotation_line
                      (id,tenant_id,quotation_id,line_number,original_text,quantity,pack_count,
                       unit_size,pack_unit,unit_price_amount,unit_price_currency)
                    select %s,tenant_id,%s,line_number,original_text,quantity,pack_count,unit_size,
                           pack_unit,unit_price_amount,unit_price_currency
                    from quotation_line where id=%s
                    """,
                    (line_id, quotation_id, original_line_id),
                )
                cur.execute(
                    "insert into match_decision (id,tenant_id,quotation_line_id,"
                    "matched_workspace_product_id,outcome,is_automatic,confidence) "
                    "select %s,tenant_id,%s,matched_workspace_product_id,outcome,is_automatic,"
                    "confidence from current_match_decision where quotation_line_id=%s",
                    (decision_id, line_id, original_line_id),
                )
                cur.execute(
                    """
                    insert into landed_cost
                      (tenant_id,quotation_line_id,match_decision_id,quantity,
                       normalised_base_quantity,base_unit,unit_price_amount,unit_price_currency,
                       vat_amount,vat_currency,delivery_fee_amount,delivery_fee_currency,
                       discount_amount,discount_currency,other_charges_amount,other_charges_currency,
                       total_amount,total_currency,raw_inputs,rule_version,valid_from,recorded_at)
                    select tenant_id,%s,%s,quantity,normalised_base_quantity,base_unit,
                           unit_price_amount,unit_price_currency,vat_amount,vat_currency,
                           delivery_fee_amount,delivery_fee_currency,discount_amount,
                           discount_currency,other_charges_amount,other_charges_currency,
                           total_amount,total_currency,raw_inputs,rule_version,valid_from,now()
                    from landed_cost where quotation_line_id=%s
                    """,
                    (line_id, decision_id, original_line_id),
                )
            cur.execute(
                "insert into rfq_recipient (tenant_id,rfq_id,supplier_id,status) "
                "select %s,%s,%s,'sent' where not exists "
                "(select 1 from rfq_recipient where rfq_id=%s and supplier_id=%s)",
                (
                    fixture.member.tenant_id,
                    fixture.rfq_id,
                    supplier_id or fixture.supplier_ids[0],
                    fixture.rfq_id,
                    supplier_id or fixture.supplier_ids[0],
                ),
            )
            return cur.execute(
                "insert into rfq_response (tenant_id,rfq_recipient_id,quotation_id) "
                "select tenant_id,id,%s from rfq_recipient where rfq_id=%s and supplier_id=%s "
                "returning id",
                (quotation_id, fixture.rfq_id, supplier_id or fixture.supplier_ids[0]),
            ).fetchone()[0]


@pytest.mark.parametrize("priced_reply", ["latest", "original", "mixed"])
def test_preparation_uses_the_priced_reply_when_supplier_replied_twice(
    monkeypatch: pytest.MonkeyPatch,
    queue: list,
    priced_reply: str,
) -> None:
    with round1_rfq() as fixture:
        _authenticate(monkeypatch, fixture)
        products = {
            "latest": fixture.product_ids,
            "original": fixture.product_ids[1:3],  # Oil/sugar go to the other supplier.
            "mixed": fixture.product_ids[:1],  # Rice in new reply, flour only in original.
        }[priced_reply]
        latest_response_id = _copy_reply(fixture, product_ids=products)
        if priced_reply == "latest":
            # Only the actually priced reply needs expired-quotation confirmation.
            with psycopg.connect(TEST_DATABASE_URL or "", prepare_threshold=None) as conn:
                conn.execute(
                    "update quotation set issue_date=null,expiry_date=current_date-1 where id=%s",
                    (fixture.quotation_ids[0],),
                )
        job_id = _complete(fixture)
        response = _prepare(fixture, job_id)
        if priced_reply == "mixed":
            assert response.status_code == 409, response.text
            assert response.json()["details"]["reason"] == "split_stale"
            _assert_empty(fixture)
            return
        assert response.status_code == 201, response.text
        with psycopg.connect(TEST_DATABASE_URL or "", prepare_threshold=None) as conn:
            row = conn.execute(
                "select source_rfq_response_id from purchase_request where tenant_id=%s "
                "and source_supplier_id=%s",
                (fixture.member.tenant_id, fixture.supplier_ids[0]),
            ).fetchone()
            assert row[0] == (
                latest_response_id if priced_reply == "latest" else fixture.response_ids[0]
            )


def test_inactive_suppliers_reply_does_not_make_split_stale(
    monkeypatch: pytest.MonkeyPatch,
    queue: list,
) -> None:
    from integration.quotation_helpers import make_supplier

    with round1_rfq() as fixture:
        _authenticate(monkeypatch, fixture)
        with psycopg.connect(TEST_DATABASE_URL or "", prepare_threshold=None) as conn:
            with conn.cursor() as cur:
                supplier_id = make_supplier(cur, fixture.workspace, name="Archived")
                cur.execute("update supplier set status='archived' where id=%s", (supplier_id,))
        _copy_reply(fixture, supplier_id=supplier_id)
        job_id = _complete(fixture)
        response = _prepare(fixture, job_id)
        assert response.status_code == 201, response.text


@pytest.mark.parametrize("single_supplier", [False, True])
def test_prepared_split_can_be_submitted_as_a_group(
    monkeypatch: pytest.MonkeyPatch,
    queue: list,
    single_supplier: bool,
) -> None:
    with round1_rfq() as fixture:
        _authenticate(monkeypatch, fixture)
        if single_supplier:
            with psycopg.connect(TEST_DATABASE_URL or "", prepare_threshold=None) as conn:
                conn.execute(
                    "update quotation_line set unit_price_amount=unit_price_amount+100 "
                    "where quotation_id=%s",
                    (fixture.quotation_ids[1],),
                )
                conn.execute(
                    "update landed_cost set total_amount=total_amount+100*quantity "
                    "where quotation_line_id in "
                    "(select id from quotation_line where quotation_id=%s)",
                    (fixture.quotation_ids[1],),
                )
        response = _prepare(fixture, _complete(fixture))
        assert response.status_code == 201, response.text
        body = response.json()
        expected_count = 1 if single_supplier else 2
        assert len(body["purchase_request_ids"]) == expected_count
        submitted = RequestsService(get_settings()).submit_group(
            bearer_token="test",
            member=fixture.member,
            group_id=UUID(body["request_group_id"]),
            idempotency_key=uuid4(),
        )
        assert {str(request.id) for request in submitted} == set(body["purchase_request_ids"])
        assert {request.status for request in submitted} == {"submitted"}
        assert {request.branch_id for request in submitted} == {fixture.branch_id}
        assert sum(Decimal(request.estimated_total.amount) for request in submitted) == Decimal(
            4147 if single_supplier else 4063
        )

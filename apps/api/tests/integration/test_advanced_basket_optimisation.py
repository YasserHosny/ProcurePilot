from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import ValidationError

from integration.catalogue_helpers import TEST_DATABASE_URL, act_as
from integration.smart_compare_helpers import (
    committed_smart_context,
    settings_for_test_db,
)
from procurepilot_api.errors import ConflictError, UnprocessableEntityError
from procurepilot_api.modules.offers import basket_service
from procurepilot_api.modules.offers.basket_service import BasketService
from procurepilot_api.modules.offers.schemas import (
    AdvancedBasketOptimiseRequest,
    BasketItemRequest,
    OptimisationWeights,
)

psycopg = pytest.importorskip("psycopg")

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is not set; needs a migrated local Postgres",
)


def test_advanced_basket_accepts_two_to_ten_suppliers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = settings_for_test_db(monkeypatch)
    monkeypatch.setattr(basket_service, "_enqueue_redis_job", _noop_enqueue)

    with committed_smart_context("advanced-two", supplier_count=2) as context:
        job = BasketService(settings).create_job(
            member=context.member,
            payload=_advanced_payload(context.supplier_ids, context.product_id),
        )
        assert job.status == "queued"
        assert job.supplier_ids == context.supplier_ids

    with committed_smart_context("advanced-ten", supplier_count=10) as context:
        job = BasketService(settings).create_job(
            member=context.member,
            payload=_advanced_payload(context.supplier_ids, context.product_id),
        )
        assert job.status == "queued"
        assert job.supplier_ids == context.supplier_ids

    with pytest.raises(ValidationError):
        _advanced_payload([uuid4()], uuid4())

    with pytest.raises(ValidationError):
        _advanced_payload([uuid4() for _ in range(11)], uuid4())


def test_advanced_basket_rejects_more_than_fifty_lines() -> None:
    supplier_ids = [uuid4(), uuid4()]
    product_id = uuid4()

    request = _advanced_payload(supplier_ids, product_id, line_count=50)
    assert len(request.items) == 50

    with pytest.raises(ValidationError):
        _advanced_payload(supplier_ids, product_id, line_count=51)


def test_advanced_basket_refuses_mixed_currency_supplier_constraints(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = settings_for_test_db(monkeypatch)
    monkeypatch.setattr(basket_service, "_enqueue_redis_job", _noop_enqueue)

    with committed_smart_context("advanced-mixed-currency") as context:
        _insert_supplier_term(context, context.supplier_ids[0], mov_currency="GBP")
        _insert_supplier_term(context, context.supplier_ids[1], mov_currency="USD")

        with pytest.raises(UnprocessableEntityError) as exc_info:
            BasketService(settings).create_job(
                member=context.member,
                payload=_advanced_payload(context.supplier_ids, context.product_id),
            )

        assert exc_info.value.details == {
            "currency": "mixed_advanced_basket_currency"
        }
        assert _basket_jobs(context.workspace.tenant_id) == []


def test_advanced_basket_persists_constraint_snapshot_and_worker_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = settings_for_test_db(monkeypatch)
    enqueued: list[dict[str, object]] = []

    def fake_enqueue(_settings: object, row: dict[str, object], _member: object) -> None:
        enqueued.append(dict(row))

    monkeypatch.setattr(basket_service, "_enqueue_redis_job", fake_enqueue)

    with committed_smart_context("advanced-snapshot") as context:
        _insert_supplier_term(
            context,
            context.supplier_ids[0],
            mov_currency="GBP",
            quantity_tier_product_id=context.product_id,
        )
        request = _advanced_payload(
            context.supplier_ids,
            context.product_id,
            excluded_supplier_ids=[context.supplier_ids[1]],
        )

        job = BasketService(settings).create_job(member=context.member, payload=request)

        persisted = _basket_jobs(context.workspace.tenant_id)
        snapshot = persisted[0]["request_snapshot"]
        assert job.status == "queued"
        assert snapshot["kind"] == "advanced_basket_optimisation"
        assert snapshot["rule_version"] == "advanced-basket-v1"
        assert snapshot["urgency"] == "urgent"
        assert snapshot["hard_constraints"]["excluded_supplier_ids"] == [
            str(context.supplier_ids[1])
        ]
        assert snapshot["soft_weights"]["price_competitiveness"] == "0.5000"
        assert snapshot["supplier_terms"][0]["minimum_order_value"] == {
            "amount": "250.0000",
            "currency": "GBP",
        }
        assert {constraint["kind"] for constraint in snapshot["constraints"]} >= {
            "minimum_order_value",
            "quantity_tier",
            "supplier_exclusion",
            "urgency",
        }
        assert enqueued[0]["request_snapshot"]["rule_version"] == "advanced-basket-v1"


def test_advanced_basket_equivalent_active_job_conflicts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = settings_for_test_db(monkeypatch)
    monkeypatch.setattr(basket_service, "_enqueue_redis_job", _noop_enqueue)

    with committed_smart_context("advanced-conflict") as context:
        payload = _advanced_payload(context.supplier_ids, context.product_id)
        BasketService(settings).create_job(member=context.member, payload=payload)

        with pytest.raises(ConflictError) as exc_info:
            BasketService(settings).create_job(member=context.member, payload=payload)

        assert exc_info.value.details == {"reason": "basket_split_already_running"}


def test_advanced_basket_is_advisory_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = settings_for_test_db(monkeypatch)
    monkeypatch.setattr(basket_service, "_enqueue_redis_job", _noop_enqueue)

    with committed_smart_context("advanced-advisory") as context:
        before_purchase_requests = _purchase_request_count(context.workspace.tenant_id)

        job = BasketService(settings).create_job(
            member=context.member,
            payload=_advanced_payload(context.supplier_ids, context.product_id),
        )

        persisted = _basket_jobs(context.workspace.tenant_id)
        assert job.status == "queued"
        assert persisted[0]["result"] is None
        assert persisted[0]["status"] == "queued"
        assert _purchase_request_count(context.workspace.tenant_id) == before_purchase_requests


def _advanced_payload(
    supplier_ids: list[UUID],
    product_id: UUID,
    *,
    line_count: int = 1,
    excluded_supplier_ids: list[UUID] | None = None,
) -> AdvancedBasketOptimiseRequest:
    return AdvancedBasketOptimiseRequest(
        supplier_ids=supplier_ids,
        items=[
            BasketItemRequest(
                workspace_product_id=product_id,
                quantity="2.000000",
            )
            for _ in range(line_count)
        ],
        risk_tolerance="medium",
        urgency="urgent",
        weights=OptimisationWeights(
            price=0.5,
            preferred_supplier=0.2,
            risk=0.1,
            lead_time=0.1,
            quality=0.1,
        ),
        excluded_supplier_ids=excluded_supplier_ids or [],
    )


def _insert_supplier_term(
    context: object,
    supplier_id: UUID,
    *,
    mov_currency: str,
    quantity_tier_product_id: UUID | None = None,
) -> None:
    if not TEST_DATABASE_URL:
        raise RuntimeError("TEST_DATABASE_URL is required")
    now = datetime.now(UTC)
    quantity_tiers = []
    if quantity_tier_product_id is not None:
        quantity_tiers.append(
            {
                "workspace_product_id": str(quantity_tier_product_id),
                "min_quantity": "10.000000",
                "unit_price": {"amount": "9.5000", "currency": mov_currency},
            }
        )
    with psycopg.connect(TEST_DATABASE_URL) as conn:
        with conn.cursor() as cur:
            act_as(cur, context.workspace)
            cur.execute(
                """
                insert into supplier_commercial_term
                  (
                    tenant_id,
                    supplier_id,
                    effective_from,
                    effective_to,
                    minimum_order_value_amount,
                    minimum_order_value_currency,
                    quantity_tiers,
                    created_by_membership_id
                  )
                values (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    context.workspace.tenant_id,
                    supplier_id,
                    now - timedelta(days=1),
                    None,
                    Decimal("250.0000"),
                    mov_currency,
                    Jsonb(quantity_tiers),
                    context.workspace.membership_id,
                ),
            )
        conn.commit()


def _basket_jobs(tenant_id: UUID) -> list[dict[str, object]]:
    if not TEST_DATABASE_URL:
        raise RuntimeError("TEST_DATABASE_URL is required")
    with psycopg.connect(TEST_DATABASE_URL) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                select id, status, result, request_snapshot
                from basket_split_job
                where tenant_id = %s
                order by created_at desc
                """,
                (tenant_id,),
            )
            return [dict(row) for row in cur.fetchall()]


def _purchase_request_count(tenant_id: UUID) -> int:
    if not TEST_DATABASE_URL:
        raise RuntimeError("TEST_DATABASE_URL is required")
    with psycopg.connect(TEST_DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "select count(*) from purchase_request where tenant_id = %s",
                (tenant_id,),
            )
            return int(cur.fetchone()[0])


def _noop_enqueue(_settings: object, _row: dict[str, object], _member: object) -> None:
    return None

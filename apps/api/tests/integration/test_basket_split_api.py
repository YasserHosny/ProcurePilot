from __future__ import annotations

from decimal import Decimal
from uuid import UUID

import pytest

from integration.catalogue_helpers import TEST_DATABASE_URL
from integration.smart_compare_helpers import (
    add_costed_offer,
    committed_smart_context,
    fetch_basket_jobs,
    settings_for_test_db,
)
from procurepilot_api.errors import ServiceUnavailableError
from procurepilot_api.modules.offers import basket_service
from procurepilot_api.modules.offers.basket_service import BasketService
from procurepilot_api.modules.offers.schemas import BasketItemRequest, BasketOptimiseRequest

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is not set; needs a migrated local Postgres",
)


def test_create_job_persists_queued_row_for_real_visible_suppliers_and_products(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = settings_for_test_db(monkeypatch)
    with committed_smart_context("basket-queued") as context:
        for supplier_id in context.supplier_ids:
            add_costed_offer(
                context,
                supplier_id=supplier_id,
                amount=Decimal("3.0000"),
            )
        enqueued: list[tuple[UUID, UUID]] = []

        def fake_enqueue(_settings: object, row: dict[str, object], member: object) -> None:
            enqueued.append((UUID(str(row["id"])), member.tenant_id))

        monkeypatch.setattr(basket_service, "_enqueue_redis_job", fake_enqueue)
        job, created = BasketService(settings).create_job(
            member=context.member,
            payload=BasketOptimiseRequest(
                supplier_ids=context.supplier_ids,
                items=[
                    BasketItemRequest(
                        workspace_product_id=context.product_id,
                        quantity="2.000000",
                    )
                ],
            ),
        )

        assert created is True
        assert job.status == "queued"
        assert enqueued == [(job.id, context.workspace.tenant_id)]
        persisted = fetch_basket_jobs(context.workspace.tenant_id)
        assert persisted[0]["id"] == job.id
        assert persisted[0]["status"] == "queued"


def test_redis_enqueue_failure_durably_marks_job_failed_after_exception_unwinds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = settings_for_test_db(monkeypatch)
    with committed_smart_context("basket-failed") as context:
        for supplier_id in context.supplier_ids:
            add_costed_offer(
                context,
                supplier_id=supplier_id,
                amount=Decimal("3.0000"),
            )

        def fail_enqueue(_settings: object, _row: dict[str, object], _member: object) -> None:
            raise ServiceUnavailableError(details={"dependency": "redis"})

        monkeypatch.setattr(basket_service, "_enqueue_redis_job", fail_enqueue)
        with pytest.raises(ServiceUnavailableError):
            BasketService(settings).create_job(
                member=context.member,
                payload=BasketOptimiseRequest(
                    supplier_ids=context.supplier_ids,
                    items=[
                        BasketItemRequest(
                            workspace_product_id=context.product_id,
                            quantity="2.000000",
                        )
                    ],
                ),
            )

        persisted = fetch_basket_jobs(context.workspace.tenant_id)
        assert len(persisted) == 1
        assert persisted[0]["status"] == "failed"
        assert persisted[0]["error"]["code"] == "redis_enqueue_failed"


def test_create_job_replays_on_idempotency_key_without_reenqueuing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = settings_for_test_db(monkeypatch)
    with committed_smart_context("basket-replay") as context:
        for supplier_id in context.supplier_ids:
            add_costed_offer(context, supplier_id=supplier_id, amount=Decimal("3.0000"))
        enqueued: list[UUID] = []
        monkeypatch.setattr(
            basket_service,
            "_enqueue_redis_job",
            lambda _settings, row, _member: enqueued.append(UUID(str(row["id"]))),
        )
        payload = BasketOptimiseRequest(
            supplier_ids=context.supplier_ids,
            items=[
                BasketItemRequest(
                    workspace_product_id=context.product_id,
                    quantity="2.000000",
                )
            ],
        )
        key = UUID("00000000-0000-0000-0000-000000000001")
        first, first_created = BasketService(settings).create_job(
            member=context.member, payload=payload, idempotency_key=key
        )
        second, second_created = BasketService(settings).create_job(
            member=context.member, payload=payload, idempotency_key=key
        )

        assert first_created is True
        assert second_created is False
        assert second.id == first.id
        assert enqueued == [first.id]
        assert len(fetch_basket_jobs(context.workspace.tenant_id)) == 1


def test_failed_enqueue_is_retried_for_the_same_idempotency_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = settings_for_test_db(monkeypatch)
    with committed_smart_context("basket-failed-retry") as context:
        for supplier_id in context.supplier_ids:
            add_costed_offer(context, supplier_id=supplier_id, amount=Decimal("3.0000"))
        payload = BasketOptimiseRequest(
            supplier_ids=context.supplier_ids,
            items=[
                BasketItemRequest(
                    workspace_product_id=context.product_id,
                    quantity="2.000000",
                )
            ],
        )
        key = UUID("00000000-0000-0000-0000-000000000003")
        attempts = 0

        def enqueue(_settings: object, _row: dict[str, object], _member: object) -> None:
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise ServiceUnavailableError(details={"dependency": "redis"})

        monkeypatch.setattr(basket_service, "_enqueue_redis_job", enqueue)
        with pytest.raises(ServiceUnavailableError):
            BasketService(settings).create_job(
                member=context.member, payload=payload, idempotency_key=key
            )

        job, created = BasketService(settings).create_job(
            member=context.member, payload=payload, idempotency_key=key
        )
        assert created is True
        assert job.status == "queued"
        assert attempts == 2
        assert fetch_basket_jobs(context.workspace.tenant_id)[0]["status"] == "queued"

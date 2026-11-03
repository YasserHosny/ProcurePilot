from __future__ import annotations

from decimal import Decimal
from uuid import UUID

import psycopg
import pytest

from integration.catalogue_helpers import TEST_DATABASE_URL
from integration.smart_compare_helpers import (
    add_costed_offer,
    committed_smart_context,
    fetch_basket_jobs,
    settings_for_test_db,
)
from procurepilot_api.errors import ServiceUnavailableError, UnprocessableEntityError
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


def test_failed_enqueue_compensation_never_overwrites_an_attempt_a_worker_claimed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Redis can accept the job and still raise (lost reply); a worker may already be running
    it by the time the API compensates, and that attempt must be left alone."""
    settings = settings_for_test_db(monkeypatch)
    with committed_smart_context("basket-fenced") as context:
        for supplier_id in context.supplier_ids:
            add_costed_offer(context, supplier_id=supplier_id, amount=Decimal("3.0000"))

        def claimed_then_fail(_settings: object, row: dict[str, object], _member: object) -> None:
            with psycopg.connect(TEST_DATABASE_URL, prepare_threshold=None) as worker:
                worker.execute(
                    "update basket_split_job set status = 'running', started_at = now() "
                    "where id = %s and created_at = %s",
                    (row["id"], row["created_at"]),
                )
                worker.commit()
            raise ServiceUnavailableError(details={"dependency": "redis"})

        monkeypatch.setattr(basket_service, "_enqueue_redis_job", claimed_then_fail)
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
        assert persisted[0]["status"] == "running"
        assert persisted[0]["error"] is None


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


def test_recent_splits_list_pages_newest_first_with_a_summary_of_each(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PPS-209: there was no way to find an earlier split except by its URL."""
    settings = settings_for_test_db(monkeypatch)
    with committed_smart_context("basket-history") as context:
        for supplier_id in context.supplier_ids:
            add_costed_offer(context, supplier_id=supplier_id, amount=Decimal("3.0000"))
        monkeypatch.setattr(basket_service, "_enqueue_redis_job", lambda *_a, **_k: None)
        service = BasketService(settings)
        created: list[UUID] = []
        for quantity in ("1.000000", "2.000000", "3.000000"):
            job, _ = service.create_job(
                member=context.member,
                payload=BasketOptimiseRequest(
                    supplier_ids=context.supplier_ids,
                    items=[
                        BasketItemRequest(
                            workspace_product_id=context.product_id, quantity=quantity
                        )
                    ],
                ),
            )
            created.append(job.id)

        first = service.list_jobs(member=context.member, limit=2)
        assert [item.id for item in first.items] == [created[2], created[1]]
        assert first.next_cursor is not None
        assert first.items[0].status == "queued"
        assert first.items[0].item_count == 1
        assert len(first.items[0].supplier_ids) == 2

        # A split created between pages must not repeat or hide anything.
        service.create_job(
            member=context.member,
            payload=BasketOptimiseRequest(
                supplier_ids=context.supplier_ids,
                items=[
                    BasketItemRequest(workspace_product_id=context.product_id, quantity="9.000000")
                ],
            ),
        )
        second = service.list_jobs(member=context.member, limit=2, cursor=first.next_cursor)
        assert [item.id for item in second.items] == [created[0]]
        assert second.next_cursor is None

        with pytest.raises(UnprocessableEntityError):
            service.list_jobs(member=context.member, cursor="not-a-cursor")


def test_recent_splits_names_the_suppliers_and_reports_a_dead_job_as_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Review: the list must not show a job nobody works on as Queued, nor bare supplier ids."""
    settings = settings_for_test_db(monkeypatch)
    with committed_smart_context("basket-history-stale") as context:
        for supplier_id in context.supplier_ids:
            add_costed_offer(context, supplier_id=supplier_id, amount=Decimal("3.0000"))
        monkeypatch.setattr(basket_service, "_enqueue_redis_job", lambda *_a, **_k: None)
        monkeypatch.setattr(basket_service, "optimiser_worker_alive", lambda _settings: None)
        service = BasketService(settings)
        job, _ = service.create_job(
            member=context.member,
            payload=BasketOptimiseRequest(
                supplier_ids=context.supplier_ids,
                items=[
                    BasketItemRequest(workspace_product_id=context.product_id, quantity="1.000000")
                ],
            ),
        )
        with psycopg.connect(TEST_DATABASE_URL, autocommit=True) as conn:
            conn.execute(
                "update basket_split_job set created_at = now() - interval '2 days' where id = %s",
                (job.id,),
            )

        listed = service.list_jobs(member=context.member).items[0]

        assert listed.status == "failed"
        assert all(name for name in listed.supplier_names)
        assert len(listed.supplier_names) == 2

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from procurepilot_api.config import Settings, get_settings
from procurepilot_api.deps import CurrentMember
from procurepilot_api.errors import ConflictError, NotFoundError, ServiceUnavailableError
from procurepilot_api.modules.offers.schemas import BasketOptimiseRequest, BasketSplitJob
from procurepilot_api.modules.offers.service import _authenticated_db


class BasketService:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    def create_job(
        self,
        *,
        member: CurrentMember,
        payload: BasketOptimiseRequest,
    ) -> BasketSplitJob:
        with _authenticated_db(self._settings, member) as conn:
            _visible_suppliers(conn, payload.supplier_ids)
            _visible_products(conn, [item.workspace_product_id for item in payload.items])
            _ensure_no_active_equivalent(conn, payload)
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    insert into basket_split_job
                      (tenant_id, requested_by, supplier_ids, items, status)
                    values (%s, %s, %s, %s, 'queued')
                    returning *
                    """,
                    (
                        member.tenant_id,
                        member.membership_id,
                        [str(supplier_id) for supplier_id in payload.supplier_ids],
                        Jsonb([item.model_dump(mode="json") for item in payload.items]),
                    ),
                )
                row = dict(cur.fetchone())
            try:
                _enqueue_redis_job(self._settings, row, member)
            except ServiceUnavailableError:
                _compensate_failed_enqueue(conn, UUID(str(row["id"])))
                conn.commit()
                raise
            return _job(row)

    def get_job(self, *, member: CurrentMember, job_id: UUID) -> BasketSplitJob:
        with _authenticated_db(self._settings, member) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute("select * from basket_split_job where id = %s", (job_id,))
                row = cur.fetchone()
        if row is None:
            raise NotFoundError(details={"resource": "basket_split_job"})
        return _job(dict(row))


def get_basket_service() -> BasketService:
    return BasketService()


def _visible_suppliers(conn: object, supplier_ids: list[UUID]) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            select id from supplier
            where id = any(%s::uuid[]) and status in ('active','preferred')
            """,
            ([str(supplier_id) for supplier_id in supplier_ids],),
        )
        found = {row[0] for row in cur.fetchall()}
    if found != set(supplier_ids):
        raise NotFoundError(details={"resource": "supplier"})


def _visible_products(conn: object, product_ids: list[UUID]) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "select id from workspace_product where id = any(%s::uuid[]) and status = 'active'",
            ([str(product_id) for product_id in product_ids],),
        )
        found = {row[0] for row in cur.fetchall()}
    if found != set(product_ids):
        raise NotFoundError(details={"resource": "workspace_product"})


def _ensure_no_active_equivalent(conn: object, payload: BasketOptimiseRequest) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            select id from basket_split_job
            where status in ('queued', 'running')
              and supplier_ids = %s::uuid[]
              and items = %s::jsonb
            limit 1
            """,
            (
                [str(supplier_id) for supplier_id in payload.supplier_ids],
                Jsonb([item.model_dump(mode="json") for item in payload.items]),
            ),
        )
        if cur.fetchone() is not None:
            raise ConflictError(details={"reason": "basket_split_already_running"})


def _enqueue_redis_job(settings: Settings, row: dict[str, object], member: CurrentMember) -> None:
    try:
        from redis import Redis
        from rq import Queue
    except ImportError as exc:
        raise ServiceUnavailableError(details={"dependency": "rq"}) from exc
    try:
        queue = Queue(
            settings.basket_split_queue_name,
            connection=Redis.from_url(settings.redis_url),
        )
        queue.enqueue(
            "procurepilot_optimiser_worker.worker.process_basket_split_job",
            {"job_id": str(row["id"]), "tenant_id": str(member.tenant_id)},
            job_id=str(row["id"]),
        )
    except Exception as exc:
        raise ServiceUnavailableError(details={"dependency": "redis"}) from exc


def _compensate_failed_enqueue(conn: object, job_id: UUID) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            update basket_split_job
            set status = 'failed',
                error = %s,
                completed_at = %s
            where id = %s
            """,
            (
                Jsonb(
                    {
                        "code": "redis_enqueue_failed",
                        "message": "Basket split job could not be queued in Redis.",
                    }
                ),
                datetime.now(UTC),
                job_id,
            ),
        )


def _job(row: dict[str, object]) -> BasketSplitJob:
    return BasketSplitJob.model_validate(
        {
            "id": row["id"],
            "supplier_ids": row["supplier_ids"],
            "items": row["items"],
            "status": row["status"],
            "result": row.get("result"),
            "error": row.get("error"),
            "result_url": f"/api/v1/baskets/{row['id']}",
            "created_at": row["created_at"],
            "started_at": row.get("started_at"),
            "completed_at": row.get("completed_at"),
        }
    )

from __future__ import annotations

import logging
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from procurepilot_api.config import Settings, get_settings
from procurepilot_api.deps import CurrentMember
from procurepilot_api.errors import (
    ConflictError,
    NotFoundError,
    ServiceUnavailableError,
    UnprocessableEntityError,
)
from procurepilot_api.modules.offers.basket_liveness import (
    STALE_MESSAGES,
    attempt_token,
    cancel_rq_job,
    optimiser_worker_alive,
    rq_job_id,
    stale_code,
)
from procurepilot_api.modules.offers.basket_result_compat import normalise_stored_result
from procurepilot_api.modules.offers.schemas import (
    AdvancedBasketOptimiseRequest,
    BasketOptimiseRequest,
    BasketSplitJob,
    Money,
)
from procurepilot_api.modules.offers.service import _authenticated_db
from procurepilot_api.shared.audit import AuditEventCreate, get_audit_writer
from procurepilot_api.shared.logging import get_trace_id

ADVANCED_BASKET_RULE_VERSION = "advanced-basket-v1"
BasketRequest = BasketOptimiseRequest | AdvancedBasketOptimiseRequest


logger = logging.getLogger(__name__)


class BasketService:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    def create_job(
        self,
        *,
        member: CurrentMember,
        payload: BasketRequest | None = None,
        rfq_id: UUID | None = None,
        bearer_token: str | None = None,
        idempotency_key: UUID | None = None,
    ) -> tuple[BasketSplitJob, bool]:
        with _authenticated_db(self._settings, member) as conn:
            if rfq_id is not None:
                from procurepilot_api.modules.rfq.service import lock_rfq_for_preparation

                with conn.cursor() as cur:
                    if (
                        lock_rfq_for_preparation(cur, tenant_id=member.tenant_id, rfq_id=rfq_id)
                        is None
                    ):
                        raise NotFoundError(details={"resource": "rfq"})
            job, created, pending = self._create_job_in_tx(
                conn, member=member, payload=payload, idempotency_key=idempotency_key, rfq_id=rfq_id
            )
        if pending is not None:
            # Enqueue only after the row is committed: a worker that dequeues first would
            # otherwise find nothing to claim and drop the delivery as stale.
            try:
                _enqueue_redis_job(self._settings, pending, member)
            except ServiceUnavailableError:
                with _authenticated_db(self._settings, member) as conn:
                    _compensate_failed_enqueue(
                        conn, UUID(str(pending["id"])), attempt=pending["created_at"]
                    )
                raise
        if created and isinstance(payload, AdvancedBasketOptimiseRequest):
            _record_audit(
                bearer_token=bearer_token,
                member=member,
                action="offers.advanced_basket_submitted",
                target={
                    "basket_split_job_id": str(job.id),
                    "supplier_ids": [str(supplier_id) for supplier_id in payload.supplier_ids],
                    "line_count": len(payload.items),
                    "rule_version": ADVANCED_BASKET_RULE_VERSION,
                },
            )
        return job, created

    def _create_job_in_tx(
        self,
        conn: object,
        *,
        member: CurrentMember,
        payload: BasketRequest | None,
        idempotency_key: UUID | None,
        rfq_id: UUID | None = None,
    ) -> tuple[BasketSplitJob, bool, dict[str, object] | None]:
        """Persist (or find) the job; returns the row to enqueue once this transaction commits."""
        if idempotency_key is not None:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    "select * from basket_split_job "
                    "where tenant_id = %s and idempotency_key = %s limit 1",
                    (member.tenant_id, idempotency_key),
                )
                existing = cur.fetchone()
            if existing is not None:
                existing = dict(existing)
                if existing.get("rfq_id") != rfq_id:
                    raise ConflictError(details={"reason": "idempotency_key_reused"})
                if existing["status"] != "failed":
                    return _job(existing), False, None
                if rfq_id is not None:
                    from procurepilot_api.modules.offers.rfq_split import build_rfq_split_request

                    # A failed attempt cannot restart after conversion or after its replies
                    # cease to qualify. Keep its original pricing snapshot for a retry.
                    build_rfq_split_request(conn, member, rfq_id)
                # Requeue first: the new created_at is this attempt's fence token.
                requeued = _requeue_failed_job(conn, UUID(str(existing["id"])))
                return _job(requeued), True, requeued
        rfq_snapshot = None
        if rfq_id is not None:
            from procurepilot_api.modules.offers.rfq_split import build_rfq_split_request

            payload, rfq_snapshot = build_rfq_split_request(conn, member, rfq_id)
        if payload is None:
            raise ValueError("basket payload or rfq_id is required")
        self._expire_stuck_jobs(conn)
        _visible_suppliers(conn, payload.supplier_ids)
        _visible_products(conn, [item.workspace_product_id for item in payload.items])
        request_snapshot = _request_snapshot(conn, member, payload)
        if rfq_snapshot is not None:
            request_snapshot["rfq"] = rfq_snapshot
        _ensure_no_active_equivalent(conn, payload, request_snapshot)
        job_id = uuid4()
        with conn.cursor() as cur:
            cur.execute("savepoint basket_split_job_insert")
        try:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    insert into basket_split_job
                      (id, tenant_id, requested_by, supplier_ids, items, request_snapshot,
                       idempotency_key, status, rfq_id)
                    values (%s, %s, %s, %s, %s, %s, %s, 'queued', %s)
                    returning *
                    """,
                    (
                        job_id,
                        member.tenant_id,
                        member.membership_id,
                        [str(supplier_id) for supplier_id in payload.supplier_ids],
                        Jsonb([item.model_dump(mode="json") for item in payload.items]),
                        Jsonb(request_snapshot) if request_snapshot is not None else None,
                        idempotency_key,
                        rfq_id,
                    ),
                )
                row = dict(cur.fetchone())
        except psycopg.errors.UniqueViolation:
            with conn.cursor() as cur:
                cur.execute("rollback to savepoint basket_split_job_insert")
                cur.execute("release savepoint basket_split_job_insert")
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    "select * from basket_split_job "
                    "where tenant_id = %s and idempotency_key = %s limit 1",
                    (member.tenant_id, idempotency_key),
                )
                existing = cur.fetchone()
            if existing is None:
                raise
            if existing.get("rfq_id") != rfq_id:
                raise ConflictError(details={"reason": "idempotency_key_reused"}) from None
            return _job(dict(existing)), False, None
        if rfq_snapshot is not None:
            with conn.cursor() as cur:
                cur.execute(
                    "select record_audit_event(%s, 'success'::audit_outcome, %s, %s, %s, "
                    "%s::jsonb, %s)",
                    (
                        "offers.rfq_split_started",
                        member.tenant_id,
                        member.membership_id,
                        member.email,
                        Jsonb(
                            {
                                "rfq_id": str(rfq_id),
                                "basket_split_job_id": str(job_id),
                                "price_quotation_ids": rfq_snapshot["price_quotation_ids"],
                            }
                        ),
                        get_trace_id(),
                    ),
                )
        return _job(row), True, row

    def get_job(self, *, member: CurrentMember, job_id: UUID) -> BasketSplitJob:
        with _authenticated_db(self._settings, member) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute("select * from basket_split_job where id = %s", (job_id,))
                row = cur.fetchone()
            if row is None:
                raise NotFoundError(details={"resource": "basket_split_job"})
            row = dict(row)
            code = self._stale_code(row, worker_alive=None)
            if code is not None:
                row = self._fail_stuck(conn, row, code)
        return _job(row)

    def _stale_code(self, row: dict[str, object], *, worker_alive: bool | None) -> str | None:
        if row["status"] == "queued" and worker_alive is None:
            worker_alive = optimiser_worker_alive(self._settings)
        return stale_code(
            status=str(row["status"]),
            created_at=row["created_at"],
            started_at=row.get("started_at"),
            now=datetime.now(UTC),
            stall_seconds=self._settings.basket_split_stall_seconds,
            expiry_seconds=self._settings.basket_split_expiry_seconds,
            worker_alive=worker_alive,
        )

    def _fail_stuck(self, conn: object, row: dict[str, object], code: str) -> dict[str, object]:
        """Mark a job nobody is working on as failed so the UI can offer a retry.

        The update is best-effort under RLS; the returned row reflects the failure either way
        so a read-only member also sees it.
        """
        error = {"code": code, "message": STALE_MESSAGES[code]}
        completed_at = datetime.now(UTC)
        cancel_rq_job(self._settings, row)
        with conn.cursor() as cur:
            cur.execute(
                "update basket_split_job set status = 'failed', error = %s, completed_at = %s "
                "where id = %s and status in ('queued', 'running')",
                (Jsonb(error), completed_at, row["id"]),
            )
        return {**row, "status": "failed", "error": error, "completed_at": completed_at}

    def _expire_stuck_jobs(self, conn: object) -> None:
        """Fail stuck jobs in this tenant so a retry is not blocked as 'already running'."""
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("select * from basket_split_job where status in ('queued', 'running')")
            active = [dict(r) for r in cur.fetchall()]
        alive = (
            optimiser_worker_alive(self._settings)
            if any(r["status"] == "queued" for r in active)
            else None
        )
        for row in active:
            code = self._stale_code(row, worker_alive=alive)
            if code is not None:
                self._fail_stuck(conn, row, code)


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


def _ensure_no_active_equivalent(
    conn: object,
    payload: BasketRequest,
    request_snapshot: dict[str, object] | None,
) -> None:
    if request_snapshot is not None:
        _ensure_no_active_advanced_equivalent(conn, request_snapshot)
        return
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


def _ensure_no_active_advanced_equivalent(
    conn: object,
    request_snapshot: dict[str, object],
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            select id from basket_split_job
            where status in ('queued', 'running')
              and request_snapshot = %s::jsonb
            limit 1
            """,
            (Jsonb(request_snapshot),),
        )
        if cur.fetchone() is not None:
            raise ConflictError(details={"reason": "basket_split_already_running"})


def _request_snapshot(
    conn: object,
    member: CurrentMember,
    payload: BasketRequest,
) -> dict[str, object] | None:
    if isinstance(payload, BasketOptimiseRequest):
        return None
    supplier_terms = _current_supplier_terms(conn, payload.supplier_ids)
    _ensure_single_currency(supplier_terms)
    weights = payload.weights.model_dump(mode="json")
    return {
        "kind": "advanced_basket_optimisation",
        "rule_version": ADVANCED_BASKET_RULE_VERSION,
        "tenant_id": str(member.tenant_id),
        "requested_by": str(member.membership_id),
        "supplier_ids": [str(supplier_id) for supplier_id in payload.supplier_ids],
        "items": [item.model_dump(mode="json") for item in payload.items],
        "risk_tolerance": payload.risk_tolerance,
        "urgency": payload.urgency,
        "excluded_supplier_ids": [
            str(supplier_id) for supplier_id in payload.excluded_supplier_ids
        ],
        "hard_constraints": {
            "excluded_supplier_ids": [
                str(supplier_id) for supplier_id in payload.excluded_supplier_ids
            ],
            "risk_tolerance": payload.risk_tolerance,
            "urgency": payload.urgency,
        },
        "soft_weights": {
            "price_competitiveness": _weight(weights["price"]),
            "preferred_supplier": _weight(weights["preferred_supplier"]),
            "risk": _weight(weights["risk"]),
            "lead_time": _weight(weights["lead_time"]),
            "quality": _weight(weights["quality"]),
        },
        "weights": weights,
        "pack_snapshot": _pack_snapshot(
            conn, [item.workspace_product_id for item in payload.items]
        ),
        "supplier_terms": supplier_terms,
        "constraints": _constraints_from_supplier_terms(
            supplier_terms,
            payload.excluded_supplier_ids,
            payload.urgency,
        ),
    }


def _pack_snapshot(conn: object, product_ids: list[UUID]) -> dict[str, dict[str, str]]:
    """Pack size and base unit per product at submission: the newest pack, as the catalogue
    shows it (same tie-break as the purchase_request_line pack-snapshot migration)."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            select distinct on (wp.id)
              wp.id, pd.base_quantity, cp.base_unit
            from workspace_product wp
            join canonical_product cp on cp.id = wp.canonical_product_id
            join pack_definition pd on pd.workspace_product_id = wp.id
            where wp.id = any(%s::uuid[])
            order by wp.id, pd.created_at desc, pd.id desc
            """,
            ([str(product_id) for product_id in product_ids],),
        )
        rows = cur.fetchall()
    return {
        str(row["id"]): {
            "base_quantity": f"{Decimal(str(row['base_quantity'])):f}",
            "base_unit": str(row["base_unit"]),
        }
        for row in rows
    }


def _current_supplier_terms(
    conn: object,
    supplier_ids: list[UUID],
) -> list[dict[str, object]]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            select distinct on (supplier_id)
              id,
              supplier_id,
              effective_from,
              effective_to,
              minimum_order_value_amount,
              minimum_order_value_currency,
              delivery_fee_amount,
              delivery_fee_currency,
              free_delivery_threshold_amount,
              free_delivery_threshold_currency,
              quantity_tiers,
              rule_version
            from supplier_commercial_term
            where supplier_id = any(%s::uuid[])
              and effective_from <= now()
              and (effective_to is null or effective_to > now())
            order by supplier_id, effective_from desc, created_at desc, id desc
            """,
            ([str(supplier_id) for supplier_id in supplier_ids],),
        )
        rows = [dict(row) for row in cur.fetchall()]
    return [_supplier_term_snapshot(row) for row in rows]


def _supplier_term_snapshot(row: dict[str, object]) -> dict[str, object]:
    return {
        "id": str(row["id"]),
        "supplier_id": str(row["supplier_id"]),
        "rule_version": str(row["rule_version"]),
        "effective_from": row["effective_from"].isoformat(),
        "effective_to": (
            row["effective_to"].isoformat() if row.get("effective_to") is not None else None
        ),
        "minimum_order_value": _money(row, "minimum_order_value"),
        "delivery_fee": _money(row, "delivery_fee"),
        "free_delivery_threshold": _money(row, "free_delivery_threshold"),
        "quantity_tiers": row.get("quantity_tiers") or [],
    }


def _constraints_from_supplier_terms(
    supplier_terms: list[dict[str, object]],
    excluded_supplier_ids: list[UUID],
    urgency: str,
) -> list[dict[str, object]]:
    constraints: list[dict[str, object]] = [
        {
            "kind": "supplier_exclusion",
            "supplier_id": str(supplier_id),
            "description": "Supplier excluded by requester.",
            "source_ids": [],
        }
        for supplier_id in excluded_supplier_ids
    ]
    constraints.append(
        {
            "kind": "urgency",
            "description": "Requested basket urgency.",
            "value": urgency,
            "source_ids": [],
        }
    )
    for term in supplier_terms:
        supplier_id = str(term["supplier_id"])
        source_ids = [str(term["id"])]
        for field_name, kind in (
            ("minimum_order_value", "minimum_order_value"),
            ("delivery_fee", "delivery_fee"),
            ("free_delivery_threshold", "free_delivery_threshold"),
        ):
            money = term.get(field_name)
            if money is not None:
                constraints.append(
                    {
                        "kind": kind,
                        "supplier_id": supplier_id,
                        "description": field_name,
                        "money": money,
                        "source_ids": source_ids,
                    }
                )
        for tier in term["quantity_tiers"]:
            constraints.append(
                {
                    "kind": "quantity_tier",
                    "supplier_id": supplier_id,
                    "workspace_product_id": tier.get("workspace_product_id"),
                    "description": "Supplier quantity tier.",
                    "money": tier.get("unit_price"),
                    "source_ids": source_ids,
                }
            )
    return constraints


def _ensure_single_currency(supplier_terms: list[dict[str, object]]) -> None:
    currencies: set[str] = set()
    for term in supplier_terms:
        for key in ("minimum_order_value", "delivery_fee", "free_delivery_threshold"):
            money = term.get(key)
            if money is not None:
                currencies.add(_money_currency(money))
        for tier in term["quantity_tiers"]:
            currencies.add(_money_currency(tier.get("unit_price")))
    if len(currencies) > 1:
        raise UnprocessableEntityError(details={"currency": "mixed_advanced_basket_currency"})


def _money_currency(value: object) -> str:
    if not isinstance(value, dict) or not value.get("currency"):
        raise UnprocessableEntityError(details={"currency": "money_currency_required"})
    return str(value["currency"])


def _money(row: dict[str, object], prefix: str) -> dict[str, str] | None:
    amount = row.get(f"{prefix}_amount")
    currency = row.get(f"{prefix}_currency")
    if amount is None and currency is None:
        return None
    if amount is None or currency is None:
        raise UnprocessableEntityError(details={prefix: "money_pair_required"})
    return Money(amount=f"{Decimal(str(amount)):.4f}", currency=str(currency)).model_dump(
        mode="json"
    )


def _weight(value: object) -> str:
    return f"{Decimal(str(value)):.4f}"


def _record_audit(
    *,
    bearer_token: str | None,
    member: CurrentMember,
    action: str,
    target: dict[str, object],
) -> None:
    get_audit_writer().record(
        AuditEventCreate(
            tenant_id=member.tenant_id,
            actor_membership_id=member.membership_id,
            actor_email=member.email,
            action=action,
            target=target,
            outcome="success",
            trace_id=get_trace_id(),
        ),
        bearer_token=bearer_token,
    )


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
            {
                "job_id": str(row["id"]),
                "tenant_id": str(member.tenant_id),
                "rule_version": (
                    row["request_snapshot"].get("rule_version")
                    if isinstance(row.get("request_snapshot"), dict)
                    else None
                ),
                "attempt": attempt_token(row),
                "request_kind": (
                    row["request_snapshot"].get("kind")
                    if isinstance(row.get("request_snapshot"), dict)
                    else "basket_split"
                ),
            },
            job_id=rq_job_id(row),
        )
    except Exception as exc:
        # The client sees only «redis unavailable»; the cause (refused, timeout, AUTH, a bad
        # payload) goes to the log. Never log settings.redis_url: it can carry the password.
        logger.exception(
            "Could not enqueue basket-split job %s on queue %s: %s: %s",
            row.get("id"),
            settings.basket_split_queue_name,
            type(exc).__name__,
            exc,
        )
        raise ServiceUnavailableError(details={"dependency": "redis"}) from exc


def _requeue_failed_job(conn: object, job_id: UUID) -> dict[str, object]:
    """Reset a failed job to a fresh queued attempt.

    ``created_at``/``started_at`` restart so the stuck-job expiry measures this attempt, not
    the original one (otherwise a retry of an expired job is failed again on its first poll).
    """
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            "update basket_split_job "
            "set status = 'queued', error = null, completed_at = null, "
            "started_at = null, created_at = now() "
            "where id = %s returning *",
            (job_id,),
        )
        return dict(cur.fetchone())


def _compensate_failed_enqueue(conn: object, job_id: UUID, *, attempt: object) -> None:
    """Fail the attempt whose enqueue raised, only if it is still queued as that attempt.

    Redis may have accepted the job before the client lost the reply, so a worker can already
    have claimed or finished it; ``created_at`` is the attempt's fence token (see
    ``attempt_token``).
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            update basket_split_job
            set status = 'failed',
                error = %s,
                completed_at = %s
            where id = %s and status = 'queued' and created_at = %s
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
                attempt,
            ),
        )


def _job(row: dict[str, object]) -> BasketSplitJob:
    return BasketSplitJob.model_validate(
        {
            "id": row["id"],
            "supplier_ids": row["supplier_ids"],
            "items": row["items"],
            "status": row["status"],
            "result": normalise_stored_result(row.get("result")),
            "error": row.get("error"),
            "result_url": f"/api/v1/baskets/{row['id']}",
            "created_at": row["created_at"],
            "started_at": row.get("started_at"),
            "completed_at": row.get("completed_at"),
            "rfq_id": row.get("rfq_id"),
            "pack_snapshot": (
                row["request_snapshot"].get("pack_snapshot")
                if isinstance(row.get("request_snapshot"), dict)
                else None
            ),
        }
    )

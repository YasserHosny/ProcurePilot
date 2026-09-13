from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

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


class BasketService:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    def create_job(
        self,
        *,
        member: CurrentMember,
        payload: BasketRequest,
        bearer_token: str | None = None,
    ) -> BasketSplitJob:
        with _authenticated_db(self._settings, member) as conn:
            _visible_suppliers(conn, payload.supplier_ids)
            _visible_products(conn, [item.workspace_product_id for item in payload.items])
            request_snapshot = _request_snapshot(conn, member, payload)
            _ensure_no_active_equivalent(conn, payload, request_snapshot)
            job_id = uuid4()
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    insert into basket_split_job
                      (id, tenant_id, requested_by, supplier_ids, items, request_snapshot, status)
                    values (%s, %s, %s, %s, %s, %s, 'queued')
                    returning *
                    """,
                    (
                        job_id,
                        member.tenant_id,
                        member.membership_id,
                        [str(supplier_id) for supplier_id in payload.supplier_ids],
                        Jsonb([item.model_dump(mode="json") for item in payload.items]),
                        Jsonb(request_snapshot) if request_snapshot is not None else None,
                    ),
                )
                row = dict(cur.fetchone())
            try:
                _enqueue_redis_job(self._settings, row, member)
            except ServiceUnavailableError:
                _compensate_failed_enqueue(conn, UUID(str(row["id"])))
                conn.commit()
                raise
            job = _job(row)
        if isinstance(payload, AdvancedBasketOptimiseRequest):
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
        return job

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
        "supplier_terms": supplier_terms,
        "constraints": _constraints_from_supplier_terms(
            supplier_terms,
            payload.excluded_supplier_ids,
            payload.urgency,
        ),
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
        raise UnprocessableEntityError(
            details={"currency": "mixed_advanced_basket_currency"}
        )


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
                "request_kind": (
                    row["request_snapshot"].get("kind")
                    if isinstance(row.get("request_snapshot"), dict)
                    else "basket_split"
                ),
            },
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

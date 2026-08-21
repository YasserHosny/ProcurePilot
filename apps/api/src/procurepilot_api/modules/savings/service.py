from __future__ import annotations

import base64
import json
from datetime import date
from decimal import Decimal
from uuid import UUID

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from procurepilot_api.config import Settings, get_settings
from procurepilot_api.deps import CurrentMember
from procurepilot_api.errors import (
    ConflictError,
    NotFoundError,
    UnprocessableEntityError,
)
from procurepilot_api.modules.offers.service import _authenticated_db
from procurepilot_api.modules.savings.baseline import CALCULATION_VERSION, capture_baseline
from procurepilot_api.modules.savings.schemas import (
    Money,
    PurchaseOutcomeCreate,
    PurchaseOutcomeCreated,
    PurchaseRecord,
    SavingList,
    SavingRecord,
)


class SavingsService:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    def record_purchase(
        self,
        *,
        member: CurrentMember,
        payload: PurchaseOutcomeCreate,
    ) -> PurchaseOutcomeCreated:
        if payload.unit_price.currency != payload.total_paid.currency:
            raise UnprocessableEntityError(details={"currency": "unit_price_total_paid_mismatch"})
        with _authenticated_db(self._settings, member) as conn:
            _visible(
                conn,
                "workspace_product",
                payload.workspace_product_id,
                extra="status = 'active'",
            )
            _visible_optional(conn, "supplier", payload.supplier_id)
            _visible_optional(conn, "quotation_line", payload.quotation_line_id)
            _visible_optional(conn, "match_decision", payload.match_decision_id)
            _visible_optional(conn, "landed_cost", payload.landed_cost_id)
            baseline = capture_baseline(
                conn,
                product_id=payload.workspace_product_id,
                quantity=payload.quantity,
                actual=payload.total_paid,
            )
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    insert into purchase_record (
                      tenant_id, workspace_product_id, supplier_id, quotation_line_id,
                      match_decision_id, landed_cost_id, recorded_by, quantity, base_unit,
                      unit_price_amount, unit_price_currency, total_paid_amount,
                      total_paid_currency, delivery_result, ordered_at, delivered_at, notes
                    ) values (
                      %(tenant_id)s, %(workspace_product_id)s, %(supplier_id)s,
                      %(quotation_line_id)s, %(match_decision_id)s, %(landed_cost_id)s,
                      %(recorded_by)s, %(quantity)s, %(base_unit)s, %(unit_price_amount)s,
                      %(unit_price_currency)s, %(total_paid_amount)s, %(total_paid_currency)s,
                      %(delivery_result)s, %(ordered_at)s, %(delivered_at)s, %(notes)s
                    )
                    returning *
                    """,
                    {
                        "tenant_id": member.tenant_id,
                        "workspace_product_id": payload.workspace_product_id,
                        "supplier_id": payload.supplier_id,
                        "quotation_line_id": payload.quotation_line_id,
                        "match_decision_id": payload.match_decision_id,
                        "landed_cost_id": payload.landed_cost_id,
                        "recorded_by": member.membership_id,
                        "quantity": payload.quantity,
                        "base_unit": payload.base_unit,
                        "unit_price_amount": payload.unit_price.amount,
                        "unit_price_currency": payload.unit_price.currency,
                        "total_paid_amount": payload.total_paid.amount,
                        "total_paid_currency": payload.total_paid.currency,
                        "delivery_result": payload.delivery_result,
                        "ordered_at": payload.ordered_at,
                        "delivered_at": payload.delivered_at,
                        "notes": payload.notes,
                    },
                )
                purchase = dict(cur.fetchone())
                cur.execute(
                    """
                    insert into saving_record (
                      tenant_id, purchase_record_id, workspace_product_id, supplier_id,
                      status, baseline_policy, baseline_source_landed_cost_ids,
                      baseline_unit_price_amount, baseline_unit_price_currency,
                      baseline_value_amount, baseline_value_currency, actual_value_amount,
                      actual_value_currency, delta_amount, delta_currency, calculation_version,
                      calculation_inputs, recorded_by
                    ) values (
                      %(tenant_id)s, %(purchase_record_id)s, %(workspace_product_id)s,
                      %(supplier_id)s, 'pending', %(baseline_policy)s,
                      %(baseline_source_landed_cost_ids)s, %(baseline_unit_price_amount)s,
                      %(baseline_unit_price_currency)s, %(baseline_value_amount)s,
                      %(baseline_value_currency)s, %(actual_value_amount)s,
                      %(actual_value_currency)s, %(delta_amount)s, %(delta_currency)s,
                      %(calculation_version)s, %(calculation_inputs)s, %(recorded_by)s
                    )
                    returning *
                    """,
                    {
                        "tenant_id": member.tenant_id,
                        "purchase_record_id": purchase["id"],
                        "workspace_product_id": payload.workspace_product_id,
                        "supplier_id": payload.supplier_id,
                        "baseline_policy": baseline.policy,
                        "baseline_source_landed_cost_ids": baseline.source_landed_cost_ids,
                        "baseline_unit_price_amount": (
                            None if baseline.unit_price is None else baseline.unit_price.amount
                        ),
                        "baseline_unit_price_currency": (
                            None if baseline.unit_price is None else baseline.unit_price.currency
                        ),
                        "baseline_value_amount": (
                            None if baseline.value is None else baseline.value.amount
                        ),
                        "baseline_value_currency": (
                            None if baseline.value is None else baseline.value.currency
                        ),
                        "actual_value_amount": payload.total_paid.amount,
                        "actual_value_currency": payload.total_paid.currency,
                        "delta_amount": None if baseline.delta is None else baseline.delta.amount,
                        "delta_currency": (
                            None if baseline.delta is None else baseline.delta.currency
                        ),
                        "calculation_version": CALCULATION_VERSION,
                        "calculation_inputs": Jsonb(baseline.calculation_inputs),
                        "recorded_by": member.membership_id,
                    },
                )
                saving = dict(cur.fetchone())
            return PurchaseOutcomeCreated(
                purchase_record=_purchase(purchase),
                saving_record=_saving(saving),
            )

    def list_savings(
        self,
        *,
        member: CurrentMember,
        status: str | None = None,
        period_start: date | None = None,
        period_end: date | None = None,
        supplier_id: UUID | None = None,
        branch_id: UUID | None = None,
        cursor: str | None = None,
        limit: int = 50,
    ) -> SavingList:
        if branch_id is not None:
            raise UnprocessableEntityError(details={"branch_id": "unsupported_in_phase_1"})
        capped = max(1, min(limit, 100))
        offset = _decode_cursor(cursor)
        clauses = []
        params: dict[str, object] = {"limit": capped + 1, "offset": offset}
        if status is not None:
            clauses.append("status = %(status)s")
            params["status"] = status
        if period_start is not None:
            clauses.append("recorded_at::date >= %(period_start)s")
            params["period_start"] = period_start
        if period_end is not None:
            clauses.append("recorded_at::date <= %(period_end)s")
            params["period_end"] = period_end
        if supplier_id is not None:
            clauses.append("supplier_id = %(supplier_id)s")
            params["supplier_id"] = supplier_id
        where = "" if not clauses else "where " + " and ".join(clauses)
        with _authenticated_db(self._settings, member) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    f"""
                    select *
                    from saving_record {where}
                    order by recorded_at desc, id desc
                    limit %(limit)s offset %(offset)s
                    """,
                    params,
                )
                rows = [dict(row) for row in cur.fetchall()]
        next_cursor = _encode_cursor(offset + capped) if len(rows) > capped else None
        return SavingList(items=[_saving(row) for row in rows[:capped]], next_cursor=next_cursor)

    def get_saving(self, *, member: CurrentMember, saving_id: UUID) -> SavingRecord:
        with _authenticated_db(self._settings, member) as conn:
            row = _saving_row(conn, saving_id)
        return _saving(row)

    def verify_saving(self, *, member: CurrentMember, saving_id: UUID) -> SavingRecord:
        with _authenticated_db(self._settings, member) as conn:
            existing = _saving_row(conn, saving_id)
            if existing["status"] == "verified":
                raise ConflictError(details={"reason": "saving_already_verified"})
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    update saving_record
                    set status = 'verified', verified_at = now(), verified_by = %s
                    where id = %s and status = 'pending'
                    returning *
                    """,
                    (member.membership_id, saving_id),
                )
                row = cur.fetchone()
        if row is None:
            raise ConflictError(details={"reason": "saving_not_verifiable"})
        return _saving(dict(row))


def get_savings_service() -> SavingsService:
    return SavingsService()


def _visible(conn: object, table: str, row_id: UUID, *, extra: str | None = None) -> None:
    suffix = "" if extra is None else f" and {extra}"
    with conn.cursor() as cur:
        cur.execute(f"select id from {table} where id = %s{suffix}", (row_id,))
        if cur.fetchone() is None:
            raise NotFoundError(details={"resource": table})


def _visible_optional(conn: object, table: str, row_id: UUID | None) -> None:
    if row_id is not None:
        _visible(conn, table, row_id)


def _saving_row(conn: object, saving_id: UUID) -> dict[str, object]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("select * from saving_record where id = %s", (saving_id,))
        row = cur.fetchone()
    if row is None:
        raise NotFoundError(details={"resource": "saving_record"})
    return dict(row)


def _purchase(row: dict[str, object]) -> PurchaseRecord:
    return PurchaseRecord(
        id=UUID(str(row["id"])),
        workspace_product_id=UUID(str(row["workspace_product_id"])),
        supplier_id=_uuid_or_none(row.get("supplier_id")),
        quotation_line_id=_uuid_or_none(row.get("quotation_line_id")),
        match_decision_id=_uuid_or_none(row.get("match_decision_id")),
        landed_cost_id=_uuid_or_none(row.get("landed_cost_id")),
        quantity=Decimal(str(row["quantity"])),
        base_unit=str(row["base_unit"]),
        unit_price=Money(
            amount=Decimal(str(row["unit_price_amount"])),
            currency=str(row["unit_price_currency"]),
        ),
        total_paid=Money(
            amount=Decimal(str(row["total_paid_amount"])),
            currency=str(row["total_paid_currency"]),
        ),
        delivery_result=str(row["delivery_result"]),
        ordered_at=row.get("ordered_at"),
        delivered_at=row.get("delivered_at"),
        recorded_by=UUID(str(row["recorded_by"])),
        recorded_at=row["recorded_at"],
        notes=row.get("notes"),
    )


def _saving(row: dict[str, object]) -> SavingRecord:
    return SavingRecord(
        id=UUID(str(row["id"])),
        purchase_record_id=UUID(str(row["purchase_record_id"])),
        workspace_product_id=UUID(str(row["workspace_product_id"])),
        supplier_id=_uuid_or_none(row.get("supplier_id")),
        status=str(row["status"]),
        baseline_policy=str(row["baseline_policy"]),
        baseline_source_landed_cost_ids=[
            UUID(str(item)) for item in row["baseline_source_landed_cost_ids"]
        ],
        baseline_unit_price=_money_or_none(
            row.get("baseline_unit_price_amount"),
            row.get("baseline_unit_price_currency"),
        ),
        baseline_value=_money_or_none(
            row.get("baseline_value_amount"),
            row.get("baseline_value_currency"),
        ),
        actual_value=Money(
            amount=Decimal(str(row["actual_value_amount"])),
            currency=str(row["actual_value_currency"]),
        ),
        delta=_money_or_none(row.get("delta_amount"), row.get("delta_currency")),
        calculation_version=str(row["calculation_version"]),
        calculation_inputs=dict(row["calculation_inputs"]),
        recorded_by=UUID(str(row["recorded_by"])),
        recorded_at=row["recorded_at"],
        verified_by=_uuid_or_none(row.get("verified_by")),
        verified_at=row.get("verified_at"),
    )


def _money_or_none(amount: object, currency: object) -> Money | None:
    if amount is None:
        return None
    return Money(amount=Decimal(str(amount)), currency=str(currency))


def _uuid_or_none(value: object) -> UUID | None:
    return None if value is None else UUID(str(value))


def _encode_cursor(offset: int) -> str:
    raw = json.dumps({"offset": offset}, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def _decode_cursor(cursor: str | None) -> int:
    if cursor is None:
        return 0
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii"))
        offset = json.loads(raw.decode("utf-8"))["offset"]
    except (KeyError, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise UnprocessableEntityError(details={"cursor": "invalid"}) from exc
    if not isinstance(offset, int) or offset < 0:
        raise UnprocessableEntityError(details={"cursor": "invalid"})
    return offset


def load_purchase_for_saving(conn: object, purchase_id: UUID) -> PurchaseRecord:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("select * from purchase_record where id = %s", (purchase_id,))
        row = cur.fetchone()
    if row is None:
        raise NotFoundError(details={"resource": "purchase_record"})
    return _purchase(dict(row))

from __future__ import annotations

import base64
import json
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

import psycopg.errors
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
from procurepilot_api.modules.savings.baseline import (
    CALCULATION_VERSION,
    MONEY_QUANT,
    PO_BASELINE_STATUSES,
    QUANTITY_QUANT,
    capture_baseline,
)
from procurepilot_api.modules.savings.schemas import (
    DeliveryResult,
    Money,
    PurchaseOutcomeCreate,
    PurchaseOutcomeCreated,
    PurchaseOutcomePrefill,
    PurchaseOutcomePrefillLine,
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
        idempotency_key: UUID | None = None,
    ) -> tuple[PurchaseOutcomeCreated, bool]:
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
            supplier_id = payload.supplier_id
            source_order_id: UUID | None = None
            if payload.purchase_order_line_id is not None:
                order_line = _recordable_order_line(conn, payload.purchase_order_line_id)
                if order_line["workspace_product_id"] != payload.workspace_product_id:
                    raise UnprocessableEntityError(
                        details={"purchase_order_line_id": "product_mismatch"}
                    )
                if str(order_line["base_unit"]) != payload.base_unit:
                    raise UnprocessableEntityError(
                        details={"purchase_order_line_id": "base_unit_mismatch"}
                    )
                if supplier_id is None:
                    supplier_id = order_line["supplier_id"]
                elif supplier_id != order_line["supplier_id"]:
                    raise UnprocessableEntityError(
                        details={"purchase_order_line_id": "supplier_mismatch"}
                    )
                source_order_id = order_line["purchase_order_id"]
            baseline = capture_baseline(
                conn,
                product_id=payload.workspace_product_id,
                quantity=payload.quantity,
                actual=payload.total_paid,
                base_unit=payload.base_unit,
                exclude_purchase_order_id=source_order_id,
            )
            with conn.cursor(row_factory=dict_row) as cur:
                try:
                    cur.execute(
                        """
                    insert into purchase_record (
                      tenant_id, workspace_product_id, supplier_id, quotation_line_id,
                      match_decision_id, landed_cost_id, purchase_order_line_id, recorded_by,
                      quantity, base_unit,
                      unit_price_amount, unit_price_currency, total_paid_amount,
                      total_paid_currency, delivery_result, ordered_at, delivered_at, notes,
                      idempotency_key
                    ) values (
                      %(tenant_id)s, %(workspace_product_id)s, %(supplier_id)s,
                      %(quotation_line_id)s, %(match_decision_id)s, %(landed_cost_id)s,
                      %(purchase_order_line_id)s, %(recorded_by)s, %(quantity)s, %(base_unit)s,
                      %(unit_price_amount)s,
                      %(unit_price_currency)s, %(total_paid_amount)s, %(total_paid_currency)s,
                      %(delivery_result)s, %(ordered_at)s, %(delivered_at)s, %(notes)s,
                      %(idempotency_key)s
                    )
                    returning *
                    """,
                        {
                            "tenant_id": member.tenant_id,
                            "workspace_product_id": payload.workspace_product_id,
                            "supplier_id": supplier_id,
                            "quotation_line_id": payload.quotation_line_id,
                            "match_decision_id": payload.match_decision_id,
                            "landed_cost_id": payload.landed_cost_id,
                            "purchase_order_line_id": payload.purchase_order_line_id,
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
                            "idempotency_key": idempotency_key,
                        },
                    )
                except psycopg.errors.UniqueViolation as exc:
                    conn.rollback()
                    replay = None
                    if idempotency_key is not None:
                        with conn.cursor(row_factory=dict_row) as lookup:
                            lookup.execute(
                                "select * from purchase_record "
                                "where tenant_id = %s and idempotency_key = %s",
                                (member.tenant_id, idempotency_key),
                            )
                            replay = lookup.fetchone()
                    if replay is None:
                        if exc.diag.constraint_name == "purchase_record_purchase_order_line_key":
                            raise ConflictError(
                                details={"reason": "purchase_order_line_already_recorded"}
                            ) from exc
                        raise
                    purchase = dict(replay)
                    with conn.cursor(row_factory=dict_row) as lookup:
                        lookup.execute(
                            "select * from saving_record "
                            "where tenant_id = %s and purchase_record_id = %s",
                            (member.tenant_id, purchase["id"]),
                        )
                        saving = dict(lookup.fetchone())
                    return (
                        PurchaseOutcomeCreated(
                            purchase_record=_purchase(purchase), saving_record=_saving(saving)
                        ),
                        False,
                    )
                purchase = dict(cur.fetchone())
                cur.execute(
                    """
                    insert into saving_record (
                      tenant_id, purchase_record_id, workspace_product_id, supplier_id,
                      status, baseline_policy, baseline_source_landed_cost_ids,
                      baseline_source_po_line_ids, baseline_unit_price_amount,
                      baseline_unit_price_currency,
                      baseline_value_amount, baseline_value_currency, actual_value_amount,
                      actual_value_currency, delta_amount, delta_currency, calculation_version,
                      calculation_inputs, recorded_by
                    ) values (
                      %(tenant_id)s, %(purchase_record_id)s, %(workspace_product_id)s,
                      %(supplier_id)s, 'pending', %(baseline_policy)s,
                      %(baseline_source_landed_cost_ids)s, %(baseline_source_po_line_ids)s,
                      %(baseline_unit_price_amount)s,
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
                        "supplier_id": supplier_id,
                        "baseline_policy": baseline.policy,
                        "baseline_source_landed_cost_ids": baseline.source_landed_cost_ids,
                        "baseline_source_po_line_ids": baseline.source_po_line_ids,
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
            return (
                PurchaseOutcomeCreated(
                    purchase_record=_purchase(purchase),
                    saving_record=_saving(saving),
                ),
                True,
            )

    def purchase_prefill(
        self, *, member: CurrentMember, purchase_order_id: UUID
    ) -> PurchaseOutcomePrefill:
        """One outcome line per PO line, converted from packs to base units (ADR-020)."""
        with _authenticated_db(self._settings, member) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    "select id, order_number, status::text as status, supplier_id, order_date "
                    "from purchase_order where id = %s",
                    (purchase_order_id,),
                )
                order = cur.fetchone()
                if order is None:
                    raise NotFoundError(details={"resource": "purchase_order"})
                order = dict(order)
                if order["status"] not in PO_BASELINE_STATUSES:
                    raise ConflictError(details={"reason": "purchase_order_not_recordable"})
                cur.execute(
                    """
                    select pol.id, pol.line_number, pol.description, pol.workspace_product_id,
                           pol.ordered_quantity, pol.base_unit, pol.unit_price_amount,
                           pol.unit_price_currency, pol.pack_base_quantity,
                           recorded.saving_id
                    from purchase_order_line pol
                    left join lateral (
                      select sr.id as saving_id
                      from purchase_record pr
                      join saving_record sr on sr.purchase_record_id = pr.id
                      where pr.purchase_order_line_id = pol.id
                      limit 1
                    ) recorded on true
                    where pol.purchase_order_id = %s
                    order by pol.line_number
                    """,
                    (purchase_order_id,),
                )
                rows = [dict(row) for row in cur.fetchall()]
        return PurchaseOutcomePrefill(
            purchase_order_id=UUID(str(order["id"])),
            order_number=str(order["order_number"]),
            status=str(order["status"]),
            supplier_id=UUID(str(order["supplier_id"])),
            order_date=order["order_date"],
            delivery_result=_delivery_result(str(order["status"])),
            lines=[_prefill_line(row) for row in rows],
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


def _recordable_order_line(conn: object, line_id: UUID) -> dict[str, object]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            select pol.id, pol.purchase_order_id, pol.workspace_product_id, pol.base_unit,
                   po.supplier_id, po.status::text as status
            from purchase_order_line pol
            join purchase_order po
              on po.tenant_id = pol.tenant_id and po.id = pol.purchase_order_id
            where pol.id = %s
            """,
            (line_id,),
        )
        row = cur.fetchone()
    if row is None:
        raise NotFoundError(details={"resource": "purchase_order_line"})
    row = dict(row)
    if row["status"] not in PO_BASELINE_STATUSES:
        raise ConflictError(details={"reason": "purchase_order_not_recordable"})
    return row


def _delivery_result(order_status: str) -> DeliveryResult:
    if order_status in {"received", "closed"}:
        return "delivered"
    if order_status == "partially_received":
        return "partially_delivered"
    return "ordered"


def _prefill_line(row: dict[str, object]) -> PurchaseOutcomePrefillLine:
    packs = Decimal(str(row["ordered_quantity"]))
    pack_size = row.get("pack_base_quantity")
    per_pack = Decimal("1") if pack_size is None else Decimal(str(pack_size))
    currency = str(row["unit_price_currency"])
    pack_price = Decimal(str(row["unit_price_amount"]))
    quantity = (packs * per_pack).quantize(QUANTITY_QUANT, rounding=ROUND_HALF_UP)
    reason = None
    if row.get("saving_id") is not None:
        reason = "already_recorded"
    elif row.get("workspace_product_id") is None:
        reason = "no_product"
    elif quantity <= 0:
        reason = "zero_quantity"
    return PurchaseOutcomePrefillLine(
        purchase_order_line_id=UUID(str(row["id"])),
        line_number=int(row["line_number"]),
        description=str(row["description"]),
        workspace_product_id=_uuid_or_none(row.get("workspace_product_id")),
        ordered_packs=packs,
        pack_base_quantity=None if pack_size is None else per_pack,
        quantity=quantity,
        base_unit=str(row["base_unit"]),
        unit_price=Money(
            amount=(pack_price / per_pack).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP),
            currency=currency,
        ),
        # Exclusive of tax, like the baseline's unit prices.
        total_paid=Money(
            amount=(pack_price * packs).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP),
            currency=currency,
        ),
        recordable=reason is None,
        reason=reason,
        recorded_saving_id=_uuid_or_none(row.get("saving_id")),
    )


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
        purchase_order_line_id=_uuid_or_none(row.get("purchase_order_line_id")),
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
        baseline_source_po_line_ids=(
            None
            if row.get("baseline_source_po_line_ids") is None
            else [UUID(str(item)) for item in row["baseline_source_po_line_ids"]]
        ),
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

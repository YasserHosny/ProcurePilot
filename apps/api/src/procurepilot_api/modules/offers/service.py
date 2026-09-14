from __future__ import annotations

import base64
import json
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from procurepilot_api.config import Settings, get_settings
from procurepilot_api.deps import CurrentMember
from procurepilot_api.errors import NotFoundError, ServiceUnavailableError, UnprocessableEntityError
from procurepilot_api.modules.offers.price_history import (
    normalised_unit_price,
    price_history_summary,
)
from procurepilot_api.modules.offers.projection import project_landed_cost
from procurepilot_api.modules.offers.recommendation import recommend_offer
from procurepilot_api.modules.offers.schemas import (
    Money,
    Offer,
    OfferComparison,
    OfferList,
    PriceHistoryPoint,
    PriceHistoryResponse,
    ProductRef,
)

OFFER_READ_SQL = """
with product as (
  select wp.id, wp.tenant_id, wp.tenant_name, wp.status
  from workspace_product wp
  where wp.id = %(product_id)s
),
ranked as (
  select
    lc.id,
    md.matched_workspace_product_id as workspace_product_id,
    q.supplier_id,
    s.name as supplier_name,
    lc.quotation_line_id,
    lc.match_decision_id,
    lc.total_amount,
    lc.total_currency,
    lc.raw_inputs,
    lc.rule_version,
    lc.valid_from,
    lc.valid_to,
    lc.recorded_at,
    lc.base_unit,
    md.confidence as match_confidence,
    s.lead_time_days,
    s.reliability_score,
    pd.base_quantity as pack_base_quantity,
    row_number() over (
      partition by md.matched_workspace_product_id, q.supplier_id, lc.rule_version
      order by lc.recorded_at desc, lc.id desc
    ) as rn
  from product p
  join match_decision md on md.matched_workspace_product_id = p.id
  join landed_cost lc on lc.match_decision_id = md.id
  join quotation_line ql on ql.id = lc.quotation_line_id
  join quotation q on q.id = ql.quotation_id
  join supplier s on s.id = q.supplier_id
  join pack_definition pd on pd.workspace_product_id = p.id
  where p.status = 'active'
    and q.status = 'reviewed'
    and s.status in ('active', 'preferred')
    and (%(include_expired)s or lc.valid_to is null or lc.valid_to >= %(now)s)
)
select * from ranked where rn = 1
order by supplier_name, supplier_id
limit %(limit)s offset %(offset)s
"""

PRICE_HISTORY_SQL = """
select
  lc.id as landed_cost_id,
  md.matched_workspace_product_id as workspace_product_id,
  q.supplier_id,
  s.name as supplier_name,
  lc.recorded_at,
  lc.valid_from,
  lc.valid_to,
  lc.total_amount,
  lc.total_currency,
  lc.normalised_base_quantity,
  lc.quantity,
  lc.base_unit,
  wp.tenant_name
from workspace_product wp
join match_decision md on md.matched_workspace_product_id = wp.id
join landed_cost lc on lc.match_decision_id = md.id
join quotation_line ql on ql.id = lc.quotation_line_id
join quotation q on q.id = ql.quotation_id
join supplier s on s.id = q.supplier_id
where wp.id = %(product_id)s
  and (%(supplier_id)s::uuid is null or q.supplier_id = %(supplier_id)s::uuid)
order by lc.recorded_at desc, lc.id desc
limit %(limit)s offset %(offset)s
"""


class OfferService:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    def list_offers(
        self,
        *,
        member: CurrentMember,
        product_id: UUID,
        quantity: Decimal,
        include_expired: bool = False,
        cursor: str | None = None,
        limit: int = 50,
    ) -> OfferList:
        capped_limit = max(1, min(limit, 100))
        offset = _decode_cursor(cursor)
        with _authenticated_db(self._settings, member) as conn:
            product = _product(conn, product_id)
            rows = _offer_rows(
                conn,
                product_id=product_id,
                quantity=quantity,
                include_expired=include_expired,
                offset=offset,
                limit=capped_limit + 1,
            )
        offers = [_offer(row, quantity=quantity) for row in rows[:capped_limit]]
        next_cursor = _encode_cursor(offset + capped_limit) if len(rows) > capped_limit else None
        del product
        return OfferList(items=offers, next_cursor=next_cursor)

    def compare_offers(
        self,
        *,
        member: CurrentMember,
        product_id: UUID,
        quantity: Decimal,
    ) -> OfferComparison:
        with _authenticated_db(self._settings, member) as conn:
            product = _product(conn, product_id)
            rows = _offer_rows(
                conn,
                product_id=product_id,
                quantity=quantity,
                include_expired=True,
                offset=0,
                limit=101,
            )
            offers = [_offer(row, quantity=quantity) for row in rows]
            supplier_risk_scores: dict[UUID, str] = {}
            supplier_ids = list({offer.supplier_id for offer in offers})
            if supplier_ids:
                with conn.cursor(row_factory=dict_row) as cur:
                    cur.execute(
                        """
                        select distinct on (supplier_id) supplier_id, risk_score
                        from supplier_scorecard_snapshot
                        where supplier_id = any(%s::uuid[])
                        order by supplier_id, window_end desc, computed_at desc, id desc
                        """,
                        ([str(supplier_id) for supplier_id in supplier_ids],),
                    )
                    for snapshot_row in cur.fetchall():
                        supp_id = snapshot_row["supplier_id"]
                        risk_score = snapshot_row["risk_score"]
                        if isinstance(risk_score, str):
                            try:
                                risk_score = json.loads(risk_score)
                            except json.JSONDecodeError:
                                pass
                        if isinstance(risk_score, dict) and "total" in risk_score:
                            supplier_risk_scores[supp_id] = str(risk_score["total"])

        return OfferComparison(
            product=ProductRef(id=product_id, tenant_name=str(product["tenant_name"])),
            requested_quantity=_quantity_string(quantity),
            offers=offers,
            recommendation=recommend_offer(offers, supplier_risk_scores=supplier_risk_scores),
        )

    def price_history(
        self,
        *,
        member: CurrentMember,
        product_id: UUID,
        supplier_id: UUID | None = None,
        window_months: int = 6,
        cursor: str | None = None,
        limit: int = 100,
    ) -> PriceHistoryResponse:
        capped_limit = max(1, min(limit, 100))
        offset = _decode_cursor(cursor)
        with _authenticated_db(self._settings, member) as conn:
            product = _product(conn, product_id)
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    PRICE_HISTORY_SQL,
                    {
                        "product_id": product_id,
                        "supplier_id": supplier_id,
                        "limit": capped_limit + 1,
                        "offset": offset,
                    },
                )
                rows = [dict(row) for row in cur.fetchall()]
        points = [_history_point(row) for row in rows[:capped_limit]]
        window_start = _subtract_calendar_months(datetime.now(UTC), window_months)
        next_cursor = _encode_cursor(offset + capped_limit) if len(rows) > capped_limit else None
        return PriceHistoryResponse(
            product=ProductRef(id=product_id, tenant_name=str(product["tenant_name"])),
            window_months=window_months,
            points=points,
            summary=price_history_summary(points, window_start=window_start),
            next_cursor=next_cursor,
        )


def get_offer_service() -> OfferService:
    return OfferService()


@contextmanager
def _authenticated_db(settings: Settings, member: CurrentMember) -> Iterator[psycopg.Connection]:
    try:
        with psycopg.connect(settings.database_url.get_secret_value()) as conn:
            with conn.cursor() as cur:
                claims = {
                    "sub": str(member.user_id),
                    "tenant_id": str(member.tenant_id),
                    "role": "authenticated",
                    "member_role": member.role.value,
                }
                cur.execute("set local role authenticated")
                cur.execute(
                    "select set_config('request.jwt.claims', %s, true)",
                    (json.dumps(claims),),
                )
            yield conn
    except psycopg.Error as exc:
        raise ServiceUnavailableError(details={"dependency": "database"}) from exc


def _product(conn: psycopg.Connection, product_id: UUID) -> dict[str, object]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            "select id, tenant_name from workspace_product where id = %s and status = 'active'",
            (product_id,),
        )
        row = cur.fetchone()
    if row is None:
        raise NotFoundError(details={"resource": "workspace_product"})
    return dict(row)


def _offer_rows(
    conn: psycopg.Connection,
    *,
    product_id: UUID,
    quantity: Decimal,
    include_expired: bool,
    offset: int,
    limit: int,
) -> list[dict[str, object]]:
    del quantity
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            OFFER_READ_SQL,
            {
                "product_id": product_id,
                "include_expired": include_expired,
                "now": datetime.now(UTC),
                "limit": limit,
                "offset": offset,
            },
        )
        return [dict(row) for row in cur.fetchall()]


def _offer(row: dict[str, object], *, quantity: Decimal) -> Offer:
    projected = project_landed_cost(
        raw_inputs=_json_object(row["raw_inputs"]),
        rule_version=str(row["rule_version"]),
        requested_quantity=quantity,
        pack_base_quantity=Decimal(str(row["pack_base_quantity"])),
    )
    valid_to = row.get("valid_to")
    is_expired = valid_to is not None and valid_to < datetime.now(UTC)
    reliability = row.get("reliability_score")
    return Offer(
        id=UUID(str(row["id"])),
        workspace_product_id=UUID(str(row["workspace_product_id"])),
        supplier_id=UUID(str(row["supplier_id"])),
        supplier_name=str(row["supplier_name"]),
        quotation_line_id=UUID(str(row["quotation_line_id"])),
        match_decision_id=UUID(str(row["match_decision_id"])),
        landed_cost=projected.total,
        normalised_unit_price=projected.normalised_unit_price,
        requested_quantity=projected.requested_quantity,
        base_unit=str(row["base_unit"]),
        lead_time_days=row.get("lead_time_days"),
        reliability_score=None if reliability is None else _decimal_string(reliability, "0.001"),
        stock_signal=None,
        match_confidence=_decimal_string(row["match_confidence"], "0.0001"),
        valid_from=row["valid_from"],
        valid_to=valid_to,
        is_expired=is_expired,
        rule_version=str(row["rule_version"]),
        recorded_at=row["recorded_at"],
    )


def _history_point(row: dict[str, object]) -> PriceHistoryPoint:
    unit = normalised_unit_price(row["total_amount"], row["normalised_base_quantity"])
    currency = str(row["total_currency"])
    return PriceHistoryPoint(
        landed_cost_id=UUID(str(row["landed_cost_id"])),
        workspace_product_id=UUID(str(row["workspace_product_id"])),
        supplier_id=UUID(str(row["supplier_id"])),
        supplier_name=str(row["supplier_name"]),
        recorded_at=row["recorded_at"],
        valid_from=row["valid_from"],
        valid_to=row.get("valid_to"),
        normalised_unit_price=Money(amount=format(unit, "f"), currency=currency),
        landed_cost_total=Money(
            amount=_decimal_string(row["total_amount"], "0.0001"),
            currency=currency,
        ),
        quantity=_decimal_string(row["quantity"], "0.000001"),
        base_unit=str(row["base_unit"]),
    )


def _json_object(value: object) -> dict[str, object]:
    if isinstance(value, dict):
        return value
    raise ServiceUnavailableError(details={"reason": "invalid_landed_cost_raw_inputs"})


def _quantity_string(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.000001")), "f")


def _decimal_string(value: object, exponent: str) -> str:
    return format(Decimal(str(value)).quantize(Decimal(exponent)), "f")


def _subtract_calendar_months(value: datetime, months: int) -> datetime:
    month_index = value.month - months
    year = value.year
    while month_index <= 0:
        month_index += 12
        year -= 1
    day = min(value.day, _days_in_month(year, month_index))
    return value.replace(year=year, month=month_index, day=day)


def _days_in_month(year: int, month: int) -> int:
    if month == 2:
        if year % 400 == 0 or (year % 4 == 0 and year % 100 != 0):
            return 29
        return 28
    if month in {4, 6, 9, 11}:
        return 30
    return 31


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

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from postgrest.exceptions import APIError

from procurepilot_api.config import Settings, get_settings
from procurepilot_api.deps import CurrentMember
from procurepilot_api.errors import ConflictError, NotFoundError, ServiceUnavailableError
from procurepilot_api.modules.landed_cost.rules import (
    RULE_VERSION_V1,
    LandedCostInputs,
    MoneyValue,
    compute_landed_cost,
)
from procurepilot_api.modules.landed_cost.schemas import LandedCost, Money
from procurepilot_api.modules.members.service import authenticated_client

LINE_COLUMNS = (
    "id,tenant_id,quotation_id,quantity,pack_count,unit_size,unit_price_amount,"
    "unit_price_currency,vat_rate,delivery_fee_amount,delivery_fee_currency,discount_amount,"
    "discount_currency"
)
DECISION_COLUMNS = (
    "id,tenant_id,quotation_line_id,matched_workspace_product_id,selected_match_candidate_id,"
    "outcome,is_automatic,decided_by,decided_at,confidence,alias_id,created_at"
)
PRODUCT_COLUMNS = "id,tenant_id,canonical_product_id,tenant_name,status"
CANONICAL_COLUMNS = "id,base_unit"
PACK_COLUMNS = "id,tenant_id,workspace_product_id,pack_count,unit_size,base_quantity,created_at"
LANDED_COLUMNS = (
    "id,quotation_line_id,match_decision_id,quantity,normalised_base_quantity,base_unit,"
    "unit_price_amount,unit_price_currency,vat_amount,vat_currency,delivery_fee_amount,"
    "delivery_fee_currency,discount_amount,discount_currency,other_charges_amount,"
    "other_charges_currency,total_amount,total_currency,raw_inputs,rule_version,valid_from,"
    "valid_to,recorded_at,created_at"
)


class LandedCostService:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self.active_rule_version = RULE_VERSION_V1

    def get_landed_cost(self, *, bearer_token: str, line_id: UUID) -> LandedCost:
        client = authenticated_client(self._settings, bearer_token)
        decision = self._decision_for_line(client, line_id)
        if decision is None:
            raise ConflictError(details={"reason": "line_not_matched"})
        row = self._latest_landed_cost(client, UUID(str(decision["id"])))
        if row is not None:
            return _landed_cost(row)
        raise NotFoundError(details={"resource": "landed_cost"})

    def get_landed_cost_or_none(self, *, bearer_token: str, line_id: UUID) -> LandedCost | None:
        client = authenticated_client(self._settings, bearer_token)
        decision = self._decision_for_line(client, line_id)
        if decision is None:
            return None
        row = self._latest_landed_cost(client, UUID(str(decision["id"])))
        return _landed_cost(row) if row else None

    def compute_for_line_with_client(
        self,
        *,
        client: object,
        member: CurrentMember,
        line_id: UUID,
        rule_version: str | None = None,
    ) -> LandedCost:
        version = rule_version or self.active_rule_version
        # Cost belongs to a decision, not a line: after a correction (spec 023 R5) the line has a
        # cost row per decision, and only the current decision's counts.
        decision = self._decision_for_line(client, line_id)
        if decision is None:
            raise ConflictError(details={"reason": "line_not_matched"})
        existing = self._landed_cost_for_rule(client, UUID(str(decision["id"])), version)
        if existing is not None:
            return _landed_cost(existing)
        line = _line_row(client, line_id)
        product = _product_row(client, UUID(str(decision["matched_workspace_product_id"])))
        canonical = _canonical_row(client, UUID(str(product["canonical_product_id"])))
        pack = _pack_row(client, UUID(str(product["id"])))
        quantity = Decimal(str(line.get("quantity") or "1"))
        base_quantity = Decimal(str(pack["base_quantity"]))
        quote = _quotation_row(client, UUID(str(line["quotation_id"])))
        quote_currency = str(quote["currency"]).upper() if quote.get("currency") else None
        unit_currency = _required_currency(
            _resolve_currency(line.get("unit_price_currency"), quote_currency)
        )
        result = compute_landed_cost(
            LandedCostInputs(
                quantity=quantity,
                normalised_base_quantity=quantity * base_quantity,
                base_unit=str(canonical["base_unit"]),
                unit_price=MoneyValue(
                    Decimal(str(line.get("unit_price_amount") or "0")),
                    unit_currency,
                ),
                vat_rate=Decimal(str(line["vat_rate"]))
                if line.get("vat_rate") is not None
                else None,
                delivery_fee=MoneyValue(
                    Decimal(str(line.get("delivery_fee_amount") or "0")),
                    str(line.get("delivery_fee_currency") or unit_currency),
                ),
                discount=MoneyValue(
                    Decimal(str(line.get("discount_amount") or "0")),
                    str(line.get("discount_currency") or unit_currency),
                ),
            ),
            rule_version=version,
        )
        recorded_at = datetime.now(UTC)
        valid_to = _quotation_valid_to(client, member.tenant_id, quote.get("expiry_date"))
        # A quote that had already lapsed when it was matched still satisfies
        # landed_cost_valid_to_after_valid_from, and reads as expired, not open-ended.
        valid_from = recorded_at if valid_to is None else min(recorded_at, valid_to)
        now = recorded_at.isoformat()
        try:
            response = (
                client.table("landed_cost")
                .insert(
                    {
                        "tenant_id": str(member.tenant_id),
                        "quotation_line_id": str(line_id),
                        "match_decision_id": str(decision["id"]),
                        "quantity": format(result.quantity, "f"),
                        "normalised_base_quantity": format(result.normalised_base_quantity, "f"),
                        "base_unit": result.base_unit,
                        "unit_price_amount": format(result.unit_price.amount, "f"),
                        "unit_price_currency": result.unit_price.currency,
                        "vat_amount": format(result.vat_amount.amount, "f"),
                        "vat_currency": result.vat_amount.currency,
                        "delivery_fee_amount": format(result.delivery_fee.amount, "f"),
                        "delivery_fee_currency": result.delivery_fee.currency,
                        "discount_amount": format(result.discount.amount, "f"),
                        "discount_currency": result.discount.currency,
                        "other_charges_amount": format(result.other_charges.amount, "f"),
                        "other_charges_currency": result.other_charges.currency,
                        "total_amount": format(result.total.amount, "f"),
                        "total_currency": result.total.currency,
                        "raw_inputs": result.raw_inputs,
                        "rule_version": version,
                        "valid_from": valid_from.isoformat(),
                        "valid_to": valid_to.isoformat() if valid_to is not None else None,
                        "recorded_at": now,
                    }
                )
                .execute()
            )
        except APIError as exc:
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc
        return _landed_cost(_one_row(response.data, resource="landed_cost"))

    def _decision_for_line(self, client: object, line_id: UUID) -> dict[str, object] | None:
        try:
            rows = _rows(
                client.table("current_match_decision")
                .select(DECISION_COLUMNS)
                .eq("quotation_line_id", str(line_id))
                .limit(2)
                .execute()
                .data
            )
        except APIError as exc:
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc
        if len(rows) > 1:
            raise ServiceUnavailableError(details={"reason": "multiple_match_decisions"})
        return rows[0] if rows else None

    def _latest_landed_cost(self, client: object, decision_id: UUID) -> dict[str, object] | None:
        try:
            rows = _rows(
                client.table("landed_cost")
                .select(LANDED_COLUMNS)
                .eq("match_decision_id", str(decision_id))
                .order("recorded_at", desc=True)
                .limit(1)
                .execute()
                .data
            )
        except APIError as exc:
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc
        return rows[0] if rows else None

    def _landed_cost_for_rule(
        self,
        client: object,
        decision_id: UUID,
        rule_version: str,
    ) -> dict[str, object] | None:
        try:
            rows = _rows(
                client.table("landed_cost")
                .select(LANDED_COLUMNS)
                .eq("match_decision_id", str(decision_id))
                .eq("rule_version", rule_version)
                .limit(2)
                .execute()
                .data
            )
        except APIError as exc:
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc
        if len(rows) > 1:
            raise ServiceUnavailableError(details={"reason": "multiple_landed_cost_rows"})
        return rows[0] if rows else None


def get_landed_cost_service() -> LandedCostService:
    return LandedCostService()


def _line_row(client: object, line_id: UUID) -> dict[str, object]:
    try:
        response = (
            client.table("quotation_line")
            .select(LINE_COLUMNS)
            .eq("id", str(line_id))
            .limit(2)
            .execute()
        )
    except APIError as exc:
        raise ServiceUnavailableError(details={"dependency": "database"}) from exc
    return _one_row(response.data, resource="quotation_line")


def _resolve_currency(line_currency: object, quote_currency: object) -> str | None:
    # The tenant's home currency is deliberately not a step here: a quote whose currency was
    # never established is reported missing, not costed in a guessed currency (spec 022 FR-011).
    return next((str(value).upper() for value in (line_currency, quote_currency) if value), None)


def _required_currency(currency: str | None) -> str:
    if currency is None:
        raise ConflictError(details={"reason": "currency_missing"})
    return currency


def _quotation_row(client: object, quotation_id: UUID) -> dict[str, object]:
    response = (
        client.table("quotation")
        .select("currency,expiry_date")
        .eq("id", str(quotation_id))
        .limit(1)
        .execute()
    )
    rows = getattr(response, "data", None) or []
    return rows[0] if rows else {}


def _quotation_valid_to(client: object, tenant_id: UUID, expiry_date: object) -> datetime | None:
    """The last instant of the quotation's expiry day, in the tenant's reporting timezone.

    A quote "valid until 3 Nov" is still good on 3 Nov, so the offer lapses when that local
    day ends. No expiry date means the offer stays open-ended.
    """
    if expiry_date is None:
        return None
    expiry = expiry_date if isinstance(expiry_date, date) else date.fromisoformat(str(expiry_date))
    next_day = datetime.combine(
        expiry + timedelta(days=1), time.min, _tenant_timezone(client, tenant_id)
    )
    return (next_day - timedelta(microseconds=1)).astimezone(UTC)


def _tenant_timezone(client: object, tenant_id: UUID) -> ZoneInfo:
    response = (
        client.table("tenant")
        .select("reporting_timezone")
        .eq("id", str(tenant_id))
        .limit(1)
        .execute()
    )
    rows = getattr(response, "data", None) or []
    name = str(rows[0].get("reporting_timezone") or "UTC") if rows else "UTC"
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")


def _product_row(client: object, product_id: UUID) -> dict[str, object]:
    try:
        response = (
            client.table("workspace_product")
            .select(PRODUCT_COLUMNS)
            .eq("id", str(product_id))
            .limit(2)
            .execute()
        )
    except APIError as exc:
        raise ServiceUnavailableError(details={"dependency": "database"}) from exc
    return _one_row(response.data, resource="product")


def _canonical_row(client: object, canonical_product_id: UUID) -> dict[str, object]:
    try:
        response = (
            client.table("canonical_product")
            .select(CANONICAL_COLUMNS)
            .eq("id", str(canonical_product_id))
            .limit(2)
            .execute()
        )
    except APIError as exc:
        raise ServiceUnavailableError(details={"dependency": "database"}) from exc
    return _one_row(response.data, resource="canonical_product")


def _pack_row(client: object, product_id: UUID) -> dict[str, object]:
    try:
        response = (
            client.table("pack_definition")
            .select(PACK_COLUMNS)
            .eq("workspace_product_id", str(product_id))
            .limit(2)
            .execute()
        )
    except APIError as exc:
        raise ServiceUnavailableError(details={"dependency": "database"}) from exc
    return _one_row(response.data, resource="pack_definition")


def _landed_cost(row: dict[str, object]) -> LandedCost:
    return LandedCost(
        id=UUID(str(row["id"])),
        quotation_line_id=UUID(str(row["quotation_line_id"])),
        match_decision_id=UUID(str(row["match_decision_id"])),
        quantity=_decimal(row["quantity"], scale=6),
        normalised_base_quantity=_decimal(row["normalised_base_quantity"], scale=6),
        base_unit=str(row["base_unit"]),
        unit_price=_money(row, "unit_price"),
        vat_amount=_money(row, "vat"),
        delivery_fee=_money(row, "delivery_fee"),
        discount=_money(row, "discount"),
        other_charges=_money(row, "other_charges"),
        total=_money(row, "total"),
        raw_inputs=row["raw_inputs"],
        rule_version=str(row["rule_version"]),
        valid_from=row["valid_from"],
        valid_to=row.get("valid_to"),
        recorded_at=row["recorded_at"],
        created_at=row.get("created_at"),
    )


def _money(row: dict[str, object], prefix: str) -> Money:
    return Money(
        amount=_decimal(row[f"{prefix}_amount"], scale=4),
        currency=str(row[f"{prefix}_currency"]),
    )


def _decimal(value: object, *, scale: int) -> str:
    exponent = Decimal(10) ** -scale
    return format(Decimal(str(value)).quantize(exponent), "f")


def _rows(data: object) -> list[dict[str, object]]:
    if isinstance(data, list) and all(isinstance(row, dict) for row in data):
        return data
    raise ServiceUnavailableError(details={"reason": "invalid_database_response"})


def _one_row(data: object, *, resource: str) -> dict[str, object]:
    rows = _rows(data)
    if len(rows) == 1:
        return rows[0]
    if not rows:
        raise NotFoundError(details={"resource": resource})
    raise ServiceUnavailableError(details={"reason": "multiple_rows", "resource": resource})

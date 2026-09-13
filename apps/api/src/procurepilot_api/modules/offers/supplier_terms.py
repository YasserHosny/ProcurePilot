from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from procurepilot_api.config import Settings, get_settings
from procurepilot_api.deps import CurrentMember
from procurepilot_api.errors import ConflictError, NotFoundError, UnprocessableEntityError
from procurepilot_api.modules.offers.schemas import (
    Money,
    SupplierCommercialTerm,
    SupplierCommercialTermCreate,
    SupplierCommercialTermList,
    SupplierQuantityTier,
)
from procurepilot_api.modules.offers.service import _authenticated_db

SUPPLIER_TERMS_RULE_VERSION = "supplier-commercial-terms-v1"


class SupplierTermsService:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    def list_terms(
        self,
        *,
        member: CurrentMember,
        supplier_id: UUID,
    ) -> SupplierCommercialTermList:
        with _authenticated_db(self._settings, member) as conn:
            _supplier_visible(conn, supplier_id)
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    select *
                    from supplier_commercial_term
                    where supplier_id = %s
                    order by effective_from desc, created_at desc, id desc
                    """,
                    (supplier_id,),
                )
                rows = [dict(row) for row in cur.fetchall()]
        return SupplierCommercialTermList(items=[_term(row) for row in rows])

    def create_term(
        self,
        *,
        member: CurrentMember,
        supplier_id: UUID,
        payload: SupplierCommercialTermCreate,
    ) -> SupplierCommercialTerm:
        _validate_term_payload(payload)
        with _authenticated_db(self._settings, member) as conn:
            _supplier_visible(conn, supplier_id)
            try:
                with conn.cursor(row_factory=dict_row) as cur:
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
                            delivery_fee_amount,
                            delivery_fee_currency,
                            free_delivery_threshold_amount,
                            free_delivery_threshold_currency,
                            quantity_tiers,
                            rule_version,
                            created_by_membership_id
                          )
                        values
                          (
                            %(tenant_id)s,
                            %(supplier_id)s,
                            %(effective_from)s,
                            %(effective_to)s,
                            %(minimum_order_value_amount)s,
                            %(minimum_order_value_currency)s,
                            %(delivery_fee_amount)s,
                            %(delivery_fee_currency)s,
                            %(free_delivery_threshold_amount)s,
                            %(free_delivery_threshold_currency)s,
                            %(quantity_tiers)s,
                            %(rule_version)s,
                            %(created_by_membership_id)s
                          )
                        returning *
                        """,
                        {
                            "tenant_id": member.tenant_id,
                            "supplier_id": supplier_id,
                            "effective_from": payload.effective_from,
                            "effective_to": payload.effective_to,
                            **_money_columns("minimum_order_value", payload.minimum_order_value),
                            **_money_columns("delivery_fee", payload.delivery_fee),
                            **_money_columns(
                                "free_delivery_threshold",
                                payload.free_delivery_threshold,
                            ),
                            "quantity_tiers": Jsonb(
                                [
                                    tier.model_dump(mode="json", exclude_none=True)
                                    for tier in payload.quantity_tiers
                                ]
                            ),
                            "rule_version": SUPPLIER_TERMS_RULE_VERSION,
                            "created_by_membership_id": member.membership_id,
                        },
                    )
                    row = dict(cur.fetchone())
            except Exception as exc:
                _raise_term_write_error(exc)
                raise
        return _term(row)


def get_supplier_terms_service() -> SupplierTermsService:
    return SupplierTermsService()


def _supplier_visible(conn: object, supplier_id: UUID) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "select id from supplier where id = %s and status in ('active','preferred')",
            (supplier_id,),
        )
        if cur.fetchone() is None:
            raise NotFoundError(details={"resource": "supplier"})


def _validate_term_payload(payload: SupplierCommercialTermCreate) -> None:
    for tier in payload.quantity_tiers:
        if Decimal(tier.min_quantity) <= 0:
            raise UnprocessableEntityError(details={"quantity_tiers": "min_quantity_positive"})
        if Decimal(tier.unit_price.amount) < 0:
            raise UnprocessableEntityError(details={"quantity_tiers": "unit_price_non_negative"})
    _ensure_same_currency_if_present(
        payload.minimum_order_value,
        payload.delivery_fee,
        payload.free_delivery_threshold,
        *(tier.unit_price for tier in payload.quantity_tiers),
    )


def _ensure_same_currency_if_present(*money_values: Money | None) -> None:
    currencies = {money.currency for money in money_values if money is not None}
    if len(currencies) > 1:
        raise UnprocessableEntityError(details={"currency": "mixed_supplier_terms_currency"})


def _money_columns(prefix: str, money: Money | None) -> dict[str, object]:
    return {
        f"{prefix}_amount": Decimal(money.amount) if money is not None else None,
        f"{prefix}_currency": money.currency if money is not None else None,
    }


def _term(row: dict[str, object]) -> SupplierCommercialTerm:
    return SupplierCommercialTerm(
        id=UUID(str(row["id"])),
        supplier_id=UUID(str(row["supplier_id"])),
        effective_from=row["effective_from"],
        effective_to=row.get("effective_to"),
        minimum_order_value=_money(row, "minimum_order_value"),
        delivery_fee=_money(row, "delivery_fee"),
        free_delivery_threshold=_money(row, "free_delivery_threshold"),
        quantity_tiers=[
            SupplierQuantityTier.model_validate(tier) for tier in row.get("quantity_tiers") or []
        ],
        rule_version=str(row["rule_version"]),
        created_at=row["created_at"],
    )


def _money(row: dict[str, object], prefix: str) -> Money | None:
    amount = row.get(f"{prefix}_amount")
    currency = row.get(f"{prefix}_currency")
    if amount is None and currency is None:
        return None
    if amount is None or currency is None:
        raise UnprocessableEntityError(details={prefix: "money_pair_required"})
    return Money(amount=f"{Decimal(str(amount)):.4f}", currency=str(currency))


def _raise_term_write_error(exc: Exception) -> None:
    sqlstate = getattr(exc, "sqlstate", None)
    if sqlstate == "23505":
        raise ConflictError(details={"reason": "supplier_term_conflict"}) from exc
    if sqlstate in {"23503", "23514", "22P02"}:
        raise UnprocessableEntityError(details={"reason": "database_constraint"}) from exc

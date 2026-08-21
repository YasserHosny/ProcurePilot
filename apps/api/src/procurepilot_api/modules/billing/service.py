from __future__ import annotations

import json
from decimal import Decimal

import psycopg
from psycopg.rows import dict_row

from procurepilot_api.config import Settings, get_settings
from procurepilot_api.deps import CurrentMember
from procurepilot_api.errors import ConflictError, NotFoundError
from procurepilot_api.modules.billing.schemas import (
    BillingAccount,
    LimitCheck,
    Money,
    Plan,
    PlanLimits,
)
from procurepilot_api.modules.offers.service import _authenticated_db

ACCOUNT_SQL = """
select ba.*, p.name as plan_name, p.status as plan_status, p.monthly_price_amount,
       p.monthly_price_currency, p.limits, p.features
from billing_account ba
join plan p on p.code = ba.plan_code
where ba.tenant_id = %s
"""


class BillingService:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    def assign_default_plan(self, *, member: CurrentMember) -> BillingAccount:
        with _authenticated_db(self._settings, member) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    insert into billing_account (
                      tenant_id, plan_code, provider, provider_customer_id,
                      provider_subscription_id, status
                    ) values (%s, 'starter', 'stub', %s, %s, 'active')
                    on conflict (tenant_id) do update
                    set plan_code = billing_account.plan_code
                    returning tenant_id
                    """,
                    (
                        member.tenant_id,
                        f"stub_customer:{member.tenant_id}",
                        f"stub_subscription:{member.tenant_id}:starter",
                    ),
                )
            return self.current_account(member=member)

    def current_account(self, *, member: CurrentMember) -> BillingAccount:
        with _authenticated_db(self._settings, member) as conn:
            return _account(conn, member.tenant_id)

    def check_limit(self, *, member: CurrentMember, resource: str) -> LimitCheck:
        if resource != "active_catalogue_products":
            raise NotFoundError(details={"resource": "plan_limit"})
        with _authenticated_db(self._settings, member) as conn:
            account = _account(conn, member.tenant_id)
            with conn.cursor() as cur:
                cur.execute("select count(*) from workspace_product where status = 'active'")
                used = int(cur.fetchone()[0])
        limit = account.plan.limits.active_catalogue_products
        remaining = max(limit - used, 0)
        return LimitCheck(
            resource="active_catalogue_products",
            plan_code=account.plan.code,
            limit=limit,
            used=used,
            allowed=used < limit,
            remaining=remaining,
        )

    def ensure_can_add_active_product(self, *, member: CurrentMember) -> None:
        check = self.check_limit(member=member, resource="active_catalogue_products")
        if not check.allowed:
            raise ConflictError(
                details={
                    "reason": "plan_limit_reached",
                    "resource": check.resource,
                    "plan_code": check.plan_code,
                    "limit": check.limit,
                    "used": check.used,
                }
            )


def get_billing_service() -> BillingService:
    return BillingService()


def assign_default_plan_in_signup(cur: psycopg.Cursor, *, tenant_id: object) -> None:
    cur.execute(
        """
        insert into billing_account (
          tenant_id, plan_code, provider, provider_customer_id, provider_subscription_id, status
        ) values (%s, 'starter', 'stub', %s, %s, 'active')
        on conflict (tenant_id) do nothing
        """,
        (
            tenant_id,
            f"stub_customer:{tenant_id}",
            f"stub_subscription:{tenant_id}:starter",
        ),
    )


def _account(conn: object, tenant_id: object) -> BillingAccount:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(ACCOUNT_SQL, (tenant_id,))
        row = cur.fetchone()
    if row is None:
        raise NotFoundError(details={"resource": "billing_account"})
    return _billing_account(dict(row))


def _billing_account(row: dict[str, object]) -> BillingAccount:
    limits = row["limits"]
    features = row["features"]
    if isinstance(limits, str):
        limits = json.loads(limits)
    if isinstance(features, str):
        features = json.loads(features)
    return BillingAccount(
        id=row["id"],
        plan=Plan(
            code=str(row["plan_code"]),
            name=str(row["plan_name"]),
            status=str(row["plan_status"]),
            monthly_price=Money(
                amount=Decimal(str(row["monthly_price_amount"])),
                currency=str(row["monthly_price_currency"]),
            ),
            limits=PlanLimits.model_validate(limits),
            features=dict(features),
        ),
        provider="stub",
        provider_customer_id=str(row["provider_customer_id"]),
        provider_subscription_id=row.get("provider_subscription_id"),
        status=str(row["status"]),
        current_period_start=row.get("current_period_start"),
        current_period_end=row.get("current_period_end"),
        assigned_at=row["assigned_at"],
    )

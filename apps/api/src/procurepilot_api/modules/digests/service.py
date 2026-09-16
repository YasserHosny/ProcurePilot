from __future__ import annotations

import base64
import json
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID

import psycopg.errors
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from procurepilot_api.config import Settings, get_settings
from procurepilot_api.deps import CurrentMember
from procurepilot_api.errors import ConflictError, NotFoundError, UnprocessableEntityError
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.digests.schemas import (
    DigestFilters,
    DigestItem,
    DigestMoney,
    DigestSection,
    DigestSubscription,
    DigestSubscriptionCreate,
    DigestSubscriptionList,
    DigestSubscriptionUpdate,
    DigestView,
)
from procurepilot_api.modules.offers.service import _authenticated_db
from procurepilot_api.modules.reports.schedules import (
    canonical_filters_digest,
    derive_weekly_window,
    next_run_after,
)
from procurepilot_api.shared.audit import AuditEventCreate, get_audit_writer
from procurepilot_api.shared.i18n import t
from procurepilot_api.shared.logging import get_trace_id


class DigestsService:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    def list_subscriptions(
        self,
        *,
        member: CurrentMember,
        cursor: str | None = None,
        limit: int = 50,
    ) -> DigestSubscriptionList:
        offset = _decode_cursor(cursor)
        fetch_limit = min(max(limit, 1), 100)
        with _authenticated_db(self._settings, member) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                if member.role == MemberRole.owner:
                    cur.execute(
                        """
                        select * from digest_subscription
                        where tenant_id = %(tenant_id)s
                        order by created_at desc, id desc
                        offset %(offset)s limit %(limit)s
                        """,
                        {
                            "tenant_id": member.tenant_id,
                            "offset": offset,
                            "limit": fetch_limit + 1,
                        },
                    )
                else:
                    cur.execute(
                        """
                        select * from digest_subscription
                        where tenant_id = %(tenant_id)s and membership_id = %(membership_id)s
                        order by created_at desc, id desc
                        offset %(offset)s limit %(limit)s
                        """,
                        {
                            "tenant_id": member.tenant_id,
                            "membership_id": member.membership_id,
                            "offset": offset,
                            "limit": fetch_limit + 1,
                        },
                    )
                rows = [dict(r) for r in cur.fetchall()]

        has_more = len(rows) > fetch_limit
        page_rows = rows[:fetch_limit]
        next_cursor = _encode_cursor(offset + fetch_limit) if has_more else None
        return DigestSubscriptionList(
            items=[self._map_subscription(r) for r in page_rows],
            next_cursor=next_cursor,
        )

    def create_subscription(
        self,
        *,
        member: CurrentMember,
        payload: DigestSubscriptionCreate,
        bearer_token: str | None = None,
    ) -> DigestSubscription:
        filter_dict = payload.filters.model_dump(mode="json")
        digest = canonical_filters_digest(filter_dict)
        with _authenticated_db(self._settings, member) as conn:
            ctx = _tenant_context(conn, member.tenant_id, member.membership_id)
            _authorize_branch(conn, member=member, branch_id=payload.filters.branch_id)
            locale = (
                payload.locale or ctx.get("preferred_locale") or ctx.get("default_locale") or "en"
            )
            next_run = next_run_after(
                0, datetime.now(UTC), str(ctx.get("reporting_timezone") or "UTC")
            )
            try:
                with conn.cursor(row_factory=dict_row) as cur:
                    cur.execute(
                        """
                        insert into digest_subscription
                          (tenant_id, membership_id, kind, locale, filters, filters_digest,
                           channel, status, next_run_at)
                        values
                          (%(tenant_id)s, %(membership_id)s, 'weekly_digest', %(locale)s,
                           %(filters)s, %(digest)s, %(channel)s, 'active', %(next_run)s)
                        returning *
                        """,
                        {
                            "tenant_id": member.tenant_id,
                            "membership_id": member.membership_id,
                            "locale": locale,
                            "filters": Jsonb(filter_dict),
                            "digest": digest,
                            "channel": payload.channel,
                            "next_run": next_run,
                        },
                    )
                    row = dict(cur.fetchone())
                conn.commit()
            except psycopg.errors.UniqueViolation as exc:
                raise ConflictError(details={"subscription": "already_exists"}) from exc

        sub = self._map_subscription(row)
        _record_audit(
            bearer_token=bearer_token,
            member=member,
            action="digests.subscription_created",
            target={"subscription_id": str(sub.id), "channel": sub.channel},
        )
        return sub

    def update_subscription(
        self,
        *,
        member: CurrentMember,
        subscription_id: UUID,
        payload: DigestSubscriptionUpdate,
        bearer_token: str | None = None,
    ) -> DigestSubscription:
        with _authenticated_db(self._settings, member) as conn:
            existing = self._require_subscription_row(conn, member, subscription_id)
            updates: dict[str, Any] = {}
            if payload.filters is not None:
                _authorize_branch(conn, member=member, branch_id=payload.filters.branch_id)
                filter_dict = payload.filters.model_dump(mode="json")
                updates["filters"] = Jsonb(filter_dict)
                updates["filters_digest"] = canonical_filters_digest(filter_dict)
            if payload.locale is not None:
                updates["locale"] = payload.locale
            if payload.channel is not None:
                updates["channel"] = payload.channel
            if payload.status is not None:
                updates["status"] = payload.status

            if not updates:
                return self._map_subscription(existing)

            updates["updated_at"] = datetime.now(UTC)
            set_clause = ", ".join(f"{k} = %({k})s" for k in updates)
            params = {**updates, "id": subscription_id, "tenant_id": member.tenant_id}

            try:
                with conn.cursor(row_factory=dict_row) as cur:
                    cur.execute(
                        f"""
                        update digest_subscription
                        set {set_clause}
                        where id = %(id)s and tenant_id = %(tenant_id)s
                        returning *
                        """,
                        params,
                    )
                    row = dict(cur.fetchone())
                conn.commit()
            except psycopg.errors.UniqueViolation as exc:
                raise ConflictError(details={"subscription": "already_exists"}) from exc

        sub = self._map_subscription(row)
        status_action = (
            f"digests.subscription_{sub.status}"
            if payload.status is not None
            else "digests.subscription_updated"
        )
        _record_audit(
            bearer_token=bearer_token,
            member=member,
            action=status_action,
            target={"subscription_id": str(sub.id), "status": sub.status},
        )
        return sub

    def delete_subscription(
        self,
        *,
        member: CurrentMember,
        subscription_id: UUID,
        bearer_token: str | None = None,
    ) -> None:
        with _authenticated_db(self._settings, member) as conn:
            # Enforce that caller owns this subscription (or 404)
            self._require_subscription_row(conn, member, subscription_id)
            with conn.cursor() as cur:
                cur.execute(
                    """
                    delete from digest_subscription
                    where id = %s and tenant_id = %s and membership_id = %s
                    """,
                    (subscription_id, member.tenant_id, member.membership_id),
                )
            conn.commit()

        _record_audit(
            bearer_token=bearer_token,
            member=member,
            action="digests.subscription_deleted",
            target={"subscription_id": str(subscription_id)},
        )

    def get_latest_digest(self, *, member: CurrentMember) -> DigestView:
        with _authenticated_db(self._settings, member) as conn:
            ctx = _tenant_context(conn, member.tenant_id, member.membership_id)
            tz_name = str(ctx.get("reporting_timezone") or "UTC")

            # Look up caller's active subscription if one exists
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    select * from digest_subscription
                    where tenant_id = %s and membership_id = %s and status = 'active'
                    order by created_at desc
                    limit 1
                    """,
                    (member.tenant_id, member.membership_id),
                )
                sub_row = cur.fetchone()

            sub_id = UUID(str(sub_row["id"])) if sub_row else member.membership_id
            branch_id = None
            last_status = "succeeded"
            if sub_row:
                filters = sub_row["filters"]
                if isinstance(filters, str):
                    filters = json.loads(filters)
                if isinstance(filters, dict):
                    branch_str = filters.get("branch_id")
                    if branch_str:
                        branch_id = UUID(str(branch_str))
                last_status = sub_row.get("last_delivery_status") or "succeeded"

            now = datetime.now(UTC)
            period_start, period_end = derive_weekly_window(now, tz_name)
            sub_locale = str(sub_row.get("locale") or "en") if sub_row else "en"
            sections = self._assemble_sections(
                conn,
                tenant_id=member.tenant_id,
                membership_id=member.membership_id,
                period_start=period_start,
                period_end=period_end,
                branch_id=branch_id,
                now=now,
                locale=sub_locale,
            )

        if last_status not in ("succeeded", "failed", "email_unconfigured"):
            last_status = "succeeded"

        return DigestView(
            subscription_id=sub_id,
            period_start=period_start,
            period_end=period_end,
            sections=sections,
            rendered_at=now,
            delivery_status=last_status,
        )

    def provision_default_subscription(
        self,
        *,
        tenant_id: UUID,
        membership_id: UUID,
        email: str | None = None,
        bearer_token: str | None = None,
        member: CurrentMember | None = None,
    ) -> DigestSubscription | None:
        """Provision the default active subscription upon membership acceptance (FR-008)."""
        channel = "email" if self._settings.email_configured else "in_app"
        db_cm = (
            _authenticated_db(self._settings, member)
            if member is not None
            else psycopg.connect(self._settings.database_url.get_secret_value())
        )
        with db_cm as conn:
            if member is None:
                with conn.cursor() as setup_cur:
                    claims = {
                        "sub": str(membership_id),
                        "tenant_id": str(tenant_id),
                        "role": "authenticated",
                        "member_role": "member",
                    }
                    setup_cur.execute("set local role authenticated")
                    setup_cur.execute(
                        "select set_config('request.jwt.claims', %s, true)",
                        (json.dumps(claims),),
                    )
            ctx = _tenant_context(conn, tenant_id, membership_id)
            locale = ctx.get("preferred_locale") or ctx.get("default_locale") or "en"
            tz_name = str(ctx.get("reporting_timezone") or "UTC")
            next_run = next_run_after(0, datetime.now(UTC), tz_name)
            digest = canonical_filters_digest({})

            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    insert into digest_subscription
                      (tenant_id, membership_id, kind, locale, filters, filters_digest,
                       channel, status, next_run_at)
                    values
                      (%(tenant_id)s, %(membership_id)s, 'weekly_digest', %(locale)s,
                       '{}'::jsonb, %(digest)s, %(channel)s, 'active', %(next_run)s)
                    on conflict (tenant_id, membership_id, kind, filters_digest) do nothing
                    returning *
                    """,
                    {
                        "tenant_id": tenant_id,
                        "membership_id": membership_id,
                        "locale": locale,
                        "digest": digest,
                        "channel": channel,
                        "next_run": next_run,
                    },
                )
                row = cur.fetchone()
            conn.commit()

        if row is None:
            return None

        sub = self._map_subscription(dict(row))
        get_audit_writer().record(
            AuditEventCreate(
                tenant_id=tenant_id,
                actor_membership_id=membership_id,
                actor_email=email or "",
                action="digests.subscription_provisioned",
                target={"subscription_id": str(sub.id), "channel": sub.channel},
                outcome="success",
                trace_id=get_trace_id(),
            ),
            bearer_token=bearer_token,
        )
        return sub

    def _assemble_sections(
        self,
        conn: psycopg.Connection,
        *,
        tenant_id: UUID,
        membership_id: UUID,
        period_start: date,
        period_end: date,
        branch_id: UUID | None,
        now: datetime,
        locale: str = "en",
    ) -> list[DigestSection]:
        """Assemble the 5 sections in strict FR-009 order."""
        sections: list[DigestSection] = []

        # 1. verified_savings (hero)
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                select * from reporting_savings_for_period(
                    %(tenant_id)s, %(period_start)s, %(period_end)s, null, %(branch_id)s
                )
                """,
                {
                    "tenant_id": tenant_id,
                    "period_start": period_start,
                    "period_end": period_end,
                    "branch_id": branch_id,
                },
            )
            savings_rows = [dict(r) for r in cur.fetchall()]

        savings_items: list[DigestItem] = []
        for s in savings_rows:
            sid = str(s.get("saving_id") or "")
            amt = float(s.get("verified_saving_amount") or 0.0)
            curr = str(s.get("verified_saving_currency") or "")
            pname = str(s.get("product_name") or "Item")
            savings_items.append(
                DigestItem(
                    label=f"#{sid[:8]} {pname}",
                    money=DigestMoney(amount=amt, currency=curr) if curr else None,
                    evidence_ref=f"/savings-ledger/{sid}/evidence",
                    deep_link=f"/savings-ledger/{sid}/evidence",
                )
            )
        sections.append(DigestSection(kind="verified_savings", items=savings_items))

        # 2. pending_verifications
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                select
                  sr.id as saving_id,
                  sr.recorded_at,
                  pc.id as purchase_record_id,
                  wp.tenant_name as product_name,
                  pc.total_paid_amount,
                  pc.total_paid_currency,
                  sr.delta_amount,
                  sr.delta_currency,
                  attr.branch_id
                from saving_record sr
                join purchase_record pc
                  on pc.id = sr.purchase_record_id and pc.tenant_id = %(tenant_id)s
                join workspace_product wp
                  on wp.id = sr.workspace_product_id and wp.tenant_id = %(tenant_id)s
                left join lateral (
                  select pr.branch_id
                  from purchase_request_line prl
                  join purchase_request pr
                    on pr.id = prl.purchase_request_id and pr.tenant_id = prl.tenant_id
                  where prl.tenant_id = %(tenant_id)s
                    and prl.estimated_unit_price_source_landed_cost_id = pc.landed_cost_id
                  order by pr.created_at desc, pr.id desc
                  limit 1
                ) attr on true
                where sr.tenant_id = %(tenant_id)s
                  and sr.status = 'pending'
                  and sr.recorded_at::date >= %(period_start)s
                  and sr.recorded_at::date <= %(period_end)s
                  and (%(branch_id)s::uuid is null or attr.branch_id = %(branch_id)s)
                order by sr.recorded_at desc, sr.id desc
                """,
                {
                    "tenant_id": tenant_id,
                    "period_start": period_start,
                    "period_end": period_end,
                    "branch_id": branch_id,
                },
            )
            pending_rows = [dict(r) for r in cur.fetchall()]

        pending_items: list[DigestItem] = []
        for p in pending_rows:
            sid = str(p.get("saving_id") or "")
            pname = str(p.get("product_name") or "Item")
            amt = float(p.get("total_paid_amount") or 0.0)
            curr = str(p.get("total_paid_currency") or "")
            pending_items.append(
                DigestItem(
                    label=t("digests.itemLabels.pendingVerification", locale, product=pname),
                    money=DigestMoney(amount=amt, currency=curr) if curr else None,
                    evidence_ref=f"/savings-ledger/{sid}/evidence" if sid else "/savings-ledger",
                    deep_link=f"/savings-ledger/{sid}/evidence" if sid else "/savings-ledger",
                )
            )
        sections.append(DigestSection(kind="pending_verifications", items=pending_items))

        # 3. pending_approvals (for subscriber)
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                select
                  ast.id as step_id,
                  pr.id as request_id,
                  pr.request_number,
                  pr.total_estimated_amount,
                  pr.total_estimated_currency,
                  pr.created_at,
                  pr.branch_id
                from approval_step ast
                join purchase_request pr
                  on pr.id = ast.purchase_request_id and pr.tenant_id = ast.tenant_id
                where ast.tenant_id = %(tenant_id)s
                  and ast.assigned_membership_id = %(membership_id)s
                  and ast.status = 'pending'
                  and (%(branch_id)s::uuid is null or pr.branch_id = %(branch_id)s)
                order by ast.created_at desc, ast.id desc
                """,
                {
                    "tenant_id": tenant_id,
                    "membership_id": membership_id,
                    "branch_id": branch_id,
                },
            )
            approval_rows = [dict(r) for r in cur.fetchall()]

        approval_items: list[DigestItem] = []
        for a in approval_rows:
            req_num = a.get("request_number") or str(a.get("request_id") or "")[:8]
            amt = float(a.get("total_estimated_amount") or 0.0)
            curr = str(a.get("total_estimated_currency") or "")
            approval_items.append(
                DigestItem(
                    label=t("digests.itemLabels.approvalRequest", locale, number=req_num),
                    money=DigestMoney(amount=amt, currency=curr) if curr else None,
                    evidence_ref=None,
                    deep_link=f"/approvals/{a['step_id']}",
                )
            )
        sections.append(DigestSection(kind="pending_approvals", items=approval_items))

        # 4. anomalies
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                select * from reporting_alert_snapshot(
                    %(tenant_id)s, %(period_start)s, %(period_end)s, %(branch_id)s
                )
                """,
                {
                    "tenant_id": tenant_id,
                    "period_start": period_start,
                    "period_end": period_end,
                    "branch_id": branch_id,
                },
            )
            alert_rows = [dict(r) for r in cur.fetchall()]

        anomaly_items: list[DigestItem] = []
        for al in alert_rows[:20]:
            pname = str(al.get("product_name") or al.get("canonical_name") or "Product")
            sname = str(al.get("supplier_name") or "Supplier")
            amt = float(al.get("total_amount") or 0.0)
            curr = str(al.get("total_currency") or "")
            anomaly_items.append(
                DigestItem(
                    label=t(
                        "digests.itemLabels.priceAnomaly",
                        locale,
                        product=pname,
                        supplier=sname,
                    ),
                    money=DigestMoney(amount=amt, currency=curr) if curr else None,
                    evidence_ref=None,
                    deep_link="/alerts",
                )
            )
        sections.append(DigestSection(kind="anomalies", items=anomaly_items))

        # 5. expiring_validity (next 7 days)
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                select * from reporting_validity_expiring(
                    %(tenant_id)s, %(now)s, 7, %(branch_id)s
                )
                """,
                {
                    "tenant_id": tenant_id,
                    "now": now,
                    "branch_id": branch_id,
                },
            )
            expiring_rows = [dict(r) for r in cur.fetchall()]

        expiring_items: list[DigestItem] = []
        for ex in expiring_rows[:20]:
            pname = str(ex.get("product_name") or "Product")
            sname = str(ex.get("supplier_name") or "Supplier")
            amt = float(ex.get("total_amount") or 0.0)
            curr = str(ex.get("total_currency") or "")
            expiring_items.append(
                DigestItem(
                    label=t(
                        "digests.itemLabels.expiringOffer",
                        locale,
                        product=pname,
                        supplier=sname,
                    ),
                    money=DigestMoney(amount=amt, currency=curr) if curr else None,
                    evidence_ref=None,
                    deep_link="/quotations",
                )
            )
        sections.append(DigestSection(kind="expiring_validity", items=expiring_items))

        return sections

    def _require_subscription_row(
        self, conn: psycopg.Connection, member: CurrentMember, subscription_id: UUID
    ) -> dict[str, object]:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                select * from digest_subscription
                where id = %s and tenant_id = %s and membership_id = %s
                """,
                (subscription_id, member.tenant_id, member.membership_id),
            )
            row = cur.fetchone()
        if row is None:
            raise NotFoundError(details={"resource": "digest_subscription"})
        return dict(row)

    def _map_subscription(self, row: dict[str, object]) -> DigestSubscription:
        filters = row.get("filters")
        if isinstance(filters, str):
            filters = json.loads(filters)
        elif filters is None:
            filters = {}

        return DigestSubscription(
            id=UUID(str(row["id"])),
            kind="weekly_digest",
            filters=DigestFilters.model_validate(filters),
            channel=str(row["channel"]),
            status=str(row["status"]),
            locale=str(row.get("locale") or "en"),
            next_run_at=row["next_run_at"],
            last_delivery_at=row.get("last_delivery_at"),
            last_delivery_status=row.get("last_delivery_status"),
            email_configured=self._settings.email_configured,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


def _tenant_context(
    conn: psycopg.Connection, tenant_id: UUID, membership_id: UUID
) -> dict[str, object]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            select t.reporting_timezone, t.default_locale, m.preferred_locale
            from tenant t
            left join membership m on m.tenant_id = t.id and m.id = %s
            where t.id = %s
            """,
            (membership_id, tenant_id),
        )
        row = cur.fetchone()
    if row is None:
        return {"reporting_timezone": "UTC", "default_locale": "en", "preferred_locale": "en"}
    return dict(row)


def _authorize_branch(
    conn: psycopg.Connection, *, member: CurrentMember, branch_id: UUID | None
) -> None:
    if branch_id is None:
        return
    if member.role == MemberRole.owner:
        with conn.cursor() as cur:
            cur.execute(
                "select 1 from branch where id = %s and tenant_id = %s",
                (branch_id, member.tenant_id),
            )
            if cur.fetchone() is None:
                raise NotFoundError(details={"resource": "branch"})
        return
    with conn.cursor() as cur:
        cur.execute(
            """
            select 1
            from branch b
            join branch_role_assignment bra
              on bra.branch_id = b.id and bra.tenant_id = b.tenant_id
            where b.id = %s and b.tenant_id = %s and bra.membership_id = %s
            """,
            (branch_id, member.tenant_id, member.membership_id),
        )
        if cur.fetchone() is None:
            raise NotFoundError(details={"resource": "branch"})


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


def _encode_cursor(offset: int) -> str:
    return base64.urlsafe_b64encode(str(offset).encode("ascii")).decode("ascii")


def _decode_cursor(cursor: str | None) -> int:
    if cursor is None:
        return 0
    try:
        return int(base64.urlsafe_b64decode(cursor.encode("ascii")))
    except (ValueError, UnicodeError) as exc:
        raise UnprocessableEntityError(details={"cursor": "invalid"}) from exc

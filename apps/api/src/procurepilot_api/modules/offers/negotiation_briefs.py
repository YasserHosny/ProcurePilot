"""Deterministic, evidence-linked negotiation brief drafts."""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from statistics import median
from typing import Literal
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from procurepilot_api.config import Settings, get_settings
from procurepilot_api.deps import CurrentMember
from procurepilot_api.errors import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    UnprocessableEntityError,
)
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.offers.schemas import (
    BriefItemKind,
    Money,
    NegotiationBrief,
    NegotiationBriefEvidenceRef,
    NegotiationBriefItem,
    NegotiationBriefList,
    SupplierRiskComponentV2,
    SupplierRiskResult,
)
from procurepilot_api.modules.offers.service import _authenticated_db
from procurepilot_api.modules.offers.supplier_iq_repository import load_risk_input
from procurepilot_api.modules.offers.supplier_iq_v2 import PurchaseOrder

BRIEF_VERSION = "negotiation-brief-v1"
CALCULATION_VERSION = "negotiation-brief-v1"
__all__ = [
    "BRIEF_VERSION",
    "BriefContext",
    "BriefDraft",
    "NegotiationBriefService",
    "build_negotiation_brief",
]


@dataclass(frozen=True)
class BriefBill:
    id: UUID
    status: str
    due_date: date | None
    remaining_balance: Decimal | None
    currency: str | None


@dataclass(frozen=True)
class BriefContext:
    supplier_id: UUID
    as_of: date
    orders: tuple[PurchaseOrder, ...] = ()
    bills: tuple[BriefBill, ...] = ()
    payment_term_source_id: UUID | None = None
    quality_issue_ids: tuple[UUID, ...] = ()
    discrepancy_ids: tuple[UUID, ...] = ()


@dataclass(frozen=True)
class BriefDraft:
    supplier_id: UUID
    snapshot_fingerprint: str
    brief_version: str
    release_posture: Literal["g3_unmet"]
    valid_from: date
    valid_until: date
    items: tuple[NegotiationBriefItem, ...]


_ORDER: tuple[BriefItemKind, ...] = (
    "price_trajectory",
    "alternatives",
    "service_performance",
    "concentration_volume",
    "payment_context",
    "purchase_pattern",
)


def build_negotiation_brief(
    snapshot: SupplierRiskResult,
    context: BriefContext,
) -> BriefDraft:
    """Build at most one deterministic, source-linked point per category."""
    if snapshot.supplier_id != context.supplier_id:
        raise ValueError("snapshot and brief context supplier IDs must match")
    if snapshot.state == "insufficient_data" or snapshot.score is None:
        raise ValueError("insufficient Supplier IQ evidence")
    if snapshot.window_end > context.as_of:
        raise ValueError("snapshot is from the future")

    candidates = [
        _risk_component_item(
            snapshot, "price_drift", "price_trajectory", "negotiationBrief.priceTrajectory.question"
        ),
        _risk_component_item(
            snapshot, "single_source", "alternatives", "negotiationBrief.alternatives.question"
        ),
        _risk_component_item(
            snapshot,
            "reliability",
            "service_performance",
            "negotiationBrief.servicePerformance.question",
        ),
        _concentration_item(snapshot, "negotiationBrief.concentrationVolume.question"),
        _payment_item(context, "negotiationBrief.paymentContext.question"),
        _purchase_pattern_item(context, "negotiationBrief.purchasePattern.question"),
    ]
    available = [item for item in candidates if item is not None]
    available.sort(
        key=lambda item: (
            -(Decimal(item.risk) if item.risk is not None else Decimal("-1")),
            _ORDER.index(item.kind),
        )
    )
    ranked = tuple(item.model_copy(update={"rank": rank}) for rank, item in enumerate(available, 1))
    return BriefDraft(
        supplier_id=snapshot.supplier_id,
        snapshot_fingerprint=snapshot.source_fingerprint,
        brief_version=BRIEF_VERSION,
        release_posture=snapshot.release_posture,
        valid_from=snapshot.window_end,
        valid_until=context.as_of + timedelta(days=1),
        items=ranked,
    )


def _risk_component_item(
    snapshot: SupplierRiskResult,
    component_name: Literal["price_drift", "single_source", "reliability"],
    kind: BriefItemKind,
    question_key: str,
) -> NegotiationBriefItem | None:
    component = snapshot.components[component_name]
    evidence_ids = component.source_ids
    if component.risk is None or not evidence_ids:
        return None
    return NegotiationBriefItem(
        kind=kind,
        rank=1,
        value=_decimal_text(component.value),
        confidence=component.confidence,
        risk=_decimal_text(component.risk),
        valid_from=component.window_start,
        valid_until=component.window_end,
        question_i18n_key=question_key,
        calculation_version=component.calculation_version,
        evidence_ids=evidence_ids,
    )


def _concentration_item(
    snapshot: SupplierRiskResult, question_key: str
) -> NegotiationBriefItem | None:
    component = snapshot.components["concentration"]
    buckets = [bucket for bucket in component.currency_buckets if bucket.share is not None]
    if component.risk is None or not buckets:
        return None
    bucket = max(buckets, key=lambda item: (item.share or Decimal("-1"), item.currency))
    return NegotiationBriefItem(
        kind="concentration_volume",
        rank=1,
        value=_decimal_text(bucket.share),
        amount=Money(amount=_decimal_text(bucket.supplier_spend), currency=bucket.currency),
        confidence=component.confidence,
        risk=_decimal_text(component.risk),
        valid_from=component.window_start,
        valid_until=component.window_end,
        question_i18n_key=question_key,
        calculation_version=component.calculation_version,
        evidence_ids=bucket.source_ids,
    )


def _payment_item(context: BriefContext, question_key: str) -> NegotiationBriefItem | None:
    due_open = [
        bill
        for bill in context.bills
        if bill.status in {"open", "partially_paid"} and bill.due_date is not None
    ]
    overdue = [bill for bill in due_open if bill.due_date < context.as_of]
    if not overdue:
        return None
    currencies = {
        bill.currency
        for bill in overdue
        if bill.remaining_balance is not None and bill.currency is not None
    }
    amount = None
    if len(currencies) == 1:
        currency = next(iter(currencies))
        amount = Money(
            amount=_decimal_text(
                sum(
                    (
                        bill.remaining_balance or Decimal("0")
                        for bill in overdue
                        if bill.currency == currency
                    ),
                    Decimal("0"),
                )
            ),
            currency=currency,
        )
    evidence_ids = tuple(bill.id for bill in overdue)
    return NegotiationBriefItem(
        kind="payment_context",
        rank=1,
        value=_decimal_text(Decimal(len(overdue)) / Decimal(len(due_open))),
        amount=amount,
        confidence="high" if len(due_open) >= 10 else "medium" if len(due_open) >= 3 else "low",
        risk=_decimal_text(Decimal(len(overdue)) / Decimal(len(due_open))),
        valid_from=min(bill.due_date for bill in due_open if bill.due_date is not None),
        valid_until=context.as_of + timedelta(days=1),
        question_i18n_key=question_key,
        calculation_version=CALCULATION_VERSION,
        evidence_ids=evidence_ids,
    )


def _purchase_pattern_item(context: BriefContext, question_key: str) -> NegotiationBriefItem | None:
    dates = sorted({order.ordered_on for order in context.orders})
    if len(dates) < 4:
        return None
    intervals = [(right - left).days for left, right in zip(dates, dates[1:], strict=False)]
    median_days = median(intervals)
    evidence_ids = tuple(order.id for order in context.orders if order.ordered_on in dates)
    return NegotiationBriefItem(
        kind="purchase_pattern",
        rank=1,
        value=_decimal_text(Decimal(str(median_days))),
        confidence="high" if len(dates) >= 10 else "medium",
        risk=None,
        valid_from=dates[0],
        valid_until=dates[-1],
        question_i18n_key=question_key,
        calculation_version=CALCULATION_VERSION,
        evidence_ids=evidence_ids,
    )


def _decimal_text(value: Decimal | None) -> str | None:
    return None if value is None else format(value.quantize(Decimal("0.0001")), "f")


class NegotiationBriefService:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    @staticmethod
    def prepare(snapshot: SupplierRiskResult, context: BriefContext) -> BriefDraft:
        return build_negotiation_brief(snapshot, context)

    def prepare_for_supplier(
        self,
        *,
        member: CurrentMember,
        supplier_id: UUID,
        idempotency_key: UUID | None,
    ) -> NegotiationBrief:
        _require_write(member, idempotency_key)
        with _authenticated_db(self._settings, member) as conn:
            snapshot = _latest_snapshot(conn, supplier_id)
            if snapshot is None:
                raise NotFoundError(details={"resource": "supplier_scorecard_snapshot"})
            if snapshot["valid_until"] <= datetime.now(UTC):
                raise UnprocessableEntityError(details={"reason": "snapshot_expired"})
            result = _snapshot_result(snapshot)
            payload = load_risk_input(
                conn,
                supplier_id=supplier_id,
                window_start=result.window_start,
                window_end=result.window_end,
            )
            context = BriefContext(
                supplier_id=supplier_id,
                as_of=datetime.now(UTC).date(),
                orders=tuple(
                    order for order in payload.purchase_orders if order.supplier_id == supplier_id
                ),
                bills=_brief_bills(conn, supplier_id),
            )
            draft = build_negotiation_brief(result, context)
            brief_id = _insert_brief(conn, member, snapshot, draft)
            _record_brief_audit(conn, member, "negotiation_brief.prepared", brief_id)
            return _brief_response(conn, brief_id)

    def list(
        self, *, member: CurrentMember, cursor: str | None = None, limit: int = 50
    ) -> NegotiationBriefList:
        after = _decode_brief_cursor(cursor)
        fetch_limit = min(100, max(1, limit))
        with _authenticated_db(self._settings, member) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                after_clause = ""
                query_params: list[object] = []
                if after is not None:
                    after_clause = "where (created_at, id) < (%s, %s)"
                    query_params.extend(after)
                cur.execute(
                    f"""
                    select id, created_at
                    from negotiation_brief
                    {after_clause}
                    order by created_at desc, id desc
                    limit %s
                    """,
                    (*query_params, fetch_limit + 1),
                )
                rows = cur.fetchall()
            has_more = len(rows) > fetch_limit
            visible_rows = rows[:fetch_limit]
            items = tuple(_brief_response(conn, UUID(str(row["id"]))) for row in visible_rows)
            next_cursor = (
                _encode_brief_cursor(visible_rows[-1]["created_at"], visible_rows[-1]["id"])
                if has_more
                else None
            )
        return NegotiationBriefList(
            items=items,
            next_cursor=next_cursor,
        )

    def get(self, *, member: CurrentMember, brief_id: UUID) -> NegotiationBrief:
        with _authenticated_db(self._settings, member) as conn:
            return _brief_response(conn, brief_id)

    def acknowledge(
        self, *, member: CurrentMember, brief_id: UUID, idempotency_key: UUID | None
    ) -> NegotiationBrief:
        return self._act(member, brief_id, idempotency_key, "acknowledged", None)

    def dismiss(
        self,
        *,
        member: CurrentMember,
        brief_id: UUID,
        idempotency_key: UUID | None,
        reason: str,
    ) -> NegotiationBrief:
        return self._act(member, brief_id, idempotency_key, "dismissed", reason)

    def _act(
        self,
        member: CurrentMember,
        brief_id: UUID,
        idempotency_key: UUID | None,
        action: str,
        reason: str | None,
    ) -> NegotiationBrief:
        _require_write(member, idempotency_key)
        if action == "dismissed" and not reason:
            raise UnprocessableEntityError(details={"reason": "dismiss_reason_required"})
        with _authenticated_db(self._settings, member) as conn:
            if _brief_response(conn, brief_id) is None:
                raise NotFoundError(details={"resource": "negotiation_brief"})
            with conn.cursor() as cur:
                cur.execute(
                    """
                    select action from negotiation_brief_action
                    where tenant_id = %s and idempotency_key = %s
                    """,
                    (member.tenant_id, str(idempotency_key)),
                )
                existing = cur.fetchone()
                if existing is not None:
                    if existing[0] != action:
                        raise ConflictError(details={"reason": "idempotency_key_reused"})
                    return _brief_response(conn, brief_id)
                cur.execute(
                    """
                    insert into negotiation_brief_action (
                      tenant_id, brief_id, action, reason, idempotency_key,
                      acted_by_membership_id
                    ) values (%s, %s, %s, %s, %s, %s)
                    """,
                    (
                        member.tenant_id,
                        brief_id,
                        action,
                        reason,
                        str(idempotency_key),
                        member.membership_id,
                    ),
                )
            _record_brief_audit(conn, member, f"negotiation_brief.{action}", brief_id)
            return _brief_response(conn, brief_id)


def get_negotiation_brief_service() -> NegotiationBriefService:
    return NegotiationBriefService()


def _require_write(member: CurrentMember, idempotency_key: UUID | None) -> None:
    if member.role not in {MemberRole.owner, MemberRole.buyer}:
        raise PermissionDeniedError()
    if idempotency_key is None:
        raise UnprocessableEntityError(details={"header": "Idempotency-Key is required"})


def _latest_snapshot(conn: psycopg.Connection, supplier_id: UUID) -> dict[str, object] | None:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            select id, supplier_id, window_start, window_end, metrics, risk_score, state,
                   confidence, release_posture, valid_from, valid_until, source_fingerprint,
                   observed_history_days
            from supplier_scorecard_snapshot
            where supplier_id = %s and rule_version = 'supplier-scorecard-v2'
            order by window_end desc, computed_at desc, id desc
            limit 1
            """,
            (supplier_id,),
        )
        row = cur.fetchone()
    return dict(row) if row is not None else None


def _snapshot_result(row: dict[str, object]) -> SupplierRiskResult:
    metrics = row["metrics"]
    risk_score = row["risk_score"]
    if isinstance(metrics, str):
        metrics = json.loads(metrics)
    if isinstance(risk_score, str):
        risk_score = json.loads(risk_score)
    assert isinstance(metrics, dict) and isinstance(risk_score, dict)
    score_value = risk_score.get("total")
    score = None if score_value is None else Decimal(str(score_value))
    risk_level = (
        None
        if score is None
        else "low"
        if score < Decimal(".35")
        else "medium"
        if score < Decimal(".65")
        else "high"
    )
    return SupplierRiskResult(
        supplier_id=UUID(str(row["supplier_id"])),
        components={
            name: SupplierRiskComponentV2.model_validate(component)
            for name, component in metrics.items()
        },
        weights={
            name: Decimal(str(value)) for name, value in risk_score.get("weights", {}).items()
        },
        score=score,
        risk_level=risk_level,
        confidence=str(row["confidence"]),
        state=str(row["state"]),
        release_posture=str(row["release_posture"]),
        window_start=row["window_start"],
        split_date=row["window_start"]
        + timedelta(days=(row["window_end"] - row["window_start"]).days // 2),
        window_end=row["window_end"],
        observed_history_days=int(row["observed_history_days"] or 0),
        scorecard_version="supplier-scorecard-v2",
        risk_version="supplier-risk-v2",
        source_fingerprint=str(row["source_fingerprint"]),
    )


def _brief_bills(conn: psycopg.Connection, supplier_id: UUID) -> tuple[BriefBill, ...]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            select id, provider_status::text as status, due_date, remaining_balance_amount,
                   remaining_balance_currency
            from synced_bill
            where matched_supplier_id = %s
            """,
            (supplier_id,),
        )
        return tuple(
            BriefBill(
                id=UUID(str(row["id"])),
                status=str(row["status"]),
                due_date=row["due_date"],
                remaining_balance=(
                    Decimal(str(row["remaining_balance_amount"]))
                    if row["remaining_balance_amount"] is not None
                    else None
                ),
                currency=row["remaining_balance_currency"],
            )
            for row in cur.fetchall()
        )


def _insert_brief(
    conn: psycopg.Connection,
    member: CurrentMember,
    snapshot: dict[str, object],
    draft: BriefDraft,
) -> UUID:
    with conn.cursor() as cur:
        cur.execute(
            """
            insert into negotiation_brief (
              tenant_id, supplier_id, snapshot_id, brief_version, source_fingerprint,
              release_posture, valid_from, valid_until, created_by_membership_id
            ) values (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            on conflict (tenant_id, supplier_id, snapshot_id, brief_version) do nothing
            returning id
            """,
            (
                member.tenant_id,
                draft.supplier_id,
                snapshot["id"],
                draft.brief_version,
                draft.snapshot_fingerprint,
                draft.release_posture,
                datetime.combine(draft.valid_from, time.min, UTC),
                datetime.combine(draft.valid_until, time.min, UTC),
                member.membership_id,
            ),
        )
        row = cur.fetchone()
        if row is None:
            cur.execute(
                """
                select id from negotiation_brief
                where tenant_id = %s and supplier_id = %s and snapshot_id = %s
                  and brief_version = %s
                """,
                (member.tenant_id, draft.supplier_id, snapshot["id"], draft.brief_version),
            )
            existing = cur.fetchone()
            if existing is None:
                raise RuntimeError("brief insert did not return an id")
            return UUID(str(existing[0]))
        brief_id = UUID(str(row[0]))
        metric_ids = _metric_ids(cur, snapshot["id"])
        for item in draft.items:
            metric_id = metric_ids.get(item.kind)
            if item.kind == "payment_context":
                _ensure_bill_evidence(
                    cur,
                    tenant_id=member.tenant_id,
                    metric_id=next(iter(metric_ids.values()), None),
                    source_ids=item.evidence_ids,
                )
            amount = Decimal(item.amount.amount) if item.amount else None
            currency = item.amount.currency if item.amount else None
            cur.execute(
                """
                insert into negotiation_brief_item (
                  tenant_id, brief_id, metric_id, item_kind, rank, value, amount, currency,
                  confidence, risk, valid_from, valid_until, question_i18n_key,
                  calculation_version
                ) values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                returning id
                """,
                (
                    member.tenant_id,
                    brief_id,
                    metric_id,
                    item.kind,
                    item.rank,
                    item.value,
                    amount,
                    currency,
                    item.confidence,
                    item.risk,
                    datetime.combine(item.valid_from, time.min, UTC),
                    datetime.combine(item.valid_until, time.min, UTC),
                    item.question_i18n_key,
                    item.calculation_version,
                ),
            )
            item_id = UUID(str(cur.fetchone()[0]))
            for evidence_id in _evidence_ids(cur, metric_id, item.evidence_ids):
                cur.execute(
                    """
                    insert into negotiation_brief_item_evidence (tenant_id, item_id, evidence_id)
                    values (%s, %s, %s)
                    """,
                    (member.tenant_id, item_id, evidence_id),
                )
        return brief_id


def _metric_ids(cur: psycopg.Cursor, snapshot_id: object) -> dict[str, UUID]:
    cur.execute(
        "select id, metric_kind from supplier_scorecard_metric where snapshot_id = %s",
        (snapshot_id,),
    )
    mapping = {
        "price_trajectory": "price_drift",
        "alternatives": "single_source_exposure",
        "service_performance": "reliability",
        "concentration_volume": "concentration",
        "payment_context": "payment_context",
        "purchase_pattern": "purchase_pattern",
    }
    rows = {str(row[1]): UUID(str(row[0])) for row in cur.fetchall()}
    return {kind: rows[metric] for kind, metric in mapping.items() if metric in rows}


def _evidence_ids(
    cur: psycopg.Cursor, metric_id: UUID | None, source_ids: tuple[UUID, ...]
) -> tuple[UUID, ...]:
    if not source_ids:
        return ()
    cur.execute(
        """
        select id from supplier_scorecard_evidence
        where (%s::uuid is null or metric_id = %s) and (
          purchase_order_id = any(%s::uuid[]) or delivery_receipt_id = any(%s::uuid[])
          or landed_cost_id = any(%s::uuid[]) or workspace_product_id = any(%s::uuid[])
          or synced_bill_id = any(%s::uuid[])
        )
        """,
        (
            metric_id,
            metric_id,
            list(source_ids),
            list(source_ids),
            list(source_ids),
            list(source_ids),
            list(source_ids),
        ),
    )
    return tuple(UUID(str(row[0])) for row in cur.fetchall())


def _ensure_bill_evidence(
    cur: psycopg.Cursor,
    *,
    tenant_id: UUID,
    metric_id: UUID | None,
    source_ids: tuple[UUID, ...],
) -> None:
    if metric_id is None or not source_ids:
        return
    cur.execute(
        """
        insert into supplier_scorecard_evidence (tenant_id, metric_id, synced_bill_id)
        select %s, %s, bill.id
        from synced_bill bill
        where bill.id = any(%s::uuid[])
          and not exists (
            select 1
            from supplier_scorecard_evidence evidence
            where evidence.tenant_id = bill.tenant_id
              and evidence.synced_bill_id = bill.id
          )
        """,
        (tenant_id, metric_id, list(source_ids)),
    )


def _brief_response(conn: psycopg.Connection, brief_id: UUID) -> NegotiationBrief:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("select * from negotiation_brief where id = %s", (brief_id,))
        header = cur.fetchone()
        if header is None:
            raise NotFoundError(details={"resource": "negotiation_brief"})
        cur.execute(
            """
            select action
            from negotiation_brief_action
            where brief_id = %s
            order by created_at desc, id desc
            limit 1
            """,
            (brief_id,),
        )
        action = cur.fetchone()
        status = action["action"] if action else "prepared"
        cur.execute(
            "select * from negotiation_brief_item where brief_id = %s order by rank", (brief_id,)
        )
        item_rows = cur.fetchall()
        items = []
        for row in item_rows:
            cur.execute(
                """
                select evidence_id
                from negotiation_brief_item_evidence
                where item_id = %s
                order by evidence_id
                """,
                (row["id"],),
            )
            evidence_ids = tuple(UUID(str(link["evidence_id"])) for link in cur.fetchall())
            evidence = _brief_evidence_refs(cur, row["id"])
            items.append(
                NegotiationBriefItem(
                    kind=row["item_kind"],
                    rank=row["rank"],
                    value=str(row["value"]) if row["value"] is not None else None,
                    amount=(
                        Money(amount=str(row["amount"]), currency=row["currency"])
                        if row["amount"] is not None
                        else None
                    ),
                    confidence=row["confidence"],
                    risk=str(row["risk"]) if row["risk"] is not None else None,
                    valid_from=row["valid_from"].date(),
                    valid_until=row["valid_until"].date(),
                    question_i18n_key=row["question_i18n_key"],
                    calculation_version=row["calculation_version"],
                    metric_id=row["metric_id"],
                    evidence_ids=evidence_ids,
                    evidence=evidence,
                )
            )
    return NegotiationBrief(
        id=brief_id,
        supplier_id=header["supplier_id"],
        snapshot_id=header["snapshot_id"],
        brief_version=header["brief_version"],
        source_fingerprint=header["source_fingerprint"],
        release_posture=header["release_posture"],
        valid_from=header["valid_from"],
        valid_until=header["valid_until"],
        status=status,
        items=tuple(items),
    )


def _brief_evidence_refs(
    cur: psycopg.Cursor,
    item_id: UUID,
) -> tuple[NegotiationBriefEvidenceRef, ...]:
    source_columns = (
        ("purchase_order", "purchase_order_id"),
        ("delivery_receipt", "delivery_receipt_id"),
        ("landed_cost", "landed_cost_id"),
        ("three_way_match", "three_way_match_id"),
        ("synced_bill", "synced_bill_id"),
        ("workspace_product", "workspace_product_id"),
        ("delivery_quality_issue", "delivery_quality_issue_id"),
        ("supplier_commercial_term", "supplier_commercial_term_id"),
    )
    cur.execute(
        """
        select evidence.id, evidence.purchase_order_id, evidence.delivery_receipt_id,
               evidence.landed_cost_id, evidence.three_way_match_id,
               evidence.synced_bill_id, evidence.workspace_product_id,
               evidence.delivery_quality_issue_id,
               evidence.supplier_commercial_term_id
        from negotiation_brief_item_evidence link
        join supplier_scorecard_evidence evidence
          on evidence.tenant_id = link.tenant_id and evidence.id = link.evidence_id
        where link.item_id = %s
        order by evidence.id
        """,
        (item_id,),
    )
    refs: list[NegotiationBriefEvidenceRef] = []
    for row in cur.fetchall():
        for source_kind, column in source_columns:
            if row[column] is not None:
                refs.append(
                    NegotiationBriefEvidenceRef(
                        evidence_id=UUID(str(row["id"])),
                        source_kind=source_kind,
                        source_id=UUID(str(row[column])),
                    )
                )
                break
    return tuple(refs)


def _encode_brief_cursor(created_at: datetime, brief_id: object) -> str:
    raw = json.dumps(
        {"created_at": created_at.isoformat(), "id": str(brief_id)},
        separators=(",", ":"),
    ).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def _decode_brief_cursor(cursor: str | None) -> tuple[datetime, UUID] | None:
    if cursor is None:
        return None
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii"))
        payload = json.loads(raw.decode("utf-8"))
        created_at = datetime.fromisoformat(payload["created_at"])
        brief_id = UUID(payload["id"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise UnprocessableEntityError(details={"cursor": "invalid"}) from exc
    if created_at.tzinfo is None:
        raise UnprocessableEntityError(details={"cursor": "invalid"})
    return created_at, brief_id


def _record_brief_audit(
    conn: psycopg.Connection, member: CurrentMember, action: str, brief_id: UUID
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "select record_audit_event(%s, 'success'::audit_outcome, %s, %s, %s, %s::jsonb, null)",
            (
                action,
                member.tenant_id,
                member.membership_id,
                member.email,
                Jsonb({"brief_id": str(brief_id)}),
            ),
        )

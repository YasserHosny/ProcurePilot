"""Turn service for the Grounded Procurement Analyst (R4.2).

Responsibilities (T013):
  1. Classify the member's question via intent.py (FR-005).
  2. If unsupported: persist a turn with an explicit refusal answer, no citations,
     no retrieval call.
  3. If supported: load the pre-scoped input records for that category (thin DB
     fetches here, no business logic), call the matching retrieval.py function.
  4. Persist the immutable turn + citation rows atomically (one transaction; on any
     failure, zero partial rows — matching the atomicity discipline in
     negotiation_briefs.py).
  5. Append an audit event (FR-012) using the same SECURITY DEFINER
     ``record_audit_event`` function called via psycopg — not the Supabase client
     wrapper — so the audit row is committed in the same transaction as the turn rows.
  6. Every persisted/returned turn carries ``release_posture = "g3_unmet"`` (FR-011).

All database access uses the ``_authenticated_db`` pattern from offers/service.py:
  ``set local role authenticated`` + ``set_config('request.jwt.claims', …)`` so
  Postgres RLS policies evaluate the correct tenant_id from the JWT claims.

The loader queries (step 3) are intentionally thin: they fetch pre-scoped records
using tenant_id from the member context and any entity IDs the intent layer resolved.
No business logic lives here — only the data fetch that feeds retrieval.py's pure
functions.

FR-007 cross-tenant guarantee: because every loader query filters by
``tenant_id = member.tenant_id`` AND relies on RLS, a question referencing another
tenant's supplier/product/order IDs silently returns empty results → NoGroundingData.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from decimal import Decimal
from typing import Literal
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from procurepilot_api.config import Settings, get_settings
from procurepilot_api.deps import CurrentMember
from procurepilot_api.errors import ServiceUnavailableError
from procurepilot_api.modules.analyst.intent import (
    IntentProvider,
    IntentResult,
    PriorTurnContext,
    get_intent_provider,
)
from procurepilot_api.modules.analyst.retrieval import (
    CALCULATION_VERSION,
    AnalystResult,
    NoGroundingData,
    OrderRecord,
    OrdersQuotationsInput,
    QuotationRecord,
    ReorderForecastsInput,
    ReorderRecord,
    SavingRecord,
    SpendRecord,
    SpendSavingsInput,
    SupplierPerformanceRiskInput,
    SupplierRiskRecord,
    retrieve_orders_quotations,
    retrieve_reorder_forecasts,
    retrieve_spend_savings,
    retrieve_supplier_performance_risk,
)
from procurepilot_api.modules.analyst.schemas import (
    AnalystCategory,
    AnalystCitationCreate,
    AnalystCitationResponse,
    AnalystConversationResponse,
    AnalystTurnResponse,
    CalculationDetail,
    CitationSourceKind,
)

# Explicit refusal answer text (FR-002, FR-006)
_UNSUPPORTED_ANSWER = (
    "I can't answer that question yet. This analyst only supports questions about "
    "spend and savings, supplier performance and risk, order and quotation history, "
    "and reorder forecasts. Please ask about one of those topics."
)
_NO_GROUNDING_ANSWER_PREFIX = "No data found to answer this question. "

RELEASE_POSTURE: Literal["g3_unmet"] = "g3_unmet"


# ---------------------------------------------------------------------------
# Main service class
# ---------------------------------------------------------------------------


class AnalystService:
    def __init__(
        self,
        settings: Settings | None = None,
        intent_provider: IntentProvider | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._intent_provider = intent_provider or get_intent_provider()

    def ask(
        self,
        *,
        member: CurrentMember,
        question_text: str,
        idempotency_key: UUID,
        bearer_token: str,
        conversation_id: UUID | None = None,
        prior_turn_context: PriorTurnContext | None = None,
    ) -> AnalystConversationResponse:
        """Create a new conversation (or add a turn to an existing one) and answer the question.

        Returns the full AnalystConversationResponse including the new turn.
        """
        with _authenticated_db(self._settings, member) as conn:
            # Idempotency: return existing result if this key was already processed
            existing = _find_by_idempotency_key(conn, member.tenant_id, idempotency_key)
            if existing is not None:
                return _build_conversation_response(conn, existing)

            # 1. Classify
            intent: IntentResult = self._intent_provider.classify(
                question=question_text,
                prior_turn_context=prior_turn_context,
            )

            # 2. Retrieve (or produce refusal)
            if intent.category == "unsupported":
                result: AnalystResult = NoGroundingData(
                    reason="unsupported_category",
                    explanation=_UNSUPPORTED_ANSWER,
                )
                resolved_category = AnalystCategory.spend_savings  # stored sentinel
                is_unsupported = True
            else:
                resolved_category = intent.category
                is_unsupported = False
                result = _load_and_retrieve(
                    conn,
                    member=member,
                    category=resolved_category,
                    entities=intent.entities,
                )

            # 3. Build the answer components
            if is_unsupported:
                answer_text = _UNSUPPORTED_ANSWER
                calculation: CalculationDetail | None = None
                citations: tuple[AnalystCitationCreate, ...] = ()
            elif isinstance(result, NoGroundingData):
                answer_text = _NO_GROUNDING_ANSWER_PREFIX + result.explanation
                calculation = None
                citations = ()
            else:
                answer_text = result.answer_text
                calculation = result.calculation
                citations = result.citations

            # 4. Persist atomically (conversation + turn + citations + audit)
            if conversation_id is None:
                conversation_id = _insert_conversation(conn, member)

            turn_id = _insert_turn(
                conn,
                member=member,
                conversation_id=conversation_id,
                question_text=question_text,
                category=resolved_category,
                answer_text=answer_text,
                calculation=calculation,
                idempotency_key=idempotency_key,
                is_unsupported=is_unsupported,
            )
            for citation in citations:
                _insert_citation(conn, member.tenant_id, turn_id, citation)

            # 5. Audit event (FR-012) — committed in the same transaction
            _record_turn_audit(conn, member, conversation_id, turn_id)

            return _build_conversation_response(conn, conversation_id)


def get_analyst_service() -> AnalystService:
    return AnalystService()


# ---------------------------------------------------------------------------
# Authenticated psycopg context (mirrors offers/service.py exactly)
# ---------------------------------------------------------------------------


@contextmanager
def _authenticated_db(settings: Settings, member: CurrentMember) -> Iterator[psycopg.Connection]:
    try:
        with psycopg.connect(
            settings.database_url.get_secret_value(), prepare_threshold=None
        ) as conn:
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


# ---------------------------------------------------------------------------
# Thin data loaders (one per FR-002 category)
# ---------------------------------------------------------------------------


def _load_and_retrieve(
    conn: psycopg.Connection,
    *,
    member: CurrentMember,
    category: AnalystCategory,
    entities: object,  # IntentEntities
) -> AnalystResult:
    """Fetch pre-scoped records for the category and call the matching retrieval function."""
    if category == AnalystCategory.spend_savings:
        return retrieve_spend_savings(_load_spend_savings(conn, member, entities))
    if category == AnalystCategory.supplier_performance_risk:
        return retrieve_supplier_performance_risk(
            _load_supplier_performance_risk(conn, member, entities)
        )
    if category == AnalystCategory.orders_quotations:
        return retrieve_orders_quotations(_load_orders_quotations(conn, member, entities))
    if category == AnalystCategory.reorder_forecasts:
        return retrieve_reorder_forecasts(_load_reorder_forecasts(conn, member, entities))
    # Should never reach here, but be safe
    return NoGroundingData(reason="unsupported_category", explanation=_UNSUPPORTED_ANSWER)


def _load_spend_savings(
    conn: psycopg.Connection,
    member: CurrentMember,
    entities: object,
) -> SpendSavingsInput:
    supplier_id = getattr(entities, "supplier_id", None)
    with conn.cursor(row_factory=dict_row) as cur:
        # Spend: purchase orders scoped by tenant + optional supplier
        cur.execute(
            """
            select po.id,
                   po.supplier_id,
                   po.total_amount,
                   po.total_currency,
                   po.order_date
            from purchase_order po
            where po.tenant_id = %s
              and (%s::uuid is null or po.supplier_id = %s::uuid)
            order by po.order_date desc
            limit 500
            """,
            (member.tenant_id, supplier_id, supplier_id),
        )
        spend_rows = cur.fetchall()
        # Savings: saving_record scoped by tenant + optional supplier. The realized
        # saving is actual_value (what was actually paid/saved), not baseline.
        cur.execute(
            """
            select sr.id,
                   sr.workspace_product_id,
                   sr.supplier_id,
                   sr.actual_value_amount,
                   sr.actual_value_currency,
                   sr.recorded_at::date as recorded_on
            from saving_record sr
            where sr.tenant_id = %s
              and (%s::uuid is null or sr.supplier_id = %s::uuid)
            order by sr.recorded_at desc
            limit 500
            """,
            (member.tenant_id, supplier_id, supplier_id),
        )
        saving_rows = cur.fetchall()

    spend_records = tuple(
        SpendRecord(
            id=UUID(str(r["id"])),
            source_kind=CitationSourceKind.purchase_order,
            supplier_id=UUID(str(r["supplier_id"])) if r["supplier_id"] else None,
            product_id=None,
            amount=Decimal(str(r["total_amount"])),
            currency=str(r["total_currency"]),
            recorded_on=_to_date(r["order_date"]),
        )
        for r in spend_rows
    )
    saving_records = tuple(
        SavingRecord(
            id=UUID(str(r["id"])),
            product_id=UUID(str(r["workspace_product_id"])) if r["workspace_product_id"] else None,
            supplier_id=UUID(str(r["supplier_id"])) if r["supplier_id"] else None,
            amount=Decimal(str(r["actual_value_amount"])),
            currency=str(r["actual_value_currency"]),
            recorded_on=_to_date(r["recorded_on"]),
        )
        for r in saving_rows
    )
    return SpendSavingsInput(spend_records=spend_records, saving_records=saving_records)


def _load_supplier_performance_risk(
    conn: psycopg.Connection,
    member: CurrentMember,
    entities: object,
) -> SupplierPerformanceRiskInput:
    supplier_id = getattr(entities, "supplier_id", None)
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            select sss.id,
                   sss.supplier_id,
                   s.name as supplier_name,
                   sss.state,
                   sss.window_end::date as window_end,
                   sss.risk_score,
                   sss.confidence,
                   sss.release_posture
            from supplier_scorecard_snapshot sss
            join supplier s on s.id = sss.supplier_id and s.tenant_id = sss.tenant_id
            where sss.tenant_id = %s
              and sss.rule_version = 'supplier-scorecard-v2'
              and (%s::uuid is null or sss.supplier_id = %s::uuid)
            order by sss.window_end desc, sss.id desc
            limit 200
            """,
            (member.tenant_id, supplier_id, supplier_id),
        )
        rows = cur.fetchall()

    snapshots = tuple(
        SupplierRiskRecord(
            id=UUID(str(r["id"])),
            supplier_id=UUID(str(r["supplier_id"])),
            supplier_name=str(r["supplier_name"]),
            risk_level=_risk_level_from_score(r.get("risk_score")),
            risk_score=_extract_total_risk_score(r.get("risk_score")),
            state=str(r["state"]),
            window_end=_to_date(r["window_end"]),
        )
        for r in rows
    )
    return SupplierPerformanceRiskInput(snapshots=snapshots)


def _load_orders_quotations(
    conn: psycopg.Connection,
    member: CurrentMember,
    entities: object,
) -> OrdersQuotationsInput:
    supplier_id = getattr(entities, "supplier_id", None)
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            select po.id,
                   po.supplier_id,
                   po.status,
                   po.total_amount,
                   po.total_currency,
                   po.order_date,
                   po.expected_delivery_date
            from purchase_order po
            where po.tenant_id = %s
              and (%s::uuid is null or po.supplier_id = %s::uuid)
            order by po.order_date desc
            limit 200
            """,
            (member.tenant_id, supplier_id, supplier_id),
        )
        order_rows = cur.fetchall()
        # quotation_line has no direct product column — the match is via match_decision,
        # the same table the rest of the app uses to resolve a line to a workspace product.
        cur.execute(
            """
            select ql.id,
                   q.supplier_id,
                   md.matched_workspace_product_id as product_id,
                   ql.unit_price_amount,
                   ql.unit_price_currency,
                   q.issue_date
            from quotation_line ql
            join quotation q on q.tenant_id = ql.tenant_id and q.id = ql.quotation_id
            left join match_decision md
              on md.tenant_id = ql.tenant_id and md.quotation_line_id = ql.id
            where q.tenant_id = %s
              and (%s::uuid is null or q.supplier_id = %s::uuid)
              and ql.unit_price_amount is not null
            order by q.issue_date desc
            limit 200
            """,
            (member.tenant_id, supplier_id, supplier_id),
        )
        quotation_rows = cur.fetchall()

    orders = tuple(
        OrderRecord(
            id=UUID(str(r["id"])),
            supplier_id=UUID(str(r["supplier_id"])),
            status=str(r["status"]),
            total_amount=Decimal(str(r["total_amount"])),
            currency=str(r["total_currency"]),
            order_date=_to_date(r["order_date"]),
            expected_delivery_date=r["expected_delivery_date"],
        )
        for r in order_rows
    )
    quotations = tuple(
        QuotationRecord(
            id=UUID(str(r["id"])),
            supplier_id=UUID(str(r["supplier_id"])) if r["supplier_id"] else None,
            product_id=UUID(str(r["product_id"])) if r["product_id"] else None,
            unit_price_amount=Decimal(str(r["unit_price_amount"])),
            currency=str(r["unit_price_currency"]),
            created_at=_to_date(r["issue_date"]) if r["issue_date"] else date.today(),
        )
        for r in quotation_rows
    )
    return OrdersQuotationsInput(orders=orders, quotations=quotations)


def _load_reorder_forecasts(
    conn: psycopg.Connection,
    member: CurrentMember,
    entities: object,
) -> ReorderForecastsInput:
    product_id = getattr(entities, "product_id", None)
    with conn.cursor(row_factory=dict_row) as cur:
        # suggested_quantity lives on demand_forecast, not reorder_proposal — a proposal is
        # a human-facing wrapper around one forecast snapshot. This schema has no genuine
        # urgency concept (demand_forecast.confidence describes the forecast's statistical
        # confidence, not business urgency) — inventing one from an unrelated field would be
        # exactly the fabricated-signal Constitution Principle I forbids, so urgency stays
        # unset here rather than being approximated from a field that means something else.
        cur.execute(
            """
            select rp.id,
                   rp.workspace_product_id as product_id,
                   df.suggested_quantity as proposed_quantity,
                   rp.status,
                   rp.created_at::date as created_at
            from reorder_proposal rp
            join demand_forecast df
              on df.tenant_id = rp.tenant_id and df.id = rp.demand_forecast_id
            where rp.tenant_id = %s
              and (%s::uuid is null or rp.workspace_product_id = %s::uuid)
            order by rp.created_at desc
            limit 200
            """,
            (member.tenant_id, product_id, product_id),
        )
        rows = cur.fetchall()

    proposals = tuple(
        ReorderRecord(
            id=UUID(str(r["id"])),
            product_id=UUID(str(r["product_id"])),
            proposed_quantity=(
                Decimal(str(r["proposed_quantity"])) if r["proposed_quantity"] else Decimal(0)
            ),
            status=str(r["status"]),
            created_at=_to_date(r["created_at"]),
            urgency=r.get("urgency"),
        )
        for r in rows
    )
    return ReorderForecastsInput(proposals=proposals)


# ---------------------------------------------------------------------------
# DB write helpers
# ---------------------------------------------------------------------------


def _find_by_idempotency_key(
    conn: psycopg.Connection,
    tenant_id: UUID,
    idempotency_key: UUID,
) -> UUID | None:
    """Return the conversation_id if this idempotency key was already used."""
    with conn.cursor() as cur:
        cur.execute(
            """
            select at.conversation_id
            from analyst_turn at
            where at.tenant_id = %s and at.idempotency_key = %s
            limit 1
            """,
            (tenant_id, str(idempotency_key)),
        )
        row = cur.fetchone()
    return UUID(str(row[0])) if row else None


def _insert_conversation(
    conn: psycopg.Connection,
    member: CurrentMember,
) -> UUID:
    with conn.cursor() as cur:
        cur.execute(
            """
            insert into analyst_conversation (tenant_id, creating_member_id)
            values (%s, %s)
            returning id
            """,
            (member.tenant_id, member.membership_id),
        )
        row = cur.fetchone()
        assert row is not None
        return UUID(str(row[0]))


def _insert_turn(
    conn: psycopg.Connection,
    *,
    member: CurrentMember,
    conversation_id: UUID,
    question_text: str,
    category: AnalystCategory,
    answer_text: str,
    calculation: CalculationDetail | None,
    idempotency_key: UUID,
    is_unsupported: bool,
) -> UUID:
    calculation_json = calculation.model_dump(mode="json") if calculation else None
    with conn.cursor() as cur:
        cur.execute(
            """
            insert into analyst_turn (
                tenant_id, conversation_id, creating_member_id,
                question_text, category, answer_text, calculation_version,
                release_posture, calculation, idempotency_key, is_unsupported
            ) values (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s)
            returning id
            """,
            (
                member.tenant_id,
                conversation_id,
                member.membership_id,
                question_text,
                category.value,
                answer_text,
                CALCULATION_VERSION,
                RELEASE_POSTURE,
                Jsonb(calculation_json) if calculation_json is not None else None,
                str(idempotency_key),
                is_unsupported,
            ),
        )
        row = cur.fetchone()
        assert row is not None
        return UUID(str(row[0]))


def _citation_column(source_kind: CitationSourceKind) -> str:
    """analyst_turn_citation has one nullable FK column per source kind (mirroring
    supplier_scorecard_evidence's typed-reference-per-row pattern), not a generic
    (source_kind, source_id) pair — the column name is always f"{kind}_id"."""
    return f"{source_kind.value}_id"


def _citation_from_row(row: dict[str, object]) -> AnalystCitationResponse:
    """Recover (source_kind, source_id) from whichever of the 7 typed FK columns is
    non-null — the migration's check constraint guarantees exactly one is."""
    for kind in CitationSourceKind:
        value = row.get(_citation_column(kind))
        if value is not None:
            return AnalystCitationResponse(
                id=UUID(str(row["id"])),
                turn_id=UUID(str(row["turn_id"])),
                source_kind=kind,
                source_id=UUID(str(value)),
                created_at=row["created_at"],  # type: ignore[arg-type]
            )
    raise ValueError(f"analyst_turn_citation row {row['id']} has no non-null source column")


def _insert_citation(
    conn: psycopg.Connection,
    tenant_id: UUID,
    turn_id: UUID,
    citation: AnalystCitationCreate,
) -> None:
    column = _citation_column(citation.source_kind)
    with conn.cursor() as cur:
        cur.execute(
            # nosec: `column` is built from the CitationSourceKind enum, never user input.
            f"insert into analyst_turn_citation (tenant_id, turn_id, {column}) "  # noqa: S608
            "values (%s, %s, %s)",
            (tenant_id, turn_id, citation.source_id),
        )


def _record_turn_audit(
    conn: psycopg.Connection,
    member: CurrentMember,
    conversation_id: UUID,
    turn_id: UUID,
) -> None:
    """Append an audit event in the same transaction (FR-012)."""
    with conn.cursor() as cur:
        cur.execute(
            "select record_audit_event(%s, 'success'::audit_outcome, %s, %s, %s, %s::jsonb, null)",
            (
                "analyst_turn.created",
                member.tenant_id,
                member.membership_id,
                member.email,
                Jsonb({"conversation_id": str(conversation_id), "turn_id": str(turn_id)}),
            ),
        )


def _build_conversation_response(
    conn: psycopg.Connection,
    conversation_id: UUID,
) -> AnalystConversationResponse:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            select id, tenant_id, creating_member_id, created_at
            from analyst_conversation
            where id = %s
            """,
            (conversation_id,),
        )
        conv = cur.fetchone()
        assert conv is not None

        cur.execute(
            """
            select id, conversation_id, creating_member_id, question_text, category,
                   answer_text, calculation_version, release_posture, calculation, created_at
            from analyst_turn
            where conversation_id = %s
            order by created_at asc, id asc
            """,
            (conversation_id,),
        )
        turn_rows = cur.fetchall()

        turns = []
        for tr in turn_rows:
            cur.execute(
                """
                select id, turn_id, created_at,
                       purchase_order_id, quotation_line_id, landed_cost_id,
                       saving_record_id, supplier_scorecard_snapshot_id,
                       delivery_receipt_id, reorder_proposal_id
                from analyst_turn_citation
                where turn_id = %s
                order by id asc
                """,
                (tr["id"],),
            )
            citation_rows = cur.fetchall()
            citations = [_citation_from_row(c) for c in citation_rows]
            calc_raw = tr["calculation"]
            if calc_raw is not None:
                if isinstance(calc_raw, str):
                    calc_raw = json.loads(calc_raw)
                calculation = CalculationDetail.model_validate(calc_raw)
            else:
                calculation = None
            turns.append(
                AnalystTurnResponse(
                    id=UUID(str(tr["id"])),
                    conversation_id=UUID(str(tr["conversation_id"])),
                    creating_member_id=UUID(str(tr["creating_member_id"])),
                    question_text=str(tr["question_text"]),
                    category=AnalystCategory(str(tr["category"])),
                    answer_text=str(tr["answer_text"]),
                    calculation_version=str(tr["calculation_version"]),
                    release_posture="g3_unmet",
                    calculation=calculation,
                    citations=citations,
                    next_step_url=None,
                    created_at=tr["created_at"],
                )
            )

    return AnalystConversationResponse(
        id=UUID(str(conv["id"])),
        tenant_id=UUID(str(conv["tenant_id"])),
        creating_member_id=UUID(str(conv["creating_member_id"])),
        created_at=conv["created_at"],
        turns=turns,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_date(value: object) -> date:
    """Coerce a psycopg-returned date/str to a Python date."""
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _extract_total_risk_score(risk_score_raw: object) -> Decimal | None:
    if risk_score_raw is None:
        return None
    if isinstance(risk_score_raw, str):
        try:
            risk_score_raw = json.loads(risk_score_raw)
        except json.JSONDecodeError:
            return None
    if isinstance(risk_score_raw, dict):
        total = risk_score_raw.get("total")
        if total is not None:
            return Decimal(str(total))
    return None


def _risk_level_from_score(risk_score_raw: object) -> str | None:
    score = _extract_total_risk_score(risk_score_raw)
    if score is None:
        return None
    if score < Decimal("0.35"):
        return "low"
    if score < Decimal("0.65"):
        return "medium"
    return "high"

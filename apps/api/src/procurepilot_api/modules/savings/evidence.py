from __future__ import annotations

from uuid import UUID

from psycopg.rows import dict_row

from procurepilot_api.config import Settings, get_settings
from procurepilot_api.deps import CurrentMember
from procurepilot_api.modules.offers.service import _authenticated_db
from procurepilot_api.modules.savings.schemas import Money, SavingEvidence
from procurepilot_api.modules.savings.service import (
    _saving,
    _saving_row,
    load_purchase_for_saving,
)


class EvidenceService:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    def get_evidence(self, *, member: CurrentMember, saving_id: UUID) -> SavingEvidence:
        with _authenticated_db(self._settings, member) as conn:
            saving_row = _saving_row(conn, saving_id)
            saving = _saving(saving_row)
            purchase = load_purchase_for_saving(conn, saving.purchase_record_id)
            return SavingEvidence(
                saving_record=saving,
                purchase_record=purchase,
                quotation=_quotation(conn, purchase.quotation_line_id),
                match_decision=_match_decision(conn, purchase.match_decision_id),
                competing_offers=_competing_offers(conn, saving.workspace_product_id),
                calculation={
                    "baseline_policy": saving.baseline_policy,
                    "baseline_value": _money_dump(saving.baseline_value),
                    "actual_value": saving.actual_value.model_dump(mode="json"),
                    "delta": _money_dump(saving.delta),
                    "source_landed_cost_ids": [
                        str(item) for item in saving.baseline_source_landed_cost_ids
                    ],
                    "calculation_inputs": saving.calculation_inputs,
                },
            )


def get_evidence_service() -> EvidenceService:
    return EvidenceService()


def _money_dump(value: Money | None) -> dict[str, object] | None:
    if value is None:
        return None
    return value.model_dump(mode="json")


def _quotation(conn: object, quotation_line_id: UUID | None) -> dict[str, object] | None:
    if quotation_line_id is None:
        return None
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            select q.id as quotation_id, q.supplier_id, q.status, q.created_at,
                   ql.id as quotation_line_id, ql.line_number, ql.original_text
            from quotation_line ql
            join quotation q on q.id = ql.quotation_id
            where ql.id = %s
            """,
            (quotation_line_id,),
        )
        row = cur.fetchone()
    return None if row is None else dict(row)


def _match_decision(conn: object, match_decision_id: UUID | None) -> dict[str, object] | None:
    if match_decision_id is None:
        return None
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            select id, quotation_line_id, matched_workspace_product_id, outcome,
                   confidence, decided_by, decided_at
            from match_decision
            where id = %s
            """,
            (match_decision_id,),
        )
        row = cur.fetchone()
    return None if row is None else dict(row)


def _competing_offers(conn: object, product_id: UUID) -> list[dict[str, object]]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            select lc.id as landed_cost_id, q.supplier_id, s.name as supplier_name,
                   lc.total_amount, lc.total_currency, lc.recorded_at,
                   lc.quotation_line_id, lc.match_decision_id
            from match_decision md
            join landed_cost lc on lc.match_decision_id = md.id
            join quotation_line ql on ql.id = lc.quotation_line_id
            join quotation q on q.id = ql.quotation_id
            join supplier s on s.id = q.supplier_id
            where md.matched_workspace_product_id = %s
            order by lc.recorded_at desc, lc.id desc
            limit 25
            """,
            (product_id,),
        )
        return [dict(row) for row in cur.fetchall()]

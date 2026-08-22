from __future__ import annotations

import base64
from decimal import Decimal
from uuid import UUID

from postgrest.exceptions import APIError
from supabase import create_client

from procurepilot_api.config import Settings, get_settings
from procurepilot_api.deps import CurrentMember
from procurepilot_api.errors import ConflictError, NotFoundError, ServiceUnavailableError
from procurepilot_api.modules.landed_cost.service import LandedCostService
from procurepilot_api.modules.matching.deterministic import find_deterministic_candidate
from procurepilot_api.modules.matching.embeddings import StubEmbeddingProvider, vector_literal
from procurepilot_api.modules.matching.schemas import (
    MatchCandidate,
    MatchDecision,
    MatchTask,
    MatchTaskList,
    MatchTaskPriority,
    MatchTaskReason,
    MatchTaskStatusFilter,
    ProductSummary,
    QuotationLineMatchState,
    QuotationLineSummary,
    QuotationMatches,
)
from procurepilot_api.modules.matching.scoring import SCORING_VERSION, decimal_string
from procurepilot_api.modules.matching.search import build_similarity_candidates
from procurepilot_api.modules.members.service import authenticated_client
from procurepilot_api.modules.quotations.schemas import Money, Pack
from procurepilot_api.modules.quotations.schemas import decimal_string as quantity_string

QUOTATION_COLUMNS = "id,tenant_id,supplier_id,status"
LINE_COLUMNS = (
    "id,tenant_id,quotation_id,line_number,original_text,quantity,pack_count,unit_size,pack_unit,"
    "unit_price_amount,unit_price_currency,vat_rate,delivery_fee_amount,delivery_fee_currency,"
    "discount_amount,discount_currency"
)
PRODUCT_COLUMNS = (
    "id,tenant_id,canonical_product_id,tenant_name,preferred_supplier_id,status,created_at"
)
CANONICAL_COLUMNS = (
    "id,brand,name,variant,gtin,base_unit,canonical_embedding_model,created_at"
)
CANDIDATE_COLUMNS = (
    "id,quotation_line_id,candidate_workspace_product_id,confidence,reasons,rank,scoring_version,"
    "embedding_model,created_at"
)
TASK_COLUMNS = "id,quotation_line_id,status,priority,reason,created_at,resolved_at"
DECISION_COLUMNS = (
    "id,quotation_line_id,matched_workspace_product_id,selected_match_candidate_id,outcome,"
    "is_automatic,decided_by,decided_at,confidence,alias_id,created_at"
)
ALIAS_COLUMNS = "id,workspace_product_id,supplier_id,alias_text,created_by,created_at"


class MatchingService:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._embeddings = StubEmbeddingProvider(self._settings.matching_embedding_model)
        self._landed_cost = LandedCostService(self._settings)

    def quotation_matches(
        self,
        *,
        bearer_token: str,
        member: CurrentMember,
        quotation_id: UUID,
    ) -> QuotationMatches:
        client = authenticated_client(self._settings, bearer_token)
        quote = _quotation_row(client, quotation_id)
        if quote["status"] != "reviewed":
            raise ConflictError(details={"reason": "quotation_not_reviewed"})
        lines = _line_rows(client, quotation_id)
        if not lines:
            return QuotationMatches(quotation_id=quotation_id, lines=[])
        self._ensure_pipeline(client=client, member=member, quote=quote, lines=lines)
        return self._build_quotation_matches(client, bearer_token, quotation_id, lines)

    def list_match_tasks(
        self,
        *,
        bearer_token: str,
        cursor: str | None = None,
        limit: int = 50,
        status: MatchTaskStatusFilter | str = "open",
        priority: MatchTaskPriority | None = None,
        reason: MatchTaskReason | None = None,
        quotation_id: UUID | None = None,
    ) -> MatchTaskList:
        client = authenticated_client(self._settings, bearer_token)
        capped_limit = max(1, min(limit, 100))
        offset = _decode_cursor(cursor)
        try:
            query = client.table("match_task").select(TASK_COLUMNS)
            if status != "all":
                query = query.eq("status", status)
            if priority is not None:
                query = query.eq("priority", priority)
            if reason is not None:
                query = query.eq("reason", reason)
            if quotation_id is not None:
                line_ids = [str(row["id"]) for row in _line_rows(client, quotation_id)]
                if not line_ids:
                    return MatchTaskList(items=[], next_cursor=None)
                query = query.in_("quotation_line_id", line_ids)
            response = (
                query.order("created_at").order("id").range(offset, offset + capped_limit).execute()
            )
        except APIError as exc:
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc
        rows = _rows(response.data)
        visible = rows[:capped_limit]
        return MatchTaskList(
            items=[self._task(client, row) for row in visible],
            next_cursor=_encode_cursor(offset + capped_limit) if len(rows) > capped_limit else None,
        )

    def _ensure_pipeline(
        self,
        *,
        client: object,
        member: CurrentMember,
        quote: dict[str, object],
        lines: list[dict[str, object]],
    ) -> None:
        self._backfill_missing_embeddings(client)
        for line in lines:
            if _decision_for_line(client, UUID(str(line["id"]))) is not None:
                continue
            existing_candidates = _candidate_rows(client, UUID(str(line["id"])))
            if existing_candidates:
                self._route_or_accept(client, member, line, existing_candidates)
                continue
            deterministic = find_deterministic_candidate(
                line=line,
                products=_deterministic_products_for_line(client, line),
                aliases=_aliases_for_line(client, line),
                supplier_code_aliases=[],
            )
            if deterministic is not None:
                persisted = self._persist_candidates(
                    client,
                    member,
                    line,
                    [
                        {
                            "workspace_product_id": deterministic.workspace_product_id,
                            "confidence": deterministic.confidence,
                            "reasons": deterministic.reasons,
                        }
                    ],
                )
                self._create_automatic_decision(client, member, line, persisted[0])
                continue
            candidates = build_similarity_candidates(
                client=client,
                line=_line_summary_dict(line),
                embedding_provider=self._embeddings,
                trigram_threshold=self._settings.matching_trigram_threshold,
            )
            persisted = self._persist_candidates(
                client,
                member,
                line,
                [
                    {
                        "workspace_product_id": candidate.workspace_product_id,
                        "confidence": candidate.confidence,
                        "reasons": candidate.reasons,
                    }
                    for candidate in candidates
                ],
            )
            self._route_or_accept(client, member, line, persisted)

    def _persist_candidates(
        self,
        client: object,
        member: CurrentMember,
        line: dict[str, object],
        candidates: list[dict[str, object]],
    ) -> list[dict[str, object]]:
        persisted: list[dict[str, object]] = []
        for rank, candidate in enumerate(candidates, start=1):
            try:
                response = (
                    client.table("match_candidate")
                    .insert(
                        {
                            "tenant_id": str(member.tenant_id),
                            "quotation_line_id": str(line["id"]),
                            "candidate_workspace_product_id": str(
                                candidate["workspace_product_id"]
                            ),
                            "confidence": decimal_string(candidate["confidence"]),
                            "reasons": candidate["reasons"],
                            "rank": rank,
                            "scoring_version": SCORING_VERSION,
                            "embedding_model": self._embeddings.model,
                        }
                    )
                    .execute()
                )
            except APIError as exc:
                raise ServiceUnavailableError(details={"dependency": "database"}) from exc
            persisted.extend(_rows(response.data))
        return persisted

    def _route_or_accept(
        self,
        client: object,
        member: CurrentMember,
        line: dict[str, object],
        candidates: list[dict[str, object]],
    ) -> None:
        if not candidates:
            self._create_task(client, member, line, reason="no_candidate")
            return
        top = candidates[0]
        second = candidates[1] if len(candidates) > 1 else None
        top_confidence = Decimal(str(top["confidence"]))
        close_call = second is not None and top_confidence - Decimal(
            str(second["confidence"])
        ) < Decimal(str(self._settings.matching_review_margin))
        if (
            top_confidence >= Decimal(str(self._settings.matching_auto_accept_threshold))
            and not close_call
        ):
            self._create_automatic_decision(client, member, line, top)
            return
        self._create_task(
            client,
            member,
            line,
            reason="close_candidates" if close_call else "low_confidence",
        )

    def _create_automatic_decision(
        self,
        client: object,
        member: CurrentMember,
        line: dict[str, object],
        candidate: dict[str, object],
    ) -> dict[str, object]:
        try:
            response = (
                client.table("match_decision")
                .insert(
                    {
                        "tenant_id": str(member.tenant_id),
                        "quotation_line_id": str(line["id"]),
                        "matched_workspace_product_id": str(
                            candidate["candidate_workspace_product_id"]
                        ),
                        "selected_match_candidate_id": str(candidate["id"]),
                        "outcome": "same_product",
                        "is_automatic": True,
                        "confidence": decimal_string(candidate["confidence"]),
                    }
                )
                .execute()
            )
        except APIError as exc:
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc
        decision = _one_row(response.data, resource="match_decision")
        self._landed_cost.compute_for_line_with_client(
            client=client, member=member, line_id=UUID(str(line["id"]))
        )
        return decision

    def _create_task(
        self,
        client: object,
        member: CurrentMember,
        line: dict[str, object],
        *,
        reason: MatchTaskReason,
    ) -> None:
        existing = _open_task_for_line(client, UUID(str(line["id"])))
        if existing is not None:
            return
        try:
            client.table("match_task").insert(
                {
                    "tenant_id": str(member.tenant_id),
                    "quotation_line_id": str(line["id"]),
                    "reason": reason,
                    "priority": "normal",
                }
            ).execute()
        except APIError as exc:
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc

    def _build_quotation_matches(
        self,
        client: object,
        bearer_token: str,
        quotation_id: UUID,
        lines: list[dict[str, object]],
    ) -> QuotationMatches:
        states = []
        for line in lines:
            line_id = UUID(str(line["id"]))
            candidates = [_candidate(client, row) for row in _candidate_rows(client, line_id)]
            decision_row = _decision_for_line(client, line_id)
            task_row = _open_task_for_line(client, line_id) or _latest_task_for_line(
                client, line_id
            )
            landed_cost = None
            if decision_row is not None:
                landed_cost = self._landed_cost.get_landed_cost_or_none(
                    bearer_token=bearer_token, line_id=line_id
                )
            states.append(
                QuotationLineMatchState(
                    line=_line(line),
                    candidates=candidates,
                    task=self._task(client, task_row) if task_row else None,
                    decision=_decision(client, decision_row) if decision_row else None,
                    landed_cost=landed_cost,
                )
            )
        return QuotationMatches(quotation_id=quotation_id, lines=states)

    def _task(self, client: object, row: dict[str, object]) -> MatchTask:
        line_row = _line_row(client, UUID(str(row["quotation_line_id"])))
        decision_row = _decision_for_line(client, UUID(str(row["quotation_line_id"])))
        return MatchTask(
            id=UUID(str(row["id"])),
            quotation_id=UUID(str(line_row["quotation_id"])),
            quotation_line=_line(line_row),
            status=str(row["status"]),
            priority=str(row["priority"]),
            reason=str(row["reason"]),
            candidates=[
                _candidate(client, candidate)
                for candidate in _candidate_rows(client, UUID(str(line_row["id"])))
            ],
            decision=_decision(client, decision_row) if decision_row else None,
            created_at=row["created_at"],
            resolved_at=row.get("resolved_at"),
        )

    def _backfill_missing_embeddings(self, client: object) -> None:
        workspace_rows = _workspace_products_missing_tenant_embedding(client)
        for row in workspace_rows:
            _update_workspace_embedding(
                client=client,
                product_id=UUID(str(row["id"])),
                tenant_name=str(row["tenant_name"]),
                embedding_provider=self._embeddings,
            )
        canonical_ids = [
            UUID(str(row["canonical_product_id"]))
            for row in workspace_rows
            if row.get("canonical_product_id")
        ]
        if canonical_ids:
            service_client = self._service_role_client()
            for row in _canonical_rows_missing_embedding(service_client, canonical_ids):
                _update_canonical_embedding(
                    client=service_client,
                    canonical=row,
                    embedding_provider=self._embeddings,
                )

    def _service_role_client(self) -> object:
        return create_client(
            self._settings.supabase_url,
            self._settings.supabase_service_role_key.get_secret_value(),
        )


def get_matching_service() -> MatchingService:
    return MatchingService()


def _quotation_row(client: object, quotation_id: UUID) -> dict[str, object]:
    try:
        response = (
            client.table("quotation")
            .select(QUOTATION_COLUMNS)
            .eq("id", str(quotation_id))
            .limit(2)
            .execute()
        )
    except APIError as exc:
        raise ServiceUnavailableError(details={"dependency": "database"}) from exc
    return _one_row(response.data, resource="quotation")


def _line_rows(client: object, quotation_id: UUID) -> list[dict[str, object]]:
    try:
        response = (
            client.table("quotation_line")
            .select(LINE_COLUMNS)
            .eq("quotation_id", str(quotation_id))
            .order("line_number")
            .execute()
        )
    except APIError as exc:
        raise ServiceUnavailableError(details={"dependency": "database"}) from exc
    return _rows(response.data)


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


def _deterministic_products_for_line(
    client: object,
    line: dict[str, object],
) -> list[dict[str, object]]:
    gtin = _line_field(line, "gtin")
    if not gtin:
        return []
    try:
        canonical_rows = _rows(
            client.table("canonical_product")
            .select(CANONICAL_COLUMNS)
            .eq("gtin", gtin)
            .limit(10)
            .execute()
            .data
        )
        if not canonical_rows:
            return []
        product_rows = _rows(
            client.table("workspace_product")
            .select(PRODUCT_COLUMNS)
            .in_("canonical_product_id", [str(row["id"]) for row in canonical_rows])
            .limit(10)
            .execute()
            .data
        )
    except APIError as exc:
        raise ServiceUnavailableError(details={"dependency": "database"}) from exc
    canonical_by_id = {str(row["id"]): row for row in canonical_rows}
    return [
        {
            **product,
            "workspace_product_id": product["id"],
            "gtin": canonical_by_id[str(product["canonical_product_id"])].get("gtin"),
        }
        for product in product_rows
    ]


def _aliases_for_line(client: object, line: dict[str, object]) -> list[dict[str, object]]:
    original_text = str(line.get("original_text") or "")
    if not original_text:
        return []
    try:
        response = (
            client.table("product_alias")
            .select(ALIAS_COLUMNS)
            .ilike("alias_text", original_text)
            .limit(2)
            .execute()
        )
    except APIError as exc:
        raise ServiceUnavailableError(details={"dependency": "database"}) from exc
    return [
        row
        for row in _rows(response.data)
        if str(row["alias_text"]).casefold() == original_text.casefold()
    ]


def _line_field(line: dict[str, object], field_name: str) -> str | None:
    value = line.get(field_name)
    if value:
        return str(value)
    extracted = line.get("extracted_fields")
    if isinstance(extracted, dict) and extracted.get(field_name):
        return str(extracted[field_name])
    return None


def _workspace_products_missing_tenant_embedding(client: object) -> list[dict[str, object]]:
    try:
        response = (
            client.table("workspace_product")
            .select("id,canonical_product_id,tenant_name,tenant_name_embedding_model")
            .is_("tenant_name_embedding", "null")
            .limit(100)
            .execute()
        )
    except APIError as exc:
        raise ServiceUnavailableError(details={"dependency": "database"}) from exc
    return _rows(response.data)


def _canonical_rows_missing_embedding(
    client: object,
    canonical_ids: list[UUID],
) -> list[dict[str, object]]:
    try:
        response = (
            client.table("canonical_product")
            .select(CANONICAL_COLUMNS)
            .in_("id", [str(canonical_id) for canonical_id in canonical_ids])
            .is_("canonical_embedding", "null")
            .execute()
        )
    except APIError as exc:
        raise ServiceUnavailableError(details={"dependency": "database"}) from exc
    return _rows(response.data)


def _update_workspace_embedding(
    *,
    client: object,
    product_id: UUID,
    tenant_name: str,
    embedding_provider: StubEmbeddingProvider,
) -> None:
    try:
        client.table("workspace_product").update(
            {
                "tenant_name_embedding": vector_literal(embedding_provider.embed(tenant_name)),
                "tenant_name_embedding_model": embedding_provider.model,
            }
        ).eq("id", str(product_id)).execute()
    except APIError as exc:
        raise ServiceUnavailableError(details={"dependency": "database"}) from exc


def _update_canonical_embedding(
    *,
    client: object,
    canonical: dict[str, object],
    embedding_provider: StubEmbeddingProvider,
) -> None:
    try:
        client.table("canonical_product").update(
            {
                "canonical_embedding": vector_literal(
                    embedding_provider.embed(_canonical_embedding_text(canonical))
                ),
                "canonical_embedding_model": embedding_provider.model,
            }
        ).eq("id", str(canonical["id"])).execute()
    except APIError as exc:
        raise ServiceUnavailableError(details={"dependency": "database"}) from exc


def _canonical_embedding_text(canonical: dict[str, object]) -> str:
    return " ".join(
        str(canonical.get(key) or "") for key in ("brand", "name", "variant")
    ).strip()


def _canonical_by_id(client: object, canonical_ids: list[UUID]) -> dict[str, dict[str, object]]:
    try:
        rows = _rows(
            client.table("canonical_product")
            .select(CANONICAL_COLUMNS)
            .in_("id", [str(canonical_id) for canonical_id in canonical_ids])
            .execute()
            .data
        )
    except APIError as exc:
        raise ServiceUnavailableError(details={"dependency": "database"}) from exc
    return {str(row["id"]): row for row in rows}


def _candidate_rows(client: object, line_id: UUID) -> list[dict[str, object]]:
    try:
        return _rows(
            client.table("match_candidate")
            .select(CANDIDATE_COLUMNS)
            .eq("quotation_line_id", str(line_id))
            .order("rank")
            .execute()
            .data
        )
    except APIError as exc:
        raise ServiceUnavailableError(details={"dependency": "database"}) from exc


def _decision_for_line(client: object, line_id: UUID) -> dict[str, object] | None:
    try:
        rows = _rows(
            client.table("match_decision")
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


def _open_task_for_line(client: object, line_id: UUID) -> dict[str, object] | None:
    try:
        rows = _rows(
            client.table("match_task")
            .select(TASK_COLUMNS)
            .eq("quotation_line_id", str(line_id))
            .in_("status", ["open", "in_progress"])
            .limit(2)
            .execute()
            .data
        )
    except APIError as exc:
        raise ServiceUnavailableError(details={"dependency": "database"}) from exc
    if len(rows) > 1:
        raise ServiceUnavailableError(details={"reason": "multiple_open_match_tasks"})
    return rows[0] if rows else None


def _latest_task_for_line(client: object, line_id: UUID) -> dict[str, object] | None:
    try:
        rows = _rows(
            client.table("match_task")
            .select(TASK_COLUMNS)
            .eq("quotation_line_id", str(line_id))
            .order("created_at", desc=True)
            .limit(1)
            .execute()
            .data
        )
    except APIError as exc:
        raise ServiceUnavailableError(details={"dependency": "database"}) from exc
    return rows[0] if rows else None


def _candidate(client: object, row: dict[str, object]) -> MatchCandidate:
    return MatchCandidate(
        id=UUID(str(row["id"])),
        quotation_line_id=UUID(str(row["quotation_line_id"])),
        candidate_product=_product_summary(
            client, UUID(str(row["candidate_workspace_product_id"]))
        ),
        confidence=decimal_string(row["confidence"]),
        reasons=row["reasons"],
        rank=int(row["rank"]),
        scoring_version=str(row["scoring_version"]) if row.get("scoring_version") else None,
        embedding_model=str(row["embedding_model"]) if row.get("embedding_model") else None,
        created_at=row["created_at"],
    )


def _decision(client: object, row: dict[str, object]) -> MatchDecision:
    return MatchDecision(
        id=UUID(str(row["id"])),
        quotation_line_id=UUID(str(row["quotation_line_id"])),
        matched_product=_product_summary(client, UUID(str(row["matched_workspace_product_id"]))),
        selected_match_candidate_id=(
            UUID(str(row["selected_match_candidate_id"]))
            if row.get("selected_match_candidate_id")
            else None
        ),
        outcome=str(row["outcome"]),
        is_automatic=bool(row["is_automatic"]),
        decided_by=UUID(str(row["decided_by"])) if row.get("decided_by") else None,
        decided_at=row["decided_at"],
        confidence=decimal_string(row["confidence"]),
        alias_id=UUID(str(row["alias_id"])) if row.get("alias_id") else None,
    )


def _product_summary(client: object, product_id: UUID) -> ProductSummary:
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
    product = _one_row(response.data, resource="product")
    canonical = _canonical_by_id(client, [UUID(str(product["canonical_product_id"]))]).get(
        str(product["canonical_product_id"])
    )
    if canonical is None:
        raise ServiceUnavailableError(details={"reason": "canonical_product_not_readable"})
    return ProductSummary(
        id=UUID(str(product["id"])),
        tenant_name=str(product["tenant_name"]),
        brand=str(canonical["brand"]) if canonical.get("brand") else None,
        canonical_name=str(canonical["name"]),
        variant=str(canonical["variant"]) if canonical.get("variant") else None,
        gtin=str(canonical["gtin"]) if canonical.get("gtin") else None,
        base_unit=str(canonical["base_unit"]),
        status=str(product["status"]),
    )


def _line(row: dict[str, object]) -> QuotationLineSummary:
    pack = None
    if row.get("pack_count") is not None and row.get("unit_size") is not None:
        pack = Pack(
            pack_count=int(row["pack_count"]),
            unit_size=quantity_string(row["unit_size"]) or "",
            unit=str(row["pack_unit"]) if row.get("pack_unit") else None,
        )
    return QuotationLineSummary(
        id=UUID(str(row["id"])),
        line_number=int(row["line_number"]),
        original_text=str(row["original_text"]),
        quantity=quantity_string(row.get("quantity")),
        pack=pack,
        unit_price=_money(row, "unit_price"),
        vat_rate=quantity_string(row.get("vat_rate")),
        delivery_fee=_money(row, "delivery_fee"),
        discount=_money(row, "discount"),
    )


def _line_summary_dict(row: dict[str, object]) -> dict[str, object]:
    return _line(row).model_dump(mode="json")


def _money(row: dict[str, object], prefix: str) -> Money | None:
    amount = row.get(f"{prefix}_amount")
    currency = row.get(f"{prefix}_currency")
    if amount is None or currency is None:
        return None
    return Money(amount=quantity_string(amount, scale=4) or "0.0000", currency=str(currency))


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


def _encode_cursor(offset: int) -> str:
    return base64.urlsafe_b64encode(str(offset).encode()).decode()


def _decode_cursor(cursor: str | None) -> int:
    if cursor is None:
        return 0
    try:
        return int(base64.urlsafe_b64decode(cursor.encode()).decode())
    except (ValueError, UnicodeDecodeError) as exc:
        raise NotFoundError(details={"cursor": "invalid"}) from exc

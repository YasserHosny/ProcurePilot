from __future__ import annotations

import base64
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import PurePosixPath
from typing import Literal
from uuid import UUID

import psycopg
from postgrest.exceptions import APIError
from psycopg.rows import dict_row
from supabase import create_client

from procurepilot_api.config import Settings, get_settings
from procurepilot_api.deps import CurrentMember
from procurepilot_api.errors import ConflictError, NotFoundError, ServiceUnavailableError
from procurepilot_api.modules.landed_cost.service import LandedCostService
from procurepilot_api.modules.matching.deterministic import find_deterministic_candidate
from procurepilot_api.modules.matching.embeddings import StubEmbeddingProvider, vector_literal
from procurepilot_api.modules.matching.quoted_exposure import quoted_exposure
from procurepilot_api.modules.matching.schemas import (
    MatchCandidate,
    MatchDecision,
    MatchQueueCandidateSummary,
    MatchQueueItem,
    MatchQueueList,
    MatchTask,
    MatchTaskList,
    MatchTaskPriority,
    MatchTaskReason,
    MatchTaskStatusFilter,
    ProductSummary,
    QuotationLineMatchState,
    QuotationLineSummary,
    QuotationMatches,
    QuotationMatchSummary,
)
from procurepilot_api.modules.matching.scoring import SCORING_VERSION, decimal_string
from procurepilot_api.modules.matching.search import build_similarity_candidates
from procurepilot_api.modules.members.service import authenticated_client
from procurepilot_api.modules.offers.service import _authenticated_db
from procurepilot_api.modules.quotations.schemas import Money, Pack
from procurepilot_api.modules.quotations.schemas import decimal_string as quantity_string
from procurepilot_api.shared.audit import AuditEventCreate, get_audit_writer
from procurepilot_api.shared.logging import get_trace_id

QUOTATION_COLUMNS = (
    "id,tenant_id,document_id,supplier_id,status,issue_date,reviewed_at,reviewed_by,deleted_at"
)
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
        self._ensure_pipeline(
            client=client,
            member=member,
            quote=quote,
            lines=lines,
            bearer_token=bearer_token,
        )
        return self._build_quotation_matches(client, bearer_token, quotation_id, lines)

    def list_match_tasks(
        self,
        *,
        bearer_token: str,
        member: CurrentMember | None = None,
        cursor: str | None = None,
        limit: int = 50,
        status: MatchTaskStatusFilter | str = "open",
        priority: MatchTaskPriority | None = None,
        reason: MatchTaskReason | None = None,
        quotation_id: UUID | None = None,
        search: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        sort_by: Literal["created_at", "priority", "status"] = "created_at",
        sort_order: Literal["asc", "desc"] = "desc",
    ) -> MatchQueueList | MatchTaskList:
        if member is not None:
            return self._list_match_queue(
                member=member,
                cursor=cursor,
                limit=limit,
                status=status,
                priority=priority,
                reason=reason,
                quotation_id=quotation_id,
                search=search,
                date_from=date_from,
                date_to=date_to,
                sort_by=sort_by,
                sort_order=sort_order,
            )
        client = authenticated_client(self._settings, bearer_token)
        capped_limit = max(1, min(limit, 100))
        offset = _decode_cursor(cursor)
        clean_search = search.strip()[:200].lower() if search else None
        try:
            _sync_open_match_tasks(client)
            needs_merge = status in ("all", "auto_accepted") or clean_search is not None
            if status == "auto_accepted":
                rows = []
            else:
                query = client.table("match_task").select(TASK_COLUMNS)
                if status != "all":
                    query = query.eq("status", status)
                if priority is not None:
                    query = query.eq("priority", priority)
                if reason is not None:
                    query = query.eq("reason", reason)
                if date_from is not None:
                    query = query.gte("created_at", date_from)
                if date_to is not None:
                    query = query.lte("created_at", date_to)
                if quotation_id is not None:
                    line_ids = [str(row["id"]) for row in _line_rows(client, quotation_id)]
                    if not line_ids:
                        return MatchTaskList(items=[], next_cursor=None)
                    query = query.in_("quotation_line_id", line_ids)
                query = query.order(sort_by, desc=sort_order == "desc").order("id")
                if needs_merge:
                    response = query.execute()
                else:
                    response = query.range(offset, offset + capped_limit).execute()
                rows = _rows(response.data)
        except APIError as exc:
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc

        if clean_search:
            line_ids = list({str(row["quotation_line_id"]) for row in rows})
            context_by_line = _prefetch_search_context(client, line_ids) if line_ids else {}

            filtered_rows: list[dict[str, object]] = []
            for row in rows:
                if clean_search in str(row.get("reason", "")).lower():
                    filtered_rows.append(row)
                    continue

                line_ctx = context_by_line.get(str(row["quotation_line_id"]))
                if not line_ctx:
                    continue

                if clean_search in str(line_ctx.get("original_text", "")).lower():
                    filtered_rows.append(row)
                    continue

                if clean_search in f"#{line_ctx.get('line_number')}":
                    filtered_rows.append(row)
                    continue

                if clean_search in str(line_ctx.get("line_number")):
                    filtered_rows.append(row)
                    continue

                if clean_search in str(line_ctx.get("quotation_id", "")).lower():
                    filtered_rows.append(row)
                    continue

                if clean_search in str(line_ctx.get("supplier_name", "")).lower():
                    filtered_rows.append(row)
                    continue

            rows = filtered_rows

        # Automatic decisions are queue items only for the explicit auto status or all statuses.
        auto_tasks: list[MatchTask] = []
        if status in ("all", "auto_accepted"):
            auto_tasks = self._auto_accepted_tasks(
                client,
                quotation_id=quotation_id,
                date_from=date_from,
                date_to=date_to,
                clean_search=clean_search,
                priority=priority,
                reason=reason,
            )

        if needs_merge:
            # Build task objects for regular rows, then merge with auto tasks
            tasks_from_rows = [self._task(client, row) for row in rows]
            merged = tasks_from_rows + auto_tasks
            # Sort merged list according to requested sort
            reverse = sort_order == "desc"
            if sort_by == "created_at":
                merged.sort(key=lambda t: t.created_at, reverse=reverse)
            elif sort_by == "priority":
                order = {"high": 3, "normal": 2, "low": 1}
                merged.sort(key=lambda t: order.get(t.priority, 0), reverse=reverse)
            elif sort_by == "status":
                order = {"open": 3, "in_progress": 2, "resolved": 1}
                merged.sort(key=lambda t: order.get(t.status, 0), reverse=reverse)
            # Stable secondary sort by id for determinism
            # Paginate after merge
            start = offset
            visible = merged[start : start + capped_limit]
            has_more = len(merged) > start + capped_limit
            next_cursor = _encode_cursor(offset + capped_limit) if has_more else None
            return MatchTaskList(items=visible, next_cursor=next_cursor)

        start = offset if clean_search else 0
        visible_rows = rows[start : start + capped_limit]
        tasks = [self._task(client, row) for row in visible_rows]

        return MatchTaskList(
            items=tasks,
            next_cursor=(
                _encode_cursor(offset + capped_limit)
                if len(rows) > start + capped_limit
                else None
            ),
        )

    def _list_match_queue(
        self,
        *,
        member: CurrentMember,
        cursor: str | None,
        limit: int,
        status: MatchTaskStatusFilter | str,
        priority: MatchTaskPriority | None,
        reason: MatchTaskReason | None,
        quotation_id: UUID | None,
        search: str | None,
        date_from: str | None,
        date_to: str | None,
        sort_by: Literal["created_at", "priority", "status"],
        sort_order: Literal["asc", "desc"],
    ) -> MatchQueueList:
        offset = _decode_cursor(cursor)
        fetch_limit = min(max(limit, 1), 100) + 1
        ordering = {
            "created_at": "created_at",
            "priority": "priority_rank",
            "status": "status_rank",
        }[sort_by]
        direction = "asc" if sort_order == "asc" else "desc"
        filters = ["(%(status)s = 'all' or status = %(status)s)"]
        params: dict[str, object] = {
            "tenant_id": member.tenant_id,
            "status": status,
            "priority": priority,
            "reason": reason,
            "quotation_id": quotation_id,
            "search": search.strip() if search else None,
            "date_from": date_from,
            "date_to": date_to,
            "offset": offset,
            "limit": fetch_limit,
        }
        if priority is not None:
            filters.append("priority = %(priority)s")
        if reason is not None:
            filters.append("reason = %(reason)s")
        if quotation_id is not None:
            filters.append("quotation_id = %(quotation_id)s")
        if date_from is not None:
            filters.append("created_at >= %(date_from)s::timestamptz")
        if date_to is not None:
            filters.append("created_at <= %(date_to)s::timestamptz")
        if search and search.strip():
            filters.append(
                "(lower(original_text) like '%%' || lower(%(search)s) || '%%' "
                "or lower(reason) like '%%' || lower(%(search)s) || '%%' "
                "or lower(supplier_name) like '%%' || lower(%(search)s) || '%%' "
                "or quotation_id::text like '%%' || lower(%(search)s) || '%%' "
                "or line_number::text like '%%' || lower(%(search)s) || '%%')"
            )

        where_sql = " and ".join(filters)
        query = f"""
            with queue_items as (
                select
                    mt.id,
                    mt.tenant_id,
                    q.id as quotation_id,
                    q.status as quotation_status,
                    q.document_id,
                    q.issue_date,
                    q.reviewed_at,
                    q.reviewed_by,
                    reviewer.email as reviewed_by_email,
                    d.storage_path,
                    q.supplier_id,
                    supplier.name as supplier_name,
                    ql.id as quotation_line_id,
                    ql.line_number,
                    ql.original_text,
                    ql.quantity,
                    ql.pack_count,
                    ql.unit_size,
                    ql.pack_unit,
                    ql.unit_price_amount,
                    ql.unit_price_currency,
                    ql.vat_rate,
                    ql.delivery_fee_amount,
                    ql.delivery_fee_currency,
                    ql.discount_amount,
                    ql.discount_currency,
                    mt.status::text as status,
                    mt.priority::text as priority,
                    mt.reason::text as reason,
                    mt.created_at,
                    mt.resolved_at,
                    top_candidate.product_name as top_candidate_name,
                    top_candidate.confidence as top_candidate_confidence
                from match_task mt
                join quotation_line ql
                  on ql.tenant_id = mt.tenant_id and ql.id = mt.quotation_line_id
                join quotation q on q.tenant_id = mt.tenant_id and q.id = ql.quotation_id
                left join document d on d.tenant_id = mt.tenant_id and d.id = q.document_id
                left join supplier
                  on supplier.tenant_id = mt.tenant_id and supplier.id = q.supplier_id
                left join membership reviewer
                  on reviewer.tenant_id = mt.tenant_id and reviewer.id = q.reviewed_by
                left join lateral (
                    select wp.tenant_name as product_name, mc.confidence
                    from match_candidate mc
                    join workspace_product wp
                      on wp.tenant_id = mc.tenant_id
                     and wp.id = mc.candidate_workspace_product_id
                    where mc.tenant_id = mt.tenant_id
                      and mc.quotation_line_id = mt.quotation_line_id
                    order by mc.rank
                    limit 1
                ) top_candidate on true
                where mt.tenant_id = %(tenant_id)s

                union all

                select
                    md.id,
                    md.tenant_id,
                    q.id as quotation_id,
                    q.status as quotation_status,
                    q.document_id,
                    q.issue_date,
                    q.reviewed_at,
                    q.reviewed_by,
                    reviewer.email as reviewed_by_email,
                    d.storage_path,
                    q.supplier_id,
                    supplier.name as supplier_name,
                    ql.id as quotation_line_id,
                    ql.line_number,
                    ql.original_text,
                    ql.quantity,
                    ql.pack_count,
                    ql.unit_size,
                    ql.pack_unit,
                    ql.unit_price_amount,
                    ql.unit_price_currency,
                    ql.vat_rate,
                    ql.delivery_fee_amount,
                    ql.delivery_fee_currency,
                    ql.discount_amount,
                    ql.discount_currency,
                    'auto_accepted'::text as status,
                    'normal'::text as priority,
                    'auto_accepted'::text as reason,
                    coalesce(md.decided_at, md.created_at) as created_at,
                    coalesce(md.decided_at, md.created_at) as resolved_at,
                    top_candidate.product_name as top_candidate_name,
                    coalesce(top_candidate.confidence, md.confidence) as top_candidate_confidence
                from match_decision md
                join quotation_line ql
                  on ql.tenant_id = md.tenant_id and ql.id = md.quotation_line_id
                join quotation q on q.tenant_id = md.tenant_id and q.id = ql.quotation_id
                left join document d on d.tenant_id = md.tenant_id and d.id = q.document_id
                left join supplier
                  on supplier.tenant_id = md.tenant_id and supplier.id = q.supplier_id
                left join membership reviewer
                  on reviewer.tenant_id = md.tenant_id and reviewer.id = q.reviewed_by
                left join lateral (
                    select wp.tenant_name as product_name, mc.confidence
                    from match_candidate mc
                    join workspace_product wp
                      on wp.tenant_id = mc.tenant_id
                     and wp.id = mc.candidate_workspace_product_id
                    where mc.tenant_id = md.tenant_id
                      and mc.quotation_line_id = md.quotation_line_id
                    order by (mc.id = md.selected_match_candidate_id) desc, mc.rank
                    limit 1
                ) top_candidate on true
                where md.tenant_id = %(tenant_id)s and md.is_automatic = true
            )
            select *,
                   case priority
                     when 'high' then 3 when 'normal' then 2 else 1
                   end as priority_rank,
                   case status
                     when 'open' then 4 when 'in_progress' then 3
                     when 'resolved' then 2 else 1
                   end as status_rank,
                   (select count(*)
                    from match_task mto
                    join quotation_line qlo
                      on qlo.tenant_id = mto.tenant_id and qlo.id = mto.quotation_line_id
                    where mto.tenant_id = queue_items.tenant_id
                      and qlo.quotation_id = queue_items.quotation_id
                      and mto.status in ('open', 'in_progress')
                   ) as quotation_open_task_count,
                   (select count(*)
                    from quotation_line qlc
                    where qlc.tenant_id = queue_items.tenant_id
                      and qlc.quotation_id = queue_items.quotation_id
                   ) as quotation_total_line_count
            from queue_items
            where {where_sql}
            order by {ordering} {direction}, id {direction}
            offset %(offset)s limit %(limit)s
        """

        try:
            with _authenticated_db(self._settings, member) as conn:
                with conn.cursor(row_factory=dict_row) as cur:
                    cur.execute(query, params)
                    rows = [dict(row) for row in cur.fetchall()]
        except psycopg.Error as exc:
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc

        has_more = len(rows) > fetch_limit - 1
        page_rows = rows[: fetch_limit - 1]
        return MatchQueueList(
            items=[_queue_item(row) for row in page_rows],
            next_cursor=_encode_cursor(offset + fetch_limit - 1) if has_more else None,
        )

    def match_task_for_line(self, *, bearer_token: str, line_id: UUID) -> MatchTask:
        client = authenticated_client(self._settings, bearer_token)
        line = _line_row(client, line_id)
        task = _latest_task_for_line(client, line_id)
        if task is None:
            decision = _decision_for_line(client, line_id)
            if decision and bool(decision.get("is_automatic")):
                decided_at = decision.get("decided_at") or decision.get("created_at")
                synthetic_row: dict[str, object] = {
                    "id": decision["id"],
                    "quotation_line_id": decision["quotation_line_id"],
                    "status": "auto_accepted",
                    "priority": "normal",
                    "reason": "auto_accepted",
                    "created_at": decided_at,
                    "resolved_at": decided_at,
                }
                return self._task(client, synthetic_row, line_row=line)
            raise NotFoundError(details={"resource": "match_task"})
        return self._task(client, task, line_row=line)

    def _ensure_pipeline(
        self,
        *,
        client: object,
        member: CurrentMember,
        quote: dict[str, object],
        lines: list[dict[str, object]],
        bearer_token: str | None = None,
    ) -> None:
        self._backfill_missing_embeddings(client)
        for line in lines:
            if _decision_for_line(client, UUID(str(line["id"]))) is not None:
                continue
            existing_candidates = _candidate_rows(client, UUID(str(line["id"])))
            if existing_candidates:
                self._route_or_accept(
                    client, member, line, existing_candidates, bearer_token=bearer_token
                )
                continue
            deterministic = find_deterministic_candidate(
                line=line,
                products=_deterministic_products_for_line(client, line),
                aliases=_aliases_for_line(client, line),
                supplier_code_aliases=_supplier_code_aliases_for_line(client, line),
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
                self._create_automatic_decision(
                    client, member, line, persisted[0], bearer_token=bearer_token
                )
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
            self._route_or_accept(
                client, member, line, persisted, bearer_token=bearer_token
            )

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
        *,
        bearer_token: str | None = None,
    ) -> None:
        if not candidates:
            self._create_task(
                client, member, line, reason="no_candidate", bearer_token=bearer_token
            )
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
            self._create_automatic_decision(
                client, member, line, top, bearer_token=bearer_token
            )
            return
        self._create_task(
            client,
            member,
            line,
            reason="close_candidates" if close_call else "low_confidence",
            bearer_token=bearer_token,
            candidate=top,
        )

    def _create_automatic_decision(
        self,
        client: object,
        member: CurrentMember,
        line: dict[str, object],
        candidate: dict[str, object],
        *,
        bearer_token: str | None = None,
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
        if bearer_token is not None:
            self._record(
                bearer_token=bearer_token,
                member=member,
                action="matching.auto_accepted",
                target={
                    "quotation_id": str(line["quotation_id"]),
                    "quotation_line_id": str(line["id"]),
                    "decision_id": str(decision["id"]),
                    "candidate_id": str(candidate["id"]),
                    "matched_product_id": str(
                        candidate["candidate_workspace_product_id"]
                    ),
                    "outcome": "same_product",
                    "score": decimal_string(candidate["confidence"]),
                    "threshold": decimal_string(
                        self._settings.matching_auto_accept_threshold
                    ),
                    "scoring_version": candidate.get("scoring_version") or SCORING_VERSION,
                },
            )
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
        bearer_token: str | None = None,
        candidate: dict[str, object] | None = None,
    ) -> None:
        existing = _open_task_for_line(client, UUID(str(line["id"])))
        if existing is not None:
            return
        try:
            response = client.table("match_task").insert(
                {
                    "tenant_id": str(member.tenant_id),
                    "quotation_line_id": str(line["id"]),
                    "reason": reason,
                    "priority": "normal",
                }
            ).execute()
        except APIError as exc:
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc
        task = _one_row(response.data, resource="match_task")
        if bearer_token is not None:
            target: dict[str, object] = {
                "quotation_id": str(line["quotation_id"]),
                "quotation_line_id": str(line["id"]),
                "match_task_id": str(task["id"]),
                "reason": reason,
                "priority": str(task.get("priority") or "normal"),
            }
            if candidate is not None:
                target.update(
                    {
                        "candidate_id": str(candidate["id"]),
                        "score": decimal_string(candidate["confidence"]),
                        "threshold": decimal_string(
                            self._settings.matching_auto_accept_threshold
                        ),
                        "scoring_version": candidate.get("scoring_version")
                        or SCORING_VERSION,
                    }
                )
            self._record(
                bearer_token=bearer_token,
                member=member,
                action="matching.task_routed",
                target=target,
            )

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

    def _auto_accepted_tasks(
        self,
        client: object,
        *,
        quotation_id: UUID | None,
        date_from: str | None,
        date_to: str | None,
        clean_search: str | None,
        priority: MatchTaskPriority | None,
        reason: MatchTaskReason | None,
    ) -> list[MatchTask]:
        if (priority is not None and priority != "normal") or (
            reason is not None and reason != "auto_accepted"
        ):
            return []
        try:
            query = client.table("match_decision").select(DECISION_COLUMNS).eq("is_automatic", True)
            if date_from is not None:
                query = query.gte("decided_at", date_from)
            if date_to is not None:
                query = query.lte("decided_at", date_to)
            if quotation_id is not None:
                line_ids = [str(row["id"]) for row in _line_rows(client, quotation_id)]
                if not line_ids:
                    return []
                query = query.in_("quotation_line_id", line_ids)
            response = query.execute()
        except APIError as exc:
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc
        decision_rows = _rows(response.data)
        if clean_search:
            line_ids = list({str(row["quotation_line_id"]) for row in decision_rows})
            context_by_line = _prefetch_search_context(client, line_ids) if line_ids else {}
            filtered: list[dict[str, object]] = []
            for row in decision_rows:
                line_ctx = context_by_line.get(str(row["quotation_line_id"]))
                if not line_ctx:
                    continue
                if clean_search in str(line_ctx.get("original_text", "")).lower():
                    filtered.append(row)
                    continue
                if clean_search in f"#{line_ctx.get('line_number')}":
                    filtered.append(row)
                    continue
                if clean_search in str(line_ctx.get("line_number")):
                    filtered.append(row)
                    continue
                if clean_search in str(line_ctx.get("quotation_id", "")).lower():
                    filtered.append(row)
                    continue
                if clean_search in str(line_ctx.get("supplier_name", "")).lower():
                    filtered.append(row)
                    continue
            decision_rows = filtered

        auto_tasks: list[MatchTask] = []
        for dec in decision_rows:
            try:
                line = _line_row(client, UUID(str(dec["quotation_line_id"])))
            except NotFoundError:
                continue
            decided_at = dec.get("decided_at") or dec.get("created_at")
            synthetic_row: dict[str, object] = {
                "id": dec["id"],
                "quotation_line_id": dec["quotation_line_id"],
                "status": "auto_accepted",
                "priority": "normal",
                "reason": "auto_accepted",
                "created_at": decided_at,
                "resolved_at": decided_at,
            }
            try:
                task = self._task(client, synthetic_row, line_row=line)
            except (NotFoundError, ServiceUnavailableError):
                continue
            auto_tasks.append(task)
        return auto_tasks

    def _task(
        self,
        client: object,
        row: dict[str, object],
        *,
        line_row: dict[str, object] | None = None,
    ) -> MatchTask:
        line_row = line_row or _line_row(client, UUID(str(row["quotation_line_id"])))
        decision_row = _decision_for_line(client, UUID(str(row["quotation_line_id"])))
        quotation_id = UUID(str(line_row["quotation_id"]))
        quote = _quotation_row(client, quotation_id)
        supplier_name = (
            _supplier_name(client, UUID(str(quote["supplier_id"]))) or None
            if quote.get("supplier_id")
            else None
        )
        quotation_lines = _line_rows(client, quotation_id)
        document_id = UUID(str(quote["document_id"])) if quote.get("document_id") else None
        source_filename = _source_filename(client, document_id) if document_id else None
        reviewer_email = (
            _membership_email(client, UUID(str(quote["reviewed_by"])))
            if quote.get("reviewed_by")
            else None
        )
        quotation = QuotationMatchSummary(
            id=quotation_id,
            status=str(quote["status"]),
            document_id=document_id,
            source_filename=source_filename,
            supplier_id=UUID(str(quote["supplier_id"])) if quote.get("supplier_id") else None,
            issue_date=quote.get("issue_date"),
            reviewed_at=quote.get("reviewed_at"),
            reviewed_by=(
                UUID(str(quote["reviewed_by"])) if quote.get("reviewed_by") else None
            ),
            reviewed_by_email=reviewer_email,
            line_count=len(quotation_lines),
            open_match_task_count=_open_task_count(
                client, [UUID(str(line["id"])) for line in quotation_lines]
            ),
            supplier_name=supplier_name,
        )
        return MatchTask(
            id=UUID(str(row["id"])),
            quotation_id=quotation_id,
            quotation=quotation,
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
            supplier_name=supplier_name,
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

    def _record(
        self,
        *,
        bearer_token: str,
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


def _supplier_name(client: object, supplier_id: UUID) -> str:
    try:
        response = (
            client.table("supplier")
            .select("name")
            .eq("id", str(supplier_id))
            .limit(1)
            .execute()
        )
    except APIError as exc:
        raise ServiceUnavailableError(details={"dependency": "database"}) from exc
    rows = _rows(response.data)
    return str(rows[0]["name"]) if rows else ""


def _source_filename(client: object, document_id: UUID) -> str | None:
    try:
        response = (
            client.table("document")
            .select("id,storage_path")
            .eq("id", str(document_id))
            .limit(1)
            .execute()
        )
    except APIError as exc:
        raise ServiceUnavailableError(details={"dependency": "database"}) from exc
    rows = _rows(response.data)
    if not rows or not rows[0].get("storage_path"):
        return None
    return PurePosixPath(str(rows[0]["storage_path"])).name


def _membership_email(client: object, membership_id: UUID) -> str | None:
    try:
        response = (
            client.table("membership")
            .select("email")
            .eq("id", str(membership_id))
            .limit(1)
            .execute()
        )
    except APIError:
        return None
    rows = _rows(response.data)
    return str(rows[0]["email"]) if rows and rows[0].get("email") else None


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
    return _with_line_extracted_fields(client, _rows(response.data))


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
    return _with_line_extracted_fields(
        client, [_one_row(response.data, resource="quotation_line")]
    )[0]


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


def _supplier_code_aliases_for_line(
    client: object,
    line: dict[str, object],
) -> list[dict[str, object]]:
    supplier_code = _line_field(line, "supplier_product_code")
    if not supplier_code:
        return []
    supplier_id = _quotation_supplier_id(client, UUID(str(line["quotation_id"])))
    try:
        response = (
            client.table("product_alias")
            .select(ALIAS_COLUMNS)
            .ilike("alias_text", supplier_code)
            .limit(10)
            .execute()
        )
    except APIError as exc:
        raise ServiceUnavailableError(details={"dependency": "database"}) from exc
    rows = [
        row
        for row in _rows(response.data)
        if str(row["alias_text"]).casefold() == supplier_code.casefold()
    ]
    if supplier_id is None:
        return rows
    return [
        row
        for row in rows
        if row.get("supplier_id") is None
        or str(row["supplier_id"]) == str(supplier_id)
    ]


def _with_line_extracted_fields(
    client: object,
    lines: list[dict[str, object]],
) -> list[dict[str, object]]:
    if not lines:
        return lines
    line_ids = [UUID(str(line["id"])) for line in lines]
    try:
        response = (
            client.table("field_extraction")
            .select("entity_id,field_name,extracted_value,confidence")
            .eq("entity_type", "quotation_line")
            .in_("entity_id", [str(line_id) for line_id in line_ids])
            .execute()
        )
    except APIError as exc:
        raise ServiceUnavailableError(details={"dependency": "database"}) from exc
    extracted_by_line: dict[str, dict[str, object]] = {str(line_id): {} for line_id in line_ids}
    confidence_by_field: dict[tuple[str, str], Decimal] = {}
    for field in _rows(response.data):
        entity_id = str(field.get("entity_id") or "")
        field_name = str(field.get("field_name") or "")
        if not entity_id or not field_name or entity_id not in extracted_by_line:
            continue
        key = (entity_id, field_name)
        confidence = _decimal_or_zero(field.get("confidence"))
        if key in confidence_by_field and confidence < confidence_by_field[key]:
            continue
        confidence_by_field[key] = confidence
        extracted_by_line[entity_id][field_name] = field.get("extracted_value")
    return [
        {
            **line,
            "extracted_fields": extracted_by_line.get(str(line["id"]), {}),
        }
        for line in lines
    ]


def _line_field(line: dict[str, object], field_name: str) -> str | None:
    value = line.get(field_name)
    if value:
        return str(value)
    extracted = line.get("extracted_fields")
    if isinstance(extracted, dict) and extracted.get(field_name):
        return str(extracted[field_name])
    return None


def _quotation_supplier_id(client: object, quotation_id: UUID) -> UUID | None:
    quote = _quotation_row(client, quotation_id)
    return UUID(str(quote["supplier_id"])) if quote.get("supplier_id") else None


def _decimal_or_zero(value: object) -> Decimal:
    if value is None:
        return Decimal("0")
    return Decimal(str(value))


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


def _sync_open_match_tasks(client: object) -> None:
    open_tasks = _rows(
        client.table("match_task")
        .select(TASK_COLUMNS)
        .in_("status", ["open", "in_progress"])
        .execute()
        .data
    )
    for task in open_tasks:
        line = _line_row(client, UUID(str(task["quotation_line_id"])))
        quote = _quotation_row(client, UUID(str(line["quotation_id"])))
        if (
            quote.get("deleted_at") is None
            and quote.get("status") == "reviewed"
            and _decision_for_line(client, UUID(str(line["id"]))) is None
        ):
            continue
        client.table("match_task").update(
            {"status": "resolved", "resolved_at": datetime.now(UTC).isoformat()}
        ).eq("id", str(task["id"])).execute()


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


def _open_task_count(client: object, line_ids: list[UUID]) -> int:
    if not line_ids:
        return 0
    try:
        response = (
            client.table("match_task")
            .select("id")
            .in_("quotation_line_id", [str(line_id) for line_id in line_ids])
            .in_("status", ["open", "in_progress"])
            .execute()
        )
    except APIError as exc:
        raise ServiceUnavailableError(details={"dependency": "database"}) from exc
    return len(_rows(response.data))


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
    quantity = quantity_string(row.get("quantity"))
    unit_price = _money(row, "unit_price")
    vat_rate = quantity_string(row.get("vat_rate"))
    delivery_fee = _money(row, "delivery_fee")
    discount = _money(row, "discount")
    exposure = quoted_exposure(
        quantity=quantity,
        unit_price=unit_price,
        vat_rate=vat_rate,
        delivery_fee=delivery_fee,
        discount=discount,
    )
    return QuotationLineSummary(
        id=UUID(str(row["id"])),
        line_number=int(row["line_number"]),
        original_text=str(row["original_text"]),
        quantity=quantity,
        pack=pack,
        unit_price=unit_price,
        vat_rate=vat_rate,
        delivery_fee=delivery_fee,
        discount=discount,
        quoted_line_total=exposure.total,
        quoted_line_total_issue=exposure.issue,
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

def _prefetch_search_context(client: object, line_ids: list[str]) -> dict[str, dict[str, object]]:
    context: dict[str, dict[str, object]] = {}
    for i in range(0, len(line_ids), 100):
        chunk = line_ids[i : i + 100]
        try:
            resp = (
                client.table("quotation_line")
                .select("id, original_text, line_number, quotation_id, quotation(id, supplier_id)")
                .in_("id", chunk)
                .execute()
            )
            for r in _rows(resp.data):
                context[str(r["id"])] = r
        except APIError as exc:
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc

    supplier_ids = list(
        {
            str(c["quotation"].get("supplier_id"))
            for c in context.values()
            if isinstance(c.get("quotation"), dict) and c["quotation"].get("supplier_id")
        }
    )

    suppliers_by_id: dict[str, str] = {}
    for i in range(0, len(supplier_ids), 100):
        chunk = supplier_ids[i : i + 100]
        try:
            resp = (
                client.table("supplier")
                .select("id, name")
                .in_("id", chunk)
                .execute()
            )
            for r in _rows(resp.data):
                suppliers_by_id[str(r["id"])] = str(r.get("name") or "")
        except APIError as exc:
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc

    for c in context.values():
        if isinstance(c.get("quotation"), dict):
            sid = c["quotation"].get("supplier_id")
            c["supplier_name"] = suppliers_by_id.get(str(sid), "") if sid else ""
        else:
            c["supplier_name"] = ""

    return context


def _queue_item(row: dict[str, object]) -> MatchQueueItem:
    line = {
        "id": row["quotation_line_id"],
        "line_number": row["line_number"],
        "original_text": row["original_text"],
        "quantity": row.get("quantity"),
        "pack_count": row.get("pack_count"),
        "unit_size": row.get("unit_size"),
        "pack_unit": row.get("pack_unit"),
        "unit_price_amount": row.get("unit_price_amount"),
        "unit_price_currency": row.get("unit_price_currency"),
        "vat_rate": row.get("vat_rate"),
        "delivery_fee_amount": row.get("delivery_fee_amount"),
        "delivery_fee_currency": row.get("delivery_fee_currency"),
        "discount_amount": row.get("discount_amount"),
        "discount_currency": row.get("discount_currency"),
    }
    quotation = QuotationMatchSummary(
        id=UUID(str(row["quotation_id"])),
        status=str(row["quotation_status"]),
        document_id=UUID(str(row["document_id"])) if row.get("document_id") else None,
        source_filename=(
            PurePosixPath(str(row["storage_path"])).name if row.get("storage_path") else None
        ),
        supplier_id=UUID(str(row["supplier_id"])) if row.get("supplier_id") else None,
        issue_date=row.get("issue_date"),
        reviewed_at=row.get("reviewed_at"),
        reviewed_by=UUID(str(row["reviewed_by"])) if row.get("reviewed_by") else None,
        reviewed_by_email=row.get("reviewed_by_email"),
        line_count=int(row.get("quotation_total_line_count") or 0),
        open_match_task_count=int(row.get("quotation_open_task_count") or 0),
        supplier_name=row.get("supplier_name"),
    )
    top_candidate = (
        MatchQueueCandidateSummary(
            product_name=str(row["top_candidate_name"]),
            confidence=decimal_string(row["top_candidate_confidence"]),
        )
        if row.get("top_candidate_name")
        else None
    )
    return MatchQueueItem(
        id=UUID(str(row["id"])),
        quotation_id=UUID(str(row["quotation_id"])),
        quotation=quotation,
        quotation_line=_line(line),
        status=str(row["status"]),
        priority=str(row["priority"]),
        reason=str(row["reason"]),
        top_candidate=top_candidate,
        created_at=row["created_at"],
        resolved_at=row.get("resolved_at"),
        supplier_name=row.get("supplier_name"),
    )

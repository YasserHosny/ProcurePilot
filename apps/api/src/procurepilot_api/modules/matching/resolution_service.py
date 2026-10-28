from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import Lock
from uuid import UUID, uuid5

import psycopg
from postgrest.exceptions import APIError
from psycopg.rows import dict_row

from procurepilot_api.config import Settings, get_settings
from procurepilot_api.deps import CurrentMember
from procurepilot_api.errors import ConflictError, NotFoundError, ServiceUnavailableError
from procurepilot_api.modules.catalogue.service import CatalogueService
from procurepilot_api.modules.ingestion.guardrail_jobs import enqueue_guardrail_evaluation
from procurepilot_api.modules.landed_cost.service import LandedCostService
from procurepilot_api.modules.matching.alias_service import AliasLearningService
from procurepilot_api.modules.matching.exact import is_exact_name_match
from procurepilot_api.modules.matching.schemas import (
    BulkConfirmResult,
    ExactMatchSummary,
    MatchCorrectionRequest,
    MatchCorrectionResponse,
    MatchDecision,
    MatchResolutionRequest,
)
from procurepilot_api.modules.matching.scoring import decimal_string
from procurepilot_api.modules.matching.service import (
    CANONICAL_COLUMNS,
    DECISION_COLUMNS,
    LINE_COLUMNS,
    PRODUCT_COLUMNS,
    _candidate,
    _decision,
    _decision_for_line,
    _line_row,
)
from procurepilot_api.modules.members.service import authenticated_client
from procurepilot_api.modules.offers.service import _authenticated_db
from procurepilot_api.shared.audit import AuditEventCreate, get_audit_writer
from procurepilot_api.shared.logging import get_trace_id

EXACT_CONFIRM_WORKERS = 12  # overlap hosted RTT; never more than twelve in-flight lines
EXACT_CONFIRM_BATCH = 100  # exact pairs returned per call
EXACT_SCAN_LIMIT = 1000  # open tasks examined while collecting them
EXACT_LOOKUP_CHUNK = 100  # lines per batched read (keeps PostgREST URLs short)


class MatchResolutionService:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._catalogue = CatalogueService(self._settings)
        self._aliases = AliasLearningService()
        self._landed_cost = LandedCostService(self._settings)

    def resolve(
        self,
        *,
        bearer_token: str,
        member: CurrentMember,
        line_id: UUID,
        payload: MatchResolutionRequest,
        idempotency_key: UUID | None = None,
    ) -> MatchDecision:
        client = authenticated_client(self._settings, bearer_token)
        return self._resolve_with_client(
            client=client,
            bearer_token=bearer_token,
            member=member,
            line_id=line_id,
            payload=payload,
            idempotency_key=idempotency_key,
        )

    def _resolve_with_client(
        self,
        *,
        client: object,
        bearer_token: str,
        member: CurrentMember,
        line_id: UUID,
        payload: MatchResolutionRequest,
        idempotency_key: UUID | None,
        defer_guardrail: Callable[[UUID], None] | None = None,
    ) -> MatchDecision:
        """The same resolution pipeline for single requests and isolated bulk workers."""
        fingerprint = _request_fingerprint(payload)
        if idempotency_key is not None:
            existing_request = _idempotency_record_for_key(
                client, member.tenant_id, idempotency_key
            )
            if existing_request is not None:
                if (
                    str(existing_request["quotation_line_id"]) != str(line_id)
                    or str(existing_request["request_fingerprint"]) != fingerprint
                ):
                    raise ConflictError(details={"reason": "idempotency_key_reused"})
                return _decision(
                    client,
                    _decision_by_id(client, UUID(str(existing_request["match_decision_id"]))),
                )
        line = _line_row(client, line_id)
        existing_decision = _decision_for_line(client, line_id)
        if existing_decision is not None:
            if idempotency_key is not None and _decision_matches_payload(
                existing_decision, payload
            ):
                decision = _decision(client, existing_decision)
                self._complete_resolution_side_effects(
                    client=client,
                    bearer_token=bearer_token,
                    member=member,
                    line=line,
                    line_id=line_id,
                    decision=decision,
                    idempotency_key=idempotency_key,
                    request_fingerprint=fingerprint,
                    repair_existing_decision=True,
                )
                return decision
            raise ConflictError(details={"reason": "line_already_matched"})
        if payload.outcome == "no_match_new_product":
            if payload.create_product is None:
                raise ConflictError(details={"reason": "create_product_required"})
            product, _created = self._catalogue.create_product(
                bearer_token=bearer_token, member=member, payload=payload.create_product
            )
            candidate_id = None
            product_id = product.id
            confidence = "1.0000"
        else:
            if payload.selected_match_candidate_id is None:
                raise ConflictError(details={"reason": "candidate_required"})
            candidate_row = self._candidate_row(
                client, payload.selected_match_candidate_id, line_id
            )
            _candidate(client, candidate_row)
            candidate_id = payload.selected_match_candidate_id
            product_id = UUID(str(candidate_row["candidate_workspace_product_id"]))
            confidence = decimal_string(candidate_row["confidence"])
        alias_id = self._aliases.learn_or_reuse_alias(
            client=client,
            tenant_id=member.tenant_id,
            membership_id=member.membership_id,
            workspace_product_id=product_id,
            supplier_id=self._quotation_supplier_id(client, UUID(str(line["quotation_id"]))),
            alias_text=str(line["original_text"]),
        )
        try:
            response = (
                client.table("match_decision")
                .insert(
                    {
                        "tenant_id": str(member.tenant_id),
                        "quotation_line_id": str(line_id),
                        "matched_workspace_product_id": str(product_id),
                        "selected_match_candidate_id": str(candidate_id) if candidate_id else None,
                        "outcome": payload.outcome,
                        "is_automatic": False,
                        "decided_by": str(member.membership_id),
                        "confidence": confidence,
                        "alias_id": str(alias_id),
                    }
                )
                .execute()
            )
        except APIError as exc:
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc
        decision = _decision(client, _one_row(response.data, resource="match_decision"))
        quotation_id = UUID(str(line["quotation_id"]))
        if defer_guardrail is None:
            enqueue_guardrail_evaluation(
                self._settings, tenant_id=member.tenant_id, quotation_id=quotation_id
            )
        else:
            defer_guardrail(quotation_id)
        self._complete_resolution_side_effects(
            client=client,
            bearer_token=bearer_token,
            member=member,
            line=line,
            line_id=line_id,
            decision=decision,
            idempotency_key=idempotency_key,
            request_fingerprint=fingerprint,
            repair_existing_decision=False,
        )
        return decision

    def correct(
        self,
        *,
        bearer_token: str,
        member: CurrentMember,
        line_id: UUID,
        payload: MatchCorrectionRequest,
        idempotency_key: UUID,
    ) -> MatchCorrectionResponse:
        client = authenticated_client(self._settings, bearer_token)
        fingerprint = _request_fingerprint(payload)
        # Transaction-scoped advisory locks work across API processes and pooler connections.
        # The head and its replay mapping must commit together on the member/RLS connection.
        # An explicit transaction also rolls both back when this connection is shared.
        with _authenticated_db(self._settings, member) as conn, conn.transaction():
            with conn.cursor() as cur:
                for scope in (
                    f"correction-key:{member.tenant_id}:{idempotency_key}",
                    f"correction-line:{member.tenant_id}:{line_id}",
                ):
                    cur.execute("select pg_advisory_xact_lock(hashtextextended(%s, 0))", (scope,))
                line = _line_row(client, line_id)
                existing = _idempotency_record_for_key(client, member.tenant_id, idempotency_key)
                if existing is not None:
                    if (
                        str(existing["quotation_line_id"]) != str(line_id)
                        or existing["request_fingerprint"] != fingerprint
                    ):
                        raise ConflictError(details={"reason": "idempotency_key_reused"})
                    decision = _decision_by_id(client, UUID(str(existing["match_decision_id"])))
                else:
                    head = _decision_for_line(client, line_id)
                    if head is None:
                        raise ConflictError(details={"reason": "no_decision"})
                    if str(head["id"]) != str(payload.expected_current_decision_id):
                        raise ConflictError(details={"reason": "decision_changed"})
                    # Tenant-pinned definer (20261029070000): a branch-assigned buyer cannot see
                    # other branches' requests, but a request priced from this match still locks it.
                    cur.execute(
                        "select match_decision_live_request(%s)",
                        (payload.expected_current_decision_id,),
                    )
                    request = cur.fetchone()
                    if request is not None and request[0] is not None:
                        raise ConflictError(
                            details={
                                "reason": "line_on_purchase_request",
                                "purchase_request_id": str(request[0]),
                            }
                        )
                    if payload.outcome == "no_match_new_product":
                        # The boundary validator guarantees new_product for this outcome.
                        product, _created = self._catalogue.create_product(
                            bearer_token=bearer_token, member=member, payload=payload.new_product
                        )
                        product_id, candidate_id, confidence = product.id, None, "1.0000"
                    else:
                        row = self._candidate_row(
                            client, payload.selected_match_candidate_id, line_id
                        )
                        _candidate(client, row)
                        product_id = UUID(str(row["candidate_workspace_product_id"]))
                        candidate_id = payload.selected_match_candidate_id
                        confidence = decimal_string(row["confidence"])
                    alias_id = None
                    if payload.learn_alias:
                        try:
                            alias_id = self._aliases.learn_or_reuse_alias(
                                client=client,
                                tenant_id=member.tenant_id,
                                membership_id=member.membership_id,
                                workspace_product_id=product_id,
                                supplier_id=self._quotation_supplier_id(
                                    client, UUID(str(line["quotation_id"]))
                                ),
                                alias_text=str(line["original_text"]),
                            )
                        except ConflictError as exc:
                            if exc.details is None or exc.details.get("reason") != "alias_conflict":
                                raise
                            # Aliases are evidence too: never rewrite an old human's wording.
                    try:
                        with conn.cursor(row_factory=dict_row) as decision_cur:
                            decision_cur.execute(
                                "insert into match_decision (tenant_id,quotation_line_id,"
                                "matched_workspace_product_id,selected_match_candidate_id,outcome,"
                                "is_automatic,decided_by,confidence,alias_id,"
                                "supersedes_decision_id) "
                                "values (%s,%s,%s,%s,%s,false,%s,%s,%s,%s) returning *",
                                (
                                    member.tenant_id,
                                    line_id,
                                    product_id,
                                    candidate_id,
                                    payload.outcome,
                                    member.membership_id,
                                    confidence,
                                    alias_id,
                                    payload.expected_current_decision_id,
                                ),
                            )
                            decision = dict(decision_cur.fetchone())
                        cur.execute(
                            "insert into match_resolution_idempotency "
                            "(tenant_id,idempotency_key,quotation_line_id,request_fingerprint,"
                            "match_decision_id) values (%s,%s,%s,%s,%s)",
                            (
                                member.tenant_id,
                                idempotency_key,
                                line_id,
                                fingerprint,
                                decision["id"],
                            ),
                        )
                    except psycopg.Error as exc:
                        if exc.sqlstate in ("23505", "23514"):
                            raise ConflictError(details={"reason": "decision_changed"}) from exc
                        raise ServiceUnavailableError(details={"dependency": "database"}) from exc

        # PostgREST side effects must see the committed head. Reacquire the same locks so
        # concurrent replays cannot duplicate the audit event while finishing side effects.
        with _authenticated_db(self._settings, member) as conn:
            with conn.cursor() as cur:
                for scope in (
                    f"correction-key:{member.tenant_id}:{idempotency_key}",
                    f"correction-line:{member.tenant_id}:{line_id}",
                ):
                    cur.execute("select pg_advisory_xact_lock(hashtextextended(%s, 0))", (scope,))
            return self._finish_correction(
                client=client,
                bearer_token=bearer_token,
                member=member,
                line=line,
                decision_row=decision,
                report_alias_conflict=payload.learn_alias,
            )

    def _finish_correction(
        self,
        *,
        client: object,
        bearer_token: str,
        member: CurrentMember,
        line: dict[str, object],
        decision_row: dict[str, object],
        report_alias_conflict: bool = True,
    ) -> MatchCorrectionResponse:
        decision_id = UUID(str(decision_row["id"]))
        try:
            events = _rows(
                client.table("audit_event")
                .select("target")
                .eq("action", "matching.decision_corrected")
                .eq("target->>decision_id", str(decision_id))
                .limit(1)
                .execute()
                .data
            )
        except APIError as exc:
            raise ServiceUnavailableError(details={"dependency": "audit_event"}) from exc
        if events:
            # Snapshot the full response in append-only audit evidence, including the dependent
            # lines and alias conflict, so a later correction or sweep cannot change a replay.
            return MatchCorrectionResponse.model_validate(events[0]["target"]["response"])
        superseded_id = UUID(str(decision_row["supersedes_decision_id"]))
        old = _decision_by_id(client, superseded_id)
        try:
            learned = _rows(
                client.table("current_match_decision")
                .select("quotation_line_id")
                .eq("learned_from_decision_id", str(superseded_id))
                .execute()
                .data
            )
        except APIError as exc:
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc
        conflict_product = None
        if report_alias_conflict and decision_row.get("alias_id") is None:
            alias = self._aliases._find_alias(client, str(line["original_text"]))
            if alias is not None and str(alias["workspace_product_id"]) != str(
                decision_row["matched_workspace_product_id"]
            ):
                conflict_product = UUID(str(alias["workspace_product_id"]))
        result = MatchCorrectionResponse(
            decision=_decision(client, decision_row),
            superseded_decision_id=superseded_id,
            lines_matched_through_old_wording=sorted(
                {UUID(str(row["quotation_line_id"])) for row in learned}
            ),
            alias_conflict_product_id=conflict_product,
        )
        self._landed_cost.compute_for_line_with_client(
            client=client, member=member, line_id=UUID(str(line["id"]))
        )
        enqueue_guardrail_evaluation(
            self._settings, tenant_id=member.tenant_id, quotation_id=UUID(str(line["quotation_id"]))
        )
        get_audit_writer().record(
            AuditEventCreate(
                tenant_id=member.tenant_id,
                actor_membership_id=member.membership_id,
                actor_email=member.email,
                action="matching.decision_corrected",
                outcome="success",
                trace_id=get_trace_id(),
                target={
                    "quotation_line_id": str(line["id"]),
                    "superseded_decision_id": str(superseded_id),
                    "decision_id": str(decision_id),
                    "from_product_id": str(old["matched_workspace_product_id"]),
                    "to_product_id": str(decision_row["matched_workspace_product_id"]),
                    "response": result.model_dump(mode="json"),
                },
            ),
            bearer_token=bearer_token,
        )
        return result

    def count_exact_matches(self, *, bearer_token: str) -> ExactMatchSummary:
        client = authenticated_client(self._settings, bearer_token)
        return ExactMatchSummary(count=len(self._exact_match_pairs(client)))

    def confirm_exact_matches(
        self,
        *,
        bearer_token: str,
        member: CurrentMember,
        idempotency_key: UUID | None = None,
    ) -> BulkConfirmResult:
        """Human-triggered bulk confirm of open tasks whose top candidate is an exact
        normalised-name match. Each line gets an ordinary human decision + alias.

        With an Idempotency-Key the first call freezes its batch (`match_bulk_confirmation`) and
        derives a per-line key from it, so a retry replays the same plan: lines already decided
        replay as confirmed, the rest are completed, and the queue is never re-selected."""
        client = authenticated_client(self._settings, bearer_token)
        inputs: dict[tuple[str, str], _BulkReadResult] = {}
        plan: list[tuple[UUID, UUID]] | None = None
        if idempotency_key is not None:
            plan = _stored_bulk_plan(client, member.tenant_id, idempotency_key)
        if plan is None:
            plan = self._exact_match_pairs(client, inputs=inputs)
            if idempotency_key is not None:
                _store_bulk_plan(client, member.tenant_id, idempotency_key, plan)
        if not plan:
            return BulkConfirmResult(confirmed=0, skipped=0)

        # Equal alias text must retain plan order: alias learning is a read/insert pair.
        # Parallelizing equal text could create duplicates or change which product wins.
        try:
            missing = [
                str(line_id)
                for line_id, _ in plan
                if ("quotation_line", str(line_id)) not in inputs
            ]
            if missing:
                for row in _rows(
                    client.table("quotation_line")
                    .select(LINE_COLUMNS)
                    .in_("id", missing)
                    .execute()
                    .data
                ):
                    inputs[("quotation_line", str(row["id"]))] = _BulkReadResult([row])
            texts = {
                row_id: str(result.data[0]["original_text"]).casefold()
                for (table, row_id), result in inputs.items()
                if table == "quotation_line"
            }
            # Populate the read-only input snapshot in bounded reads rather than once per line.
            for table, ids in (
                (
                    "canonical_product",
                    {
                        str(result.data[0]["canonical_product_id"])
                        for (name, _), result in inputs.items()
                        if name == "workspace_product"
                    },
                ),
                (
                    "quotation",
                    {
                        str(result.data[0]["quotation_id"])
                        for (name, _), result in inputs.items()
                        if name == "quotation_line"
                    },
                ),
            ):
                if ids:
                    for row in _rows(
                        client.table(table)
                        .select(_BULK_READ_COLUMNS[table])
                        .in_("id", sorted(ids))
                        .execute()
                        .data
                    ):
                        inputs[(table, str(row["id"]))] = _BulkReadResult([row])
        except APIError as exc:
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc
        groups: dict[str, list[tuple[UUID, UUID]]] = {}
        for pair in plan:
            groups.setdefault(texts.get(str(pair[0]), str(pair[0])), []).append(pair)
        quotations: set[UUID] = set()
        quotation_lock = Lock()

        def defer_guardrail(quotation_id: UUID) -> None:
            with quotation_lock:
                quotations.add(quotation_id)

        def confirm_group(group: list[tuple[UUID, UUID]]) -> BulkConfirmResult:
            # Each worker owns its authenticated client; no shared HTTP session or auth state.
            worker_client = authenticated_client(self._settings, bearer_token)
            read_client = _BulkReadClient(worker_client)
            read_client.rows.update(inputs)
            confirmed = skipped = 0
            try:
                for line_id, candidate_id in group:
                    line_key = (
                        uuid5(idempotency_key, str(line_id))
                        if idempotency_key is not None
                        else None
                    )
                    try:
                        self._resolve_with_client(
                            client=read_client,
                            bearer_token=bearer_token,
                            member=member,
                            line_id=line_id,
                            payload=MatchResolutionRequest(
                                outcome="same_product", selected_match_candidate_id=candidate_id
                            ),
                            idempotency_key=line_key,
                            defer_guardrail=defer_guardrail,
                        )
                    except ConflictError:
                        skipped += 1
                        continue
                    confirmed += 1
                return BulkConfirmResult(confirmed=confirmed, skipped=skipped)
            finally:
                postgrest = getattr(worker_client, "postgrest", None)
                if postgrest is not None:
                    postgrest.session.close()

        try:
            with ThreadPoolExecutor(max_workers=EXACT_CONFIRM_WORKERS) as executor:
                # ContextVars carry the request trace ID into audit events in each worker.
                futures = [
                    executor.submit(copy_context().run, confirm_group, group)
                    for group in groups.values()
                ]
                results = [future.result() for future in futures]
        finally:
            # The executor waits even on failure. Evaluate completed decisions only after all
            # workers finish; preserve enqueue-on-insert even if a later side effect failed.
            for quotation_id in sorted(quotations):
                enqueue_guardrail_evaluation(
                    self._settings, tenant_id=member.tenant_id, quotation_id=quotation_id
                )
        return BulkConfirmResult(
            confirmed=sum(result.confirmed for result in results),
            skipped=sum(result.skipped for result in results),
        )

    def _exact_match_pairs(
        self, client: object, *, inputs: dict[tuple[str, str], _BulkReadResult] | None = None
    ) -> list[tuple[UUID, UUID]]:
        """Up to EXACT_CONFIRM_BATCH (line, candidate) pairs, oldest task first.

        Bounded batched reads: one task query, then per chunk of EXACT_LOOKUP_CHUNK lines one
        query each for rank-1 candidates, product names and line text."""
        try:
            tasks = _rows(
                client.table("match_task")
                .select("quotation_line_id")
                .in_("status", ["open", "in_progress"])
                .order("created_at")
                .limit(EXACT_SCAN_LIMIT)
                .execute()
                .data
            )
            line_ids = [str(task["quotation_line_id"]) for task in tasks]
            pairs: list[tuple[UUID, UUID]] = []
            for offset in range(0, len(line_ids), EXACT_LOOKUP_CHUNK):
                if len(pairs) >= EXACT_CONFIRM_BATCH:
                    break
                chunk = line_ids[offset : offset + EXACT_LOOKUP_CHUNK]
                candidates = {
                    str(row["quotation_line_id"]): row
                    for row in _rows(
                        client.table("match_candidate")
                        .select("id,quotation_line_id,candidate_workspace_product_id")
                        .in_("quotation_line_id", chunk)
                        .eq("rank", 1)
                        .execute()
                        .data
                    )
                }
                if not candidates:
                    continue
                product_ids = sorted(
                    {str(row["candidate_workspace_product_id"]) for row in candidates.values()}
                )
                products = {
                    str(row["id"]): row
                    for row in _rows(
                        client.table("workspace_product")
                        .select(PRODUCT_COLUMNS if inputs is not None else "id,tenant_name")
                        .in_("id", product_ids)
                        .execute()
                        .data
                    )
                }
                lines = {
                    str(row["id"]): row
                    for row in _rows(
                        client.table("quotation_line")
                        .select(LINE_COLUMNS if inputs is not None else "id,original_text")
                        .in_("id", list(candidates))
                        .execute()
                        .data
                    )
                }
                for line_id in chunk:
                    candidate = candidates.get(line_id)
                    if candidate is None or len(pairs) >= EXACT_CONFIRM_BATCH:
                        continue
                    product_id = str(candidate["candidate_workspace_product_id"])
                    product = products.get(product_id)
                    line = lines.get(line_id)
                    if (
                        product is not None
                        and line is not None
                        and is_exact_name_match(line.get("original_text"), product["tenant_name"])
                    ):
                        pairs.append((UUID(line_id), UUID(str(candidate["id"]))))
                        if inputs is not None:
                            inputs[("workspace_product", product_id)] = _BulkReadResult([product])
                            inputs[("quotation_line", line_id)] = _BulkReadResult([line])
        except APIError as exc:
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc
        return pairs

    def _complete_resolution_side_effects(
        self,
        *,
        client: object,
        bearer_token: str,
        member: CurrentMember,
        line: dict[str, object],
        line_id: UUID,
        decision: MatchDecision,
        idempotency_key: UUID | None,
        request_fingerprint: str,
        repair_existing_decision: bool,
    ) -> None:
        self._resolve_open_task(client, line_id)
        if not repair_existing_decision or not _matching_resolution_audit_exists(
            client, decision.id
        ):
            get_audit_writer().record(
                AuditEventCreate(
                    tenant_id=member.tenant_id,
                    actor_membership_id=member.membership_id,
                    actor_email=member.email,
                    action="matching.resolved",
                    target={
                        "quotation_id": str(line["quotation_id"]),
                        "quotation_line_id": str(line_id),
                        "decision_id": str(decision.id),
                        "candidate_id": (
                            str(decision.selected_match_candidate_id)
                            if decision.selected_match_candidate_id
                            else None
                        ),
                        "matched_product_id": str(decision.matched_product.id),
                        "outcome": decision.outcome,
                        "score": decision.confidence,
                    },
                    outcome="success",
                    trace_id=get_trace_id(),
                ),
                bearer_token=bearer_token,
            )
        self._landed_cost.compute_for_line_with_client(
            client=client, member=member, line_id=line_id
        )
        if idempotency_key is not None:
            _record_idempotency_decision(
                client=client,
                member=member,
                idempotency_key=idempotency_key,
                line_id=line_id,
                request_fingerprint=request_fingerprint,
                decision_id=decision.id,
            )

    def _candidate_row(
        self,
        client: object,
        candidate_id: UUID,
        line_id: UUID,
    ) -> dict[str, object]:
        try:
            rows = _rows(
                client.table("match_candidate")
                .select(
                    "id,quotation_line_id,candidate_workspace_product_id,confidence,reasons,rank,scoring_version,embedding_model,created_at"
                )
                .eq("id", str(candidate_id))
                .eq("quotation_line_id", str(line_id))
                .limit(2)
                .execute()
                .data
            )
        except APIError as exc:
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc
        if len(rows) != 1:
            raise ConflictError(details={"reason": "candidate_not_valid_for_line"})
        return rows[0]

    def _quotation_supplier_id(self, client: object, quotation_id: UUID) -> UUID | None:
        try:
            rows = _rows(
                client.table("quotation")
                .select("id,supplier_id")
                .eq("id", str(quotation_id))
                .limit(2)
                .execute()
                .data
            )
        except APIError as exc:
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc
        row = _one_row(rows, resource="quotation")
        return UUID(str(row["supplier_id"])) if row.get("supplier_id") else None

    def _resolve_open_task(self, client: object, line_id: UUID) -> None:
        try:
            client.table("match_task").update(
                {"status": "resolved", "resolved_at": datetime.now(UTC).isoformat()}
            ).eq("quotation_line_id", str(line_id)).in_("status", ["open", "in_progress"]).execute()
        except APIError as exc:
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc


# These projections include everything read by resolution and landed cost, without embeddings.
# Inputs that resolution does not mutate are reused within a worker group. Decisions, aliases,
# tasks and idempotency records always go to the database, including after writes and on retry.
_BULK_READ_COLUMNS = {
    "quotation_line": LINE_COLUMNS,
    "workspace_product": PRODUCT_COLUMNS,
    "canonical_product": CANONICAL_COLUMNS,
    "quotation": "id,supplier_id,currency,expiry_date",
}


@dataclass(frozen=True)
class _BulkReadResult:
    data: list[dict[str, object]]


class _BulkReadClient:
    def __init__(self, client: object) -> None:
        self._client = client
        self.rows: dict[tuple[str, str], object] = {}

    def table(self, name: str) -> object:
        table = self._client.table(name)
        if name in _BULK_READ_COLUMNS:
            return _BulkReadTable(self, name, table)
        return table


class _BulkReadTable:
    def __init__(self, client: _BulkReadClient, name: str, table: object) -> None:
        self._client, self._name, self._table = client, name, table

    def select(self, _columns: str) -> _BulkReadQuery:
        return _BulkReadQuery(
            self._client, self._name, self._table.select(_BULK_READ_COLUMNS[self._name])
        )


class _BulkReadQuery:
    def __init__(self, client: _BulkReadClient, table: str, query: object) -> None:
        self._client, self._table, self._query = client, table, query
        self._filters: list[tuple[str, tuple[str, ...]]] = []
        self._limit: int | None = None

    def eq(self, column: str, value: str) -> _BulkReadQuery:
        self._filters.append((column, (value,)))
        self._query = self._query.eq(column, value)
        return self

    def in_(self, column: str, values: list[str]) -> _BulkReadQuery:
        self._filters.append((column, tuple(values)))
        self._query = self._query.in_(column, values)
        return self

    def limit(self, value: int) -> _BulkReadQuery:
        self._limit = value
        self._query = self._query.limit(value)
        return self

    def execute(self) -> object:
        # eq(id, x) and in_(id, [x]) identify the same unique row, regardless of whether
        # the caller asks for a one- or two-row limit. Other query shapes remain live.
        if (
            len(self._filters) != 1
            or self._filters[0][0] != "id"
            or len(self._filters[0][1]) != 1
            or self._limit not in (None, 1, 2)
        ):
            return self._query.execute()
        key = (self._table, self._filters[0][1][0])
        if key not in self._client.rows:
            self._client.rows[key] = self._query.execute()
        return self._client.rows[key]


def get_match_resolution_service() -> MatchResolutionService:
    return MatchResolutionService()


def _request_fingerprint(payload: MatchResolutionRequest | MatchCorrectionRequest) -> str:
    encoded = json.dumps(
        payload.model_dump(mode="json", exclude_none=True),
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _decision_matches_payload(
    decision: dict[str, object],
    payload: MatchResolutionRequest,
) -> bool:
    if str(decision.get("outcome")) != payload.outcome:
        return False
    if payload.outcome == "no_match_new_product":
        return False
    return str(decision.get("selected_match_candidate_id")) == str(
        payload.selected_match_candidate_id
    )


def _matching_resolution_audit_exists(client: object, decision_id: UUID) -> bool:
    try:
        rows = _rows(
            client.table("audit_event")
            .select("id")
            .eq("action", "matching.resolved")
            .eq("target->>decision_id", str(decision_id))
            .limit(1)
            .execute()
            .data
        )
    except APIError as exc:
        raise ServiceUnavailableError(details={"dependency": "audit_event"}) from exc
    return bool(rows)


def _idempotency_record_for_key(
    client: object,
    tenant_id: UUID,
    idempotency_key: UUID,
) -> dict[str, object] | None:
    try:
        rows = _rows(
            client.table("match_resolution_idempotency")
            .select(
                "tenant_id,idempotency_key,quotation_line_id,request_fingerprint,match_decision_id,created_at"
            )
            .eq("tenant_id", str(tenant_id))
            .eq("idempotency_key", str(idempotency_key))
            .limit(2)
            .execute()
            .data
        )
    except APIError as exc:
        raise ServiceUnavailableError(details={"dependency": "database"}) from exc
    if len(rows) > 1:
        raise ServiceUnavailableError(details={"reason": "multiple_idempotency_records"})
    return rows[0] if rows else None


def _stored_bulk_plan(
    client: object, tenant_id: UUID, idempotency_key: UUID
) -> list[tuple[UUID, UUID]] | None:
    try:
        rows = _rows(
            client.table("match_bulk_confirmation")
            .select("plan")
            .eq("tenant_id", str(tenant_id))
            .eq("idempotency_key", str(idempotency_key))
            .limit(2)
            .execute()
            .data
        )
    except APIError as exc:
        raise ServiceUnavailableError(details={"dependency": "database"}) from exc
    if not rows:
        return None
    return [
        (UUID(str(item["line_id"])), UUID(str(item["candidate_id"]))) for item in rows[0]["plan"]
    ]


def _store_bulk_plan(
    client: object, tenant_id: UUID, idempotency_key: UUID, plan: list[tuple[UUID, UUID]]
) -> None:
    try:
        client.table("match_bulk_confirmation").insert(
            {
                "tenant_id": str(tenant_id),
                "idempotency_key": str(idempotency_key),
                "plan": [
                    {"line_id": str(line_id), "candidate_id": str(candidate_id)}
                    for line_id, candidate_id in plan
                ],
            }
        ).execute()
    except APIError as exc:
        raise ServiceUnavailableError(details={"dependency": "database"}) from exc


def _decision_by_id(client: object, decision_id: UUID) -> dict[str, object]:
    try:
        response = (
            client.table("match_decision")
            .select(DECISION_COLUMNS)
            .eq("id", str(decision_id))
            .limit(2)
            .execute()
        )
    except APIError as exc:
        raise ServiceUnavailableError(details={"dependency": "database"}) from exc
    return _one_row(response.data, resource="match_decision")


def _record_idempotency_decision(
    *,
    client: object,
    member: CurrentMember,
    idempotency_key: UUID,
    line_id: UUID,
    request_fingerprint: str,
    decision_id: UUID,
) -> None:
    try:
        client.table("match_resolution_idempotency").insert(
            {
                "tenant_id": str(member.tenant_id),
                "idempotency_key": str(idempotency_key),
                "quotation_line_id": str(line_id),
                "request_fingerprint": request_fingerprint,
                "match_decision_id": str(decision_id),
            }
        ).execute()
    except APIError as exc:
        raise ServiceUnavailableError(details={"dependency": "database"}) from exc


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

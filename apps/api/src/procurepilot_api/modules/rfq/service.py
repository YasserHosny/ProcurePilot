import base64
import json
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date

import psycopg
from psycopg.rows import dict_row

from procurepilot_api import db
from procurepilot_api.config import Settings
from procurepilot_api.deps import CurrentMember
from procurepilot_api.errors import (  # noqa: E501
    NotFoundError,
    PermissionDeniedError,
    ServiceUnavailableError,
    UnprocessableEntityError,
)
from procurepilot_api.modules.requests.schemas import (
    PurchaseRequestCreate,
    PurchaseRequestLineInput,
)
from procurepilot_api.modules.requests.service import RequestsService
from procurepilot_api.modules.requests.valuation import estimate_from_source_response
from procurepilot_api.modules.rfq.email import RfqEmailLine, render_rfq_email
from procurepilot_api.modules.rfq.guardrail_evaluation import compute_guardrail_evaluation
from procurepilot_api.modules.rfq.guardrails import explain_guardrail_evaluations
from procurepilot_api.modules.rfq.schemas import (
    AutoPreparationGuardrail,
    GuardrailCreateInput,
    GuardrailUpdateInput,
    Rfq,
    RfqDetail,
    RfqGuardrailEvaluation,
    RfqLine,
    RfqList,
    RfqPrepareRequestResponse,
    RfqRecipient,
    RfqResponseComparison,
    RfqResponseComparisonList,
    RfqSummary,
)
from procurepilot_api.shared.i18n import t
from procurepilot_api.shared.mailer import get_mailer


@contextmanager
def _authenticated_db(settings: Settings, member: CurrentMember) -> Iterator[psycopg.Connection]:
    try:
        with db.connect(settings.database_url.get_secret_value()) as conn:
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


class RfqService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def _fetch_created(
        self, cur: psycopg.Cursor, rfq_id: uuid.UUID
    ) -> tuple[Rfq, list[RfqLine], list[RfqRecipient], list[dict]]:
        """Re-fetch an already-created RFQ for idempotent replay -- the exact shape
        create() would have returned the first time, minus rejected_recipients, which
        isn't persisted (the original response already told the caller about those;
        a replay's job is returning the same *created* result, not re-deriving
        rejections that were never stored)."""
        cur.execute("select * from rfq where id = %s", (rfq_id,))
        rfq = Rfq(**cur.fetchone())
        cur.execute("select * from rfq_line where rfq_id = %s order by created_at", (rfq_id,))
        lines = [RfqLine(**r) for r in cur.fetchall()]
        cur.execute("select * from rfq_recipient where rfq_id = %s order by created_at", (rfq_id,))
        recipients = [RfqRecipient(**r) for r in cur.fetchall()]
        return rfq, lines, recipients, []

    def create(
        self,
        *,
        member: CurrentMember,
        lines_data: list,
        recipient_supplier_ids: list[uuid.UUID],
        needed_by_date: date,
        idempotency_key: uuid.UUID,
        tenant_terms: str | None = None,
    ) -> tuple[Rfq, list[RfqLine], list[RfqRecipient], list[dict]]:
        with _authenticated_db(self.settings, member) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                # True idempotent replay: a retry with the same key after the original
                # request already committed must return the SAME rfq, never insert a
                # second one -- the advisory lock below only protects against two
                # concurrent callers racing with the same key, it is not itself replay
                # safety (the lock releases at commit; a retry after that would sail
                # straight through and create a duplicate without this check).
                cur.execute(
                    "select id from rfq where tenant_id = %s and idempotency_key = %s",
                    (member.tenant_id, idempotency_key),
                )
                existing = cur.fetchone()
                if existing is not None:
                    return self._fetch_created(cur, existing["id"])

                cur.execute(
                    "select pg_try_advisory_xact_lock(%s)",
                    (idempotency_key.int & 0x7FFFFFFFFFFFFFFF,),
                )
                if not cur.fetchone()["pg_try_advisory_xact_lock"]:
                    raise UnprocessableEntityError(
                        details={"idempotency_key": "concurrent request"}
                    )

                rejected_recipients, valid_supplier_ids = _validate_recipients(
                    cur, recipient_supplier_ids
                )

                rfq_id = uuid.uuid4()
                cur.execute(
                    """
                    insert into rfq (
                        id, tenant_id, created_by_membership_id, status, needed_by_date,
                        idempotency_key, tenant_terms
                    )
                    values (%s, %s, %s, 'draft', %s, %s, %s)
                    returning id, tenant_id, created_by_membership_id, status,
                              needed_by_date, idempotency_key, tenant_terms, created_at
                    """,
                    (
                        rfq_id,
                        member.tenant_id,
                        member.membership_id,
                        needed_by_date,
                        idempotency_key,
                        tenant_terms,
                    ),
                )
                rfq_row = cur.fetchone()
                rfq = Rfq(**rfq_row)

                created_lines = []
                for line_data in lines_data:
                    line_id = uuid.uuid4()
                    cur.execute(
                        """
                        insert into rfq_line (id, tenant_id, rfq_id, workspace_product_id, quantity)
                        values (%s, %s, %s, %s, %s)
                        returning id, tenant_id, rfq_id, workspace_product_id, quantity, created_at
                        """,
                        (
                            line_id,
                            member.tenant_id,
                            rfq_id,
                            line_data.workspace_product_id,
                            line_data.quantity,
                        ),
                    )
                    created_lines.append(RfqLine(**cur.fetchone()))

                created_recipients = []
                for supplier_id in valid_supplier_ids:
                    rec_id = uuid.uuid4()
                    cur.execute(
                        """
                        insert into rfq_recipient (id, tenant_id, rfq_id, supplier_id, status)
                        values (%s, %s, %s, %s, 'draft')
                        returning id, tenant_id, rfq_id, supplier_id, status,
                                  outbound_message_id, sent_at, created_at
                        """,
                        (rec_id, member.tenant_id, rfq_id, supplier_id),
                    )
                    created_recipients.append(RfqRecipient(**cur.fetchone()))

                conn.commit()
                return rfq, created_lines, created_recipients, rejected_recipients

    def get_detail(self, *, member: CurrentMember, rfq_id: uuid.UUID) -> RfqDetail:
        with _authenticated_db(self.settings, member) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute("select * from rfq where id = %s", (rfq_id,))
                row = cur.fetchone()
                if row is None:
                    raise NotFoundError(details={"resource": "rfq"})
                cur.execute(
                    "select * from rfq_line where rfq_id = %s order by created_at", (rfq_id,)
                )
                lines = [RfqLine(**item) for item in cur.fetchall()]
                cur.execute(
                    "select * from rfq_recipient where rfq_id = %s order by created_at", (rfq_id,)
                )
                recipients = [RfqRecipient(**item) for item in cur.fetchall()]
                return RfqDetail(rfq=Rfq(**row), lines=lines, recipients=recipients)

    def update_draft(
        self,
        *,
        member: CurrentMember,
        rfq_id: uuid.UUID,
        lines_data: list,
        recipient_supplier_ids: list[uuid.UUID],
        needed_by_date: date,
        tenant_terms: str | None,
        idempotency_key: uuid.UUID,
    ) -> tuple[Rfq, list[RfqLine], list[RfqRecipient], list[dict]]:
        with _authenticated_db(self.settings, member) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                row = _lock_rfq_for_creator(cur, member, rfq_id)
                if row["last_update_idempotency_key"] == idempotency_key:
                    # Replay of an already-applied PUT (lost response): return the stored
                    # result without re-creating lines/recipients or auditing again.
                    rfq, lines, recipients, _ = self._fetch_created(cur, rfq_id)
                    return rfq, lines, recipients, []
                if row["status"] != "draft":
                    from procurepilot_api.errors import ConflictError

                    raise ConflictError(details={"resource": "rfq", "reason": "not_draft"})
                rejected, valid_supplier_ids = _validate_recipients(cur, recipient_supplier_ids)
                try:
                    cur.execute("delete from rfq_line where rfq_id = %s", (rfq_id,))
                    cur.execute("delete from rfq_recipient where rfq_id = %s", (rfq_id,))
                except psycopg.errors.ForeignKeyViolation as exc:
                    from procurepilot_api.errors import ConflictError

                    raise ConflictError(
                        details={"resource": "rfq", "reason": "has_responses"}
                    ) from exc
                cur.execute(
                    "update rfq set needed_by_date = %s, tenant_terms = %s, "
                    "last_update_idempotency_key = %s where id = %s returning *",
                    (needed_by_date, tenant_terms, idempotency_key, rfq_id),
                )
                rfq = Rfq(**cur.fetchone())
                lines = []
                for item in lines_data:
                    cur.execute(
                        "insert into rfq_line "
                        "(tenant_id,rfq_id,workspace_product_id,quantity) "
                        "values (%s,%s,%s,%s) returning *",
                        (member.tenant_id, rfq_id, item.workspace_product_id, item.quantity),
                    )
                    lines.append(RfqLine(**cur.fetchone()))
                recipients = []
                for supplier_id in valid_supplier_ids:
                    cur.execute(
                        "insert into rfq_recipient "
                        "(tenant_id,rfq_id,supplier_id,status) "
                        "values (%s,%s,%s,'draft') returning *",
                        (member.tenant_id, rfq_id, supplier_id),
                    )
                    recipients.append(RfqRecipient(**cur.fetchone()))
                cur.execute(
                    "select record_audit_event(%s, 'success'::audit_outcome, "
                    "%s, %s, %s, %s::jsonb, null)",
                    (
                        "rfq.draft_updated",
                        member.tenant_id,
                        member.membership_id,
                        member.email,
                        json.dumps({"rfq_id": str(rfq_id)}),
                    ),
                )
                conn.commit()
                return rfq, lines, recipients, rejected

    def send(
        self,
        *,
        member: CurrentMember,
        rfq_id: uuid.UUID,
        idempotency_key: uuid.UUID,
    ) -> tuple[Rfq, list[RfqRecipient]]:
        mailer = get_mailer()
        with _authenticated_db(self.settings, member) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    "select pg_try_advisory_xact_lock(%s)",
                    (idempotency_key.int & 0x7FFFFFFFFFFFFFFF,),
                )
                if not cur.fetchone()["pg_try_advisory_xact_lock"]:
                    raise UnprocessableEntityError(
                        details={"idempotency_key": "concurrent request"}
                    )

                rfq_row = _lock_rfq_for_creator(cur, member, rfq_id)
                rfq = Rfq(**rfq_row)

                cur.execute("select * from rfq_line where rfq_id = %s", (rfq_id,))
                line_rows = cur.fetchall()
                lines = [RfqLine(**r) for r in line_rows]

                # The supplier email follows the sender's interface language, then the
                # workspace default -- the same order the digest uses.
                cur.execute(
                    """select t.name,
                              coalesce(m.preferred_locale, t.default_locale) as default_locale
                       from tenant t
                       left join membership m on m.tenant_id = t.id and m.id = %s
                       where t.id = %s""",
                    (member.membership_id, member.tenant_id),
                )
                tenant_row = cur.fetchone()
                cur.execute(
                    """select l.workspace_product_id, wp.tenant_name, cp.base_unit,
                              pd.pack_count, pd.unit_size
                       from rfq_line l join workspace_product wp on wp.id = l.workspace_product_id
                       left join canonical_product cp on cp.id = wp.canonical_product_id
                       left join (
                         select workspace_product_id, min(pack_count) as pack_count,
                                min(unit_size) as unit_size
                         from pack_definition group by workspace_product_id
                         having count(*) = 1
                       ) pd on pd.workspace_product_id = wp.id
                       where l.rfq_id = %s""",
                    (rfq_id,),
                )
                product_by_id = {r["workspace_product_id"]: r for r in cur.fetchall()}

                cur.execute(
                    "select * from rfq_recipient where rfq_id = %s and status = 'draft'", (rfq_id,)
                )
                recipient_rows = cur.fetchall()
                draft_recipients = [RfqRecipient(**r) for r in recipient_rows]

                cur.execute(
                    "select * from tenant_email_config where tenant_id = %s",
                    (member.tenant_id,),
                )
                email_config_row = cur.fetchone()
                reply_to = None
                if email_config_row and email_config_row["enabled"]:
                    reply_to = email_config_row["forwarding_address"]

                any_sent = False
                updated_recipients = []

                for recipient in draft_recipients:
                    cur.execute(
                        "select contact_email from supplier where id = %s",
                        (recipient.supplier_id,),  # noqa: E501
                    )
                    supp_row = cur.fetchone()
                    if not supp_row or not supp_row.get("contact_email"):
                        updated_recipients.append(recipient)
                        continue

                    contact_email = supp_row["contact_email"]
                    email_lines = []
                    for line in lines:
                        product = product_by_id.get(line.workspace_product_id)
                        email_lines.append(
                            RfqEmailLine(
                                product_name=(
                                    product["tenant_name"]
                                    if product
                                    else t("rfq.email.unknownProduct", tenant_row["default_locale"])
                                ),
                                quantity=line.quantity,
                                unit_code=product["base_unit"] if product else "each",
                                pack_count=product["pack_count"] if product else None,
                                unit_size=product["unit_size"] if product else None,
                            )
                        )
                    rendered = render_rfq_email(
                        tenant_name=tenant_row["name"],
                        locale=tenant_row["default_locale"],
                        needed_by=rfq.needed_by_date,
                        lines=email_lines,
                        tenant_terms=rfq.tenant_terms,
                        reply_to=reply_to,
                    )

                    send_kwargs = {
                        "to": contact_email,
                        "subject": rendered.subject,
                        "body": rendered.text,
                        "html": rendered.html,
                        "from_name": rendered.from_name,
                    }
                    if reply_to:
                        send_kwargs["headers"] = {"Reply-To": reply_to}

                    try:
                        res = mailer.send(**send_kwargs)
                        # On success
                        sent_msg_id = res.message_id
                        cur.execute(
                            """
                            update rfq_recipient
                            set status = 'sent', outbound_message_id = %s, sent_at = now()
                            where id = %s
                            returning *
                            """,
                            (sent_msg_id, recipient.id),
                        )
                        updated_recipients.append(RfqRecipient(**cur.fetchone()))
                        any_sent = True
                    except Exception:
                        # On failure, leave draft
                        updated_recipients.append(recipient)

                # Fetch all recipients to return
                cur.execute("select * from rfq_recipient where rfq_id = %s", (rfq_id,))
                all_recipients = [RfqRecipient(**r) for r in cur.fetchall()]

                if any_sent and rfq.status == "draft":
                    cur.execute(
                        "update rfq set status = 'sent' where id = %s returning *", (rfq_id,)
                    )
                    rfq = Rfq(**cur.fetchone())

                    # Record audit event
                    cur.execute(
                        "select record_audit_event(%s, 'success'::audit_outcome, "
                        "%s, %s, %s, %s::jsonb, null)",
                        (
                            "rfq.sent",
                            member.tenant_id,
                            member.membership_id,
                            member.email,
                            json.dumps({"rfq_id": str(rfq_id)}),
                        ),
                    )

                conn.commit()
                return rfq, all_recipients

    def list_responses(
        self,
        *,
        member: CurrentMember,
        rfq_id: uuid.UUID,
    ) -> RfqResponseComparisonList:
        with _authenticated_db(self.settings, member) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    "select id from rfq where id = %s and tenant_id = %s",
                    (rfq_id, member.tenant_id),  # noqa: E501
                )
                if not cur.fetchone():
                    raise NotFoundError(details={"resource": "rfq"})

                cur.execute(
                    """
                    select
                        r.id as response_id,
                        rec.supplier_id,
                        r.created_at as submitted_at,
                        ql.id as ql_id,
                        ql.quantity,
                        ql.unit_price_amount,
                        ql.unit_price_currency,
                        md.matched_workspace_product_id
                    from rfq_response r
                    join rfq_recipient rec on r.rfq_recipient_id = rec.id
                    left join quotation_line ql on r.quotation_id = ql.quotation_id
                    left join match_decision md on ql.id = md.quotation_line_id
                    where r.tenant_id = %s and rec.rfq_id = %s
                    order by r.created_at, ql.created_at
                    """,
                    (member.tenant_id, rfq_id),
                )
                rows = cur.fetchall()

                evaluation_by_response: dict[uuid.UUID, list[RfqGuardrailEvaluation]] = {}
                response_ids = list({row["response_id"] for row in rows})
                snapshot = compute_guardrail_evaluation(
                    cur, tenant_id=member.tenant_id, rfq_id=rfq_id
                )
                if snapshot is not None and snapshot.guardrails:
                    cur.execute(
                        "select guardrail_id, rfq_response_id "
                        "from auto_preparation_event "
                        "where tenant_id = %s and rfq_response_id = any(%s)",
                        (member.tenant_id, response_ids),
                    )
                    fired_by_response: dict[uuid.UUID, set[uuid.UUID]] = {}
                    for event in cur.fetchall():
                        fired_by_response.setdefault(event["rfq_response_id"], set()).add(
                            event["guardrail_id"]
                        )
                    for response_id in response_ids:
                        explanations = explain_guardrail_evaluations(
                            guardrails=snapshot.guardrails,
                            rfq_status=snapshot.rfq_status,
                            total_response_count=snapshot.total_response_count,
                            candidates=snapshot.candidates,
                            recent_average_price_by_product=snapshot.recent_average_price_by_product,
                            response_id=response_id,
                            responses_pending=snapshot.responses_pending,
                            fired_guardrail_ids=fired_by_response.get(response_id, set()),
                        )
                        evaluation_by_response[response_id] = [
                            RfqGuardrailEvaluation(
                                guardrail_id=item.guardrail_id,
                                fired=item.fired,
                                reason=item.reason,
                            )
                            for item in explanations
                        ]

                responses_by_id = {}
                for row in rows:
                    resp_id = row["response_id"]
                    if resp_id not in responses_by_id:
                        responses_by_id[resp_id] = {
                            "id": resp_id,
                            "rfq_id": rfq_id,
                            "supplier_id": row["supplier_id"],
                            "submitted_at": row["submitted_at"],
                            "lines": [],
                            "guardrail_evaluations": evaluation_by_response.get(resp_id, []),
                        }

                    if row["ql_id"]:
                        pending = row["matched_workspace_product_id"] is None
                        responses_by_id[resp_id]["lines"].append(
                            {
                                "workspace_product_id": row["matched_workspace_product_id"],
                                "quoted_quantity": row["quantity"],
                                "quoted_unit_price_amount": row["unit_price_amount"],
                                "quoted_unit_price_currency": row["unit_price_currency"],
                                "pending_match": pending,
                            }
                        )

                comparisons = [RfqResponseComparison(**data) for data in responses_by_id.values()]
                return RfqResponseComparisonList(items=comparisons)

    def prepare_request(
        self,
        *,
        bearer_token: str,
        member: CurrentMember,
        rfq_id: uuid.UUID,
        rfq_response_id: uuid.UUID,
        branch_id: uuid.UUID,
        cost_centre_id: uuid.UUID | None = None,
        required_by_date: date,
        idempotency_key: uuid.UUID,
    ) -> RfqPrepareRequestResponse:
        # One purchase request per RFQ. The transaction-scoped advisory lock serialises
        # preparations of the same RFQ (manual or guardrail), and the RFQ is marked converted on
        # this same connection before the lock is released, so a second preparation sees
        # 'converted'. The guardrail evaluator's own lock uses a different key.
        with _authenticated_db(self.settings, member) as lock_conn:
            with lock_conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    "select pg_advisory_xact_lock(hashtextextended(%s, 0))",
                    (f"rfq-prepare:{member.tenant_id}:{rfq_id}",),
                )
                cur.execute(
                    "select status from rfq where id = %s and tenant_id = %s",
                    (rfq_id, member.tenant_id),
                )
                rfq_row = cur.fetchone()
                if rfq_row is not None and rfq_row["status"] == "converted":
                    # A retry of the preparation that converted it gets that request back.
                    cur.execute(
                        "select id, status from purchase_request "
                        "where tenant_id = %s and idempotency_key = %s",
                        (member.tenant_id, str(idempotency_key)),
                    )
                    existing = cur.fetchone()
                    if existing is None:
                        from procurepilot_api.errors import ConflictError

                        raise ConflictError(
                            details={"resource": "rfq", "reason": "rfq_already_converted"}
                        )
                    return RfqPrepareRequestResponse(
                        purchase_request_id=existing["id"], status=existing["status"]
                    )
            response = self._prepare_request_locked(
                lock_conn,
                bearer_token=bearer_token,
                member=member,
                rfq_id=rfq_id,
                rfq_response_id=rfq_response_id,
                branch_id=branch_id,
                cost_centre_id=cost_centre_id,
                required_by_date=required_by_date,
                idempotency_key=idempotency_key,
            )
            lock_conn.commit()
        return response

    def _prepare_request_locked(
        self,
        lock_conn: psycopg.Connection,
        *,
        bearer_token: str,
        member: CurrentMember,
        rfq_id: uuid.UUID,
        rfq_response_id: uuid.UUID,
        branch_id: uuid.UUID,
        cost_centre_id: uuid.UUID | None,
        required_by_date: date,
        idempotency_key: uuid.UUID,
    ) -> RfqPrepareRequestResponse:
        with _authenticated_db(self.settings, member) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    select r.id, r.quotation_id, rfq.needed_by_date
                    from rfq_response r
                    join rfq_recipient rec on r.rfq_recipient_id = rec.id
                    join rfq on rfq.id = rec.rfq_id and rfq.tenant_id = r.tenant_id
                    where r.id = %s and rec.rfq_id = %s and r.tenant_id = %s
                    """,
                    (rfq_response_id, rfq_id, member.tenant_id),
                )
                resp_row = cur.fetchone()
                if not resp_row:
                    raise NotFoundError(details={"resource": "rfq_response"})

                cur.execute(
                    "select status, deleted_at from quotation where id = %s and tenant_id = %s",
                    (resp_row["quotation_id"], member.tenant_id),
                )
                quotation_row = cur.fetchone()
                if quotation_row and quotation_row["deleted_at"] is not None:
                    raise UnprocessableEntityError(details={"reason": "quotation_archived"})
                if quotation_row and quotation_row["status"] == "refused":
                    raise UnprocessableEntityError(details={"reason": "quotation_refused"})

                cur.execute(
                    """
                    select ql.unit_price_amount, ql.unit_price_currency, \
                           md.matched_workspace_product_id
                    from quotation_line ql
                    left join match_decision md on ql.id = md.quotation_line_id
                    where ql.quotation_id = %s
                    """,
                    (resp_row["quotation_id"],),
                )
                ql_rows = cur.fetchall()

                if not ql_rows:
                    raise UnprocessableEntityError(details={"reason": "no_quotation_lines"})

                if any(row["matched_workspace_product_id"] is None for row in ql_rows):
                    raise UnprocessableEntityError(details={"reason": "pending_matches"})

                matched_lines = {
                    row["matched_workspace_product_id"]: row
                    for row in ql_rows
                    if row["matched_workspace_product_id"]
                }

                if not matched_lines:
                    raise UnprocessableEntityError(details={"reason": "no_matched_lines"})

                cur.execute(
                    "select workspace_product_id, quantity from rfq_line "
                    "where rfq_id = %s and tenant_id = %s",
                    (rfq_id, member.tenant_id),
                )
                rfq_lines = cur.fetchall()

                pr_lines = []
                for line in rfq_lines:
                    pid = line["workspace_product_id"]
                    if pid in matched_lines:
                        pr_lines.append(
                            PurchaseRequestLineInput(
                                workspace_product_id=pid,
                                quantity=str(line["quantity"]),
                            )
                        )

                if not pr_lines:
                    raise UnprocessableEntityError(
                        details={"reason": "no_pricing_for_rfq_products"}
                    )  # noqa: E501

                request_payload = PurchaseRequestCreate(
                    branch_id=branch_id,
                    cost_centre_id=cost_centre_id,
                    required_by_date=resp_row["needed_by_date"],
                    lines=pr_lines,
                )

        purchase_request, created = RequestsService(self.settings).create_request(
            bearer_token=bearer_token,
            member=member,
            payload=request_payload,
            idempotency_key=idempotency_key,
        )

        if created:
            with lock_conn.cursor(row_factory=dict_row) as cur:
                total_amount = 0
                total_currency: str | None = None

                cur.execute(
                    "select id, workspace_product_id, quantity from purchase_request_line "
                    "where purchase_request_id = %s and tenant_id = %s",
                    (purchase_request.id, member.tenant_id),
                )
                pr_line_rows = cur.fetchall()

                # Same valuation submit uses (per pack, landed charges included), so the
                # estimate cannot change between prepare and submit.
                source_estimates = estimate_from_source_response(
                    lock_conn,
                    rfq_response_id=rfq_response_id,
                    product_ids=list(matched_lines),
                )

                for prl in pr_line_rows:
                    pid = prl["workspace_product_id"]
                    if pid in matched_lines:
                        estimate = source_estimates.get(pid)
                        if estimate is not None:
                            q_amt = estimate.unit_price_amount
                            q_curr = estimate.unit_price_currency
                            landed_id = estimate.source_landed_cost_id
                        else:
                            q_amt = matched_lines[pid]["unit_price_amount"]
                            q_curr = matched_lines[pid]["unit_price_currency"]
                            landed_id = None
                        qty = prl["quantity"]

                        cur.execute(
                            """
                            update purchase_request_line
                            set estimated_unit_price_amount = %s,
                                estimated_unit_price_currency = %s,
                                estimated_unit_price_source_landed_cost_id = %s
                            where id = %s and tenant_id = %s
                            """,
                            (q_amt, q_curr, landed_id, prl["id"], member.tenant_id),
                        )
                        total_amount += q_amt * qty
                        # A single RFQ response's quoted lines share one currency in
                        # practice (see plan.md's Task 4 note) -- take the first, don't
                        # attempt multi-currency summation.
                        total_currency = total_currency or q_curr

                cur.execute(
                    """
                    update purchase_request
                    set source_rfq_response_id = %s,
                        estimated_total_amount = %s,
                        estimated_total_currency = %s,
                        has_incomplete_estimate = false
                    where id = %s and tenant_id = %s
                    """,
                    (
                        rfq_response_id,
                        total_amount,
                        total_currency,
                        purchase_request.id,
                        member.tenant_id,
                    ),
                )

                # 'converted' is a real, intended terminal RFQ status (spec.md's Key
                # Entities section, FR-017's history view) -- a successful preparation
                # closes the sourcing loop for this RFQ. rfq_update only matches the RFQ's
                # creator, so any other owner or buyer goes through mark_rfq_converted
                # (20261019000001), which checks the request came from this RFQ.
                cur.execute(
                    "select mark_rfq_converted(%s, %s)",
                    (rfq_id, purchase_request.id),
                )

        return RfqPrepareRequestResponse(
            purchase_request_id=purchase_request.id, status=purchase_request.status
        )

    def create_guardrail(
        self,
        *,
        member: CurrentMember,
        payload: GuardrailCreateInput,
    ) -> AutoPreparationGuardrail:
        with _authenticated_db(self.settings, member) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                _validate_guardrail_destination(
                    cur,
                    tenant_id=member.tenant_id,
                    branch_id=payload.default_branch_id,
                    cost_centre_id=payload.default_cost_centre_id,
                )
                cur.execute(
                    """
                    insert into auto_preparation_guardrail
                    (tenant_id, created_by_membership_id, max_order_value_amount,
                     max_order_value_currency, supplier_allowlist, category_allowlist,
                     min_response_count, max_price_variance_pct, enabled, default_branch_id,
                     default_cost_centre_id)
                    values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    returning *
                    """,
                    (
                        member.tenant_id,
                        member.membership_id,
                        payload.max_order_value_amount,
                        payload.max_order_value_currency,
                        payload.supplier_allowlist,
                        payload.category_allowlist,
                        payload.min_response_count,
                        payload.max_price_variance_pct,
                        payload.enabled,
                        payload.default_branch_id,
                        payload.default_cost_centre_id,
                    ),
                )
                row = cur.fetchone()

                cur.execute(
                    "select record_audit_event(%s, 'success'::audit_outcome, "
                    "%s, %s, %s, %s::jsonb, null)",
                    (
                        "rfq.guardrail_changed",
                        member.tenant_id,
                        member.membership_id,
                        member.email,
                        json.dumps({"guardrail_id": str(row["id"]), "action": "created"}),
                    ),
                )

                conn.commit()
                return AutoPreparationGuardrail.model_validate(row)

    def list_guardrails(
        self,
        *,
        member: CurrentMember,
    ) -> list[AutoPreparationGuardrail]:
        with _authenticated_db(self.settings, member) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    "select * from auto_preparation_guardrail "
                    "where tenant_id = %s order by created_at desc",
                    (member.tenant_id,),
                )
                rows = cur.fetchall()
                return [AutoPreparationGuardrail.model_validate(r) for r in rows]

    def update_guardrail(
        self,
        *,
        member: CurrentMember,
        guardrail_id: uuid.UUID,
        payload: GuardrailUpdateInput,
    ) -> AutoPreparationGuardrail:
        updates = payload.model_dump(exclude_unset=True)

        with _authenticated_db(self.settings, member) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                if not updates:
                    cur.execute(
                        "select * from auto_preparation_guardrail where tenant_id = %s and id = %s",
                        (member.tenant_id, guardrail_id),
                    )
                    row = cur.fetchone()
                    if not row:
                        raise NotFoundError(details={"resource": "auto_preparation_guardrail"})
                    return AutoPreparationGuardrail.model_validate(row)

                if "default_branch_id" in updates or "default_cost_centre_id" in updates:
                    cur.execute(
                        "select default_branch_id, default_cost_centre_id "
                        "from auto_preparation_guardrail where tenant_id = %s and id = %s",
                        (member.tenant_id, guardrail_id),
                    )
                    current = cur.fetchone()
                    if not current:
                        raise NotFoundError(details={"resource": "auto_preparation_guardrail"})
                    _validate_guardrail_destination(
                        cur,
                        tenant_id=member.tenant_id,
                        branch_id=updates.get("default_branch_id", current["default_branch_id"]),
                        cost_centre_id=updates.get(
                            "default_cost_centre_id", current["default_cost_centre_id"]
                        ),
                    )

                set_clauses = [f"{key} = %s" for key in updates]
                values: list[object] = list(updates.values())
                values.extend([member.tenant_id, guardrail_id])

                query = (
                    "update auto_preparation_guardrail "
                    f"set {', '.join(set_clauses)} "
                    "where tenant_id = %s and id = %s returning *"
                )
                cur.execute(query, values)
                row = cur.fetchone()
                if not row:
                    raise NotFoundError(details={"resource": "auto_preparation_guardrail"})

                cur.execute(
                    "select record_audit_event(%s, 'success'::audit_outcome, "
                    "%s, %s, %s, %s::jsonb, null)",
                    (
                        "rfq.guardrail_changed",
                        member.tenant_id,
                        member.membership_id,
                        member.email,
                        json.dumps(
                            {
                                "guardrail_id": str(row["id"]),
                                "action": "updated",
                                "changes": list(updates.keys()),
                            }
                        ),
                    ),
                )

                conn.commit()
                return AutoPreparationGuardrail.model_validate(row)

    def list_rfqs(
        self,
        *,
        member: CurrentMember,
        status: str | None = None,
        cursor: str | None = None,
        limit: int = 50,
    ) -> RfqList:
        capped_limit = _cap_limit(limit)
        offset = _decode_cursor(cursor)

        query_filters = ["tenant_id = %s"]
        params: list[str | uuid.UUID | int] = [member.tenant_id]

        if status:
            query_filters.append("status = %s")
            params.append(status)

        query = f"""
            SELECT
                r.id,
                r.status,
                r.needed_by_date,
                r.created_at,
                r.created_by_membership_id,
                (SELECT max(rr_sent.sent_at) FROM rfq_recipient rr_sent
                 WHERE rr_sent.rfq_id = r.id) as sent_at,
                (SELECT count(*) FROM rfq_recipient rr WHERE rr.rfq_id = r.id) as recipient_count,
                (
                    SELECT count(*)
                    FROM rfq_response resp
                    JOIN rfq_recipient rr2 ON resp.rfq_recipient_id = rr2.id
                    WHERE rr2.rfq_id = r.id
                ) as response_count,
                (
                    SELECT pr.id 
                    FROM purchase_request pr 
                    JOIN rfq_response resp ON pr.source_rfq_response_id = resp.id
                    JOIN rfq_recipient rr3 ON resp.rfq_recipient_id = rr3.id
                    WHERE rr3.rfq_id = r.id 
                    LIMIT 1
                ) as converted_purchase_request_id
            FROM rfq r
            WHERE {" AND ".join(query_filters)}
            ORDER BY r.created_at DESC, r.id DESC
            LIMIT %s OFFSET %s
        """

        with _authenticated_db(self.settings, member) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(query, (*params, capped_limit + 1, offset))
                rows = cur.fetchall()

        has_next = len(rows) > capped_limit
        if has_next:
            rows = rows[:capped_limit]
            next_cursor = _encode_cursor(offset + capped_limit)
        else:
            next_cursor = None

        items = [RfqSummary.model_validate(row) for row in rows]
        return RfqList(items=items, next_cursor=next_cursor)


def _validate_guardrail_destination(
    cur: psycopg.Cursor,
    *,
    tenant_id: uuid.UUID,
    branch_id: uuid.UUID | None,
    cost_centre_id: uuid.UUID | None,
) -> None:
    """A guardrail's default branch and optional cost centre must be visible to the caller in
    their own workspace (RLS: another tenant's id reads as not found), and the cost centre must
    be an active one assigned to that branch (finding 38b)."""
    if branch_id is None:
        raise UnprocessableEntityError(details={"default_branch_id": "required"})
    cur.execute(
        "select 1 from branch where tenant_id = %s and id = %s",
        (tenant_id, branch_id),
    )
    if cur.fetchone() is None:
        raise NotFoundError(details={"resource": "branch"})
    if cost_centre_id is None:
        return
    cur.execute(
        "select branch_id, is_archived from cost_centre where tenant_id = %s and id = %s",
        (tenant_id, cost_centre_id),
    )
    cost_centre = cur.fetchone()
    if cost_centre is None:
        raise NotFoundError(details={"resource": "cost_centre"})
    if cost_centre["is_archived"]:
        raise UnprocessableEntityError(details={"default_cost_centre_id": "archived"})
    if cost_centre["branch_id"] != branch_id:
        raise UnprocessableEntityError(details={"default_cost_centre_id": "not_in_branch"})


def _lock_rfq_for_creator(cur: psycopg.Cursor, member: CurrentMember, rfq_id: uuid.UUID) -> dict:
    """Load and row-lock an RFQ the caller may mutate, BEFORE any side effect (email, delete).

    RLS makes another tenant's RFQ invisible (404). Within a tenant, `rfq_update` is
    creator-only while `rfq_select` also admits owners/buyers, so a non-creator can read a
    draft but would only fail at the final UPDATE — after suppliers were already emailed.
    Refuse up front instead (403).
    """
    cur.execute("select * from rfq where id = %s", (rfq_id,))
    row = cur.fetchone()
    if row is None:
        raise NotFoundError(details={"resource": "rfq"})
    if row["created_by_membership_id"] != member.membership_id:
        raise PermissionDeniedError(details={"resource": "rfq", "reason": "not_creator"})
    cur.execute("select * from rfq where id = %s for update", (rfq_id,))
    locked = cur.fetchone()
    if locked is None:
        raise NotFoundError(details={"resource": "rfq"})
    return locked


def _cap_limit(limit: int) -> int:
    return max(1, min(limit, 100))


def _validate_recipients(
    cur: psycopg.Cursor, supplier_ids: list[uuid.UUID]
) -> tuple[list[dict], list[uuid.UUID]]:
    rejected: list[dict] = []
    valid: list[uuid.UUID] = []
    for supplier_id in supplier_ids:
        cur.execute("select id, contact_email from supplier where id = %s", (supplier_id,))
        row = cur.fetchone()
        if row is None:
            rejected.append({"supplier_id": str(supplier_id), "reason": "not_found"})
        elif not row.get("contact_email"):
            rejected.append({"supplier_id": str(supplier_id), "reason": "missing_contact_email"})
        else:
            valid.append(supplier_id)
    return rejected, valid


def _encode_cursor(offset: int) -> str:
    raw = json.dumps({"offset": offset}, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def _decode_cursor(cursor: str | None) -> int:
    if cursor is None:
        return 0
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii"))
        payload = json.loads(raw.decode("utf-8"))
        return payload["offset"]
    except (KeyError, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise UnprocessableEntityError(details={"cursor": "invalid_format"}) from exc


def get_rfq_service() -> RfqService:
    from procurepilot_api.config import get_settings

    return RfqService(settings=get_settings())

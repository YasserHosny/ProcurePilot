import base64
import json
import uuid
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import date

import psycopg
from psycopg.rows import dict_row

from procurepilot_api.config import Settings
from procurepilot_api.deps import CurrentMember
from procurepilot_api.errors import (  # noqa: E501
    NotFoundError,
    ServiceUnavailableError,
    UnprocessableEntityError,
)
from procurepilot_api.modules.requests.schemas import (
    PurchaseRequestCreate,
    PurchaseRequestLineInput,
)
from procurepilot_api.modules.requests.service import RequestsService
from procurepilot_api.modules.rfq.schemas import (
    AutoPreparationGuardrail,
    GuardrailCreateInput,
    GuardrailUpdateInput,
    Rfq,
    RfqLine,
    RfqList,
    RfqPrepareRequestResponse,
    RfqRecipient,
    RfqResponseComparison,
    RfqResponseComparisonList,
    RfqSummary,
)
from procurepilot_api.shared.mailer import get_mailer

NAMESPACE_RFQ = uuid.UUID("361f1073-a8d1-4db8-8d07-28f0907a4a2a")


def build_rfq_message(
    rfq: Rfq,
    lines: Sequence[RfqLine],
    product_names: dict[uuid.UUID, str],
    recipient: RfqRecipient,
    tenant_terms: str | None = None,
    reply_to: str | None = None,
) -> tuple[str, str, str]:
    subject = f"Request for Quotation - {rfq.needed_by_date}"

    body_lines = [
        "Please provide a quotation for the following items:",
        "",
    ]

    for line in lines:
        name = product_names.get(line.workspace_product_id, "Unknown Product")
        body_lines.append(f"- {name}: {line.quantity}")

    body_lines.extend(
        [
            "",
            f"Needed by: {rfq.needed_by_date.isoformat()}",
        ]
    )

    if reply_to:
        body_lines.extend(
            [
                "",
                "To submit your quotation, please reply directly to this email or send it to:",
                reply_to,
            ]
        )

    if tenant_terms:
        body_lines.extend(["", "Terms:", tenant_terms])

    body = "\n".join(body_lines)

    combined = f"{rfq.tenant_id}:{rfq.id}:{recipient.id}"
    msg_hash = uuid.uuid5(NAMESPACE_RFQ, combined)
    message_id = f"<{msg_hash}@procurepilot.internal>"

    return subject, body, message_id


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

                # First, verify suppliers exist and check contact emails
                rejected_recipients = []
                valid_supplier_ids = []

                for supplier_id in recipient_supplier_ids:
                    cur.execute(
                        "select id, contact_email from supplier where id = %s", (supplier_id,)
                    )
                    row = cur.fetchone()
                    if row is None:
                        rejected_recipients.append(
                            {
                                "supplier_id": str(supplier_id),
                                "reason": "not_found",
                            }
                        )
                    elif not row.get("contact_email"):
                        rejected_recipients.append(
                            {
                                "supplier_id": str(supplier_id),
                                "reason": "missing_contact_email",
                            }
                        )
                    else:
                        valid_supplier_ids.append(supplier_id)

                rfq_id = uuid.uuid4()
                cur.execute(
                    """
                    insert into rfq (
                        id, tenant_id, created_by_membership_id, status, needed_by_date,
                        idempotency_key
                    )
                    values (%s, %s, %s, 'draft', %s, %s)
                    returning id, tenant_id, created_by_membership_id, status,
                              needed_by_date, idempotency_key, created_at
                    """,
                    (
                        rfq_id,
                        member.tenant_id,
                        member.membership_id,
                        needed_by_date,
                        idempotency_key,
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

                cur.execute("select * from rfq where id = %s", (rfq_id,))
                rfq_row = cur.fetchone()
                if not rfq_row:
                    raise NotFoundError(details={"resource": "rfq"})
                rfq = Rfq(**rfq_row)

                cur.execute("select * from rfq_line where rfq_id = %s", (rfq_id,))
                line_rows = cur.fetchall()
                lines = [RfqLine(**r) for r in line_rows]

                product_names = {}
                for line in lines:
                    cur.execute(
                        "select tenant_name from workspace_product where id = %s",
                        (line.workspace_product_id,),
                    )
                    prod_row = cur.fetchone()
                    if prod_row:
                        product_names[line.workspace_product_id] = prod_row["tenant_name"]

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
                    subject, body, msg_id = build_rfq_message(
                        rfq=rfq,
                        lines=lines,
                        product_names=product_names,
                        recipient=recipient,
                        reply_to=reply_to,
                    )

                    send_kwargs = {
                        "to": contact_email,
                        "subject": subject,
                        "body": body,
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
        with _authenticated_db(self.settings, member) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    select r.id, r.quotation_id
                    from rfq_response r
                    join rfq_recipient rec on r.rfq_recipient_id = rec.id
                    where r.id = %s and rec.rfq_id = %s and r.tenant_id = %s
                    """,
                    (rfq_response_id, rfq_id, member.tenant_id),
                )
                resp_row = cur.fetchone()
                if not resp_row:
                    raise NotFoundError(details={"resource": "rfq_response"})

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
                    required_by_date=required_by_date,
                    lines=pr_lines,
                )

        purchase_request, created = RequestsService(self.settings).create_request(
            bearer_token=bearer_token,
            member=member,
            payload=request_payload,
            idempotency_key=idempotency_key,
        )

        if created:
            with _authenticated_db(self.settings, member) as conn:
                with conn.cursor(row_factory=dict_row) as cur:
                    total_amount = 0
                    total_currency: str | None = None

                    cur.execute(
                        "select id, workspace_product_id, quantity from purchase_request_line "
                        "where purchase_request_id = %s and tenant_id = %s",
                        (purchase_request.id, member.tenant_id),
                    )
                    pr_line_rows = cur.fetchall()

                    for prl in pr_line_rows:
                        pid = prl["workspace_product_id"]
                        if pid in matched_lines:
                            q_amt = matched_lines[pid]["unit_price_amount"]
                            q_curr = matched_lines[pid]["unit_price_currency"]
                            qty = prl["quantity"]

                            cur.execute(
                                """
                                update purchase_request_line
                                set estimated_unit_price_amount = %s,
                                    estimated_unit_price_currency = %s,
                                    estimated_unit_price_source_landed_cost_id = null
                                where id = %s and tenant_id = %s
                                """,
                                (q_amt, q_curr, prl["id"], member.tenant_id),
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
                    # closes the sourcing loop for this RFQ.
                    cur.execute(
                        "update rfq set status = 'converted' where id = %s and tenant_id = %s",
                        (rfq_id, member.tenant_id),
                    )

                    conn.commit()

        return RfqPrepareRequestResponse(purchase_request_id=purchase_request.id)

    def create_guardrail(
        self,
        *,
        member: CurrentMember,
        payload: GuardrailCreateInput,
    ) -> AutoPreparationGuardrail:
        with _authenticated_db(self.settings, member) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    insert into auto_preparation_guardrail
                    (tenant_id, created_by_membership_id, max_order_value_amount,
                     max_order_value_currency, supplier_allowlist, category_allowlist,
                     min_response_count, max_price_variance_pct, enabled, default_branch_id)
                    values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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


def _cap_limit(limit: int) -> int:
    return max(1, min(limit, 100))


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

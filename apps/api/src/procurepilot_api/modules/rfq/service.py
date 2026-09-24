import json
import uuid
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import date

import psycopg
from psycopg.rows import dict_row

from procurepilot_api.config import Settings
from procurepilot_api.deps import CurrentMember
from procurepilot_api.errors import NotFoundError, ServiceUnavailableError, UnprocessableEntityError
from procurepilot_api.modules.rfq.schemas import Rfq, RfqLine, RfqRecipient
from procurepilot_api.shared.mailer import get_mailer

NAMESPACE_RFQ = uuid.UUID("361f1073-a8d1-4db8-8d07-28f0907a4a2a")


def build_rfq_message(
    rfq: Rfq,
    lines: Sequence[RfqLine],
    product_names: dict[uuid.UUID, str],
    recipient: RfqRecipient,
    tenant_terms: str | None = None,
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
        cur.execute(
            "select * from rfq_recipient where rfq_id = %s order by created_at", (rfq_id,)
        )
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

                any_sent = False
                updated_recipients = []

                for recipient in draft_recipients:
                    cur.execute(
                        "select contact_email from supplier where id = %s", (recipient.supplier_id,)
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
                    )

                    try:
                        res = mailer.send(
                            to=contact_email,
                            subject=subject,
                            body=body,
                        )
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


def get_rfq_service() -> RfqService:
    from procurepilot_api.config import get_settings

    return RfqService(settings=get_settings())

from __future__ import annotations

from uuid import UUID

import psycopg

from procurepilot_api.modules.ingestion.schemas import SupplierMatchMethod

# T009 (research R3): cascading deterministic supplier match, address -> domain -> thread,
# falling to unmatched (caller routes to the review queue).
#
# R3 assumes a `supplier_contacts` table (per-contact exact email address) for the "address"
# signal. That table does not exist anywhere in this codebase — checked directly, not assumed —
# so "address match" is implemented instead as address MEMORY: has this exact From address been
# successfully matched to a supplier before, for this tenant? That still delivers R3's stated
# purpose ("higher specificity than domain for suppliers sharing a generic domain") without a
# schema addition: once one email from `jane@acme.com` is matched (by domain, thread, or a human
# in the review queue), every later email from that same address matches immediately even if the
# domain is `@gmail.com`.


def match_supplier_by_address_history(
    conn: psycopg.Connection, *, tenant_id: UUID, from_address: str
) -> UUID | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            select supplier_id from ingestion_email_log
            where tenant_id = %(tenant_id)s
              and from_address = %(from_address)s
              and supplier_id is not null
            order by received_at desc
            limit 1
            """,
            {"tenant_id": tenant_id, "from_address": from_address.lower()},
        )
        row = cur.fetchone()
    return UUID(str(row[0])) if row else None


def match_supplier_by_domain(
    conn: psycopg.Connection, *, tenant_id: UUID, from_domain: str
) -> UUID | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            select id from supplier
            where tenant_id = %(tenant_id)s
              and status in ('active', 'preferred')
              and email_domains && array[%(domain)s]::text[]
            order by created_at
            limit 1
            """,
            {"tenant_id": tenant_id, "domain": from_domain.lower()},
        )
        row = cur.fetchone()
    return UUID(str(row[0])) if row else None


def match_supplier_by_thread(
    conn: psycopg.Connection,
    *,
    tenant_id: UUID,
    in_reply_to: str | None,
    references: list[str],
) -> UUID | None:
    thread_ids = [m for m in [in_reply_to, *references] if m]
    if not thread_ids:
        return None
    with conn.cursor() as cur:
        cur.execute(
            """
            select supplier_id from ingestion_email_log
            where tenant_id = %(tenant_id)s
              and message_id = any(%(thread_ids)s)
              and supplier_id is not null
            order by received_at desc
            limit 1
            """,
            {"tenant_id": tenant_id, "thread_ids": thread_ids},
        )
        row = cur.fetchone()
    return UUID(str(row[0])) if row else None


def match_supplier(
    conn: psycopg.Connection,
    *,
    tenant_id: UUID,
    from_address: str,
    from_domain: str,
    in_reply_to: str | None,
    references: list[str],
) -> tuple[UUID | None, SupplierMatchMethod | None]:
    """Cascading match per research R3's Decision: address -> domain -> thread."""
    supplier_id = match_supplier_by_address_history(
        conn, tenant_id=tenant_id, from_address=from_address
    )
    if supplier_id is not None:
        return supplier_id, "address"

    supplier_id = match_supplier_by_domain(conn, tenant_id=tenant_id, from_domain=from_domain)
    if supplier_id is not None:
        return supplier_id, "domain"

    supplier_id = match_supplier_by_thread(
        conn, tenant_id=tenant_id, in_reply_to=in_reply_to, references=references
    )
    if supplier_id is not None:
        return supplier_id, "thread"

    return None, None

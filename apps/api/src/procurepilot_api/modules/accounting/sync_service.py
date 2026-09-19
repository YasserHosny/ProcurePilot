"""Service layer for accounting synchronization (R3.1, US2, task T018).

Implements SyncService:
- Concurrency guard via PostgreSQL advisory lock per connection_id
- Reads connection state and enforces status == 'active'
- Refreshes access tokens and writes refreshed tokens via _service_role_db
- Fetches vendors from connector, performs R3 name-matching, upserts synced_vendor
- Fetches bills from connector (90-day window on initial sync, unbounded on resync)
- Upserts synced_bill with denormalized matched_supplier_id from vendor
- Invokes MatchingService (T019) for automatic matching against purchase_record
- Updates connection.last_synced_at and records audit events
"""

from __future__ import annotations

import json
import logging
from collections.abc import Generator
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from typing import Any
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from procurepilot_api.config import Settings
from procurepilot_api.errors import ConflictError, NotFoundError
from procurepilot_api.modules.accounting.connector import (
    AccountingConnector,
    RawBill,
    RawVendor,
    get_accounting_connector,
)
from procurepilot_api.modules.accounting.matching_service import MatchingService
from procurepilot_api.modules.accounting.quickbooks_client import QuickBooksAuthError
from procurepilot_api.modules.accounting.reconciliation_service import ReconciliationService
from procurepilot_api.modules.accounting.three_way_sync_service import run_three_way_sync
from procurepilot_api.modules.accounting.xero_client import XeroAuthError
from procurepilot_api.shared.audit import AuditEventCreate, AuditOutcome, get_audit_writer
from procurepilot_api.shared.logging import get_trace_id
from procurepilot_api.shared.token_crypto import decrypt_token, encrypt_token

logger = logging.getLogger(__name__)


class AccountingSyncError(Exception):
    """Base exception for accounting synchronization errors."""


class ConnectionNotActiveError(AccountingSyncError):
    """Raised when attempting to sync a connection whose status is not 'active'."""

    def __init__(self, connection_id: UUID, status: str) -> None:
        super().__init__(f"Accounting connection {connection_id} is not active (status: {status})")
        self.connection_id = connection_id
        self.status = status


class TokenRefreshFailedError(AccountingSyncError):
    """Raised when refreshing the accounting OAuth access token fails."""


def _configured_persisted_provider(settings: Settings) -> str:
    """Return the provider value expected in accounting_connection for this mode."""
    return "xero" if settings.accounting_provider_mode == "xero" else "quickbooks"


def _act_as_tenant_sync(conn: psycopg.Connection, tenant_id: UUID) -> None:
    """Set local authenticated role and request.jwt.claims for tenant-scoped worker operations.

    Mirrors modules/ingestion/orchestrator.py's _act_as_tenant pattern. Carries tenant_id
    and role='authenticated' without member_role or sub claims so RLS policies allow
    worker-triggered writes while distinguishing system sessions from real member sessions.
    """
    with conn.cursor() as cur:
        cur.execute("set local role authenticated")
        cur.execute(
            "select set_config('request.jwt.claims', %s, true)",
            (json.dumps({"tenant_id": str(tenant_id), "role": "authenticated"}),),
        )


@contextmanager
def _service_role_db(settings: Settings) -> Generator[psycopg.Connection, None, None]:
    """Open a direct connection as Postgres role service_role.

    RLS is bypassed for service_role! EVERY query through this connection
    MUST explicitly filter by `where id = %(id)s and tenant_id = %(tenant_id)s`.
    Used EXCLUSIVELY for reading and updating accounting_connection.access_token
    and refresh_token (which have no SELECT/UPDATE grant for authenticated role).
    """
    with psycopg.connect(settings.database_url.get_secret_value()) as conn:
        with conn.cursor() as cur:
            cur.execute("set local role service_role")
        yield conn


def _record_audit(
    *,
    tenant_id: UUID,
    action: str,
    target: dict[str, object],
    outcome: AuditOutcome = "success",
    actor_email: str = "accounting-sync@procurepilot.local",
) -> None:
    """Record an audit event for accounting sync operations."""
    try:
        get_audit_writer().record(
            AuditEventCreate(
                tenant_id=tenant_id,
                actor_email=actor_email,
                action=action,
                target=target,
                outcome=outcome,
                trace_id=get_trace_id(),
            ),
            bearer_token=None,
        )
    except Exception:
        logger.exception("Failed to record accounting audit event: %s", action)


class SyncService:
    """T018: Synchronizes vendors and bills from an external accounting provider."""

    def __init__(
        self,
        connector: AccountingConnector | None = None,
        matching_service: MatchingService | None = None,
    ) -> None:
        self._connector = connector
        self._matching_service = matching_service or MatchingService()

    def sync(
        self,
        settings: Settings,
        *,
        tenant_id: UUID,
        connection_id: UUID,
        connector: AccountingConnector | None = None,
    ) -> dict[str, object]:
        """Perform a full synchronization cycle for the specified connection.

        Acquires an advisory lock on connection_id across all operations.
        Returns a result dictionary summarizing synced counts and created matches.
        """
        # Concurrency guard: advisory lock held on dedicated connection
        lock_conn = psycopg.connect(settings.database_url.get_secret_value(), autocommit=True)
        acquired = False
        try:
            with lock_conn.cursor() as cur:
                cur.execute(
                    "select pg_try_advisory_lock(hashtext(%(key)s))",
                    {"key": str(connection_id)},
                )
                row = cur.fetchone()
                acquired = bool(row[0]) if row else False

            if not acquired:
                raise ConflictError(
                    details={
                        "resource": "accounting_connection",
                        "reason": "sync_already_running",
                        "connection_id": str(connection_id),
                    }
                )

            return self._execute_sync(
                settings=settings,
                tenant_id=tenant_id,
                connection_id=connection_id,
                connector=connector,
            )

        finally:
            if acquired:
                try:
                    with lock_conn.cursor() as cur:
                        cur.execute(
                            "select pg_advisory_unlock(hashtext(%(key)s))",
                            {"key": str(connection_id)},
                        )
                except Exception:
                    logger.exception(
                        "Failed to release advisory lock for connection %s",
                        connection_id,
                    )
            lock_conn.close()

    def _execute_sync(
        self,
        *,
        settings: Settings,
        tenant_id: UUID,
        connection_id: UUID,
        connector: AccountingConnector | None = None,
    ) -> dict[str, object]:
        # Read the connection row first via tenant-scoped session
        with psycopg.connect(settings.database_url.get_secret_value()) as conn:
            _act_as_tenant_sync(conn, tenant_id)
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    select id, tenant_id, provider, realm_id, display_name, status,
                           connected_at, last_synced_at
                    from accounting_connection
                    where id = %(id)s and tenant_id = %(tenant_id)s
                    """,
                    {"id": connection_id, "tenant_id": tenant_id},
                )
                conn_row = cur.fetchone()

        if conn_row is None:
            raise NotFoundError(
                details={"resource": "accounting_connection", "id": str(connection_id)}
            )

        status = str(conn_row["status"])
        if status != "active":
            raise ConnectionNotActiveError(connection_id=connection_id, status=status)

        expected_provider = _configured_persisted_provider(settings)
        if (
            connector is None
            and self._connector is None
            and conn_row["provider"] != expected_provider
        ):
            raise AccountingSyncError(
                "Accounting connection provider does not match configured provider mode; "
                "reauthorize the connection before syncing"
            )

        _record_audit(
            tenant_id=tenant_id,
            action="accounting.sync_started",
            target={"accounting_connection_id": str(connection_id)},
            outcome="success",
        )

        try:
            return self._run_sync_pipeline(
                settings=settings,
                tenant_id=tenant_id,
                connection_id=connection_id,
                conn_row=dict(conn_row),
                connector_override=connector,
            )
        except Exception as exc:
            # TokenRefreshFailedError already records sync_failed before raising
            if not isinstance(exc, TokenRefreshFailedError):
                _record_audit(
                    tenant_id=tenant_id,
                    action="accounting.sync_failed",
                    target={
                        "accounting_connection_id": str(connection_id),
                        "error": str(exc),
                    },
                    outcome="refused",
                )
            raise

    def _mark_needs_reauth(
        self,
        *,
        settings: Settings,
        tenant_id: UUID,
        connection_id: UUID,
        operation: str,
        error: QuickBooksAuthError | XeroAuthError,
    ) -> None:
        """Transition an authenticated provider failure without echoing Xero payloads."""
        with psycopg.connect(settings.database_url.get_secret_value()) as worker_conn:
            _act_as_tenant_sync(worker_conn, tenant_id)
            with worker_conn.cursor() as cur:
                cur.execute(
                    """
                    update accounting_connection
                    set status = 'needs_reauth',
                        updated_at = now()
                    where id = %(id)s and tenant_id = %(tenant_id)s
                    """,
                    {"id": connection_id, "tenant_id": tenant_id},
                )
            worker_conn.commit()

        safe_error = (
            "provider_authentication_failed"
            if isinstance(error, XeroAuthError)
            else str(error)
        )
        _record_audit(
            tenant_id=tenant_id,
            action="accounting.sync_failed",
            target={
                "accounting_connection_id": str(connection_id),
                "error": safe_error,
                "reason": f"{operation}_failed",
            },
            outcome="refused",
        )
        raise TokenRefreshFailedError(
            f"Accounting provider authentication failed during {operation}"
        ) from error

    def _run_sync_pipeline(
        self,
        *,
        settings: Settings,
        tenant_id: UUID,
        connection_id: UUID,
        conn_row: dict[str, Any],
        connector_override: AccountingConnector | None,
    ) -> dict[str, object]:
        # 1. Read tokens via _service_role_db (access/refresh tokens are service_role-only)
        with _service_role_db(settings) as sr_conn:
            with sr_conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    select access_token, refresh_token
                    from accounting_connection
                    where id = %(id)s and tenant_id = %(tenant_id)s
                    """,
                    {"id": connection_id, "tenant_id": tenant_id},
                )
                token_row = cur.fetchone()

        access_token = (
            decrypt_token(str(token_row["access_token"]), settings.accounting_token_encryption_key)
            if token_row and token_row.get("access_token")
            else None
        )
        refresh_token = (
            decrypt_token(str(token_row["refresh_token"]), settings.accounting_token_encryption_key)
            if token_row and token_row.get("refresh_token")
            else None
        )

        active_connector = (
            connector_override
            or self._connector
            or get_accounting_connector(
                settings,
                realm_id=conn_row["realm_id"],
                access_token=access_token,
            )
        )

        # 2. Token refresh (research.md R4)
        if hasattr(active_connector, "refresh_access_token") and refresh_token:
            try:
                tokens = active_connector.refresh_access_token(refresh_token)
                access_token = tokens.access_token

                # Persist refreshed tokens via _service_role_db
                with _service_role_db(settings) as sr_conn:
                    with sr_conn.cursor() as cur:
                        cur.execute(
                            """
                            update accounting_connection
                            set access_token = %(access_token)s,
                                refresh_token = %(refresh_token)s,
                                updated_at = now()
                            where id = %(id)s and tenant_id = %(tenant_id)s
                            """,
                            {
                                "id": connection_id,
                                "tenant_id": tenant_id,
                                "access_token": encrypt_token(
                                    tokens.access_token,
                                    settings.accounting_token_encryption_key,
                                ),
                                "refresh_token": encrypt_token(
                                    tokens.refresh_token,
                                    settings.accounting_token_encryption_key,
                                ),
                            },
                        )
                    sr_conn.commit()
            except (QuickBooksAuthError, XeroAuthError) as exc:
                self._mark_needs_reauth(
                    settings=settings,
                    tenant_id=tenant_id,
                    connection_id=connection_id,
                    operation="token_refresh",
                    error=exc,
                )

        # 3. Fetch vendors outside any DB transaction
        try:
            raw_vendors = active_connector.list_vendors()
        except XeroAuthError as exc:
            self._mark_needs_reauth(
                settings=settings,
                tenant_id=tenant_id,
                connection_id=connection_id,
                operation="vendor_fetch",
                error=exc,
            )

        # 4. Upsert vendors via tenant-scoped session
        vendor_map: dict[str, tuple[UUID, UUID | None]] = {}
        with psycopg.connect(settings.database_url.get_secret_value()) as tenant_conn:
            _act_as_tenant_sync(tenant_conn, tenant_id)
            for raw_v in raw_vendors:
                synced_v_id, matched_s_id = self._upsert_vendor(
                    tenant_conn,
                    tenant_id=tenant_id,
                    connection_id=connection_id,
                    raw_vendor=raw_v,
                )
                vendor_map[raw_v.provider_vendor_id] = (synced_v_id, matched_s_id)
            tenant_conn.commit()

        # 5. Determine since date (FR-015: first sync 90-day window; subsequent sync unbounded)
        last_synced_at = conn_row.get("last_synced_at")
        if last_synced_at is None:
            conn_at = conn_row["connected_at"]
            conn_date = conn_at.date() if isinstance(conn_at, datetime) else conn_at
            since = conn_date - timedelta(days=90)
        else:
            since = date(1970, 1, 1)

        # 6. Fetch bills outside any DB transaction
        try:
            raw_bills = active_connector.list_bills(since=since)
        except XeroAuthError as exc:
            self._mark_needs_reauth(
                settings=settings,
                tenant_id=tenant_id,
                connection_id=connection_id,
                operation="bill_fetch",
                error=exc,
            )

        # 7. Upsert bills and perform matching via tenant-scoped session
        with psycopg.connect(settings.database_url.get_secret_value()) as tenant_conn:
            _act_as_tenant_sync(tenant_conn, tenant_id)
            for raw_b in raw_bills:
                self._upsert_bill(
                    tenant_conn,
                    tenant_id=tenant_id,
                    connection_id=connection_id,
                    raw_bill=raw_b,
                    vendor_map=vendor_map,
                )
            tenant_conn.commit()

            # 8. Automatic matching for unmatched bills with matched_supplier_id
            matches_created = self._run_matching(
                tenant_conn,
                tenant_id=tenant_id,
                connection_id=connection_id,
            )
            tenant_conn.commit()

            # 9. Evaluate normalized bills against internal order evidence.  The service
            # deliberately shares this transaction and does not commit or roll it back.
            three_way_summary = run_three_way_sync(
                tenant_conn,
                tenant_id=tenant_id,
                connection_id=connection_id,
            )
            tenant_conn.commit()

            # 10. Update last_synced_at on accounting_connection
            with tenant_conn.cursor() as cur:
                cur.execute(
                    """
                    update accounting_connection
                    set last_synced_at = now(),
                        updated_at = now()
                    where id = %(id)s and tenant_id = %(tenant_id)s
                    """,
                    {"id": connection_id, "tenant_id": tenant_id},
                )
            tenant_conn.commit()

            # 11. Recompute reconciliation discrepancies (US3, T028)
            discrepancy_counts = ReconciliationService().recompute_discrepancies(
                tenant_conn,
                tenant_id=tenant_id,
                connection_id=connection_id,
            )
            tenant_conn.commit()

        summary = {
            "status": "completed",
            "connection_id": str(connection_id),
            "vendors_synced": len(raw_vendors),
            "bills_synced": len(raw_bills),
            "matches_created": matches_created,
            "discrepancies": discrepancy_counts,
            "three_way": three_way_summary.as_dict(),
        }

        _record_audit(
            tenant_id=tenant_id,
            action="accounting.sync_completed",
            target={
                "accounting_connection_id": str(connection_id),
                "vendors_synced": len(raw_vendors),
                "bills_synced": len(raw_bills),
                "matches_created": matches_created,
                "three_way": three_way_summary.as_dict(),
            },
            outcome="success",
        )

        return summary

    def _upsert_vendor(
        self,
        conn: psycopg.Connection,
        *,
        tenant_id: UUID,
        connection_id: UUID,
        raw_vendor: RawVendor,
    ) -> tuple[UUID, UUID | None]:
        """Upsert a single RawVendor into synced_vendor.

        If matched_supplier_id is already set, keeps the existing link (R3).
        If not yet matched, attempts exact case-insensitive name match against supplier.
        """
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                select id, matched_supplier_id
                from synced_vendor
                where tenant_id = %(tenant_id)s
                  and connection_id = %(connection_id)s
                  and provider_vendor_id = %(provider_vendor_id)s
                """,
                {
                    "tenant_id": tenant_id,
                    "connection_id": connection_id,
                    "provider_vendor_id": raw_vendor.provider_vendor_id,
                },
            )
            existing = cur.fetchone()

            matched_supplier_id: UUID | None = None
            if existing is not None and existing["matched_supplier_id"] is not None:
                # Already matched: keep existing matched_supplier_id, do NOT re-match by name
                matched_supplier_id = UUID(str(existing["matched_supplier_id"]))
            else:
                # Not yet matched or new row: attempt exact case-insensitive name match (R3)
                cur.execute(
                    """
                    select id from supplier
                    where tenant_id = %(tenant_id)s
                      and lower(trim(name)) = lower(trim(%(display_name)s))
                    limit 1
                    """,
                    {
                        "tenant_id": tenant_id,
                        "display_name": raw_vendor.display_name,
                    },
                )
                sup_row = cur.fetchone()
                if sup_row is not None:
                    matched_supplier_id = UUID(str(sup_row["id"]))

            cur.execute(
                """
                insert into synced_vendor (
                    tenant_id,
                    connection_id,
                    provider_vendor_id,
                    display_name,
                    matched_supplier_id,
                    created_at,
                    updated_at
                ) values (
                    %(tenant_id)s,
                    %(connection_id)s,
                    %(provider_vendor_id)s,
                    %(display_name)s,
                    %(matched_supplier_id)s,
                    now(),
                    now()
                )
                on conflict (tenant_id, connection_id, provider_vendor_id) do update
                set display_name = excluded.display_name,
                    matched_supplier_id = coalesce(
                        synced_vendor.matched_supplier_id, excluded.matched_supplier_id
                    ),
                    updated_at = now()
                returning id, matched_supplier_id
                """,
                {
                    "tenant_id": tenant_id,
                    "connection_id": connection_id,
                    "provider_vendor_id": raw_vendor.provider_vendor_id,
                    "display_name": raw_vendor.display_name,
                    "matched_supplier_id": matched_supplier_id,
                },
            )
            upserted = cur.fetchone()
            synced_vendor_id = UUID(str(upserted["id"]))
            final_supplier_id = (
                UUID(str(upserted["matched_supplier_id"]))
                if upserted["matched_supplier_id"]
                else None
            )
            return synced_vendor_id, final_supplier_id

    def _upsert_bill(
        self,
        conn: psycopg.Connection,
        *,
        tenant_id: UUID,
        connection_id: UUID,
        raw_bill: RawBill,
        vendor_map: dict[str, tuple[UUID, UUID | None]],
    ) -> UUID:
        """Upsert a single RawBill into synced_bill.

        Copies matched_supplier_id from vendor_map (denormalization per data-model.md).
        Always updates updated_at on conflict to reflect provider-side updates (Scenario 2.4).
        """
        vendor_info = vendor_map.get(raw_bill.provider_vendor_id)
        if vendor_info is None:
            # Fallback: look up in synced_vendor table
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    select id, matched_supplier_id from synced_vendor
                    where tenant_id = %(tenant_id)s
                      and connection_id = %(connection_id)s
                      and provider_vendor_id = %(provider_vendor_id)s
                    """,
                    {
                        "tenant_id": tenant_id,
                        "connection_id": connection_id,
                        "provider_vendor_id": raw_bill.provider_vendor_id,
                    },
                )
                vrow = cur.fetchone()
                if vrow is not None:
                    vendor_id = UUID(str(vrow["id"]))
                    matched_supplier_id = (
                        UUID(str(vrow["matched_supplier_id"]))
                        if vrow["matched_supplier_id"]
                        else None
                    )
                else:
                    # Create placeholder vendor to satisfy foreign key
                    cur.execute(
                        """
                        insert into synced_vendor (
                            tenant_id, connection_id, provider_vendor_id,
                            display_name, matched_supplier_id, created_at, updated_at
                        ) values (
                            %(tenant_id)s, %(connection_id)s, %(provider_vendor_id)s,
                            %(display_name)s, null, now(), now()
                        )
                        returning id, matched_supplier_id
                        """,
                        {
                            "tenant_id": tenant_id,
                            "connection_id": connection_id,
                            "provider_vendor_id": raw_bill.provider_vendor_id,
                            "display_name": f"Vendor {raw_bill.provider_vendor_id}",
                        },
                    )
                    vrow = cur.fetchone()
                    vendor_id = UUID(str(vrow["id"]))
                    matched_supplier_id = None
                vendor_map[raw_bill.provider_vendor_id] = (vendor_id, matched_supplier_id)
        else:
            vendor_id, matched_supplier_id = vendor_info

        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                insert into synced_bill (
                    tenant_id,
                    connection_id,
                    provider_bill_id,
                    vendor_id,
                    matched_supplier_id,
                    amount,
                    currency,
                    bill_date,
                    provider_status,
                    provider_order_reference,
                    document_references,
                    created_at,
                    updated_at
                ) values (
                    %(tenant_id)s,
                    %(connection_id)s,
                    %(provider_bill_id)s,
                    %(vendor_id)s,
                    %(matched_supplier_id)s,
                    %(amount)s,
                    %(currency)s,
                    %(bill_date)s,
                    %(provider_status)s,
                    %(provider_order_reference)s,
                    %(document_references)s::jsonb,
                    now(),
                    now()
                )
                on conflict (tenant_id, connection_id, provider_bill_id) do update
                set vendor_id = excluded.vendor_id,
                    matched_supplier_id = excluded.matched_supplier_id,
                    amount = excluded.amount,
                    currency = excluded.currency,
                    bill_date = excluded.bill_date,
                    provider_status = excluded.provider_status,
                    provider_order_reference = excluded.provider_order_reference,
                    document_references = excluded.document_references,
                    updated_at = now()
                returning id
                """,
                {
                    "tenant_id": tenant_id,
                    "connection_id": connection_id,
                    "provider_bill_id": raw_bill.provider_bill_id,
                    "vendor_id": vendor_id,
                    "matched_supplier_id": matched_supplier_id,
                    "amount": raw_bill.amount,
                    "currency": raw_bill.currency,
                    "bill_date": raw_bill.bill_date,
                    "provider_status": raw_bill.status,
                    "provider_order_reference": raw_bill.provider_order_reference,
                    "document_references": json.dumps(raw_bill.document_references),
                },
            )
            row = cur.fetchone()
            synced_bill_id = UUID(str(row["id"]))
            cur.execute(
                """
                delete from synced_bill_line
                where tenant_id = %(tenant_id)s
                  and synced_bill_id = %(synced_bill_id)s
                """,
                {"tenant_id": tenant_id, "synced_bill_id": synced_bill_id},
            )
            for line in raw_bill.lines:
                cur.execute(
                    """
                    insert into synced_bill_line (
                        tenant_id,
                        synced_bill_id,
                        line_number,
                        provider_line_reference,
                        provider_product_reference,
                        description,
                        quantity,
                        unit_price_amount,
                        unit_price_currency,
                        created_at,
                        updated_at
                    ) values (
                        %(tenant_id)s,
                        %(synced_bill_id)s,
                        %(line_number)s,
                        %(provider_line_reference)s,
                        %(provider_product_reference)s,
                        %(description)s,
                        %(quantity)s,
                        %(unit_price_amount)s,
                        %(unit_price_currency)s,
                        now(),
                        now()
                    )
                    on conflict (tenant_id, synced_bill_id, line_number) do update
                    set provider_line_reference = excluded.provider_line_reference,
                        provider_product_reference = excluded.provider_product_reference,
                        description = excluded.description,
                        quantity = excluded.quantity,
                        unit_price_amount = excluded.unit_price_amount,
                        unit_price_currency = excluded.unit_price_currency,
                        updated_at = now()
                    """,
                    {
                        "tenant_id": tenant_id,
                        "synced_bill_id": synced_bill_id,
                        "line_number": line.line_number,
                        "provider_line_reference": line.provider_line_reference,
                        "provider_product_reference": line.provider_product_reference,
                        "description": line.description,
                        "quantity": line.quantity,
                        "unit_price_amount": line.unit_price_amount,
                        "unit_price_currency": line.unit_price_currency,
                    },
                )
            return synced_bill_id

    def _run_matching(
        self,
        conn: psycopg.Connection,
        *,
        tenant_id: UUID,
        connection_id: UUID,
    ) -> int:
        """Attempt automatic matching for all eligible synced bills."""
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                select b.id, b.tenant_id, b.connection_id, b.provider_bill_id,
                       b.vendor_id, b.matched_supplier_id, b.amount, b.currency,
                       b.bill_date, b.provider_status
                from synced_bill b
                where b.tenant_id = %(tenant_id)s
                  and b.connection_id = %(connection_id)s
                  and b.matched_supplier_id is not null
                  and not exists (
                      select 1 from purchase_bill_match m
                      where m.tenant_id = %(tenant_id)s and m.synced_bill_id = b.id
                  )
                """,
                {"tenant_id": tenant_id, "connection_id": connection_id},
            )
            bills = cur.fetchall()

        matches_created = 0
        for bill_row in bills:
            matched_id = self._matching_service.match_bill(
                conn,
                tenant_id=tenant_id,
                bill_row=dict(bill_row),
            )
            if matched_id is not None:
                matches_created += 1

        return matches_created


def get_sync_service() -> SyncService:
    """Factory returning a SyncService instance."""
    return SyncService()

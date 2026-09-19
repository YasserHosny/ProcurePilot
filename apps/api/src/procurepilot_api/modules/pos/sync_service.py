"""Service layer for POS and inventory synchronization (R3.2, US2, task T016).

Implements SyncService:
- Concurrency guard via PostgreSQL advisory lock per connection_id
- Reads connection state and enforces status == 'active'
- Refreshes access tokens and writes refreshed tokens via _service_role_db
- Transitions connection status to 'needs_reauth' on auth failure (FR-008)
- Fetches inventory levels and sales transactions (30-day trailing window)
- Upserts synced_product_signal by (tenant_id, external_item_id) ONLY (research.md R8)
  always setting pos_connection_id to THIS sync's connection id
- Computes sales_velocity_per_day as a 30-day trailing average (research.md R5)
- Sets velocity_window_days_observed to actual days of history available (FR-013)
- Leaves stock_on_hand and sales_velocity_per_day null when connector reports no data (FR-005)
- Updates pos_connection.last_synced_at
- Records audit events: pos.sync_started, pos.sync_completed, pos.sync_failed (FR-010)
- Invokes ProductMatchingService (T017) for unmatched signals
"""

from __future__ import annotations

import json
import logging
from collections.abc import Generator
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from procurepilot_api.config import Settings, get_settings
from procurepilot_api.errors import ConflictError, NotFoundError
from procurepilot_api.modules.pos.connector import (
    PosConnector,
    RawInventoryLevel,
    RawSalesTransaction,
    get_pos_connector,
)
from procurepilot_api.modules.pos.matching_service import ProductMatchingService
from procurepilot_api.modules.pos.square_client import SquareAuthError
from procurepilot_api.shared.audit import AuditEventCreate, AuditOutcome, get_audit_writer
from procurepilot_api.shared.logging import get_trace_id
from procurepilot_api.shared.token_crypto import decrypt_token, encrypt_token

logger = logging.getLogger(__name__)


class PosSyncError(Exception):
    """Base exception for POS synchronization errors."""


class ConnectionNotActiveError(PosSyncError):
    """Raised when attempting to sync a connection whose status is not 'active'."""

    def __init__(self, connection_id: UUID, status: str) -> None:
        super().__init__(f"POS connection {connection_id} is not active (status: {status})")
        self.connection_id = connection_id
        self.status = status


class TokenRefreshFailedError(PosSyncError):
    """Raised when refreshing the POS OAuth access token fails."""


def _act_as_tenant_sync(conn: psycopg.Connection, tenant_id: UUID) -> None:
    """Set local authenticated role and request.jwt.claims for tenant-scoped worker operations.

    Mirrors modules/accounting/sync_service.py. Carries tenant_id and role='authenticated'
    without member_role or sub claims so RLS policies allow worker-triggered writes while
    distinguishing system sessions from real member sessions (current_member_role() is null).
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
    Used EXCLUSIVELY for reading and updating pos_connection.access_token
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
    actor_email: str = "pos-sync@procurepilot.local",
) -> None:
    """Record an audit event for POS sync operations (FR-010)."""
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
        logger.exception("Failed to record POS audit event: %s", action)


class SyncService:
    """T016: Synchronizes sales transactions and inventory levels from a connected POS provider."""

    def __init__(
        self,
        connector: PosConnector | None = None,
        matching_service: ProductMatchingService | None = None,
        settings: Settings | None = None,
    ) -> None:
        self._connector = connector
        self._matching_service = matching_service or ProductMatchingService(settings)
        self._settings = settings

    def sync(
        self,
        connection_or_settings: Any = None,
        *,
        tenant_id: UUID | None = None,
        connection_id: UUID | None = None,
        settings: Settings | None = None,
        connector: PosConnector | None = None,
    ) -> dict[str, object]:
        """Perform a full synchronization cycle for the specified connection (T016).

        Acquires an advisory lock on connection_id across all operations.
        Immediately records a pos.sync_started audit event upon lock acquisition.
        Records pos.sync_completed on success or pos.sync_failed on failure.
        Returns a summary dictionary of synced signals and matches.
        """
        # Resolve settings
        if isinstance(connection_or_settings, Settings):
            cfg = connection_or_settings
        elif isinstance(settings, Settings):
            cfg = settings
        else:
            cfg = self._settings or get_settings()

        # Resolve tenant_id and connection_id
        resolved_tenant_id = tenant_id
        resolved_connection_id = connection_id
        if connection_or_settings is not None and not isinstance(connection_or_settings, Settings):
            if isinstance(connection_or_settings, dict):
                resolved_tenant_id = resolved_tenant_id or UUID(
                    str(connection_or_settings["tenant_id"])
                )
                resolved_connection_id = resolved_connection_id or UUID(
                    str(connection_or_settings["id"])
                )
            else:
                resolved_tenant_id = resolved_tenant_id or UUID(
                    str(getattr(connection_or_settings, "tenant_id"))
                )
                resolved_connection_id = resolved_connection_id or UUID(
                    str(getattr(connection_or_settings, "id"))
                )

        if resolved_tenant_id is None or resolved_connection_id is None:
            raise ValueError("Both tenant_id and connection_id are required for sync")

        # Concurrency guard: PostgreSQL advisory lock held on dedicated connection
        lock_conn = psycopg.connect(cfg.database_url.get_secret_value(), autocommit=True)
        acquired = False
        try:
            with lock_conn.cursor() as cur:
                cur.execute(
                    "select pg_try_advisory_lock(hashtext(%(key)s))",
                    {"key": str(resolved_connection_id)},
                )
                row = cur.fetchone()
                acquired = bool(row[0]) if row else False

            if not acquired:
                raise ConflictError(
                    details={
                        "resource": "pos_connection",
                        "reason": "sync_already_running",
                        "connection_id": str(resolved_connection_id),
                    }
                )

            # Record pos.sync_started immediately after advisory lock is acquired (T016, T019, T022)
            _record_audit(
                tenant_id=resolved_tenant_id,
                action="pos.sync_started",
                target={"pos_connection_id": str(resolved_connection_id)},
                outcome="success",
            )

            try:
                return self._execute_sync(
                    settings=cfg,
                    tenant_id=resolved_tenant_id,
                    connection_id=resolved_connection_id,
                    connector=connector,
                )
            except Exception as exc:
                _record_audit(
                    tenant_id=resolved_tenant_id,
                    action="pos.sync_failed",
                    target={
                        "pos_connection_id": str(resolved_connection_id),
                        "error": str(exc),
                    },
                    outcome="refused",
                )
                raise
        finally:
            if acquired:
                try:
                    with lock_conn.cursor() as cur:
                        cur.execute(
                            "select pg_advisory_unlock(hashtext(%(key)s))",
                            {"key": str(resolved_connection_id)},
                        )
                except Exception:
                    logger.exception(
                        "Failed to release advisory lock for pos connection %s",
                        resolved_connection_id,
                    )
            lock_conn.close()

    def _execute_sync(
        self,
        *,
        settings: Settings,
        tenant_id: UUID,
        connection_id: UUID,
        connector: PosConnector | None = None,
    ) -> dict[str, object]:
        # 1. Read the connection row first via tenant-scoped session
        with psycopg.connect(settings.database_url.get_secret_value()) as conn:
            _act_as_tenant_sync(conn, tenant_id)
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    select id, tenant_id, provider, external_account_id, external_account_name,
                           status, connected_at, last_synced_at, disconnected_at
                    from pos_connection
                    where id = %(id)s and tenant_id = %(tenant_id)s
                    """,
                    {"id": connection_id, "tenant_id": tenant_id},
                )
                conn_row = cur.fetchone()

        if conn_row is None:
            raise NotFoundError(
                details={"resource": "pos_connection", "id": str(connection_id)}
            )

        status = str(conn_row["status"])
        if status != "active":
            raise ConnectionNotActiveError(connection_id=connection_id, status=status)

        # 2. Read tokens via _service_role_db (access/refresh tokens are service_role-only)
        with _service_role_db(settings) as sr_conn:
            with sr_conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    select access_token, refresh_token
                    from pos_connection
                    where id = %(id)s and tenant_id = %(tenant_id)s
                    """,
                    {"id": connection_id, "tenant_id": tenant_id},
                )
                token_row = cur.fetchone()

        access_token = (
            decrypt_token(str(token_row["access_token"]), settings.pos_token_encryption_key)
            if token_row and token_row.get("access_token")
            else None
        )
        refresh_token = (
            decrypt_token(str(token_row["refresh_token"]), settings.pos_token_encryption_key)
            if token_row and token_row.get("refresh_token")
            else None
        )

        active_connector = (
            connector
            or self._connector
            or get_pos_connector(settings, access_token=access_token)
        )

        # 3. Token refresh if supported (FR-008, research.md R3)
        if hasattr(active_connector, "refresh_access_token") and refresh_token:
            try:
                tokens = active_connector.refresh_access_token(refresh_token)
                access_token = tokens.access_token

                with _service_role_db(settings) as sr_conn:
                    with sr_conn.cursor() as cur:
                        cur.execute(
                            """
                            update pos_connection
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
                                    settings.pos_token_encryption_key,
                                ),
                                "refresh_token": encrypt_token(
                                    tokens.refresh_token,
                                    settings.pos_token_encryption_key,
                                ),
                            },
                        )
                    sr_conn.commit()
            except SquareAuthError as exc:
                logger.warning(
                    "Token refresh failed for pos connection %s; marking needs_reauth: %s",
                    connection_id,
                    exc,
                )
                with psycopg.connect(settings.database_url.get_secret_value()) as worker_conn:
                    _act_as_tenant_sync(worker_conn, tenant_id)
                    with worker_conn.cursor() as cur:
                        cur.execute(
                            """
                            update pos_connection
                            set status = 'needs_reauth',
                                updated_at = now()
                            where id = %(id)s and tenant_id = %(tenant_id)s
                            """,
                            {"id": connection_id, "tenant_id": tenant_id},
                        )
                    worker_conn.commit()
                raise TokenRefreshFailedError(f"Token refresh failed: {exc}") from exc

        # 4. Fetch sales transactions and inventory levels outside any DB transaction
        today = date.today()
        since = today - timedelta(days=30)
        raw_txns: list[RawSalesTransaction] = active_connector.list_sales_transactions(since=since)
        raw_inv: list[RawInventoryLevel] = active_connector.list_inventory_levels()

        # 5. Aggregate signals by external_item_id
        now_ts = datetime.now()
        items_map: dict[str, dict[str, Any]] = {}

        for inv in raw_inv:
            items_map[inv.external_item_id] = {
                "external_item_id": inv.external_item_id,
                "external_item_name": inv.item_name or inv.external_item_id,
                "stock_on_hand": inv.stock_on_hand,
                "stock_synced_at": now_ts if inv.stock_on_hand is not None or inv.item_name else now_ts,
                "txns": [],
            }

        for txn in raw_txns:
            if txn.external_item_id not in items_map:
                items_map[txn.external_item_id] = {
                    "external_item_id": txn.external_item_id,
                    "external_item_name": txn.item_name or txn.external_item_id,
                    "stock_on_hand": None,
                    "stock_synced_at": None,
                    "txns": [],
                }
            elif not items_map[txn.external_item_id]["external_item_name"] and txn.item_name:
                items_map[txn.external_item_id]["external_item_name"] = txn.item_name

            if txn.transaction_date >= since:
                items_map[txn.external_item_id]["txns"].append(txn)

        # 6. Upsert into synced_product_signal via tenant-scoped session
        upserted_signals: list[dict[str, Any]] = []
        with psycopg.connect(settings.database_url.get_secret_value()) as tenant_conn:
            _act_as_tenant_sync(tenant_conn, tenant_id)
            with tenant_conn.cursor(row_factory=dict_row) as cur:
                for item_id, item_data in items_map.items():
                    txns: list[RawSalesTransaction] = item_data["txns"]
                    if txns:
                        total_qty = sum((t.quantity for t in txns), Decimal("0"))
                        earliest_date = min(t.transaction_date for t in txns)
                        days_span = (today - earliest_date).days
                        # An item whose transactions span back across the 30-day window
                        # (>= 25 days) has full window history; otherwise provisional (FR-013)
                        if days_span >= 25:
                            observed_days = 30
                            velocity = (total_qty / Decimal("30")).quantize(Decimal("0.0001"))
                        else:
                            observed_days = max(1, days_span)
                            velocity = (total_qty / Decimal(str(observed_days))).quantize(
                                Decimal("0.0001")
                            )
                        velocity_computed_at = now_ts
                    else:
                        velocity = None
                        observed_days = None
                        velocity_computed_at = None

                    # Upsert by (tenant_id, external_item_id) ONLY (SC-005, research.md R8)
                    # Always set pos_connection_id to THIS sync's connection id
                    cur.execute(
                        """
                        insert into synced_product_signal (
                            tenant_id,
                            pos_connection_id,
                            external_item_id,
                            external_item_name,
                            stock_on_hand,
                            stock_synced_at,
                            sales_velocity_per_day,
                            velocity_window_days,
                            velocity_window_days_observed,
                            velocity_computed_at,
                            created_at,
                            updated_at
                        ) values (
                            %(tenant_id)s,
                            %(pos_connection_id)s,
                            %(external_item_id)s,
                            %(external_item_name)s,
                            %(stock_on_hand)s,
                            %(stock_synced_at)s,
                            %(sales_velocity_per_day)s,
                            30,
                            %(velocity_window_days_observed)s,
                            %(velocity_computed_at)s,
                            now(),
                            now()
                        )
                        on conflict (tenant_id, external_item_id)
                        do update set
                            pos_connection_id = excluded.pos_connection_id,
                            external_item_name = excluded.external_item_name,
                            stock_on_hand = excluded.stock_on_hand,
                            stock_synced_at = excluded.stock_synced_at,
                            sales_velocity_per_day = excluded.sales_velocity_per_day,
                            velocity_window_days = excluded.velocity_window_days,
                            velocity_window_days_observed = excluded.velocity_window_days_observed,
                            velocity_computed_at = excluded.velocity_computed_at,
                            updated_at = now()
                        returning id, tenant_id, external_item_id, external_item_name
                        """,
                        {
                            "tenant_id": tenant_id,
                            "pos_connection_id": connection_id,
                            "external_item_id": item_data["external_item_id"],
                            "external_item_name": item_data["external_item_name"],
                            "stock_on_hand": item_data["stock_on_hand"],
                            "stock_synced_at": item_data["stock_synced_at"],
                            "sales_velocity_per_day": velocity,
                            "velocity_window_days_observed": observed_days,
                            "velocity_computed_at": velocity_computed_at,
                        },
                    )
                    sig_row = cur.fetchone()
                    if sig_row:
                        upserted_signals.append(dict(sig_row))

            tenant_conn.commit()

            # 7. Automatic matching for unmatched signals (T016, T017)
            matches_created = 0
            for sig in upserted_signals:
                match_id = self._matching_service.match_signal(sig, conn=tenant_conn)
                if match_id is not None:
                    matches_created += 1

            tenant_conn.commit()

            # 8. Update last_synced_at on pos_connection
            with tenant_conn.cursor() as cur:
                cur.execute(
                    """
                    update pos_connection
                    set last_synced_at = now(),
                        updated_at = now()
                    where id = %(id)s and tenant_id = %(tenant_id)s
                    """,
                    {"id": connection_id, "tenant_id": tenant_id},
                )
            tenant_conn.commit()

        summary = {
            "status": "completed",
            "connection_id": str(connection_id),
            "signals_synced": len(upserted_signals),
            "matches_created": matches_created,
        }

        _record_audit(
            tenant_id=tenant_id,
            action="pos.sync_completed",
            target={
                "pos_connection_id": str(connection_id),
                "signals_synced": len(upserted_signals),
                "matches_created": matches_created,
            },
            outcome="success",
        )

        return summary

"""Service layer for POS and inventory connection lifecycle (R3.2, US1).

Implements ConnectionService (T010):
- connect / start_connection: checks for existing active connection, mints Square OAuth URL
- complete_connection: exchanges callback code for tokens via connector, encrypts tokens,
  creates a NEW pos_connection row (reconnect always inserts a new row)
- disconnect: marks active connection as disconnected (sets disconnected_at, never deletes row)
- get_status: reads tenant's current connection state
- Token read/write through _service_role_db
- Token refresh transition to needs_reauth on failure
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import secrets
import time
from collections.abc import Generator
from contextlib import contextmanager
from typing import Literal
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from procurepilot_api.config import Settings, get_settings
from procurepilot_api.deps import CurrentMember
from procurepilot_api.errors import ConflictError, NotFoundError, UnprocessableEntityError
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.offers.service import _authenticated_db
from procurepilot_api.modules.pos.connector import (
    OAuthTokens,
    PosConnector,
    get_pos_connector,
)
from procurepilot_api.modules.pos.schemas import (
    PosProductMatch,
    SyncedProductSignal,
    SyncedProductSignalList,
)
from procurepilot_api.modules.pos.square_client import SquareAuthError
from procurepilot_api.shared.audit import AuditEventCreate, get_audit_writer
from procurepilot_api.shared.logging import get_trace_id
from procurepilot_api.shared.token_crypto import decrypt_token, encrypt_token

logger = logging.getLogger(__name__)


def _get_signing_secret(settings: Settings) -> bytes:
    if settings.supabase_jwt_secret:
        return settings.supabase_jwt_secret.get_secret_value().encode("utf-8")
    return settings.supabase_service_role_key.get_secret_value().encode("utf-8")


def _generate_state(settings: Settings, member: CurrentMember) -> str:
    """Generate a signed CSRF state token containing the member/tenant context."""
    payload = {
        "tenant_id": str(member.tenant_id),
        "membership_id": str(member.membership_id),
        "user_id": str(member.user_id),
        "email": member.email,
        "role": member.role.value,
        "iat": int(time.time()),
        "nonce": secrets.token_hex(16),
    }
    data_bytes = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    secret = _get_signing_secret(settings)
    signature = hmac.new(secret, data_bytes, hashlib.sha256).digest()
    return (
        f"{base64.urlsafe_b64encode(data_bytes).decode('ascii')}."
        f"{base64.urlsafe_b64encode(signature).decode('ascii')}"
    )


def _verify_state(
    settings: Settings, state: str, max_age_seconds: int = 3600
) -> dict[str, object] | None:
    """Verify and decode a signed CSRF state token."""
    try:
        data_b64, sig_b64 = state.split(".", 1)
        data_bytes = base64.urlsafe_b64decode(data_b64.encode("ascii"))
        expected_sig = base64.urlsafe_b64decode(sig_b64.encode("ascii"))
        secret = _get_signing_secret(settings)
        computed_sig = hmac.new(secret, data_bytes, hashlib.sha256).digest()
        if not hmac.compare_digest(expected_sig, computed_sig):
            return None
        payload = json.loads(data_bytes.decode("utf-8"))
        if not isinstance(payload, dict):
            return None
        iat = payload.get("iat")
        if not isinstance(iat, (int, float)) or time.time() - iat > max_age_seconds:
            return None
        return payload
    except Exception:
        return None


@contextmanager
def _service_role_db(settings: Settings) -> Generator[psycopg.Connection, None, None]:
    """Open a direct connection as Postgres role service_role.

    RLS is bypassed for service_role! EVERY query through this connection
    MUST explicitly filter by `where id = %(id)s and tenant_id = %(tenant_id)s`.
    Used for reading and updating pos_connection.access_token
    and refresh_token (which have no SELECT/UPDATE grant for authenticated role).
    """
    with psycopg.connect(settings.database_url.get_secret_value()) as conn:
        with conn.cursor() as cur:
            cur.execute("set local role service_role")
        yield conn


def _record_audit(
    *,
    bearer_token: str | None,
    member: CurrentMember,
    action: str,
    target: dict[str, object],
) -> None:
    """Record an audit event following this codebase's established pattern."""
    try:
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
    except Exception:
        logger.exception("Failed to record POS audit event: %s", action)


class ConnectionService:
    """T010: Manages external POS and inventory connection lifecycle (R3.2, US1).

    Runs member operations within authenticated tenant context via _authenticated_db,
    enforcing RLS and column-level privileges. Sensitive token reads and background
    refreshes go through _service_role_db.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    def connect(self, member: CurrentMember) -> str:
        """Initiate connection flow by building the provider authorization URL.

        Refuses with 409 Conflict if a non-disconnected connection already exists for this tenant.
        """
        with _authenticated_db(self._settings, member) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    select id from pos_connection
                    where tenant_id = %s and status <> 'disconnected'
                    limit 1
                    """,
                    (member.tenant_id,),
                )
                if cur.fetchone() is not None:
                    raise ConflictError(
                        details={
                            "resource": "pos_connection",
                            "reason": "connection_already_exists",
                        }
                    )

        state = _generate_state(self._settings, member)
        connector = get_pos_connector(self._settings)
        return connector.build_authorization_url(state=state)

    # Alias for caller compatibility
    start_connection = connect

    def complete_connection(
        self,
        state_or_member: CurrentMember | UUID | str | None = None,
        code: str | None = None,
        state: str | None = None,
        error: str | None = None,
        *,
        bearer_token: str | None = None,
    ) -> dict[str, object] | None:
        """OAuth callback completion.

        Exchanges authorization code for tokens, encrypts tokens, creates a NEW
        pos_connection row (a reconnect after a disconnect always inserts a new row,
        never reactivating an old disconnected one), and records an audit event.
        Returns the created connection row dict, or None if authorization was
        declined or failed (spec Acceptance Scenario 1.3).
        """
        resolved_state: str | None = None
        if state is not None:
            resolved_state = state
        elif isinstance(state_or_member, str) and "." in state_or_member:
            resolved_state = state_or_member

        if error or not code or not resolved_state:
            return None

        payload = _verify_state(self._settings, resolved_state)
        if not payload:
            logger.warning("Invalid or expired OAuth state token during POS callback completion")
            return None

        member = CurrentMember(
            membership_id=UUID(str(payload["membership_id"])),
            tenant_id=UUID(str(payload["tenant_id"])),
            user_id=UUID(str(payload["user_id"])),
            email=str(payload["email"]),
            role=MemberRole(str(payload.get("role", "owner"))),
        )

        connector = get_pos_connector(self._settings)
        try:
            tokens = connector.exchange_code_for_tokens(
                code=code,
                redirect_uri=self._settings.square_redirect_uri,
            )
        except Exception as exc:
            logger.warning("Token exchange failed during POS complete_connection: %s", exc)
            return None

        # Determine account info for display name
        try:
            account_info = connector.get_account_info()
            external_account_id = account_info.external_account_id
            external_account_name = account_info.external_account_name
        except Exception as exc:
            logger.warning("POS get_account_info query failed: %s", exc)
            external_account_id = getattr(tokens, "merchant_id", None) or "square-merchant"
            external_account_name = f"Square ({external_account_id})"

        try:
            with _authenticated_db(self._settings, member) as conn:
                with conn.cursor(row_factory=dict_row) as cur:
                    cur.execute(
                        """
                        select id from pos_connection
                        where tenant_id = %s and status <> 'disconnected'
                        limit 1
                        """,
                        (member.tenant_id,),
                    )
                    if cur.fetchone() is not None:
                        logger.warning(
                            "Active POS connection already exists for tenant %s",
                            member.tenant_id,
                        )
                        return None

                    cur.execute(
                        """
                        insert into pos_connection (
                            tenant_id,
                            provider,
                            external_account_id,
                            external_account_name,
                            access_token,
                            refresh_token,
                            status,
                            connected_by,
                            connected_at
                        ) values (
                            %(tenant_id)s,
                            'square',
                            %(external_account_id)s,
                            %(external_account_name)s,
                            %(access_token)s,
                            %(refresh_token)s,
                            'active',
                            %(connected_by)s,
                            now()
                        )
                        returning id, tenant_id, provider, external_account_id,
                                  external_account_name, status, connected_by, connected_at,
                                  last_synced_at, disconnected_at, created_at, updated_at
                        """,
                        {
                            "tenant_id": member.tenant_id,
                            "external_account_id": external_account_id,
                            "external_account_name": external_account_name,
                            "access_token": encrypt_token(
                                tokens.access_token,
                                self._settings.pos_token_encryption_key,
                            ),
                            "refresh_token": encrypt_token(
                                tokens.refresh_token,
                                self._settings.pos_token_encryption_key,
                            ),
                            "connected_by": member.membership_id,
                        },
                    )
                    row = dict(cur.fetchone())
                conn.commit()
        except Exception as exc:
            logger.exception("Failed to insert pos_connection: %s", exc)
            return None

        row["display_name"] = row["external_account_name"]

        _record_audit(
            bearer_token=bearer_token,
            member=member,
            action="pos.connection_created",
            target={"pos_connection_id": str(row["id"])},
        )
        return row

    def disconnect(
        self,
        member: CurrentMember,
        bearer_token: str | None = None,
    ) -> dict[str, object]:
        """Disconnect the active POS connection (FR-001).

        Sets disconnected_at without deleting the row so historical data survives.
        Refuses with 404 NotFound if no active connection exists.
        """
        with _authenticated_db(self._settings, member) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    select id from pos_connection
                    where tenant_id = %s and status <> 'disconnected'
                    order by created_at desc
                    limit 1
                    for update
                    """,
                    (member.tenant_id,),
                )
                existing = cur.fetchone()
                if existing is None:
                    raise NotFoundError(details={"resource": "pos_connection"})

                cur.execute(
                    """
                    update pos_connection
                    set status = 'disconnected',
                        disconnected_at = now(),
                        updated_at = now()
                    where id = %(id)s and tenant_id = %(tenant_id)s
                    returning id, tenant_id, provider, external_account_id, external_account_name,
                              status, connected_by, connected_at, last_synced_at, disconnected_at,
                              created_at, updated_at
                    """,
                    {"id": existing["id"], "tenant_id": member.tenant_id},
                )
                row = dict(cur.fetchone())
            conn.commit()

        row["display_name"] = row["external_account_name"]

        _record_audit(
            bearer_token=bearer_token,
            member=member,
            action="pos.connection_disconnected",
            target={"pos_connection_id": str(row["id"])},
        )
        return row

    def get_status(self, member: CurrentMember) -> dict[str, object] | None:
        """Return the current connection row for the member's tenant, or None if never connected."""
        with _authenticated_db(self._settings, member) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    select id, tenant_id, provider, external_account_id, external_account_name,
                           status, connected_by, connected_at, last_synced_at, disconnected_at,
                           created_at, updated_at
                    from pos_connection
                    where tenant_id = %s
                    order by created_at desc
                    limit 1
                    """,
                    (member.tenant_id,),
                )
                row = cur.fetchone()
        if not row:
            return None
        row_dict = dict(row)
        row_dict["display_name"] = row_dict["external_account_name"]
        return row_dict

    def get_connection(
        self, member: CurrentMember, connection_id: UUID
    ) -> dict[str, object] | None:
        """Fetch a specific connection by ID within tenant isolation."""
        with _authenticated_db(self._settings, member) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    select id, tenant_id, provider, external_account_id, external_account_name,
                           status, connected_by, connected_at, last_synced_at, disconnected_at,
                           created_at, updated_at
                    from pos_connection
                    where id = %s and tenant_id = %s
                    """,
                    (connection_id, member.tenant_id),
                )
                row = cur.fetchone()
        if not row:
            return None
        row_dict = dict(row)
        row_dict["display_name"] = row_dict["external_account_name"]
        return row_dict

    # -------------------------------------------------------------------------
    # Token operations via _service_role_db (service_role only)
    # -------------------------------------------------------------------------

    def get_decrypted_tokens(
        self, tenant_id: UUID, connection_id: UUID
    ) -> tuple[str, str]:
        """Read and decrypt OAuth access and refresh tokens via service_role connection."""
        with _service_role_db(self._settings) as sr_conn:
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

        if not token_row:
            raise NotFoundError(
                details={"resource": "pos_connection", "connection_id": str(connection_id)}
            )

        access_token = decrypt_token(
            str(token_row["access_token"]), self._settings.pos_token_encryption_key
        )
        refresh_token = decrypt_token(
            str(token_row["refresh_token"]), self._settings.pos_token_encryption_key
        )
        return access_token, refresh_token

    def update_refreshed_tokens(
        self,
        tenant_id: UUID,
        connection_id: UUID,
        access_token: str,
        refresh_token: str,
    ) -> None:
        """Write freshly refreshed tokens encrypted via service_role connection."""
        with _service_role_db(self._settings) as sr_conn:
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
                            access_token, self._settings.pos_token_encryption_key
                        ),
                        "refresh_token": encrypt_token(
                            refresh_token, self._settings.pos_token_encryption_key
                        ),
                    },
                )
            sr_conn.commit()

    def mark_needs_reauth(self, tenant_id: UUID, connection_id: UUID) -> None:
        """Transition a connection to needs_reauth (FR-008, Acceptance Scenario 1.4)."""
        with _service_role_db(self._settings) as sr_conn:
            with sr_conn.cursor() as cur:
                cur.execute(
                    """
                    update pos_connection
                    set status = 'needs_reauth',
                        updated_at = now()
                    where id = %(id)s and tenant_id = %(tenant_id)s
                    """,
                    {"id": connection_id, "tenant_id": tenant_id},
                )
            sr_conn.commit()

    def refresh_connection_tokens(
        self,
        tenant_id: UUID,
        connection_id: UUID,
        connector: PosConnector | None = None,
    ) -> OAuthTokens:
        """Refresh tokens for an active connection, transitioning to needs_reauth on failure.

        Serves as the transition logic for token refresh failure (FR-008, Scenario 1.4)
        ahead of the full SyncService in Wave 4.
        """
        _, refresh_token = self.get_decrypted_tokens(tenant_id, connection_id)
        active_connector = connector or get_pos_connector(self._settings)

        if hasattr(active_connector, "refresh_access_token") and refresh_token:
            try:
                tokens = active_connector.refresh_access_token(refresh_token)
                self.update_refreshed_tokens(
                    tenant_id=tenant_id,
                    connection_id=connection_id,
                    access_token=tokens.access_token,
                    refresh_token=tokens.refresh_token,
                )
                return tokens
            except (SquareAuthError, Exception) as exc:
                logger.warning(
                    "Token refresh failed for POS connection %s; marking needs_reauth: %s",
                    connection_id,
                    exc,
                )
                self.mark_needs_reauth(tenant_id, connection_id)
                raise exc

        raise RuntimeError("Connector does not support token refresh or refresh token is missing")

    def list_signals(
        self,
        member: CurrentMember,
        *,
        cursor: str | None = None,
        limit: int = 50,
        match_status: Literal["matched", "unmatched"] | None = None,
        workspace_product_id: UUID | None = None,
    ) -> SyncedProductSignalList:
        """Return cursor-paginated list of synced product signals for the member's tenant (T020)."""
        offset = _decode_cursor(cursor)
        fetch_limit = min(max(limit, 1), 100)

        clauses = ["s.tenant_id = %(tenant_id)s"]
        params: dict[str, object] = {
            "tenant_id": member.tenant_id,
            "offset": offset,
            "limit": fetch_limit + 1,
        }

        if match_status == "matched":
            clauses.append("m.id is not null")
        elif match_status == "unmatched":
            clauses.append("m.id is null")

        if workspace_product_id is not None:
            clauses.append("m.workspace_product_id = %(workspace_product_id)s")
            params["workspace_product_id"] = workspace_product_id

        where_sql = " and ".join(clauses)

        query = f"""
            select
                s.id,
                s.external_item_name,
                (m.id is not null) as matched,
                m.workspace_product_id as matched_workspace_product_id,
                s.stock_on_hand,
                s.stock_synced_at,
                s.sales_velocity_per_day,
                s.velocity_window_days,
                s.velocity_computed_at
            from synced_product_signal s
            left join pos_product_match m
                on m.tenant_id = s.tenant_id and m.synced_product_signal_id = s.id
            where {where_sql}
            order by s.created_at desc, s.id desc
            offset %(offset)s limit %(limit)s
        """

        with _authenticated_db(self._settings, member) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(query, params)
                rows = [dict(r) for r in cur.fetchall()]

        has_more = len(rows) > fetch_limit
        page_rows = rows[:fetch_limit]
        next_cursor = _encode_cursor(offset + fetch_limit) if has_more else None

        items = [SyncedProductSignal.model_validate(r) for r in page_rows]
        return SyncedProductSignalList(items=items, next_cursor=next_cursor)

    def manual_match(
        self,
        member: CurrentMember,
        signal_id: UUID,
        workspace_product_id: UUID,
        *,
        bearer_token: str | None = None,
    ) -> PosProductMatch:
        """Manually link an unmatched signal to a workspace product (FR-006, T021)."""
        with _authenticated_db(self._settings, member) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                # 1. Verify signal exists in caller's tenant
                cur.execute(
                    """
                    select id from synced_product_signal
                    where id = %(signal_id)s and tenant_id = %(tenant_id)s
                    """,
                    {"signal_id": signal_id, "tenant_id": member.tenant_id},
                )
                if cur.fetchone() is None:
                    raise NotFoundError(
                        details={"resource": "synced_product_signal", "id": str(signal_id)}
                    )

                # 2. Verify workspace product exists in caller's tenant
                cur.execute(
                    """
                    select id from workspace_product
                    where id = %(wp_id)s and tenant_id = %(tenant_id)s
                    """,
                    {"wp_id": workspace_product_id, "tenant_id": member.tenant_id},
                )
                if cur.fetchone() is None:
                    raise NotFoundError(
                        details={"resource": "workspace_product", "id": str(workspace_product_id)}
                    )

                # 3. Check if signal or product is already matched
                cur.execute(
                    """
                    select id from pos_product_match
                    where tenant_id = %(tenant_id)s
                      and (synced_product_signal_id = %(signal_id)s
                           or workspace_product_id = %(wp_id)s)
                    limit 1
                    """,
                    {
                        "tenant_id": member.tenant_id,
                        "signal_id": signal_id,
                        "wp_id": workspace_product_id,
                    },
                )
                if cur.fetchone() is not None:
                    raise ConflictError(
                        details={"resource": "pos_product_match", "reason": "already_matched"}
                    )

                # 4. Insert manual match
                try:
                    cur.execute(
                        """
                        insert into pos_product_match (
                            tenant_id,
                            synced_product_signal_id,
                            workspace_product_id,
                            match_method,
                            matched_by,
                            matched_at
                        ) values (
                            %(tenant_id)s,
                            %(signal_id)s,
                            %(wp_id)s,
                            'manual',
                            %(matched_by)s,
                            now()
                        )
                        returning id, synced_product_signal_id, workspace_product_id,
                                  match_method, matched_at
                        """,
                        {
                            "tenant_id": member.tenant_id,
                            "signal_id": signal_id,
                            "wp_id": workspace_product_id,
                            "matched_by": member.membership_id,
                        },
                    )
                    row = dict(cur.fetchone())
                    conn.commit()
                except psycopg.errors.UniqueViolation as exc:
                    raise ConflictError(
                        details={"resource": "pos_product_match", "reason": "already_matched"}
                    ) from exc

        return PosProductMatch.model_validate(row)


def _decode_cursor(cursor: str | None) -> int:
    if cursor is None:
        return 0
    try:
        offset = int(base64.urlsafe_b64decode(cursor.encode("ascii")))
        if offset < 0:
            raise UnprocessableEntityError(details={"cursor": "invalid"})
        return offset
    except (ValueError, UnicodeError) as exc:
        raise UnprocessableEntityError(details={"cursor": "invalid"}) from exc


def _encode_cursor(offset: int) -> str:
    return base64.urlsafe_b64encode(str(offset).encode("ascii")).decode("ascii")


def get_connection_service() -> ConnectionService:
    return ConnectionService()


"""Service layer for accounting connection lifecycle (R3.1, US1).

Implements ConnectionService:
- start_connection: checks for existing connection, builds QuickBooks OAuth authorization URL
- complete_connection: exchanges callback code for tokens, creates accounting_connection row
- disconnect: marks active connection as disconnected (never deletes history)
- get_status: reads tenant's current connection state
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import secrets
import time
from uuid import UUID

from psycopg.rows import dict_row

from procurepilot_api.config import Settings, get_settings
from procurepilot_api.deps import CurrentMember
from procurepilot_api.errors import ConflictError, NotFoundError, UnprocessableEntityError
from procurepilot_api.modules.accounting.connector import get_accounting_connector
from procurepilot_api.modules.accounting.schemas import SyncedBill, SyncedBillList
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.offers.service import _authenticated_db
from procurepilot_api.shared.audit import AuditEventCreate, get_audit_writer
from procurepilot_api.shared.logging import get_trace_id
from procurepilot_api.shared.token_crypto import encrypt_token

logger = logging.getLogger(__name__)


def _get_signing_secret(settings: Settings) -> bytes:
    if settings.supabase_jwt_secret:
        return settings.supabase_jwt_secret.get_secret_value().encode("utf-8")
    return settings.supabase_service_role_key.get_secret_value().encode("utf-8")


def _effective_provider(settings: Settings) -> str:
    """Return the database provider value for the configured accounting mode.

    Stub mode retains the R3.1 QuickBooks-compatible storage contract.
    """
    return "xero" if settings.accounting_provider_mode == "xero" else "quickbooks"


def _configured_redirect_uri(settings: Settings) -> str | None:
    if settings.accounting_provider_mode == "xero":
        return settings.xero_redirect_uri
    return settings.quickbooks_redirect_uri


def _generate_state(settings: Settings, member: CurrentMember) -> str:
    """Generate signed state bound to the configured provider and mode."""
    payload = {
        "tenant_id": str(member.tenant_id),
        "membership_id": str(member.membership_id),
        "user_id": str(member.user_id),
        "email": member.email,
        "role": member.role.value,
        "iat": int(time.time()),
        "nonce": secrets.token_hex(16),
        "provider": _effective_provider(settings),
        "mode": settings.accounting_provider_mode,
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


def _record_audit(
    *,
    bearer_token: str | None,
    member: CurrentMember,
    action: str,
    target: dict[str, object],
) -> None:
    """Record an audit event following this codebase's established pattern."""
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


class ConnectionService:
    """T012: Manages external accounting system connection lifecycle.

    Runs operations within authenticated tenant context via _authenticated_db,
    enforcing RLS and column-level privileges.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    def start_connection(self, member: CurrentMember) -> str:
        """Initiate connection flow by building the provider authorization URL.

        Refuses with 409 Conflict if a non-disconnected connection already exists for this tenant.
        """
        with _authenticated_db(self._settings, member) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    select id from accounting_connection
                    where tenant_id = %s and status <> 'disconnected'
                    limit 1
                    """,
                    (member.tenant_id,),
                )
                if cur.fetchone() is not None:
                    raise ConflictError(
                        details={
                            "resource": "accounting_connection",
                            "reason": "connection_already_exists",
                        }
                    )

        state = _generate_state(self._settings, member)
        connector = get_accounting_connector(self._settings)
        return connector.build_authorization_url(state=state)

    def complete_connection(
        self,
        state_or_member: CurrentMember | UUID | str | None = None,
        code: str | None = None,
        realm_id: str | None = None,
        state: str | None = None,
        error: str | None = None,
        *,
        bearer_token: str | None = None,
    ) -> dict[str, object] | None:
        """OAuth callback completion.

        Exchanges authorization code for tokens, creates the accounting_connection row,
        and records an audit event. Returns the created connection row dict, or None if
        authorization was declined or failed (spec Acceptance Scenario 1.3).
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
            logger.warning("Invalid or expired OAuth state token during callback completion")
            return None

        configured_mode = self._settings.accounting_provider_mode
        if (
            payload.get("mode") != configured_mode
            or payload.get("provider") != _effective_provider(self._settings)
        ):
            logger.warning("OAuth state provider or mode does not match current configuration")
            return None

        is_quickbooks = _effective_provider(self._settings) == "quickbooks"
        if is_quickbooks and not realm_id:
            return None

        member = CurrentMember(
            membership_id=UUID(str(payload["membership_id"])),
            tenant_id=UUID(str(payload["tenant_id"])),
            user_id=UUID(str(payload["user_id"])),
            email=str(payload["email"]),
            role=MemberRole(str(payload.get("role", "owner"))),
        )

        connector = get_accounting_connector(self._settings, realm_id=realm_id)
        try:
            tokens = connector.exchange_code_for_tokens(
                code=code,
                redirect_uri=_configured_redirect_uri(self._settings),
                realm_id=realm_id,
            )
        except Exception as exc:
            logger.warning("Token exchange failed during complete_connection: %s", exc)
            return None

        try:
            company = connector.company_info()
            verified_realm_id = company.realm_id
            display_name = company.display_name or (
                f"{_effective_provider(self._settings).title()} ({verified_realm_id})"
            )
        except Exception as exc:
            logger.warning("Company info query failed during complete_connection: %s", exc)
            if not is_quickbooks:
                return None
            verified_realm_id = realm_id
            display_name = f"{_effective_provider(self._settings).title()} ({realm_id})"

        try:
            with _authenticated_db(self._settings, member) as conn:
                with conn.cursor(row_factory=dict_row) as cur:
                    cur.execute(
                        """
                        select id from accounting_connection
                        where tenant_id = %s and status <> 'disconnected'
                        limit 1
                        """,
                        (member.tenant_id,),
                    )
                    if cur.fetchone() is not None:
                        logger.warning(
                            "Active accounting connection already exists for tenant %s",
                            member.tenant_id,
                        )
                        return None

                    cur.execute(
                        """
                        insert into accounting_connection (
                            tenant_id,
                            provider,
                            realm_id,
                            display_name,
                            access_token,
                            refresh_token,
                            status,
                            connected_by,
                            connected_at
                        ) values (
                            %(tenant_id)s,
                            %(provider)s,
                            %(realm_id)s,
                            %(display_name)s,
                            %(access_token)s,
                            %(refresh_token)s,
                            'active',
                            %(connected_by)s,
                            now()
                        )
                        returning id, tenant_id, provider, realm_id, display_name, status,
                                  connected_by, connected_at, last_synced_at, disconnected_at,
                                  created_at, updated_at
                        """,
                        {
                            "tenant_id": member.tenant_id,
                            "provider": _effective_provider(self._settings),
                            "realm_id": verified_realm_id,
                            "display_name": display_name,
                            "access_token": encrypt_token(
                                tokens.access_token,
                                self._settings.accounting_token_encryption_key,
                            ),
                            "refresh_token": encrypt_token(
                                tokens.refresh_token,
                                self._settings.accounting_token_encryption_key,
                            ),
                            "connected_by": member.membership_id,
                        },
                    )
                    row = dict(cur.fetchone())
                conn.commit()
        except Exception as exc:
            logger.exception("Failed to insert accounting_connection: %s", exc)
            return None

        _record_audit(
            bearer_token=bearer_token,
            member=member,
            action="accounting.connection_created",
            target={"accounting_connection_id": str(row["id"])},
        )
        return row

    def disconnect(
        self,
        member: CurrentMember,
        bearer_token: str | None = None,
    ) -> dict[str, object]:
        """Disconnect the active accounting connection (FR-004).

        Preserves historical synced data. Refuses with 404 NotFound if no active connection exists.
        """
        with _authenticated_db(self._settings, member) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    select id from accounting_connection
                    where tenant_id = %s and status <> 'disconnected'
                    order by created_at desc
                    limit 1
                    for update
                    """,
                    (member.tenant_id,),
                )
                existing = cur.fetchone()
                if existing is None:
                    raise NotFoundError(details={"resource": "accounting_connection"})

                cur.execute(
                    """
                    update accounting_connection
                    set status = 'disconnected',
                        disconnected_at = now(),
                        updated_at = now()
                    where id = %(id)s and tenant_id = %(tenant_id)s
                    returning id, tenant_id, provider, realm_id, display_name, status,
                              connected_by, connected_at, last_synced_at, disconnected_at,
                              created_at, updated_at
                    """,
                    {"id": existing["id"], "tenant_id": member.tenant_id},
                )
                row = dict(cur.fetchone())
            conn.commit()

        _record_audit(
            bearer_token=bearer_token,
            member=member,
            action="accounting.connection_disconnected",
            target={"accounting_connection_id": str(row["id"])},
        )
        return row

    def get_status(self, member: CurrentMember) -> dict[str, object] | None:
        """Return the current connection row for the member's tenant, or None if never connected."""
        with _authenticated_db(self._settings, member) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    select id, tenant_id, provider, realm_id, display_name, status,
                           connected_by, connected_at, last_synced_at, disconnected_at,
                           created_at, updated_at
                    from accounting_connection
                    where tenant_id = %s
                    order by created_at desc
                    limit 1
                    """,
                    (member.tenant_id,),
                )
                row = cur.fetchone()
        return dict(row) if row else None

    def list_bills(
        self,
        member: CurrentMember,
        *,
        cursor: str | None = None,
        limit: int = 50,
        match_status: str | None = None,
    ) -> SyncedBillList:
        """Return cursor-paginated list of synced bills for the member's tenant (T022).

        A bill is matched if a corresponding row exists in purchase_bill_match.
        Joined with synced_vendor to supply vendor_name.
        """
        offset = _decode_cursor(cursor)
        fetch_limit = min(max(limit, 1), 100)

        clauses = ["b.tenant_id = %(tenant_id)s"]
        params: dict[str, object] = {
            "tenant_id": member.tenant_id,
            "offset": offset,
            "limit": fetch_limit + 1,
        }

        if match_status == "matched":
            clauses.append("m.id is not null")
        elif match_status == "unmatched":
            clauses.append("m.id is null")

        where_sql = " and ".join(clauses)

        query = f"""
            select
                b.id,
                v.display_name as vendor_name,
                b.matched_supplier_id,
                b.amount,
                b.currency,
                b.bill_date,
                b.due_date,
                b.remaining_balance_amount,
                b.remaining_balance_currency,
                b.provider_status,
                (m.id is not null) as matched,
                m.purchase_record_id
            from synced_bill b
            join synced_vendor v on v.tenant_id = b.tenant_id and v.id = b.vendor_id
            left join purchase_bill_match m on m.tenant_id = b.tenant_id and m.synced_bill_id = b.id
            where {where_sql}
            order by b.bill_date desc, b.id desc
            offset %(offset)s limit %(limit)s
        """

        with _authenticated_db(self._settings, member) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(query, params)
                rows = [dict(r) for r in cur.fetchall()]

        has_more = len(rows) > fetch_limit
        page_rows = rows[:fetch_limit]
        next_cursor = _encode_cursor(offset + fetch_limit) if has_more else None

        for row in page_rows:
            balance = row.pop("remaining_balance_amount", None)
            currency = row.pop("remaining_balance_currency", None)
            row["remaining_balance"] = (
                {"amount": balance, "currency": currency} if balance is not None else None
            )

        return SyncedBillList(
            items=[SyncedBill.model_validate(r) for r in page_rows],
            next_cursor=next_cursor,
        )


def _encode_cursor(offset: int) -> str:
    return base64.urlsafe_b64encode(str(offset).encode("ascii")).decode("ascii")


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


def get_connection_service() -> ConnectionService:
    return ConnectionService()

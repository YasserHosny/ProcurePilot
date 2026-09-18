from __future__ import annotations

from psycopg.rows import dict_row

from procurepilot_api.config import Settings, get_settings
from procurepilot_api.deps import CurrentMember
from procurepilot_api.modules.ingestion.schemas import TenantEmailConfig, TenantEmailConfigUpdate
from procurepilot_api.modules.offers.service import _authenticated_db
from procurepilot_api.shared.audit import AuditEventCreate, get_audit_writer
from procurepilot_api.shared.logging import get_trace_id


class IngestionConfigService:
    """T013: tenant email ingestion configuration. One row per tenant, upserted on first write
    (there is no separate "create" task in tasks.md) — GET before any write returns not-found,
    matching how every other per-tenant settings resource in this codebase behaves."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    def get_config(self, *, member: CurrentMember) -> TenantEmailConfig | None:
        with _authenticated_db(self._settings, member) as conn:
            row = _config_row(conn, member.tenant_id)
        return _config(row) if row else None

    def update_config(
        self,
        *,
        member: CurrentMember,
        payload: TenantEmailConfigUpdate,
        bearer_token: str | None = None,
    ) -> TenantEmailConfig:
        with _authenticated_db(self._settings, member) as conn:
            row = self._upsert(conn, member.tenant_id, member.membership_id, payload)
            conn.commit()
        _record_audit(
            bearer_token=bearer_token,
            member=member,
            action="ingestion.email_config_updated",
            target={"tenant_email_config_id": str(row["id"])},
        )
        return _config(row)

    def set_enabled(
        self,
        *,
        member: CurrentMember,
        enabled: bool,
        bearer_token: str | None = None,
    ) -> TenantEmailConfig:
        with _authenticated_db(self._settings, member) as conn:
            row = self._upsert(
                conn,
                member.tenant_id,
                member.membership_id,
                TenantEmailConfigUpdate(enabled=enabled),
            )
            conn.commit()
        action = "ingestion.email_config_enabled" if enabled else "ingestion.email_config_disabled"
        _record_audit(
            bearer_token=bearer_token,
            member=member,
            action=action,
            target={"tenant_email_config_id": str(row["id"])},
        )
        return _config(row)

    def _upsert(
        self,
        conn: object,
        tenant_id: object,
        membership_id: object,
        payload: TenantEmailConfigUpdate,
    ) -> dict[str, object]:
        existing = _config_row(conn, tenant_id)
        if existing is None:
            forwarding_address = _forwarding_address(self._settings, conn, tenant_id)
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    insert into tenant_email_config
                      (tenant_id, forwarding_address, enabled, domain_allowlist, daily_limit,
                       spf_dkim_required, created_by)
                    values (%(tenant_id)s, %(forwarding_address)s,
                            coalesce(%(enabled)s, true), %(domain_allowlist)s,
                            coalesce(%(daily_limit)s, 100),
                            coalesce(%(spf_dkim_required)s, false), %(created_by)s)
                    returning *
                    """,
                    {
                        "tenant_id": tenant_id,
                        "forwarding_address": forwarding_address,
                        "enabled": payload.enabled,
                        "domain_allowlist": payload.domain_allowlist,
                        "daily_limit": payload.daily_limit,
                        "spf_dkim_required": payload.spf_dkim_required,
                        "created_by": membership_id,
                    },
                )
                return dict(cur.fetchone())

        updates: dict[str, object] = {}
        if payload.enabled is not None:
            updates["enabled"] = payload.enabled
        if payload.domain_allowlist is not None:
            updates["domain_allowlist"] = payload.domain_allowlist
        if payload.daily_limit is not None:
            updates["daily_limit"] = payload.daily_limit
        if payload.spf_dkim_required is not None:
            updates["spf_dkim_required"] = payload.spf_dkim_required
        if not updates:
            return existing

        updates["updated_at"] = "now()"
        set_clause = ", ".join(
            f"{key} = now()" if value == "now()" else f"{key} = %({key})s"
            for key, value in updates.items()
        )
        params = {k: v for k, v in updates.items() if v != "now()"}
        params["tenant_id"] = tenant_id
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                f"update tenant_email_config set {set_clause} where tenant_id = %(tenant_id)s "
                "returning *",
                params,
            )
            return dict(cur.fetchone())


def get_ingestion_config_service() -> IngestionConfigService:
    return IngestionConfigService()


def _config_row(conn: object, tenant_id: object) -> dict[str, object] | None:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("select * from tenant_email_config where tenant_id = %s", (tenant_id,))
        row = cur.fetchone()
    return dict(row) if row else None


def _forwarding_address(settings: Settings, conn: object, tenant_id: object) -> str:
    with conn.cursor() as cur:
        cur.execute("select slug from tenant where id = %s", (tenant_id,))
        row = cur.fetchone()
    slug = str(row[0])
    return f"{slug}@{settings.ingestion_email_domain}"


def _config(row: dict[str, object]) -> TenantEmailConfig:
    return TenantEmailConfig(
        id=row["id"],
        forwarding_address=str(row["forwarding_address"]),
        enabled=bool(row["enabled"]),
        domain_allowlist=row.get("domain_allowlist"),
        daily_limit=int(row["daily_limit"]),
        daily_count=int(row["daily_count"]),
        daily_count_date=row["daily_count_date"],
        spf_dkim_required=bool(row["spf_dkim_required"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _record_audit(
    *,
    bearer_token: str | None,
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

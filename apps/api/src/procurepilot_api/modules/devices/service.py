from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from procurepilot_api.config import Settings, get_settings
from procurepilot_api.deps import CurrentMember
from procurepilot_api.errors import NotFoundError, ServiceUnavailableError
from procurepilot_api.modules.devices.schemas import (
    DeviceRegistration,
    DeviceRegistrationCreate,
)


class DevicesService:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    def register_device(
        self,
        *,
        bearer_token: str,
        member: CurrentMember,
        payload: DeviceRegistrationCreate,
        idempotency_key: UUID | None = None,
    ) -> tuple[DeviceRegistration, bool]:
        del bearer_token
        with _authenticated_db(self._settings, member) as conn:
            replay = False
            with conn.cursor(row_factory=dict_row) as cur:
                if idempotency_key is not None:
                    # device_registration's own (tenant_id, member_id, push_token) upsert target
                    # below silently absorbs a retried registration too -- it always returns a row
                    # via DO UPDATE, so the idempotency_key's own unique index never gets a chance
                    # to raise and this insert's except branch alone cannot detect a genuine
                    # replay. Check for one explicitly, first, before ever attempting the insert.
                    cur.execute(
                        "select id, member_id, platform, push_token, last_seen_at "
                        "from device_registration where tenant_id = %s and idempotency_key = %s",
                        (member.tenant_id, idempotency_key),
                    )
                    existing = cur.fetchone()
                    if existing is not None:
                        return DeviceRegistration.model_validate(dict(existing)), False
                try:
                    cur.execute(
                        """
                    insert into device_registration
                      (tenant_id, member_id, platform, push_token, idempotency_key)
                    values (%s, %s, %s, %s, %s)
                    on conflict (tenant_id, member_id, push_token)
                    do update set last_seen_at = now()
                    returning id, member_id, platform, push_token, last_seen_at
                        """,
                        (
                            member.tenant_id,
                            member.membership_id,
                            payload.platform,
                            payload.push_token,
                            idempotency_key,
                        ),
                    )
                except psycopg.errors.UniqueViolation:
                    if idempotency_key is None:
                        raise
                    conn.rollback()
                    cur.execute(
                        "select id, member_id, platform, push_token, last_seen_at "
                        "from device_registration where tenant_id = %s and idempotency_key = %s",
                        (member.tenant_id, idempotency_key),
                    )
                    replay = True
                row = cur.fetchone()
            if row is None:
                raise ServiceUnavailableError(
                    details={"reason": "device_registration_write_failed"}
                )
            return DeviceRegistration.model_validate(dict(row)), not replay

    def delete_device(
        self,
        *,
        bearer_token: str,
        member: CurrentMember,
        device_id: UUID,
    ) -> None:
        del bearer_token
        with _authenticated_db(self._settings, member) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    delete from device_registration
                    where id = %s
                    returning id
                    """,
                    (device_id,),
                )
                row = cur.fetchone()
            if row is None:
                raise NotFoundError(details={"resource": "device_registration"})


def get_devices_service() -> DevicesService:
    return DevicesService()


@contextmanager
def _authenticated_db(settings: Settings, member: CurrentMember) -> Iterator[psycopg.Connection]:
    try:
        with psycopg.connect(settings.database_url.get_secret_value()) as conn:
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

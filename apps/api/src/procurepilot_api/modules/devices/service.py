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
    ) -> DeviceRegistration:
        del bearer_token
        with _authenticated_db(self._settings, member) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    insert into device_registration
                      (tenant_id, member_id, platform, push_token)
                    values (%s, %s, %s, %s)
                    on conflict (tenant_id, member_id, push_token)
                    do update set last_seen_at = now()
                    returning id, member_id, platform, push_token, last_seen_at
                    """,
                    (
                        member.tenant_id,
                        member.membership_id,
                        payload.platform,
                        payload.push_token,
                    ),
                )
                row = cur.fetchone()
            if row is None:
                raise ServiceUnavailableError(
                    details={"reason": "device_registration_write_failed"}
                )
            return DeviceRegistration.model_validate(dict(row))

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
def _authenticated_db(
    settings: Settings, member: CurrentMember
) -> Iterator[psycopg.Connection]:
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
        raise ServiceUnavailableError(
            details={"dependency": "database"}
        ) from exc

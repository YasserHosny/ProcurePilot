from __future__ import annotations

import base64
import json
from datetime import UTC, datetime

from psycopg.rows import dict_row

from procurepilot_api.config import Settings, get_settings
from procurepilot_api.deps import CurrentMember
from procurepilot_api.errors import NotFoundError, ServiceUnavailableError, UnprocessableEntityError
from procurepilot_api.modules.alerts.conditions import AlertConditionService
from procurepilot_api.modules.alerts.schemas import AlertDismissal, AlertList
from procurepilot_api.modules.offers.service import _authenticated_db


class AlertService:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._conditions = AlertConditionService(self._settings)

    def list_alerts(
        self,
        *,
        member: CurrentMember,
        kind: str | None = None,
        cursor: str | None = None,
        limit: int = 50,
    ) -> AlertList:
        capped_limit = max(1, min(limit, 100))
        offset = _decode_cursor(cursor)
        live = self._conditions.live_alerts(member=member, kind=kind)
        dismissed = _dismissed_fingerprints(self._settings, member)
        visible = [alert for alert in live if alert.id not in dismissed]
        page = visible[offset : offset + capped_limit]
        next_cursor = (
            _encode_cursor(offset + capped_limit)
            if len(visible) > offset + capped_limit
            else None
        )
        return AlertList(items=page, next_cursor=next_cursor)

    def dismiss_alert(self, *, member: CurrentMember, alert_id: str) -> AlertDismissal:
        current = {alert.id: alert for alert in self._conditions.live_alerts(member=member)}
        alert = current.get(alert_id)
        if alert is None:
            raise NotFoundError(details={"resource": "alert"})
        now = datetime.now(UTC)
        try:
            with _authenticated_db(self._settings, member) as conn:
                with conn.cursor(row_factory=dict_row) as cur:
                    cur.execute(
                        """
                        insert into alert_dismissal
                          (tenant_id, alert_fingerprint, kind, workspace_product_id,
                           supplier_id, dismissed_by, dismissed_at)
                        values (%s, %s, %s, %s, %s, %s, %s)
                        on conflict (tenant_id, alert_fingerprint) do update
                        set dismissed_at = excluded.dismissed_at,
                            dismissed_by = excluded.dismissed_by
                        returning dismissed_at
                        """,
                        (
                            member.tenant_id,
                            alert.id,
                            alert.kind,
                            alert.workspace_product_id,
                            alert.supplier_id,
                            member.membership_id,
                            now,
                        ),
                    )
                    row = cur.fetchone()
        except Exception as exc:
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc
        return AlertDismissal(alert_id=alert.id, dismissed_at=row["dismissed_at"])


def get_alert_service() -> AlertService:
    return AlertService()


def _dismissed_fingerprints(settings: Settings, member: CurrentMember) -> set[str]:
    with _authenticated_db(settings, member) as conn:
        with conn.cursor() as cur:
            cur.execute("select alert_fingerprint from alert_dismissal")
            return {str(row[0]) for row in cur.fetchall()}


def _encode_cursor(offset: int) -> str:
    raw = json.dumps({"offset": offset}, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def _decode_cursor(cursor: str | None) -> int:
    if cursor is None:
        return 0
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii"))
        offset = json.loads(raw.decode("utf-8"))["offset"]
    except (KeyError, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise UnprocessableEntityError(details={"cursor": "invalid"}) from exc
    if not isinstance(offset, int) or offset < 0:
        raise UnprocessableEntityError(details={"cursor": "invalid"})
    return offset

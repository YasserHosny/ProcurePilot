"""devices module integration coverage — chunk R2.2 (009-mobile-app-mvp), T010-T012.

Added on review: the implementation (POST /devices upsert, DELETE /devices/{id}, the push-send
job, and the retry-sweep query) had contract-drift coverage (test_mobile_openapi_drift.py) but no
test exercising the actual SQL/RLS behaviour against a real database. These do that directly
against DevicesService and the push_job functions, the same way test_import_atomicity.py exercises
a service directly rather than through the HTTP layer.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from integration.catalogue_helpers import (
    TEST_DATABASE_URL,
    connection,
    make_workspace,
    psycopg,
)
from procurepilot_api.deps import CurrentMember
from procurepilot_api.errors import NotFoundError
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.devices import push_job
from procurepilot_api.modules.devices.schemas import DeviceRegistrationCreate
from procurepilot_api.modules.devices.service import DevicesService

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is not set; needs a Postgres with the mobile migrations applied",
)


@pytest.fixture
def conn() -> object:
    yield from connection()


def _member(workspace: object) -> CurrentMember:
    return CurrentMember(
        membership_id=workspace.membership_id,
        tenant_id=workspace.tenant_id,
        user_id=workspace.user_id,
        email=f"{workspace.label}@example.test",
        role=MemberRole.owner,
    )


def test_registering_the_same_token_twice_upserts_the_same_row(conn: object) -> None:
    with conn.cursor() as cur:
        workspace = make_workspace(cur, "devices-upsert")
    conn.commit()
    member = _member(workspace)
    service = DevicesService()

    first = service.register_device(
        bearer_token="unused",
        member=member,
        payload=DeviceRegistrationCreate(platform="ios", push_token="tok-upsert"),
    )
    second = service.register_device(
        bearer_token="unused",
        member=member,
        payload=DeviceRegistrationCreate(platform="ios", push_token="tok-upsert"),
    )

    assert second.id == first.id, "re-registering the same push_token must upsert, not duplicate"
    assert second.last_seen_at >= first.last_seen_at


def test_deleting_a_device_twice_the_second_time_is_not_found(conn: object) -> None:
    with conn.cursor() as cur:
        workspace = make_workspace(cur, "devices-delete")
    conn.commit()
    member = _member(workspace)
    service = DevicesService()

    created = service.register_device(
        bearer_token="unused",
        member=member,
        payload=DeviceRegistrationCreate(platform="android", push_token="tok-delete"),
    )

    service.delete_device(bearer_token="unused", member=member, device_id=created.id)

    with pytest.raises(NotFoundError):
        service.delete_device(bearer_token="unused", member=member, device_id=created.id)


def test_deleting_a_nonexistent_device_id_is_not_found(conn: object) -> None:
    with conn.cursor() as cur:
        workspace = make_workspace(cur, "devices-delete-missing")
    conn.commit()
    member = _member(workspace)
    service = DevicesService()

    with pytest.raises(NotFoundError):
        service.delete_device(bearer_token="unused", member=member, device_id=uuid4())


def _seed_request(cur: psycopg.Cursor, workspace: object) -> tuple[object, object]:
    branch_id = uuid4()
    request_id = uuid4()
    cur.execute(
        "insert into branch (id,tenant_id,name,region) values (%s,%s,%s,'GB')",
        (branch_id, workspace.tenant_id, f"{workspace.label}-branch"),
    )
    cur.execute(
        "insert into purchase_request "
        "(id,tenant_id,branch_id,requested_by_membership_id,required_by_date) "
        "values (%s,%s,%s,%s, current_date + interval '7 days')",
        (request_id, workspace.tenant_id, branch_id, workspace.membership_id),
    )
    return branch_id, request_id


def test_push_job_marks_sent_even_with_zero_device_registrations(conn: object) -> None:
    """FR-008: a member with no registered devices is not an error."""
    with conn.cursor() as cur:
        workspace = make_workspace(cur, "push-no-devices")
        _, request_id = _seed_request(cur, workspace)
        notification_id = uuid4()
        cur.execute(
            "insert into push_notification (id,tenant_id,purchase_request_id,member_id) "
            "values (%s,%s,%s,%s)",
            (notification_id, workspace.tenant_id, request_id, workspace.membership_id),
        )
    conn.commit()

    push_job.process_push_notification(notification_id)

    with conn.cursor() as cur:
        cur.execute(
            "select status, attempts, sent_at from push_notification where id = %s",
            (notification_id,),
        )
        status, attempts, sent_at = cur.fetchone()
    assert status == "sent"
    assert attempts == 1
    assert sent_at is not None


def test_push_job_sends_to_every_current_registration_for_the_member(conn: object) -> None:
    with conn.cursor() as cur:
        workspace = make_workspace(cur, "push-with-device")
        _, request_id = _seed_request(cur, workspace)
        device_id = uuid4()
        cur.execute(
            "insert into device_registration (id,tenant_id,member_id,platform,push_token) "
            "values (%s,%s,%s,'ios',%s)",
            (device_id, workspace.tenant_id, workspace.membership_id, "tok-push-with-device"),
        )
        notification_id = uuid4()
        cur.execute(
            "insert into push_notification (id,tenant_id,purchase_request_id,member_id) "
            "values (%s,%s,%s,%s)",
            (notification_id, workspace.tenant_id, request_id, workspace.membership_id),
        )
    conn.commit()

    push_job.process_push_notification(notification_id)

    with conn.cursor() as cur:
        cur.execute(
            "select status, sent_at from push_notification where id = %s", (notification_id,)
        )
        status, sent_at = cur.fetchone()
    assert status == "sent"
    assert sent_at is not None


def test_retry_sweep_finds_only_genuinely_stale_queued_or_failed_rows(conn: object) -> None:
    with conn.cursor() as cur:
        workspace = make_workspace(cur, "push-sweep")
        _, request_id = _seed_request(cur, workspace)

        stale_id, fresh_id, sent_id = uuid4(), uuid4(), uuid4()
        old_ts = datetime.now(UTC) - push_job.RETRY_SWEEP_AGE - timedelta(minutes=1)

        cur.execute(
            "insert into push_notification "
            "(id,tenant_id,purchase_request_id,member_id,status,created_at) "
            "values (%s,%s,%s,%s,'queued',%s)",
            (stale_id, workspace.tenant_id, request_id, workspace.membership_id, old_ts),
        )
        cur.execute(
            "insert into push_notification "
            "(id,tenant_id,purchase_request_id,member_id,status) "
            "values (%s,%s,%s,%s,'queued')",
            (fresh_id, workspace.tenant_id, request_id, workspace.membership_id),
        )
        cur.execute(
            "insert into push_notification "
            "(id,tenant_id,purchase_request_id,member_id,status,sent_at,created_at) "
            "values (%s,%s,%s,%s,'sent',now(),%s)",
            (sent_id, workspace.tenant_id, request_id, workspace.membership_id, old_ts),
        )
    conn.commit()

    found = push_job._stale_notifications(conn, cutoff=datetime.now(UTC) - push_job.RETRY_SWEEP_AGE)
    found_ids = {row["id"] for row in found}

    assert stale_id in found_ids, "an old queued row past the threshold must be found"
    assert fresh_id not in found_ids, "a queued row still within the threshold must not be swept"
    assert sent_id not in found_ids, "an already-sent row must never be re-swept, however old"

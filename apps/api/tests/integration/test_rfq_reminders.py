"""Manual reminders run against TEST_DATABASE_URL with FakeMailer; no real email is sent."""

import os
from collections.abc import Iterator
from datetime import date, timedelta
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient

from integration.test_rfq_reply_to import _seed_product, _seed_tenant_and_supplier
from procurepilot_api.config import get_settings
from procurepilot_api.deps import CurrentMember, current_member
from procurepilot_api.main import create_app
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.rfq import service as service_module
from procurepilot_api.shared.mailer import FakeMailer

DB = os.environ.get("TEST_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(not DB, reason="TEST_DATABASE_URL is required")


@pytest.fixture
def reminder(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[tuple[TestClient, str, str, CurrentMember]]:
    with psycopg.connect(DB, prepare_threshold=None) as probe:
        has_columns = probe.execute(
            "select count(*) from information_schema.columns "
            "where table_name = 'rfq_recipient' and column_name = 'reminder_count'"
        ).fetchone()[0]
    if not has_columns:
        pytest.skip("migration 20261104120000_rfq_reminders is not applied to this database")
    monkeypatch.setenv("DATABASE_URL", DB)
    monkeypatch.setenv("RFQ_MAILER_MODE", "stub")
    monkeypatch.setenv("RATE_LIMIT_RFQ_SEND", "10000/minute")
    monkeypatch.setattr(service_module, "get_mailer", FakeMailer)
    get_settings.cache_clear()
    FakeMailer.clear()
    with psycopg.connect(DB) as conn, conn.cursor() as cur:
        tenant, user, membership, supplier = _seed_tenant_and_supplier(cur)
        product = _seed_product(cur, tenant)
    member = CurrentMember(
        membership_id=membership,
        tenant_id=tenant,
        user_id=user,
        email="reminder@example.test",
        role=MemberRole.owner,
    )
    app = create_app(get_settings())
    app.dependency_overrides[current_member] = lambda: member
    with TestClient(app) as client:
        created = client.post(
            "/api/v1/rfq",
            json={
                "needed_by_date": str(date.today() + timedelta(days=7)),
                "lines": [{"workspace_product_id": str(product), "quantity": "2"}],
                "recipient_supplier_ids": [str(supplier)],
            },
            headers={"Idempotency-Key": str(uuid4())},
        )
        assert created.status_code == 201, created.text
        rfq = created.json()["rfq"]["id"]
        sent = client.post(f"/api/v1/rfq/{rfq}/send", headers={"Idempotency-Key": str(uuid4())})
        assert sent.status_code == 200, sent.text
        recipient = sent.json()["recipients"][0]["id"]
        with psycopg.connect(DB) as conn:
            conn.execute(
                "update rfq_recipient set sent_at = now() - interval '2 days' where id=%s",
                (recipient,),
            )
        FakeMailer.clear()
        yield client, rfq, recipient, member
    FakeMailer.clear()
    get_settings.cache_clear()


def path(rfq: str, recipient: str) -> str:
    return f"/api/v1/rfq/{rfq}/recipients/{recipient}/reminder"


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        ("update rfq set status='draft' where id=%s", "rfq_not_open"),
        ("update rfq set needed_by_date=current_date-1 where id=%s", "rfq_not_open"),
        (
            "update rfq set status='responded', needed_by_date=current_date-1 where id=%s",
            "rfq_not_open",
        ),
        ("update rfq_recipient set outbound_message_id=null where rfq_id=%s", "not_delivered"),
        ("update rfq_recipient set status='failed' where rfq_id=%s", "not_delivered"),
        ("update rfq_recipient set sent_at=now()-interval '23 hours' where rfq_id=%s", "too_early"),
        (
            "update rfq_recipient set reminder_count=1,last_reminder_at=now()-interval '23 hours' "
            "where rfq_id=%s",
            "cooldown",
        ),
        (
            "update rfq_recipient set reminder_count=2,last_reminder_at=now()-interval '2 days' "
            "where rfq_id=%s",
            "limit_reached",
        ),
        (
            "update rfq_recipient set reminder_count=2,last_reminder_at=now() where rfq_id=%s",
            "cooldown",
        ),
        (
            "update rfq_recipient set sent_at=now(),reminder_count=2,last_reminder_at=now() "
            "where rfq_id=%s",
            "too_early",
        ),
    ],
)
def test_blocking_reason_and_preview(reminder: tuple, change: str, reason: str) -> None:
    client, rfq, recipient, _ = reminder
    with psycopg.connect(DB) as conn:
        conn.execute(change, (rfq,))
    preview = client.get(path(rfq, recipient) + "-preview")
    assert preview.status_code == 200, preview.text
    assert preview.json()["allowed"] is False
    assert preview.json()["blocked_reason"] == reason
    result = client.post(path(rfq, recipient), headers={"Idempotency-Key": str(uuid4())})
    assert result.status_code == 422, result.text
    assert result.json()["details"]["reason"] == reason
    assert not FakeMailer.sent_messages


def test_success_replay_headers_and_detail(reminder: tuple) -> None:
    client, rfq, recipient, _ = reminder
    preview = client.get(path(rfq, recipient) + "-preview")
    assert preview.status_code == 200, preview.text
    assert preview.json()["allowed"] is True
    key = {"Idempotency-Key": str(uuid4())}
    result = client.post(path(rfq, recipient), headers=key)
    assert result.status_code == 200, result.text
    assert result.json()["reminder_count"] == 1
    assert result.json()["last_reminder_at"]
    assert result.json()["can_remind"] is False
    replay = client.post(path(rfq, recipient), headers=key)
    assert replay.json() == result.json()
    assert len(FakeMailer.sent_messages) == 1
    message = FakeMailer.sent_messages[0]
    assert message.subject == preview.json()["subject"]
    assert message.body == preview.json()["body_text"]
    with psycopg.connect(DB) as conn:
        original = conn.execute(
            "select outbound_message_id from rfq_recipient where id=%s", (recipient,)
        ).fetchone()[0]
        assert message.headers["In-Reply-To"] == original
        assert message.headers["References"] == original
    detail = client.get(f"/api/v1/rfq/{rfq}").json()
    assert detail["recipients"][0]["reminder_count"] == 1
    assert detail["recipients"][0]["remind_blocked_reason"] == "cooldown"


def test_cooldown_boundary_and_two_reminders(reminder: tuple) -> None:
    client, rfq, recipient, _ = reminder
    with psycopg.connect(DB) as conn:
        conn.execute(
            "update rfq_recipient set reminder_count=1,last_reminder_at=now()-interval '24 hours' "
            "where id=%s",
            (recipient,),
        )
    result = client.post(path(rfq, recipient), headers={"Idempotency-Key": str(uuid4())})
    assert result.status_code == 200, result.text
    assert result.json()["reminder_count"] == 2
    with psycopg.connect(DB) as conn:
        conn.execute(
            "update rfq_recipient set last_reminder_at=now()-interval '24 hours' where id=%s",
            (recipient,),
        )
    result = client.post(path(rfq, recipient), headers={"Idempotency-Key": str(uuid4())})
    assert result.json()["details"]["reason"] == "limit_reached"
    assert len(FakeMailer.sent_messages) == 1


def test_failure_leaves_counters_unchanged(
    reminder: tuple, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, rfq, recipient, _ = reminder

    def fail(self: FakeMailer, **kwargs: object) -> None:
        raise RuntimeError("test delivery failure")

    monkeypatch.setattr(FakeMailer, "send", fail)
    result = client.post(path(rfq, recipient), headers={"Idempotency-Key": str(uuid4())})
    assert result.status_code == 503, result.text
    assert result.json()["code"] == "reminder_delivery_failed"
    with psycopg.connect(DB) as conn:
        assert conn.execute(
            "select reminder_count,last_reminder_at from rfq_recipient where id=%s", (recipient,)
        ).fetchone() == (0, None)


def test_missing_idempotency_key(reminder: tuple) -> None:
    client, rfq, recipient, _ = reminder
    assert client.post(path(rfq, recipient)).status_code == 422
    assert not FakeMailer.sent_messages

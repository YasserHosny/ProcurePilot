from __future__ import annotations

import base64
from email.message import EmailMessage

import psycopg
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from integration.catalogue_helpers import TEST_DATABASE_URL
from integration.smart_compare_helpers import committed_smart_context, settings_for_test_db
from procurepilot_api.main import create_app
from procurepilot_api.modules.ingestion import router as ingestion_router_module

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is not set; needs a migrated local Postgres",
)

WEBHOOK_SECRET = "test-webhook-secret"


def _app(monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    monkeypatch.setenv("INGESTION_WEBHOOK_SHARED_SECRET", WEBHOOK_SECRET)
    monkeypatch.setenv("INGESTION_EMAIL_PROVIDER", "stub")
    return create_app(settings_for_test_db(monkeypatch))


def _raw_email(recipient: str) -> bytes:
    msg = EmailMessage()
    msg["From"] = "sales@acme.com"
    msg["To"] = recipient
    msg["Subject"] = "Quotation"
    msg["Message-ID"] = "<webhook-msg@acme.com>"
    msg.set_content("Please find our quotation attached.")
    return msg.as_bytes()


def _seed_config(
    tenant_id: object, membership_id: object, address: str, **overrides: object
) -> None:
    with psycopg.connect(TEST_DATABASE_URL or "") as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                insert into tenant_email_config
                  (tenant_id, forwarding_address, created_by, enabled, daily_limit, daily_count)
                values (%s, %s, %s, %s, %s, %s)
                """,
                (
                    tenant_id,
                    address,
                    membership_id,
                    overrides.get("enabled", True),
                    overrides.get("daily_limit", 100),
                    overrides.get("daily_count", 0),
                ),
            )
        conn.commit()


class _FakeBucket:
    def upload(self, *_args: object, **_kwargs: object) -> None:
        return None


class _FakeStorage:
    def from_(self, _bucket: str) -> _FakeBucket:
        return _FakeBucket()


class _FakeSupabaseClient:
    storage = _FakeStorage()


def test_valid_secret_queues_a_job(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        ingestion_router_module, "create_client", lambda *_a, **_k: _FakeSupabaseClient()
    )
    with committed_smart_context("ingestion-webhook-ok") as context:
        address = f"{context.workspace.tenant_id}@ingest.procurepilot.local"
        _seed_config(context.workspace.tenant_id, context.workspace.membership_id, address)
        client = TestClient(_app(monkeypatch), raise_server_exceptions=False)

        raw = _raw_email(address)
        res = client.post(
            "/api/v1/webhooks/inbound-email",
            headers={"X-Ingestion-Webhook-Secret": WEBHOOK_SECRET},
            json={"recipient": address, "raw_email_base64": base64.b64encode(raw).decode()},
        )

        assert res.status_code == 202, res.text
        with psycopg.connect(TEST_DATABASE_URL or "") as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "select count(*) from ingestion_jobs where tenant_id = %s "
                    "and job_type = 'email_ingest'",
                    (context.workspace.tenant_id,),
                )
                count = cur.fetchone()[0]
        assert count == 1


def test_invalid_secret_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    with committed_smart_context("ingestion-webhook-badsecret") as context:
        address = f"{context.workspace.tenant_id}@ingest.procurepilot.local"
        _seed_config(context.workspace.tenant_id, context.workspace.membership_id, address)
        client = TestClient(_app(monkeypatch), raise_server_exceptions=False)

        raw = _raw_email(address)
        res = client.post(
            "/api/v1/webhooks/inbound-email",
            headers={"X-Ingestion-Webhook-Secret": "wrong-secret"},
            json={"recipient": address, "raw_email_base64": base64.b64encode(raw).decode()},
        )

        assert res.status_code == 401, res.text


def test_unknown_recipient_bounces_with_202_no_existence_leak(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = TestClient(_app(monkeypatch), raise_server_exceptions=False)
    raw = _raw_email("nobody@ingest.procurepilot.local")

    res = client.post(
        "/api/v1/webhooks/inbound-email",
        headers={"X-Ingestion-Webhook-Secret": WEBHOOK_SECRET},
        json={
            "recipient": "nobody@ingest.procurepilot.local",
            "raw_email_base64": base64.b64encode(raw).decode(),
        },
    )

    # R10: same 202 as the accepted case — probing for a valid tenant address must learn
    # nothing from the response.
    assert res.status_code == 202


def test_disabled_tenant_does_not_queue_a_job(monkeypatch: pytest.MonkeyPatch) -> None:
    with committed_smart_context("ingestion-webhook-disabled") as context:
        address = f"{context.workspace.tenant_id}@ingest.procurepilot.local"
        _seed_config(
            context.workspace.tenant_id, context.workspace.membership_id, address, enabled=False
        )
        client = TestClient(_app(monkeypatch), raise_server_exceptions=False)

        raw = _raw_email(address)
        res = client.post(
            "/api/v1/webhooks/inbound-email",
            headers={"X-Ingestion-Webhook-Secret": WEBHOOK_SECRET},
            json={"recipient": address, "raw_email_base64": base64.b64encode(raw).decode()},
        )

        assert res.status_code == 202
        with psycopg.connect(TEST_DATABASE_URL or "") as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "select count(*) from ingestion_jobs where tenant_id = %s",
                    (context.workspace.tenant_id,),
                )
                count = cur.fetchone()[0]
        assert count == 0


def test_daily_limit_reached_refuses_without_queueing(monkeypatch: pytest.MonkeyPatch) -> None:
    with committed_smart_context("ingestion-webhook-ratelimit") as context:
        address = f"{context.workspace.tenant_id}@ingest.procurepilot.local"
        _seed_config(
            context.workspace.tenant_id,
            context.workspace.membership_id,
            address,
            daily_limit=1,
            daily_count=1,
        )
        client = TestClient(_app(monkeypatch), raise_server_exceptions=False)

        raw = _raw_email(address)
        res = client.post(
            "/api/v1/webhooks/inbound-email",
            headers={"X-Ingestion-Webhook-Secret": WEBHOOK_SECRET},
            json={"recipient": address, "raw_email_base64": base64.b64encode(raw).decode()},
        )

        assert res.status_code == 202
        with psycopg.connect(TEST_DATABASE_URL or "") as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "select count(*) from ingestion_jobs where tenant_id = %s",
                    (context.workspace.tenant_id,),
                )
                count = cur.fetchone()[0]
        assert count == 0

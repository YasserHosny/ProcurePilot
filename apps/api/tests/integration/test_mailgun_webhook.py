import datetime
import hashlib
import hmac
import json
import time
import uuid

import psycopg
import pytest
from httpx import ASGITransport, AsyncClient

from procurepilot_api.config import get_settings
from procurepilot_api.deps import CurrentMember, current_member
from procurepilot_api.main import create_app
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.ingestion import router as ingestion_router_module

MAILGUN_KEY = "test_mailgun_signing_key_123"


def _seed_tenant_and_supplier(
    cur: psycopg.Cursor,
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID]:
    tenant_id, user_id, membership_id, invitation_id = (
        uuid.uuid4(),
        uuid.uuid4(),
        uuid.uuid4(),
        uuid.uuid4(),
    )
    email = f"rfq-reply-{user_id}@example.test"
    cur.execute("insert into auth.users (id,email) values (%s,%s)", (user_id, email))
    cur.execute(
        "insert into supported_region (code,label_en,label_ar) values ('GB','UK','ب') "
        "on conflict do nothing"
    )
    cur.execute(
        "insert into supported_currency (code,label_en,label_ar) values ('GBP','Pound','ج') "
        "on conflict do nothing"
    )
    cur.execute(
        "insert into supported_tax_model (code,label_en,label_ar,region_code) "
        "values ('uk_vat','UK VAT','ض','GB') on conflict do nothing"
    )
    cur.execute(
        "insert into platform_invitation (id,email,token_hash,expires_at) "
        "values (%s,%s,%s, now() + interval '7 days')",
        (invitation_id, email, f"hash-{invitation_id}"),
    )
    cur.execute(
        "insert into tenant (id,name,slug,region,currency,tax_model,platform_invitation_id) "
        "values (%s,%s,%s,'GB','GBP','uk_vat',%s)",
        (tenant_id, "RFQ Reply Tenant", str(tenant_id), invitation_id),
    )
    cur.execute(
        "insert into membership (id,tenant_id,user_id,email,role,is_active_workspace) "
        "values (%s,%s,%s,%s,'owner',true)",
        (membership_id, tenant_id, user_id, email),
    )

    # Supplier
    supplier_id = uuid.uuid4()
    cur.execute(
        "insert into supplier (id,tenant_id,name,contact_email) values (%s,%s,%s,%s)",
        (supplier_id, tenant_id, f"Supplier {supplier_id}", "contact@supplier.test"),
    )

    return tenant_id, user_id, membership_id, supplier_id


def _seed_product(cur: psycopg.Cursor, tenant_id: uuid.UUID) -> uuid.UUID:
    canonical_id, product_id = uuid.uuid4(), uuid.uuid4()
    cur.execute(
        "insert into canonical_product (id,name,gtin,base_unit) values (%s,%s,null,'each')",
        (canonical_id, "RFQ Canonical Product"),
    )
    cur.execute(
        "insert into workspace_product (id,tenant_id,canonical_product_id,tenant_name) "
        "values (%s,%s,%s,%s)",
        (product_id, tenant_id, canonical_id, "RFQ Product"),
    )
    return product_id


@pytest.fixture(autouse=True)
def setup_mailgun_webhook_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INGESTION_EMAIL_PROVIDER", "mailgun")
    monkeypatch.setenv("MAILGUN_SIGNING_KEY", MAILGUN_KEY)
    monkeypatch.setenv("INGESTION_WEBHOOK_SHARED_SECRET", "dummy")
    get_settings.cache_clear()

def generate_mailgun_signature(timestamp: str, token: str) -> str:
    return hmac.new(
        MAILGUN_KEY.encode(), f"{timestamp}{token}".encode(), hashlib.sha256
    ).hexdigest()

_uploaded_bytes = None

class _CapturingFakeBucket:
    def upload(self, path: str, data: bytes, *_args: object, **_kwargs: object) -> None:
        global _uploaded_bytes
        _uploaded_bytes = data
        return None

class _CapturingFakeStorage:
    def from_(self, _bucket: str) -> _CapturingFakeBucket:
        return _CapturingFakeBucket()

class _CapturingFakeSupabaseClient:
    storage = _CapturingFakeStorage()


@pytest.mark.asyncio
async def test_mailgun_webhook_payload_structure(monkeypatch: pytest.MonkeyPatch) -> None:
    global _uploaded_bytes
    _uploaded_bytes = None

    monkeypatch.setattr(
        ingestion_router_module, "create_client", lambda *_a, **_k: _CapturingFakeSupabaseClient()
    )
    from procurepilot_api.modules.ingestion import orchestrator as orchestrator_module
    monkeypatch.setattr(
        orchestrator_module, "create_client", lambda *_a, **_k: _CapturingFakeSupabaseClient()
    )

    settings = get_settings()
    app = create_app(settings)
    test_db = settings.database_url.get_secret_value()

    with psycopg.connect(test_db, prepare_threshold=None) as conn:
        with conn.cursor() as cur:
            tenant_id, user_id, membership_id, supplier_id = _seed_tenant_and_supplier(cur)
            product_id = _seed_product(cur, tenant_id)

            forwarding_address = f"capture_{tenant_id}@{settings.ingestion_email_domain}"
            cur.execute(
                "insert into tenant_email_config "
                "(tenant_id, forwarding_address, enabled, created_by) "
                "values (%s, %s, true, (select id from membership where tenant_id = %s limit 1))",
                (tenant_id, forwarding_address, tenant_id),
            )
        conn.commit()

    async def override_current_member() -> CurrentMember:
        return CurrentMember(
            membership_id=membership_id,
            tenant_id=tenant_id,
            user_id=user_id,
            email="test@example.com",
            role=MemberRole.owner,
            features=[],
        )
    app.dependency_overrides[current_member] = override_current_member

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test/api/v1"
    ) as client:
        # Create an RFQ to reply to
        needed_date = (datetime.datetime.now() + datetime.timedelta(days=30)).strftime("%Y-%m-%d")
        res = await client.post(
            "/rfq",
            json={
                "needed_by_date": needed_date,
                "lines": [{"workspace_product_id": str(product_id), "quantity": "10"}],
                "recipient_supplier_ids": [str(supplier_id)],
            },
            headers={"Authorization": "Bearer fake", "Idempotency-Key": str(uuid.uuid4())},
        )
        assert res.status_code == 201, res.json()
        rfq_id = res.json().get("id") or res.json().get("rfq", {}).get("id")
        
        send_res = await client.post(
            f"/rfq/{rfq_id}/send",
            headers={"Authorization": "Bearer fake", "Idempotency-Key": str(uuid.uuid4())},
        )
        assert send_res.status_code == 200

        with psycopg.connect(test_db, prepare_threshold=None) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "select outbound_message_id, id from rfq_recipient where rfq_id = %s", (rfq_id,)
                )
                outbound_msg_id, recipient_id = cur.fetchone()

        # Build Mailgun webhook form-data
        timestamp = str(int(time.time()))
        token = "random_mailgun_token"
        sig = generate_mailgun_signature(timestamp, token)
        
        reply_msg_id = f"<{uuid.uuid4()}@mail.example.com>"
        headers_json = json.dumps([
            ["Message-Id", reply_msg_id],
            ["From", "Supplier <supplier@example.com>"],
            ["To", forwarding_address],
            ["Subject", "Re: Request for Quotation"],
            ["In-Reply-To", outbound_msg_id]
        ])

        data = {
            "timestamp": timestamp,
            "token": token,
            "signature": sig,
            "recipient": forwarding_address,
            "message-headers": headers_json,
            "body-plain": "This is a real quote response text.",
            "attachment-count": "1",
        }
        
        files = {
            "attachment-1": ("quote.pdf", b"%PDF-1.4 real fake pdf data", "application/pdf")
        }

        webhook_res = await client.post(
            "/webhooks/inbound-email",
            data=data,
            files=files,
        )
        assert webhook_res.status_code == 202, webhook_res.json()

        # Job queued?
        with psycopg.connect(test_db, prepare_threshold=None) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "select payload from ingestion_jobs "
                    "where tenant_id = %s and job_type = 'email_ingest' "
                    "order by created_at desc limit 1",
                    (tenant_id,),
                )
                row = cur.fetchone()
                assert row is not None

        assert _uploaded_bytes is not None, "Webhook should have uploaded bytes"

        # Process the job manually to ensure parsing succeeds
        # we have to mock it similarly to orchestrator logic or pass it down 
        # directly if orchestrator accepts raw_email_bytes
        # In test_rfq_reply_to.py they just do:
        # result = orchestrator_module.process_inbound_email(
        #    settings, tenant_id=tenant_id, raw_email_bytes=raw_email, raw_email_ref="fake_ref"
        # )
        
        result = orchestrator_module.process_inbound_email(
            settings, tenant_id=tenant_id, raw_email_bytes=_uploaded_bytes, raw_email_ref="fake_ref"
        )
        assert result["status"] == "completed"
        assert result["match_method"] == "rfq_reply"

        # Verify RFQ is responded
        with psycopg.connect(test_db, prepare_threshold=None) as conn:
            with conn.cursor() as cur:
                cur.execute("set local role service_role")
                cur.execute("select status from rfq where id = %s", (rfq_id,))
                assert cur.fetchone()[0] == "responded"

                cur.execute(
                    "select count(*) from rfq_response where rfq_recipient_id = %s", (recipient_id,)
                )
                assert cur.fetchone()[0] == 1

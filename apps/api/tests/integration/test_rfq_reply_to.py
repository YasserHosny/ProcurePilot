import base64
import uuid

import psycopg
import pytest
from httpx import ASGITransport, AsyncClient

from procurepilot_api.config import get_settings
from procurepilot_api.deps import CurrentMember, current_member
from procurepilot_api.main import create_app
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.ingestion import router as ingestion_router_module
from procurepilot_api.shared.mailer import FakeMailer

WEBHOOK_SECRET = "test-webhook-secret"


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


class _FakeBucket:
    def upload(self, *_args: object, **_kwargs: object) -> None:
        return None


class _FakeStorage:
    def from_(self, _bucket: str) -> _FakeBucket:
        return _FakeBucket()


class _FakeSupabaseClient:
    storage = _FakeStorage()


@pytest.fixture(autouse=True)
def clear_mailer() -> None:
    FakeMailer.clear()


def _create_email_bytes(message_id: str, in_reply_to: str, forwarding_address: str) -> bytes:
    headers = [
        f"Message-ID: {message_id}",
        "From: contact@supplier.test",
        f"To: {forwarding_address}",
        "Subject: Re: Request for Quotation",
        f"In-Reply-To: {in_reply_to}",
        "Content-Type: text/plain",
        "",
        "Here is your quote: $100",
    ]
    return "\r\n".join(headers).encode("utf-8")


@pytest.fixture(autouse=True)
def setup_webhook_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INGESTION_WEBHOOK_SHARED_SECRET", WEBHOOK_SECRET)
    monkeypatch.setenv("INGESTION_EMAIL_PROVIDER", "stub")
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_rfq_send_and_webhook_capture_full_chain(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        ingestion_router_module, "create_client", lambda *_a, **_k: _FakeSupabaseClient()
    )
    from procurepilot_api.modules.ingestion import orchestrator as orchestrator_module

    monkeypatch.setattr(
        orchestrator_module, "create_client", lambda *_a, **_k: _FakeSupabaseClient()
    )

    settings = get_settings()
    app = create_app(settings)
    test_db = settings.database_url.get_secret_value()

    with psycopg.connect(test_db, prepare_threshold=None) as conn:
        with conn.cursor() as cur:
            tenant_id, user_id, membership_id, supplier_id = _seed_tenant_and_supplier(cur)
            product_id = _seed_product(cur, tenant_id)

            # Setup tenant_email_config
            forwarding_address = f"capture_{tenant_id}@{settings.ingestion_email_domain}"
            cur.execute(
                "insert into tenant_email_config "\
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
        # 1. Create RFQ
        res = await client.post(
            "/rfq",
            json={
                "needed_by_date": "2026-12-01",
                "lines": [{"workspace_product_id": str(product_id), "quantity": "100"}],
                "recipient_supplier_ids": [str(supplier_id)],
            },
            headers={"Authorization": "Bearer fake", "Idempotency-Key": str(uuid.uuid4())},
        )
        assert res.status_code == 201, res.json()
        rfq_id = res.json().get("id") or res.json().get("rfq", {}).get("id")

        # 2. Send RFQ
        send_res = await client.post(
            f"/rfq/{rfq_id}/send",
            headers={"Authorization": "Bearer fake", "Idempotency-Key": str(uuid.uuid4())},
        )
        assert send_res.status_code == 200

        # Verify FakeMailer recorded the correct Reply-To
        assert len(FakeMailer.sent_messages) == 1
        msg = FakeMailer.sent_messages[0]
        assert msg.headers is not None
        assert msg.headers["Reply-To"] == forwarding_address
        assert forwarding_address in msg.body

        # Fetch outbound_message_id from DB
        with psycopg.connect(test_db, prepare_threshold=None) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "select outbound_message_id, id from rfq_recipient where rfq_id = %s", (rfq_id,)
                )
                outbound_msg_id, recipient_id = cur.fetchone()

        # 3. Simulate inbound webhook with the reply
        raw_email = _create_email_bytes(
            f"<{uuid.uuid4()}@supplier.test>", outbound_msg_id, forwarding_address
        )
        webhook_res = await client.post(
            "/webhooks/inbound-email",
            headers={"x-ingestion-webhook-secret": WEBHOOK_SECRET},
            json={
                "recipient": forwarding_address,
                "raw_email_base64": base64.b64encode(raw_email).decode(),
            },
        )
        assert webhook_res.status_code == 202, webhook_res.json()

        # 4. Verify webhook resolved correct tenant and queued job
        with psycopg.connect(test_db, prepare_threshold=None) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "select count(*) from ingestion_jobs "\
                    "where tenant_id = %s and job_type = 'email_ingest'",
                    (tenant_id,),
                )
                assert cur.fetchone()[0] == 1

        # 5. Process job explicitly to complete the chain
        from procurepilot_api.modules.ingestion.orchestrator import process_inbound_email

        result = process_inbound_email(
            settings, tenant_id=tenant_id, raw_email_bytes=raw_email, raw_email_ref="fake_ref"
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


@pytest.mark.asyncio
async def test_rfq_send_without_tenant_email_config_sends_successfully() -> None:

    settings = get_settings()
    app = create_app(settings)
    test_db = settings.database_url.get_secret_value()

    with psycopg.connect(test_db, prepare_threshold=None) as conn:
        with conn.cursor() as cur:
            tenant_id, user_id, membership_id, supplier_id = _seed_tenant_and_supplier(cur)
            product_id = _seed_product(cur, tenant_id)
            # NO tenant_email_config row inserted here
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
        # Create RFQ
        res = await client.post(
            "/rfq",
            json={
                "needed_by_date": "2026-12-01",
                "lines": [{"workspace_product_id": str(product_id), "quantity": "100"}],
                "recipient_supplier_ids": [str(supplier_id)],
            },
            headers={"Authorization": "Bearer fake", "Idempotency-Key": str(uuid.uuid4())},
        )
        assert res.status_code == 201, res.json()
        rfq_id = res.json().get("id") or res.json().get("rfq", {}).get("id")

        # Send RFQ
        send_res = await client.post(
            f"/rfq/{rfq_id}/send",
            headers={"Authorization": "Bearer fake", "Idempotency-Key": str(uuid.uuid4())},
        )
        assert send_res.status_code == 200

    # Verify FakeMailer recorded the sent message without a Reply-To
    assert len(FakeMailer.sent_messages) == 1
    msg = FakeMailer.sent_messages[0]

    assert msg.headers is None or "Reply-To" not in msg.headers

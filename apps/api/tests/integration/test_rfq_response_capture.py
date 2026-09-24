import uuid

import psycopg
import pytest

from procurepilot_api.config import get_settings
from procurepilot_api.modules.ingestion.orchestrator import process_inbound_email


def _seed_tenant_and_supplier(cur: psycopg.Cursor) -> tuple[uuid.UUID, uuid.UUID]:
    tenant_id, user_id, membership_id, invitation_id = (
        uuid.uuid4(),
        uuid.uuid4(),
        uuid.uuid4(),
        uuid.uuid4(),
    )
    email = f"rfq-capture-e2e-{tenant_id}@example.test"
    cur.execute("insert into auth.users (id,email) values (%s,%s)", (user_id, email))
    cur.execute(
        "insert into platform_invitation (id,email,token_hash,expires_at) "
        "values (%s,%s,%s, now() + interval '7 days')",
        (invitation_id, email, f"hash-{invitation_id}"),
    )
    cur.execute(
        "insert into tenant (id,name,slug,region,currency,tax_model,platform_invitation_id) "
        "values (%s,%s,%s,'GB','GBP','uk_vat',%s)",
        (tenant_id, "RFQ Capture Tenant", str(tenant_id), invitation_id),
    )
    cur.execute(
        "insert into membership (id,tenant_id,user_id,email,role,is_active_workspace) "
        "values (%s,%s,%s,%s,'owner',true)",
        (membership_id, tenant_id, user_id, email),
    )

    cur.execute(
        "insert into tenant_email_config (id, tenant_id, forwarding_address, enabled, created_by) "
        "values (%s, %s, %s, true, %s)",
        (uuid.uuid4(), tenant_id, f"{tenant_id}@inbound.procurepilot.test", membership_id)
    )

    supplier_id = uuid.uuid4()
    cur.execute(
        "insert into supplier (id,tenant_id,name,contact_email) values (%s,%s,%s,%s)",
        (supplier_id, tenant_id, "Supplier Capture", "contact@capture.test"),
    )
    return tenant_id, supplier_id

def _seed_rfq_with_recipient(
    cur: psycopg.Cursor,
    tenant_id: uuid.UUID,
    supplier_id: uuid.UUID,
    status: str = "sent",
) -> tuple[uuid.UUID, uuid.UUID, str]:
    rfq_id = uuid.uuid4()
    cur.execute(
        "insert into rfq (id, tenant_id, created_by_membership_id, status, needed_by_date, "
        "idempotency_key) "
        "values (%s, %s, (select id from membership where tenant_id = %s limit 1), %s, "
        "'2026-12-01', %s)",
        (rfq_id, tenant_id, tenant_id, status, uuid.uuid4())
    )
    rec_id = uuid.uuid4()
    msg_id = f"<msg-{rec_id}@procurepilot.internal>"
    cur.execute(
        "insert into rfq_recipient (id, tenant_id, rfq_id, supplier_id, status, "
        "outbound_message_id) "
        "values (%s, %s, %s, %s, 'sent', %s)",
        (rec_id, tenant_id, rfq_id, supplier_id, msg_id)
    )
    return rfq_id, rec_id, msg_id

def _create_email_bytes(message_id: str, in_reply_to: str | None = None) -> bytes:
    headers = [
        f"Message-ID: {message_id}",
        "From: contact@capture.test",
        "To: inbound@procurepilot.test",
        "Subject: Quote",
        "Content-Type: text/plain",
    ]
    if in_reply_to:
        headers.append(f"In-Reply-To: {in_reply_to}")
    
    headers.append("")
    headers.append("Here is your quote: $100")
    return "\r\n".join(headers).encode("utf-8")


class _FakeBucket:
    def upload(self, path: str, content: bytes, options: dict) -> None:
        pass

class _FakeStorage:
    def from_(self, bucket: str) -> _FakeBucket:
        return _FakeBucket()

class _FakeSupabaseClient:
    def __init__(self) -> None:
        self.storage = _FakeStorage()

def _fake_create_client(*args: object, **kwargs: object) -> _FakeSupabaseClient:
    return _FakeSupabaseClient()

@pytest.fixture(autouse=True)
def mock_supabase_client(monkeypatch: pytest.MonkeyPatch) -> None:
    import procurepilot_api.modules.ingestion.orchestrator
    monkeypatch.setattr(
        procurepilot_api.modules.ingestion.orchestrator,
        "create_client",
        _fake_create_client
    )

@pytest.mark.asyncio
async def test_rfq_response_capture_matches_open_rfq() -> None:
    settings = get_settings()
    test_db = settings.database_url.get_secret_value()

    with psycopg.connect(test_db, prepare_threshold=None) as conn:
        with conn.cursor() as cur:
            tenant_id, supplier_id = _seed_tenant_and_supplier(cur)
            rfq_id, rec_id, msg_id = _seed_rfq_with_recipient(cur, tenant_id, supplier_id, "sent")
        conn.commit()

    email_bytes = _create_email_bytes(f"<{uuid.uuid4()}@mail.com>", in_reply_to=msg_id)
    result = process_inbound_email(
        settings, tenant_id=tenant_id, raw_email_bytes=email_bytes, raw_email_ref="s3://path"
    )
    
    assert result["status"] == "completed"
    assert result["match_method"] == "rfq_reply"

    with psycopg.connect(test_db) as conn:
        with conn.cursor() as cur:
            cur.execute("set local role service_role")
            # Check RFQ status
            cur.execute("select status from rfq where id = %s", (rfq_id,))
            assert cur.fetchone()[0] == "responded"
            
            # Check RFQ response row
            cur.execute(
                "select quotation_id from rfq_response where rfq_recipient_id = %s", (rec_id,)
            )
            row = cur.fetchone()
            assert row is not None
            assert str(row[0]) == result["quotation_id"]


@pytest.mark.asyncio
async def test_rfq_response_capture_no_match_falls_through() -> None:
    settings = get_settings()
    test_db = settings.database_url.get_secret_value()

    with psycopg.connect(test_db, prepare_threshold=None) as conn:
        with conn.cursor() as cur:
            tenant_id, supplier_id = _seed_tenant_and_supplier(cur)
            rfq_id, rec_id, msg_id = _seed_rfq_with_recipient(cur, tenant_id, supplier_id, "sent")
        conn.commit()

    # Different in-reply-to
    email_bytes = _create_email_bytes(f"<{uuid.uuid4()}@mail.com>", in_reply_to="<other@mail>")
    result = process_inbound_email(
        settings, tenant_id=tenant_id, raw_email_bytes=email_bytes, raw_email_ref="s3://path"
    )
    
    assert result["status"] == "completed"
    # The supplier might not be matched or matched by address if we seed it
    # We just want to ensure it falls through and does NOT create rfq_response
    assert result["match_method"] != "rfq_reply"

    with psycopg.connect(test_db) as conn:
        with conn.cursor() as cur:
            cur.execute("set local role service_role")
            cur.execute("select status from rfq where id = %s", (rfq_id,))
            assert cur.fetchone()[0] == "sent" # remains sent
            
            cur.execute("select count(*) from rfq_response where rfq_recipient_id = %s", (rec_id,))
            assert cur.fetchone()[0] == 0


@pytest.mark.asyncio
async def test_rfq_response_capture_expired_rfq() -> None:
    settings = get_settings()
    test_db = settings.database_url.get_secret_value()

    with psycopg.connect(test_db, prepare_threshold=None) as conn:
        with conn.cursor() as cur:
            tenant_id, supplier_id = _seed_tenant_and_supplier(cur)
            # RFQ is expired
            rfq_id, rec_id, msg_id = _seed_rfq_with_recipient(
                cur, tenant_id, supplier_id, "expired"
            )
        conn.commit()

    email_bytes = _create_email_bytes(f"<{uuid.uuid4()}@mail.com>", in_reply_to=msg_id)
    result = process_inbound_email(
        settings, tenant_id=tenant_id, raw_email_bytes=email_bytes, raw_email_ref="s3://path"
    )
    
    assert result["status"] == "completed"

    with psycopg.connect(test_db) as conn:
        with conn.cursor() as cur:
            cur.execute("set local role service_role")
            cur.execute("select status from rfq where id = %s", (rfq_id,))
            assert cur.fetchone()[0] == "expired" # stays expired
            
            # but response IS captured
            cur.execute("select count(*) from rfq_response where rfq_recipient_id = %s", (rec_id,))
            assert cur.fetchone()[0] == 1


@pytest.mark.asyncio
async def test_rfq_response_isolation() -> None:
    # T021 - tenant B's inbound webhook must not be able to match a reply against tenant A's
    # outbound Message-ID
    settings = get_settings()
    test_db = settings.database_url.get_secret_value()

    with psycopg.connect(test_db, prepare_threshold=None) as conn:
        with conn.cursor() as cur:
            tenant_A, supplier_A = _seed_tenant_and_supplier(cur)
            rfq_A, rec_A, msg_A = _seed_rfq_with_recipient(cur, tenant_A, supplier_A, "sent")
            
            tenant_B, supplier_B = _seed_tenant_and_supplier(cur)
        conn.commit()

    # Process email for Tenant B with Tenant A's message ID
    email_bytes = _create_email_bytes(f"<{uuid.uuid4()}@mail.com>", in_reply_to=msg_A)
    result = process_inbound_email(
        settings, tenant_id=tenant_B, raw_email_bytes=email_bytes, raw_email_ref="s3://path"
    )
    
    assert result["status"] == "completed"
    assert result["match_method"] != "rfq_reply"

    with psycopg.connect(test_db) as conn:
        with conn.cursor() as cur:
            cur.execute("set local role service_role")
            cur.execute("select status from rfq where id = %s", (rfq_A,))
            assert cur.fetchone()[0] == "sent" # remains sent
            
            cur.execute("select count(*) from rfq_response where tenant_id = %s", (tenant_B,))
            assert cur.fetchone()[0] == 0

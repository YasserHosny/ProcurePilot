import uuid

import psycopg
import pytest
from httpx import ASGITransport, AsyncClient

from procurepilot_api.config import get_settings
from procurepilot_api.main import app
from procurepilot_api.shared.mailer import FakeMailer, SendResult


def _seed_tenant(cur: psycopg.Cursor) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    tenant_id, user_id, membership_id, invitation_id = (
        uuid.uuid4(),
        uuid.uuid4(),
        uuid.uuid4(),
        uuid.uuid4(),
    )
    email = f"rfq-e2e-{user_id}@example.test"
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
        (tenant_id, "RFQ Tenant", str(tenant_id), invitation_id),
    )
    cur.execute(
        "insert into membership (id,tenant_id,user_id,email,role,is_active_workspace) "
        "values (%s,%s,%s,%s,'owner',true)",
        (membership_id, tenant_id, user_id, email),
    )
    return tenant_id, user_id, membership_id


def _seed_supplier(
    cur: psycopg.Cursor, tenant_id: uuid.UUID, contact_email: str | None = None
) -> uuid.UUID:
    supplier_id = uuid.uuid4()
    cur.execute(
        "insert into supplier (id,tenant_id,name,contact_email) values (%s,%s,%s,%s)",
        (supplier_id, tenant_id, f"Supplier {supplier_id}", contact_email),
    )
    return supplier_id


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


@pytest.fixture
def auth_headers() -> dict[str, str]:
    return {
        "Authorization": "Bearer fake-token-handled-by-deps",
        "Idempotency-Key": str(uuid.uuid4()),
    }


@pytest.mark.asyncio
async def test_create_rfq_rejects_missing_email_supplier(
    auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = get_settings()
    test_db = settings.database_url.get_secret_value()

    with psycopg.connect(test_db, prepare_threshold=None) as conn:
        with conn.cursor() as cur:
            tenant_id, user_id, membership_id = _seed_tenant(cur)
            supplier_with_email = _seed_supplier(cur, tenant_id, "contact@example.test")
            supplier_no_email = _seed_supplier(cur, tenant_id, None)
            product_id = _seed_product(cur, tenant_id)
        conn.commit()

    # Mock CurrentMember dependency
    from procurepilot_api.deps import CurrentMember, current_member
    from procurepilot_api.modules.auth.jwt import MemberRole

    def override_current_member() -> CurrentMember:
        return CurrentMember(
            user_id=user_id,
            email=f"rfq-e2e-{user_id}@example.test",
            membership_id=membership_id,
            tenant_id=tenant_id,
            role=MemberRole.owner,
        )

    app.dependency_overrides[current_member] = override_current_member

    payload = {
        "lines": [{"workspace_product_id": str(product_id), "quantity": "100.5"}],
        "recipient_supplier_ids": [str(supplier_with_email), str(supplier_no_email)],
        "needed_by_date": "2026-12-01",
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/api/v1/rfq", json=payload, headers=auth_headers)

    if resp.status_code != 201:
        print(resp.json())
    assert resp.status_code == 201
    data = resp.json()
    assert data["rfq"]["status"] == "draft"

    # Only the supplier with email should be in recipients
    assert len(data["recipients"]) == 1
    assert data["recipients"][0]["supplier_id"] == str(supplier_with_email)

    # Supplier without email should be in rejected_recipients
    assert len(data["rejected_recipients"]) == 1
    assert data["rejected_recipients"][0]["supplier_id"] == str(supplier_no_email)
    assert data["rejected_recipients"][0]["reason"] == "missing_contact_email"

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_create_rfq_replays_on_idempotency_key_not_duplicates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A retry with the same Idempotency-Key after the original request already
    committed must return the SAME rfq -- never insert a second one. The advisory
    lock alone (this codebase's first attempt) only protects against two concurrent
    callers racing with the same key; it does nothing for a retry that arrives after
    the original transaction has already committed and released the lock."""
    settings = get_settings()
    test_db = settings.database_url.get_secret_value()

    with psycopg.connect(test_db, prepare_threshold=None) as conn:
        with conn.cursor() as cur:
            tenant_id, user_id, membership_id = _seed_tenant(cur)
            supplier_id = _seed_supplier(cur, tenant_id, "contact@example.test")
            product_id = _seed_product(cur, tenant_id)
        conn.commit()

    from procurepilot_api.deps import CurrentMember, current_member
    from procurepilot_api.modules.auth.jwt import MemberRole

    def override_current_member() -> CurrentMember:
        return CurrentMember(
            user_id=user_id,
            email=f"rfq-e2e-{user_id}@example.test",
            membership_id=membership_id,
            tenant_id=tenant_id,
            role=MemberRole.owner,
        )

    app.dependency_overrides[current_member] = override_current_member

    payload = {
        "lines": [{"workspace_product_id": str(product_id), "quantity": "5"}],
        "recipient_supplier_ids": [str(supplier_id)],
        "needed_by_date": "2026-12-01",
    }
    idempotency_key = str(uuid.uuid4())
    headers = {
        "Authorization": "Bearer fake-token-handled-by-deps",
        "Idempotency-Key": idempotency_key,
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        first = await client.post("/api/v1/rfq", json=payload, headers=headers)
        assert first.status_code == 201
        second = await client.post("/api/v1/rfq", json=payload, headers=headers)
        assert second.status_code == 201

    assert first.json()["rfq"]["id"] == second.json()["rfq"]["id"]

    with psycopg.connect(test_db, prepare_threshold=None) as conn:
        with conn.cursor() as cur:
            cur.execute("select count(*) from rfq where tenant_id = %s", (tenant_id,))
            assert cur.fetchone()[0] == 1, "a replayed create must not insert a second rfq"

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_send_rfq_partial_failure_leaves_failed_draft(
    auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = get_settings()
    test_db = settings.database_url.get_secret_value()

    with psycopg.connect(test_db, prepare_threshold=None) as conn:
        with conn.cursor() as cur:
            tenant_id, user_id, membership_id = _seed_tenant(cur)
            supplier_1 = _seed_supplier(cur, tenant_id, "contact1@example.test")
            supplier_2 = _seed_supplier(cur, tenant_id, "contact2@example.test")
            product_id = _seed_product(cur, tenant_id)
        conn.commit()

    from procurepilot_api.deps import CurrentMember, current_member
    from procurepilot_api.modules.auth.jwt import MemberRole

    def override_current_member() -> CurrentMember:
        return CurrentMember(
            user_id=user_id,
            email=f"rfq-e2e-{user_id}@example.test",
            membership_id=membership_id,
            tenant_id=tenant_id,
            role=MemberRole.owner,
        )

    app.dependency_overrides[current_member] = override_current_member

    # Create the RFQ first
    create_payload = {
        "lines": [{"workspace_product_id": str(product_id), "quantity": "100"}],
        "recipient_supplier_ids": [str(supplier_1), str(supplier_2)],
        "needed_by_date": "2026-12-01",
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        create_resp = await client.post("/api/v1/rfq", json=create_payload, headers=auth_headers)
        if create_resp.status_code != 201:
            print(create_resp.json())
        assert create_resp.status_code == 201
        rfq_id = create_resp.json()["rfq"]["id"]

    # Now mock mailer to fail on supplier_2
    class FailingMailer(FakeMailer):
        def send(
            self, *, to: str, subject: str, body: str, headers: dict[str, str] | None = None
        ) -> SendResult:
            if to == "contact2@example.test":
                raise RuntimeError("Simulated mailer failure")
            return super().send(to=to, subject=subject, body=body, headers=headers)

    # We monkeypatch the import where it's used in service
    import procurepilot_api.modules.rfq.service

    monkeypatch.setattr(procurepilot_api.modules.rfq.service, "get_mailer", FailingMailer)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        send_headers = {"Idempotency-Key": str(uuid.uuid4())}
        send_resp = await client.post(f"/api/v1/rfq/{rfq_id}/send", headers=send_headers)

    assert send_resp.status_code == 200
    send_data = send_resp.json()

    # RFQ should be sent because at least one succeeded
    assert send_data["rfq"]["status"] == "sent"

    recipients = send_data["recipients"]
    assert len(recipients) == 2

    r1 = next(r for r in recipients if r["supplier_id"] == str(supplier_1))
    r2 = next(r for r in recipients if r["supplier_id"] == str(supplier_2))

    assert r1["status"] == "sent"
    assert r1["outbound_message_id"] is not None

    assert r2["status"] == "draft"
    assert r2["outbound_message_id"] is None

    app.dependency_overrides.clear()

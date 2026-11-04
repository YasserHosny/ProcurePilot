"""Integration tests for RFQ migrations PPS-174, PPS-178, PPS-179, PPS-183."""

import json
import uuid
from datetime import date, timedelta
from pathlib import Path

import psycopg
import pytest
from fastapi.testclient import TestClient

from procurepilot_api.config import get_settings
from procurepilot_api.deps import CurrentMember, current_member
from procurepilot_api.main import app
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.shared.mailer import FakeMailer, SendResult


def _db() -> psycopg.Connection:
    return psycopg.connect(get_settings().database_url.get_secret_value())


def _seed_tenant(
    cur: psycopg.Cursor, label: str = "db-set"
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    tenant_id, user_id, membership_id, invitation_id = (
        uuid.uuid4(),
        uuid.uuid4(),
        uuid.uuid4(),
        uuid.uuid4(),
    )
    email = f"rfq-{label}-{user_id}@example.test"
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
        "insert into supported_base_unit (code,label_en,label_ar,dimension,is_enabled) "
        "values ('each','Each','قطعة','count',true) on conflict do nothing"
    )
    cur.execute(
        "insert into platform_invitation (id,email,token_hash,expires_at) "
        "values (%s,%s,%s, now() + interval '7 days')",
        (invitation_id, email, f"hash-{invitation_id}"),
    )
    cur.execute(
        "insert into tenant (id,name,slug,region,currency,tax_model,platform_invitation_id) "
        "values (%s,%s,%s,'GB','GBP','uk_vat',%s)",
        (tenant_id, f"RFQ Tenant {label}", str(tenant_id), invitation_id),
    )
    cur.execute(
        "insert into membership (id,tenant_id,user_id,email,role,is_active_workspace) "
        "values (%s,%s,%s,%s,'owner',true)",
        (membership_id, tenant_id, user_id, email),
    )
    return tenant_id, user_id, membership_id


def _seed_member(cur: psycopg.Cursor, tenant_id: uuid.UUID, role: str = "buyer") -> CurrentMember:
    user_id, membership_id = uuid.uuid4(), uuid.uuid4()
    email = f"rfq-{role}-{user_id}@example.test"
    cur.execute("insert into auth.users (id,email) values (%s,%s)", (user_id, email))
    cur.execute(
        "insert into membership (id,tenant_id,user_id,email,role,is_active_workspace) "
        "values (%s,%s,%s,%s,%s,true)",
        (membership_id, tenant_id, user_id, email, role),
    )
    return CurrentMember(
        user_id=user_id,
        membership_id=membership_id,
        tenant_id=tenant_id,
        email=email,
        role=MemberRole(role),
    )


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
        (canonical_id, f"Product {canonical_id}"),
    )
    cur.execute(
        "insert into workspace_product (id,tenant_id,canonical_product_id,tenant_name) "
        "values (%s,%s,%s,%s)",
        (product_id, tenant_id, canonical_id, f"Product {product_id}"),
    )
    return product_id


def _client_for(member: CurrentMember, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setitem(app.dependency_overrides, current_member, lambda: member)
    return TestClient(app, raise_server_exceptions=False)


def test_cleanup_sql_and_db_uniqueness() -> None:
    migration_path = (
        Path(__file__).resolve().parents[4]
        / "supabase"
        / "migrations"
        / "20261104000000_rfq_recipient_unique_send_record.sql"
    )
    migration_text = migration_path.read_text()
    delete_part = migration_text[migration_text.index("delete from rfq_recipient") :]
    delete_stmt = delete_part.split(";")[0] + ";"

    with psycopg.connect(get_settings().database_url.get_secret_value(), autocommit=False) as conn:
        try:
            with conn.cursor() as cur:
                # 1. Drop the unique index to allow inserting duplicates
                cur.execute("drop index rfq_recipient_rfq_supplier_key")

                tenant_id, user_id, membership_id = _seed_tenant(cur, "cleanup")
                supp1 = _seed_supplier(cur, tenant_id, "s1@example.test")
                supp2 = _seed_supplier(cur, tenant_id, "s2@example.test")
                supp3 = _seed_supplier(cur, tenant_id, "s3@example.test")
                _seed_product(cur, tenant_id)

                # RFQ 1
                rfq1_id = uuid.uuid4()
                cur.execute(
                    "insert into rfq "
                    "(id,tenant_id,created_by_membership_id,status,needed_by_date,idempotency_key) "
                    "values (%s,%s,%s,'draft',current_date + 7,%s)",
                    (rfq1_id, tenant_id, membership_id, uuid.uuid4()),
                )
                # RFQ 2
                rfq2_id = uuid.uuid4()
                cur.execute(
                    "insert into rfq "
                    "(id,tenant_id,created_by_membership_id,status,needed_by_date,idempotency_key) "
                    "values (%s,%s,%s,'draft',current_date + 7,%s)",
                    (rfq2_id, tenant_id, membership_id, uuid.uuid4()),
                )
                # RFQ 3
                rfq3_id = uuid.uuid4()
                cur.execute(
                    "insert into rfq "
                    "(id,tenant_id,created_by_membership_id,status,needed_by_date,idempotency_key) "
                    "values (%s,%s,%s,'sent',current_date + 7,%s)",
                    (rfq3_id, tenant_id, membership_id, uuid.uuid4()),
                )

                # Group 1: two unsent drafts for (tenant_id, rfq1_id, supp1)
                rec1_a, rec1_b = uuid.uuid4(), uuid.uuid4()
                cur.execute(
                    "insert into rfq_recipient (id,tenant_id,rfq_id,supplier_id,status,created_at) "
                    "values (%s,%s,%s,%s,'draft',now() - interval '2 hours')",
                    (rec1_a, tenant_id, rfq1_id, supp1),
                )
                cur.execute(
                    "insert into rfq_recipient (id,tenant_id,rfq_id,supplier_id,status,created_at) "
                    "values (%s,%s,%s,%s,'draft',now() - interval '1 hour')",
                    (rec1_b, tenant_id, rfq1_id, supp1),
                )

                # Group 2: two rows for (tenant_id, rfq2_id, supp2).
                # One has a reply in rfq_response.
                rec2_reply, rec2_draft = uuid.uuid4(), uuid.uuid4()
                cur.execute(
                    "insert into rfq_recipient (id,tenant_id,rfq_id,supplier_id,status,created_at) "
                    "values (%s,%s,%s,%s,'draft',now() - interval '1 hour')",
                    (rec2_reply, tenant_id, rfq2_id, supp2),
                )
                cur.execute(
                    "insert into rfq_recipient (id,tenant_id,rfq_id,supplier_id,status,created_at) "
                    "values (%s,%s,%s,%s,'draft',now() - interval '2 hours')",
                    (rec2_draft, tenant_id, rfq2_id, supp2),
                )
                # create document, quotation, and rfq_response for rec2_reply
                doc_id, quot_id = uuid.uuid4(), uuid.uuid4()
                cur.execute(
                    "insert into document "
                    "(id,tenant_id,storage_bucket,storage_path,mime_type,content_hash,created_by) "
                    "values (%s,%s,'quotation-documents',%s,'application/pdf',%s,%s)",
                    (
                        doc_id,
                        tenant_id,
                        f"tenants/{tenant_id}/quotations/{doc_id}.pdf",
                        f"h-{doc_id}",
                        membership_id,
                    ),
                )
                cur.execute(
                    "insert into quotation (id,tenant_id,document_id,supplier_id,currency,status) "
                    "values (%s,%s,%s,%s,'GBP','reviewed')",
                    (quot_id, tenant_id, doc_id, supp2),
                )
                cur.execute(
                    "insert into rfq_response (id,tenant_id,rfq_recipient_id,quotation_id) "
                    "values (%s,%s,%s,%s)",
                    (uuid.uuid4(), tenant_id, rec2_reply, quot_id),
                )

                # Group 3: two SENT rows for (tenant_id, rfq3_id, supp3)
                rec3_a, rec3_b = uuid.uuid4(), uuid.uuid4()
                cur.execute(
                    "insert into rfq_recipient (id,tenant_id,rfq_id,supplier_id,status,created_at) "
                    "values (%s,%s,%s,%s,'sent',now() - interval '2 hours')",
                    (rec3_a, tenant_id, rfq3_id, supp3),
                )
                cur.execute(
                    "insert into rfq_recipient (id,tenant_id,rfq_id,supplier_id,status,created_at) "
                    "values (%s,%s,%s,%s,'sent',now() - interval '1 hour')",
                    (rec3_b, tenant_id, rfq3_id, supp3),
                )

                # Run the migration DELETE statement
                cur.execute(delete_stmt)

                # Assert only the reply-less unsent extras were deleted
                # Group 1: rec1_a kept, rec1_b deleted
                cur.execute("select id from rfq_recipient where rfq_id = %s", (rfq1_id,))
                g1_ids = {row[0] for row in cur.fetchall()}
                assert g1_ids == {rec1_a}

                # Group 2: rec2_reply kept (even though newer than rec2_draft), rec2_draft deleted
                cur.execute("select id from rfq_recipient where rfq_id = %s", (rfq2_id,))
                g2_ids = {row[0] for row in cur.fetchall()}
                assert g2_ids == {rec2_reply}

                # Group 3: both sent rows remain (not deleted because status='sent')
                cur.execute("select id from rfq_recipient where rfq_id = %s", (rfq3_id,))
                g3_ids = {row[0] for row in cur.fetchall()}
                assert g3_ids == {rec3_a, rec3_b}

                # Assert index creation fails loudly because of the sent duplicate group
                with pytest.raises(psycopg.errors.UniqueViolation):
                    cur.execute(
                        "create unique index rfq_recipient_rfq_supplier_key "
                        "on rfq_recipient (tenant_id, rfq_id, supplier_id)"
                    )
        finally:
            conn.rollback()


def test_recipient_db_unique_and_api_dedup(monkeypatch: pytest.MonkeyPatch) -> None:
    with _db() as conn:
        with conn.cursor() as cur:
            tenant_id, user_id, membership_id = _seed_tenant(cur, "dedup")
            supp = _seed_supplier(cur, tenant_id, "dedup@example.test")
            prod = _seed_product(cur, tenant_id)
        conn.commit()

    owner = CurrentMember(
        user_id=user_id,
        membership_id=membership_id,
        tenant_id=tenant_id,
        email=f"rfq-dedup-{user_id}@example.test",
        role=MemberRole.owner,
    )
    client = _client_for(owner, monkeypatch)

    # 1. API create with duplicate supplier ids in request yields exactly 1 recipient
    res = client.post(
        "/api/v1/rfq",
        headers={"Authorization": "Bearer fixture", "Idempotency-Key": str(uuid.uuid4())},
        json={
            "lines": [{"workspace_product_id": str(prod), "quantity": 5}],
            "recipient_supplier_ids": [str(supp), str(supp)],
            "needed_by_date": str(date.today() + timedelta(days=7)),
        },
    )
    assert res.status_code == 201, res.text
    data = res.json()
    assert len(data["recipients"]) == 1
    rfq_id = uuid.UUID(data["rfq"]["id"])

    # 2. Database refuses a second (tenant_id, rfq_id, supplier_id) row
    with _db() as conn:
        with pytest.raises(psycopg.errors.UniqueViolation):
            conn.execute(
                "insert into rfq_recipient (id, tenant_id, rfq_id, supplier_id, status) "
                "values (%s, %s, %s, %s, 'draft')",
                (uuid.uuid4(), tenant_id, rfq_id, supp),
            )

    # 3. API update_draft with duplicate supplier ids also yields exactly 1 recipient
    res_update = client.put(
        f"/api/v1/rfq/{rfq_id}",
        headers={"Authorization": "Bearer fixture", "Idempotency-Key": str(uuid.uuid4())},
        json={
            "lines": [{"workspace_product_id": str(prod), "quantity": 10}],
            "recipient_supplier_ids": [str(supp), str(supp)],
            "needed_by_date": str(date.today() + timedelta(days=7)),
        },
    )
    assert res_update.status_code == 200, res_update.text
    assert len(res_update.json()["recipients"]) == 1


def test_reference_numbers(monkeypatch: pytest.MonkeyPatch) -> None:
    # Tenant A
    with _db() as conn:
        with conn.cursor() as cur:
            tenant_a, user_a, mem_a = _seed_tenant(cur, "ref-a")
            supp_a = _seed_supplier(cur, tenant_a, "suppa@example.test")
            prod_a = _seed_product(cur, tenant_a)
            # Tenant B
            tenant_b, user_b, mem_b = _seed_tenant(cur, "ref-b")
            supp_b = _seed_supplier(cur, tenant_b, "suppb@example.test")
            prod_b = _seed_product(cur, tenant_b)
        conn.commit()

    owner_a = CurrentMember(
        user_id=user_a,
        membership_id=mem_a,
        tenant_id=tenant_a,
        email=f"rfq-ref-a-{user_a}@example.test",
        role=MemberRole.owner,
    )
    client_a = _client_for(owner_a, monkeypatch)

    # Tenant A creates RFQ 1
    res_a1 = client_a.post(
        "/api/v1/rfq",
        headers={"Authorization": "Bearer fixture", "Idempotency-Key": str(uuid.uuid4())},
        json={
            "lines": [{"workspace_product_id": str(prod_a), "quantity": 2}],
            "recipient_supplier_ids": [str(supp_a)],
            "needed_by_date": str(date.today() + timedelta(days=5)),
        },
    )
    assert res_a1.status_code == 201, res_a1.text
    rfq_a1_data = res_a1.json()["rfq"]
    assert "reference_number" in rfq_a1_data
    ref_a1 = rfq_a1_data["reference_number"]
    assert isinstance(ref_a1, int)
    rfq_a1_id = uuid.UUID(rfq_a1_data["id"])

    # Tenant A creates RFQ 2 -> consecutive distinct numbers
    res_a2 = client_a.post(
        "/api/v1/rfq",
        headers={"Authorization": "Bearer fixture", "Idempotency-Key": str(uuid.uuid4())},
        json={
            "lines": [{"workspace_product_id": str(prod_a), "quantity": 3}],
            "recipient_supplier_ids": [str(supp_a)],
            "needed_by_date": str(date.today() + timedelta(days=5)),
        },
    )
    assert res_a2.status_code == 201, res_a2.text
    rfq_a2_data = res_a2.json()["rfq"]
    ref_a2 = rfq_a2_data["reference_number"]
    assert ref_a2 == ref_a1 + 1

    # Tenant B creates RFQ 1 -> starts at 1 independently
    owner_b = CurrentMember(
        user_id=user_b,
        membership_id=mem_b,
        tenant_id=tenant_b,
        email=f"rfq-ref-b-{user_b}@example.test",
        role=MemberRole.owner,
    )
    client_b = _client_for(owner_b, monkeypatch)
    res_b1 = client_b.post(
        "/api/v1/rfq",
        headers={"Authorization": "Bearer fixture", "Idempotency-Key": str(uuid.uuid4())},
        json={
            "lines": [{"workspace_product_id": str(prod_b), "quantity": 1}],
            "recipient_supplier_ids": [str(supp_b)],
            "needed_by_date": str(date.today() + timedelta(days=5)),
        },
    )
    assert res_b1.status_code == 201, res_b1.text
    ref_b1 = res_b1.json()["rfq"]["reference_number"]
    assert ref_b1 == 1

    # Detail includes reference_number
    client_a = _client_for(owner_a, monkeypatch)
    detail_res = client_a.get(
        f"/api/v1/rfq/{rfq_a1_id}", headers={"Authorization": "Bearer fixture"}
    )
    assert detail_res.status_code == 200, detail_res.text
    assert detail_res.json()["rfq"]["reference_number"] == ref_a1

    # List includes reference_number
    list_res = client_a.get("/api/v1/rfq", headers={"Authorization": "Bearer fixture"})
    assert list_res.status_code == 200, list_res.text
    items = list_res.json()["items"]
    item_a1 = next(item for item in items if item["id"] == str(rfq_a1_id))
    assert item_a1["reference_number"] == ref_a1

    # Cancel returns reference_number
    cancel_res = client_a.post(
        f"/api/v1/rfq/{rfq_a1_id}/cancel", headers={"Authorization": "Bearer fixture"}
    )
    assert cancel_res.status_code == 200, cancel_res.text
    assert cancel_res.json()["reference_number"] == ref_a1


def test_send_record(monkeypatch: pytest.MonkeyPatch) -> None:
    with _db() as conn:
        with conn.cursor() as cur:
            tenant_id, user_id, mem_id = _seed_tenant(cur, "send-rec")
            supp_valid = _seed_supplier(cur, tenant_id, "valid@example.test")
            supp_no_email = _seed_supplier(cur, tenant_id, "temp@example.test")
            prod = _seed_product(cur, tenant_id)
        conn.commit()

    owner = CurrentMember(
        user_id=user_id,
        membership_id=mem_id,
        tenant_id=tenant_id,
        email=f"rfq-send-rec-{user_id}@example.test",
        role=MemberRole.owner,
    )
    client = _client_for(owner, monkeypatch)

    # Create RFQ with both suppliers
    create_res = client.post(
        "/api/v1/rfq",
        headers={"Authorization": "Bearer fixture", "Idempotency-Key": str(uuid.uuid4())},
        json={
            "lines": [{"workspace_product_id": str(prod), "quantity": 1}],
            "recipient_supplier_ids": [str(supp_valid), str(supp_no_email)],
            "needed_by_date": str(date.today() + timedelta(days=5)),
        },
    )
    assert create_res.status_code == 201, create_res.text
    rfq_id = uuid.UUID(create_res.json()["rfq"]["id"])

    # Now remove contact_email from supp_no_email in DB
    with _db() as conn:
        conn.execute("update supplier set contact_email = null where id = %s", (supp_no_email,))

    # 1. Mailer provider failure
    class FailingMailer:
        def send(self, **kwargs: object) -> SendResult:
            raise RuntimeError("Provider down")

    monkeypatch.setattr("procurepilot_api.modules.rfq.service.get_mailer", lambda: FailingMailer())

    send_res1 = client.post(
        f"/api/v1/rfq/{rfq_id}/send",
        headers={"Authorization": "Bearer fixture", "Idempotency-Key": str(uuid.uuid4())},
    )
    assert send_res1.status_code == 200, send_res1.text
    recs1 = send_res1.json()["recipients"]
    rec_valid_1 = next(r for r in recs1 if r["supplier_id"] == str(supp_valid))
    rec_no_email_1 = next(r for r in recs1 if r["supplier_id"] == str(supp_no_email))

    assert rec_valid_1["status"] == "failed"
    assert rec_valid_1["failure_reason"] == "delivery_error"
    assert rec_valid_1["send_attempts"] == 1
    assert rec_valid_1["last_attempt_at"] is not None

    assert rec_no_email_1["status"] == "failed"
    assert rec_no_email_1["failure_reason"] == "missing_contact_email"
    assert rec_no_email_1["send_attempts"] == 0
    assert rec_no_email_1["last_attempt_at"] is None

    # 2. Retry success
    monkeypatch.setattr("procurepilot_api.modules.rfq.service.get_mailer", lambda: FakeMailer())

    send_res2 = client.post(
        f"/api/v1/rfq/{rfq_id}/send",
        headers={"Authorization": "Bearer fixture", "Idempotency-Key": str(uuid.uuid4())},
    )
    assert send_res2.status_code == 200, send_res2.text
    recs2 = send_res2.json()["recipients"]
    rec_valid_2 = next(r for r in recs2 if r["supplier_id"] == str(supp_valid))
    rec_no_email_2 = next(r for r in recs2 if r["supplier_id"] == str(supp_no_email))

    assert rec_valid_2["status"] == "sent"
    assert rec_valid_2["failure_reason"] is None
    assert rec_valid_2["send_attempts"] == 2
    assert rec_valid_2["last_attempt_at"] is not None

    # Missing email supplier remains untouched on retry
    assert rec_no_email_2["status"] == "failed"
    assert rec_no_email_2["failure_reason"] == "missing_contact_email"
    assert rec_no_email_2["send_attempts"] == 0
    assert rec_no_email_2["last_attempt_at"] is None


def test_owner_sends_buyer_draft_and_direct_update_rls(monkeypatch: pytest.MonkeyPatch) -> None:
    with _db() as conn:
        with conn.cursor() as cur:
            tenant_id, user_owner, mem_owner = _seed_tenant(cur, "owner-send")
            buyer1 = _seed_member(cur, tenant_id, "buyer")
            buyer2 = _seed_member(cur, tenant_id, "buyer")
            supp1 = _seed_supplier(cur, tenant_id, "supp1-owner@example.test")
            supp2 = _seed_supplier(cur, tenant_id, "supp2-owner@example.test")
            prod = _seed_product(cur, tenant_id)
        conn.commit()

    owner = CurrentMember(
        user_id=user_owner,
        membership_id=mem_owner,
        tenant_id=tenant_id,
        email=f"rfq-owner-send-{user_owner}@example.test",
        role=MemberRole.owner,
    )

    class PartialMailer:
        def __init__(self) -> None:
            self.first_attempt = True

        def send(self, **kwargs: object) -> SendResult:
            if kwargs.get("to") == "supp2-owner@example.test" and self.first_attempt:
                raise RuntimeError("Temporary error for supp2")
            return FakeMailer().send(**kwargs)  # type: ignore[arg-type]

    partial_mailer = PartialMailer()
    monkeypatch.setattr("procurepilot_api.modules.rfq.service.get_mailer", lambda: partial_mailer)

    # Buyer 1 creates draft RFQ
    client_buyer1 = _client_for(buyer1, monkeypatch)
    create_res = client_buyer1.post(
        "/api/v1/rfq",
        headers={"Authorization": "Bearer fixture", "Idempotency-Key": str(uuid.uuid4())},
        json={
            "lines": [{"workspace_product_id": str(prod), "quantity": 5}],
            "recipient_supplier_ids": [str(supp1), str(supp2)],
            "needed_by_date": str(date.today() + timedelta(days=7)),
        },
    )
    assert create_res.status_code == 201, create_res.text
    rfq_id = uuid.UUID(create_res.json()["rfq"]["id"])

    # Buyer 2 cannot send Buyer 1's draft -> 403 not_creator
    client_buyer2 = _client_for(buyer2, monkeypatch)
    send_buyer2 = client_buyer2.post(
        f"/api/v1/rfq/{rfq_id}/send",
        headers={"Authorization": "Bearer fixture", "Idempotency-Key": str(uuid.uuid4())},
    )
    assert send_buyer2.status_code == 403, send_buyer2.text
    assert send_buyer2.json()["details"] == {"resource": "rfq", "reason": "not_creator"}

    # Owner cannot edit Buyer 1's draft (update_draft is creator-only) -> 403 not_creator
    client_owner = _client_for(owner, monkeypatch)
    edit_owner = client_owner.put(
        f"/api/v1/rfq/{rfq_id}",
        headers={"Authorization": "Bearer fixture", "Idempotency-Key": str(uuid.uuid4())},
        json={
            "lines": [{"workspace_product_id": str(prod), "quantity": 10}],
            "recipient_supplier_ids": [str(supp1), str(supp2)],
            "needed_by_date": str(date.today() + timedelta(days=7)),
        },
    )
    assert edit_owner.status_code == 403, edit_owner.text
    assert edit_owner.json()["details"] == {"resource": "rfq", "reason": "not_creator"}

    # Owner sends Buyer 1's draft -> 200, recipients sent
    send_owner = client_owner.post(
        f"/api/v1/rfq/{rfq_id}/send",
        headers={"Authorization": "Bearer fixture", "Idempotency-Key": str(uuid.uuid4())},
    )
    assert send_owner.status_code == 200, send_owner.text
    recs = send_owner.json()["recipients"]
    rec1 = next(r for r in recs if r["supplier_id"] == str(supp1))
    rec2 = next(r for r in recs if r["supplier_id"] == str(supp2))
    assert rec1["status"] == "sent"
    assert rec2["status"] == "failed"

    # Owner retries send -> 200
    partial_mailer.first_attempt = False
    retry_owner = client_owner.post(
        f"/api/v1/rfq/{rfq_id}/send",
        headers={"Authorization": "Bearer fixture", "Idempotency-Key": str(uuid.uuid4())},
    )
    assert retry_owner.status_code == 200, retry_owner.text
    recs_retry = retry_owner.json()["recipients"]
    rec2_retry = next(r for r in recs_retry if r["supplier_id"] == str(supp2))
    assert rec2_retry["status"] == "sent"

    # Database level RLS check: direct UPDATE of another buyer's RFQ
    with _db() as conn:
        # Buyer 2 direct update matches 0 rows
        claims_b2 = {
            "sub": str(buyer2.user_id),
            "tenant_id": str(buyer2.tenant_id),
            "role": "authenticated",
            "member_role": "buyer",
        }
        with conn.cursor() as cur:
            cur.execute("set local role authenticated")
            cur.execute(
                "select set_config('request.jwt.claims', %s, true)", (json.dumps(claims_b2),)
            )
            cur.execute(
                "update rfq set needed_by_date = current_date + 10 where id = %s", (rfq_id,)
            )
            assert cur.rowcount == 0

        # Owner direct update matches 1 row
        claims_owner = {
            "sub": str(owner.user_id),
            "tenant_id": str(owner.tenant_id),
            "role": "authenticated",
            "member_role": "owner",
        }
        with conn.cursor() as cur:
            cur.execute("set local role authenticated")
            cur.execute(
                "select set_config('request.jwt.claims', %s, true)", (json.dumps(claims_owner),)
            )
            # The policy admits the owner (PPS-179); the status guard then refuses an edit of an
            # RFQ that is no longer a draft (PPS-213).
            cur.execute("savepoint before_owner_edit")
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                cur.execute(
                    "update rfq set needed_by_date = current_date + 10 where id = %s", (rfq_id,)
                )
            cur.execute("rollback to savepoint before_owner_edit")

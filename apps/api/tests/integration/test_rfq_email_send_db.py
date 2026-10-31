from __future__ import annotations

import os
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import psycopg
import pytest

from procurepilot_api.config import get_settings
from procurepilot_api.deps import CurrentMember
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.rfq import service as rfq_service_module
from procurepilot_api.modules.rfq.service import RfqService
from procurepilot_api.shared.mailer import FakeMailer

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="TEST_DATABASE_URL is not set")


@pytest.mark.parametrize(
    ("tenant_locale", "member_locale", "supplier_locale", "arabic"),
    [
        ("ar", None, None, True),
        ("en", None, None, False),
        ("ar", "en", None, True),
        ("en", "ar", None, False),
        ("en", "en", "ar", True),
        ("ar", "ar", "en", False),
    ],
)
def test_send_localized_rfq_with_persisted_terms(
    monkeypatch: pytest.MonkeyPatch,
    tenant_locale: str,
    member_locale: str | None,
    supplier_locale: str | None,
    arabic: bool,
) -> None:
    _assert_localized_send(monkeypatch, tenant_locale, member_locale, supplier_locale, arabic)


def test_send_one_rfq_in_each_suppliers_language(monkeypatch: pytest.MonkeyPatch) -> None:
    _assert_localized_send(monkeypatch, "en", "en", "ar", True, mixed=True)


def _assert_localized_send(
    monkeypatch: pytest.MonkeyPatch,
    tenant_locale: str,
    member_locale: str | None,
    supplier_locale: str | None,
    arabic: bool,
    *,
    mixed: bool = False,
) -> None:
    suffix = uuid4().hex
    email = f"rfq-email-{suffix}@example.test"
    tenant_id, user_id, membership_id, invitation_id = (uuid4() for _ in range(4))
    supplier_id, canonical_id, product_id, pack_id = (uuid4() for _ in range(4))
    terms = "الدفع خلال 30 يوم\nالتسليم بالمخزن"
    tenant_name = "RFQ Locale Test"
    product_name = "عدس بجبة"
    db_url = TEST_DATABASE_URL or ""
    FakeMailer.clear()

    try:
        with psycopg.connect(db_url) as conn, conn.cursor() as cur:
            cur.execute("insert into auth.users (id,email) values (%s,%s)", (user_id, email))
            cur.execute(
                "insert into platform_invitation (id,email,token_hash,expires_at) "
                "values (%s,%s,%s,now() + interval '7 days')",
                (invitation_id, email, f"hash-{suffix}"),
            )
            cur.execute(
                "insert into tenant (id,name,slug,region,currency,tax_model,"
                "platform_invitation_id,default_locale) values (%s,%s,%s,'GB','GBP',"
                "'uk_vat',%s,%s)",
                (tenant_id, tenant_name, f"rfq-email-{suffix}", invitation_id, tenant_locale),
            )
            cur.execute(
                "insert into membership "
                "(id,tenant_id,user_id,email,role,is_active_workspace,preferred_locale) "
                "values (%s,%s,%s,%s,'owner',true,%s)",
                (membership_id, tenant_id, user_id, email, member_locale),
            )
            cur.execute(
                "insert into canonical_product (id,name,base_unit) values (%s,%s,'kilogram')",
                (canonical_id, product_name),
            )
            cur.execute(
                "insert into workspace_product (id,tenant_id,canonical_product_id,tenant_name) "
                "values (%s,%s,%s,%s)",
                (product_id, tenant_id, canonical_id, product_name),
            )
            cur.execute(
                "insert into pack_definition "
                "(id,tenant_id,workspace_product_id,pack_count,unit_size) "
                "values (%s,%s,%s,20,25)",
                (pack_id, tenant_id, product_id),
            )
            cur.execute(
                "insert into supplier (id,tenant_id,name,contact_email,preferred_locale) "
                "values (%s,%s,%s,%s,%s)",
                (
                    supplier_id,
                    tenant_id,
                    f"Supplier {suffix}",
                    f"supplier-{suffix}@example.test",
                    supplier_locale,
                ),
            )
            supplier_ids = [supplier_id]
            if mixed:
                supplier_ids.append(uuid4())
                cur.execute(
                    "insert into supplier (id,tenant_id,name,contact_email,preferred_locale) "
                    "values (%s,%s,%s,%s,'en')",
                    (
                        supplier_ids[1],
                        tenant_id,
                        f"English Supplier {suffix}",
                        f"english-{suffix}@example.test",
                    ),
                )

        member = CurrentMember(
            membership_id=membership_id,
            tenant_id=tenant_id,
            user_id=user_id,
            email=email,
            role=MemberRole.owner,
        )
        service = RfqService(settings=get_settings())
        rfq, _, recipients, _ = service.create(
            member=member,
            lines_data=[SimpleNamespace(workspace_product_id=product_id, quantity=Decimal(50))],
            recipient_supplier_ids=supplier_ids,
            needed_by_date=date(2099, 10, 20),
            idempotency_key=uuid4(),
            tenant_terms=terms,
        )
        monkeypatch.setattr(rfq_service_module, "get_mailer", FakeMailer)
        _, sent_recipients = service.send(member=member, rfq_id=rfq.id, idempotency_key=uuid4())

        with psycopg.connect(db_url) as conn, conn.cursor() as cur:
            cur.execute("select tenant_terms from rfq where id=%s", (rfq.id,))
            assert cur.fetchone()[0] == terms
        assert len(FakeMailer.sent_messages) == len(supplier_ids)
        messages = {msg.to: msg for msg in FakeMailer.sent_messages}
        if mixed:
            english = messages[f"english-{suffix}@example.test"]
            assert english.subject.startswith("Request for quotation")
            assert "50 packs (500 kg each) — 25000 kg" in english.body
            assert 'dir="ltr"' in english.html
            assert "20 October 2099" in english.subject
            assert "20 October 2099" in english.body
            assert "20 October 2099" in english.html
        msg = messages[f"supplier-{suffix}@example.test"]
        assert tenant_name in msg.subject and tenant_name in msg.from_name
        # Subject, date and body use the supplier's language, then the workspace default.
        if arabic:
            assert msg.subject.startswith("طلب عرض سعر")
            assert "Request for quotation" not in msg.subject
        else:
            assert msg.subject.startswith("Request for quotation")
        expected_date = "٢٠ أكتوبر ٢٠٩٩" if arabic else "20 October 2099"
        assert expected_date in msg.subject
        assert expected_date in msg.body and expected_date in msg.html
        assert terms.splitlines()[0] in msg.body and terms.splitlines()[1] in msg.body
        assert terms.splitlines()[0] in msg.html and terms.splitlines()[1] in msg.html
        assert product_name in msg.body and product_name in msg.html
        # 50 packs of 20 × 25 kg: quantity is in packs (ADR-020), with the base-unit total.
        expected = (
            "٥٠ عبوة (٥٠٠ كجم للعبوة) — ٢٥٠٠٠ كجم"
            if arabic
            else "50 packs (500 kg each) — 25000 kg"
        )
        assert expected in msg.body and expected in msg.html
        if arabic:
            assert 'dir="rtl"' in msg.html
        assert {r.outbound_message_id for r in sent_recipients} == {
            msg.message_id for msg in messages.values()
        }
    finally:
        with psycopg.connect(db_url) as conn, conn.cursor() as cur:
            cur.execute("set session_replication_role = replica")
            cur.execute("delete from tenant where id=%s", (tenant_id,))
            cur.execute("delete from auth.users where id=%s", (user_id,))
            cur.execute("delete from tenant where id=%s", (tenant_id,))
            cur.execute("delete from platform_invitation where id=%s", (invitation_id,))
            cur.execute("delete from canonical_product where id=%s", (canonical_id,))
            cur.execute("set session_replication_role = default")
        FakeMailer.clear()

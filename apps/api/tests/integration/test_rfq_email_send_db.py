from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID, uuid4

import psycopg
import pytest

from procurepilot_api.config import get_settings
from procurepilot_api.deps import CurrentMember
from procurepilot_api.errors import ConflictError, UnprocessableEntityError
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.rfq import service as rfq_service_module
from procurepilot_api.modules.rfq.service import RfqService
from procurepilot_api.shared.mailer import FakeMailer, SendResult

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


@contextmanager
def _rfq_fixture(
    *,
    supplier_emails: list[str | None],
    has_lines: bool = True,
    needed_by_date: date = date(2099, 10, 20),
) -> Iterator[tuple[RfqService, CurrentMember, UUID, list[UUID]]]:
    suffix = uuid4().hex
    user_email = f"rfq-user-{suffix}@example.test"
    tenant_id, user_id, membership_id, invitation_id = (uuid4() for _ in range(4))
    canonical_id, product_id, pack_id = (uuid4() for _ in range(3))
    db_url = TEST_DATABASE_URL or ""
    supplier_ids = [uuid4() for _ in supplier_emails]

    with psycopg.connect(db_url) as conn, conn.cursor() as cur:
        cur.execute("insert into auth.users (id,email) values (%s,%s)", (user_id, user_email))
        cur.execute(
            "insert into platform_invitation (id,email,token_hash,expires_at) "
            "values (%s,%s,%s,now() + interval '7 days')",
            (invitation_id, user_email, f"hash-{suffix}"),
        )
        cur.execute(
            "insert into tenant (id,name,slug,region,currency,tax_model,"
            "platform_invitation_id,default_locale) values (%s,%s,%s,'GB','GBP',"
            "'uk_vat',%s,'en')",
            (tenant_id, f"Send Reliability Test {suffix}", f"rfq-rel-{suffix}", invitation_id),
        )
        cur.execute(
            "insert into membership "
            "(id,tenant_id,user_id,email,role,is_active_workspace,preferred_locale) "
            "values (%s,%s,%s,%s,'owner',true,'en')",
            (membership_id, tenant_id, user_id, user_email),
        )
        if has_lines:
            cur.execute(
                "insert into canonical_product (id,name,base_unit) values (%s,%s,'kilogram')",
                (canonical_id, f"Test Product {suffix}"),
            )
            cur.execute(
                "insert into workspace_product (id,tenant_id,canonical_product_id,tenant_name) "
                "values (%s,%s,%s,%s)",
                (product_id, tenant_id, canonical_id, f"Test Product {suffix}"),
            )
            cur.execute(
                "insert into pack_definition "
                "(id,tenant_id,workspace_product_id,pack_count,unit_size) "
                "values (%s,%s,%s,10,1)",
                (pack_id, tenant_id, product_id),
            )
        for supp_id, _ in zip(supplier_ids, supplier_emails, strict=True):
            init_email = f"init-{supp_id.hex[:6]}@example.test"
            cur.execute(
                "insert into supplier (id,tenant_id,name,contact_email,preferred_locale) "
                "values (%s,%s,%s,%s,'en')",
                (supp_id, tenant_id, f"Supplier {supp_id.hex[:6]}", init_email),
            )

    member = CurrentMember(
        membership_id=membership_id,
        tenant_id=tenant_id,
        user_id=user_id,
        email=user_email,
        role=MemberRole.owner,
    )
    service = RfqService(settings=get_settings())
    lines_data = (
        [SimpleNamespace(workspace_product_id=product_id, quantity=Decimal(10))]
        if has_lines
        else []
    )
    rfq, _, _, _ = service.create(
        member=member,
        lines_data=lines_data,
        recipient_supplier_ids=supplier_ids,
        needed_by_date=needed_by_date,
        idempotency_key=uuid4(),
    )

    # If any supplier was requested to have no email, clear it now so that at send-time
    # the RFQ recipient exists in draft but the supplier is missing contact_email.
    with psycopg.connect(db_url) as conn, conn.cursor() as cur:
        for supp_id, supp_email in zip(supplier_ids, supplier_emails, strict=True):
            if supp_email is None:
                cur.execute(
                    "update supplier set contact_email = null where id = %s",
                    (supp_id,),
                )
            elif supp_email != f"init-{supp_id.hex[:6]}@example.test":
                cur.execute(
                    "update supplier set contact_email = %s where id = %s",
                    (supp_email, supp_id),
                )

    try:
        yield service, member, rfq.id, supplier_ids
    finally:
        with psycopg.connect(db_url) as conn, conn.cursor() as cur:
            cur.execute("set session_replication_role = replica")
            cur.execute("delete from tenant where id=%s", (tenant_id,))
            cur.execute("delete from auth.users where id=%s", (user_id,))
            cur.execute("delete from platform_invitation where id=%s", (invitation_id,))
            if has_lines:
                cur.execute("delete from canonical_product where id=%s", (canonical_id,))
            cur.execute("set session_replication_role = default")
        FakeMailer.clear()


def test_send_provider_failure_marks_recipient_failed_and_rfq_stays_draft(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_url = TEST_DATABASE_URL or ""

    class FailingMailer:
        def send(self, **_kwargs: object) -> SendResult:
            raise RuntimeError("Mailgun SMTP connection failed")

    monkeypatch.setattr(rfq_service_module, "get_mailer", lambda: FailingMailer())
    with _rfq_fixture(supplier_emails=["supp1@example.test"]) as (service, member, rfq_id, _):
        rfq, recipients = service.send(member=member, rfq_id=rfq_id, idempotency_key=uuid4())
        assert rfq.status == "draft"
        assert len(recipients) == 1
        assert recipients[0].status == "failed"

        with psycopg.connect(db_url) as conn, conn.cursor() as cur:
            cur.execute("select status from rfq_recipient where id = %s", (recipients[0].id,))
            assert cur.fetchone()[0] == "failed"
            cur.execute("select status from rfq where id = %s", (rfq_id,))
            assert cur.fetchone()[0] == "draft"


def test_send_retry_only_dispatches_failed_or_draft_recipients(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent_to: list[str] = []

    class SelectiveMailer:
        def send(self, *, to: str, **_kwargs: object) -> SendResult:
            sent_to.append(to)
            if "fail" in to:
                raise RuntimeError("Provider delivery failed")
            return SendResult(message_id=f"msg-{uuid4().hex}")

    monkeypatch.setattr(rfq_service_module, "get_mailer", lambda: SelectiveMailer())

    with _rfq_fixture(supplier_emails=["ok@example.test", "fail@example.test"]) as (
        service,
        member,
        rfq_id,
        supplier_ids,
    ):
        rfq, recipients = service.send(member=member, rfq_id=rfq_id, idempotency_key=uuid4())
        assert rfq.status == "sent"
        assert set(sent_to) == {"ok@example.test", "fail@example.test"}
        rec_by_supplier = {r.supplier_id: r for r in recipients}
        assert rec_by_supplier[supplier_ids[0]].status == "sent"
        assert rec_by_supplier[supplier_ids[1]].status == "failed"

        # Retry: mailer succeeds for all
        sent_to.clear()
        monkeypatch.setattr(rfq_service_module, "get_mailer", FakeMailer)
        rfq2, recipients2 = service.send(member=member, rfq_id=rfq_id, idempotency_key=uuid4())
        assert rfq2.status == "sent"
        # Only the failed recipient should be retried; ok is not emailed twice
        assert len(FakeMailer.sent_messages) == 1
        assert FakeMailer.sent_messages[0].to == "fail@example.test"
        assert all(r.status == "sent" for r in recipients2)


def test_send_retry_when_rfq_responded_dispatches_only_failed_recipient(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_url = TEST_DATABASE_URL or ""
    monkeypatch.setattr(rfq_service_module, "get_mailer", FakeMailer)
    with _rfq_fixture(
        supplier_emails=["supp-sent@example.test", "supp-failed@example.test"]
    ) as (service, member, rfq_id, supplier_ids):
        with psycopg.connect(db_url) as conn, conn.cursor() as cur:
            cur.execute(
                "update rfq_recipient set status = 'sent', sent_at = now(), "
                "outbound_message_id = %s where rfq_id = %s and supplier_id = %s",
                (f"msg-{uuid4().hex}", rfq_id, supplier_ids[0]),
            )
            cur.execute(
                "update rfq_recipient set status = 'failed' where rfq_id = %s and supplier_id = %s",
                (rfq_id, supplier_ids[1]),
            )
            cur.execute("update rfq set status = 'responded' where id = %s", (rfq_id,))

        FakeMailer.clear()
        rfq, recipients = service.send(member=member, rfq_id=rfq_id, idempotency_key=uuid4())
        assert rfq.status == "responded"
        assert len(FakeMailer.sent_messages) == 1
        assert FakeMailer.sent_messages[0].to == "supp-failed@example.test"
        rec_by_supplier = {r.supplier_id: r for r in recipients}
        assert rec_by_supplier[supplier_ids[0]].status == "sent"
        assert rec_by_supplier[supplier_ids[1]].status == "sent"


def test_send_rejected_when_rfq_converted(monkeypatch: pytest.MonkeyPatch) -> None:
    db_url = TEST_DATABASE_URL or ""
    monkeypatch.setattr(rfq_service_module, "get_mailer", FakeMailer)
    with _rfq_fixture(supplier_emails=["supp@example.test"]) as (service, member, rfq_id, _):
        with psycopg.connect(db_url) as conn, conn.cursor() as cur:
            cur.execute("update rfq set status = 'converted' where id = %s", (rfq_id,))
        with pytest.raises(ConflictError) as exc_info:
            service.send(member=member, rfq_id=rfq_id, idempotency_key=uuid4())
        assert exc_info.value.details == {"resource": "rfq", "reason": "not_sendable"}
        assert len(FakeMailer.sent_messages) == 0


def test_send_rejected_when_needed_by_date_in_past_on_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_url = TEST_DATABASE_URL or ""
    monkeypatch.setattr(rfq_service_module, "get_mailer", FakeMailer)
    with _rfq_fixture(supplier_emails=["supp@example.test"]) as (service, member, rfq_id, _):
        yesterday = date.today() - timedelta(days=1)
        with psycopg.connect(db_url) as conn, conn.cursor() as cur:
            cur.execute(
                "update rfq set status = 'sent', needed_by_date = %s where id = %s",
                (yesterday, rfq_id),
            )
        with pytest.raises(UnprocessableEntityError) as exc_info:
            service.send(member=member, rfq_id=rfq_id, idempotency_key=uuid4())
        assert exc_info.value.details.get("reason") == "needed_by_in_past"
        assert len(FakeMailer.sent_messages) == 0


def test_send_rejected_when_rfq_has_no_lines(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rfq_service_module, "get_mailer", FakeMailer)
    with _rfq_fixture(supplier_emails=["supp@example.test"], has_lines=False) as (
        service,
        member,
        rfq_id,
        _,
    ):
        with pytest.raises(UnprocessableEntityError) as exc_info:
            service.send(member=member, rfq_id=rfq_id, idempotency_key=uuid4())
        assert exc_info.value.details == {"reason": "nothing_to_send"}
        assert len(FakeMailer.sent_messages) == 0


def test_send_supplier_without_email_marked_failed_not_silent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_url = TEST_DATABASE_URL or ""
    monkeypatch.setattr(rfq_service_module, "get_mailer", FakeMailer)
    with _rfq_fixture(supplier_emails=["has-email@example.test", None]) as (
        service,
        member,
        rfq_id,
        supplier_ids,
    ):
        rfq, recipients = service.send(member=member, rfq_id=rfq_id, idempotency_key=uuid4())
        assert rfq.status == "sent"
        rec_by_supplier = {r.supplier_id: r for r in recipients}
        assert rec_by_supplier[supplier_ids[0]].status == "sent"
        assert rec_by_supplier[supplier_ids[1]].status == "failed"

        with psycopg.connect(db_url) as conn, conn.cursor() as cur:
            cur.execute(
                "select status from rfq_recipient where rfq_id = %s and supplier_id = %s",
                (rfq_id, supplier_ids[1]),
            )
            assert cur.fetchone()[0] == "failed"


def test_send_rejected_when_no_recipient_has_contact_email(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(rfq_service_module, "get_mailer", FakeMailer)
    with _rfq_fixture(supplier_emails=[None]) as (service, member, rfq_id, _):
        with pytest.raises(UnprocessableEntityError) as exc_info:
            service.send(member=member, rfq_id=rfq_id, idempotency_key=uuid4())
        assert exc_info.value.details == {"reason": "nothing_to_send"}
        assert len(FakeMailer.sent_messages) == 0

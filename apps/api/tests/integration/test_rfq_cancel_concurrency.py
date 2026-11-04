"""Send versus cancel on one RFQ: no supplier is emailed after the cancel has committed.

RfqService.send takes the RFQ row lock (`for update`) and reads the status again under it, so a
cancel that committed first is seen and the send is refused before any email goes out; a send that
committed first has already emailed, and the RFQ then ends up cancelled. These tests hold the row
lock from a separate connection to force each order, then race both calls under a barrier.
"""

from __future__ import annotations

import os
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID, uuid4

import psycopg
import pytest

from procurepilot_api.config import get_settings
from procurepilot_api.deps import CurrentMember
from procurepilot_api.errors import ConflictError
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.rfq import service as rfq_service_module
from procurepilot_api.modules.rfq.service import RfqService
from procurepilot_api.shared.mailer import FakeMailer

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="TEST_DATABASE_URL is not set")


@dataclass
class Seeded:
    member: CurrentMember
    rfq_id: UUID
    service: RfqService
    recipients: int


@contextmanager
def _draft_rfq(monkeypatch: pytest.MonkeyPatch, recipients: int = 2) -> Iterator[Seeded]:
    suffix = uuid4().hex
    email = f"rfq-race-{suffix}@example.test"
    tenant_id, user_id, membership_id, invitation_id = (uuid4() for _ in range(4))
    canonical_id, product_id = uuid4(), uuid4()
    supplier_ids = [uuid4() for _ in range(recipients)]
    db_url = TEST_DATABASE_URL or ""
    FakeMailer.clear()
    monkeypatch.setattr(rfq_service_module, "get_mailer", FakeMailer)
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
                "'uk_vat',%s,'en')",
                (tenant_id, "RFQ Race Test", f"rfq-race-{suffix}", invitation_id),
            )
            cur.execute(
                "insert into membership (id,tenant_id,user_id,email,role,is_active_workspace) "
                "values (%s,%s,%s,%s,'owner',true)",
                (membership_id, tenant_id, user_id, email),
            )
            cur.execute(
                "insert into canonical_product (id,name,base_unit) values (%s,%s,'kilogram')",
                (canonical_id, f"Race product {suffix}"),
            )
            cur.execute(
                "insert into workspace_product (id,tenant_id,canonical_product_id,tenant_name) "
                "values (%s,%s,%s,%s)",
                (product_id, tenant_id, canonical_id, f"Race product {suffix}"),
            )
            for index, supplier_id in enumerate(supplier_ids):
                cur.execute(
                    "insert into supplier (id,tenant_id,name,contact_email) values (%s,%s,%s,%s)",
                    (
                        supplier_id,
                        tenant_id,
                        f"Race supplier {index} {suffix}",
                        f"race-{index}-{suffix}@example.test",
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
        rfq, _, _, _ = service.create(
            member=member,
            lines_data=[SimpleNamespace(workspace_product_id=product_id, quantity=Decimal(5))],
            recipient_supplier_ids=supplier_ids,
            needed_by_date=date(2099, 10, 20),
            idempotency_key=uuid4(),
        )
        yield Seeded(member=member, rfq_id=rfq.id, service=service, recipients=recipients)
    finally:
        with psycopg.connect(db_url) as conn, conn.cursor() as cur:
            cur.execute("set session_replication_role = replica")
            cur.execute("delete from tenant where id=%s", (tenant_id,))
            cur.execute("delete from auth.users where id=%s", (user_id,))
            cur.execute("delete from platform_invitation where id=%s", (invitation_id,))
            cur.execute("delete from canonical_product where id=%s", (canonical_id,))
            cur.execute("set session_replication_role = default")
        FakeMailer.clear()


def _run(outcomes: dict[str, object], name: str, call: object) -> threading.Thread:
    def target() -> None:
        try:
            outcomes[name] = call()  # type: ignore[operator]
        except Exception as exc:  # noqa: BLE001 - the test inspects what each side raised
            outcomes[name] = exc

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    return thread


def _wait_until_blocked(rfq_id: UUID, timeout: float = 10.0) -> None:
    """Wait until some other session is waiting on a lock (the call under test is queued)."""
    deadline = time.monotonic() + timeout
    with psycopg.connect(TEST_DATABASE_URL or "", autocommit=True) as conn:
        while time.monotonic() < deadline:
            waiting = conn.execute(
                "select count(*) from pg_stat_activity where wait_event_type = 'Lock' "
                "and pid <> pg_backend_pid() and datname = current_database()"
            ).fetchone()[0]
            if waiting:
                return
            time.sleep(0.05)
    pytest.fail(f"nothing queued behind the RFQ lock for {rfq_id}")


def _rfq_state(rfq_id: UUID) -> tuple[str, object]:
    with psycopg.connect(TEST_DATABASE_URL or "") as conn:
        row = conn.execute("select status, cancelled_at from rfq where id=%s", (rfq_id,)).fetchone()
    return str(row[0]), row[1]


def _recipient_statuses(rfq_id: UUID) -> list[str]:
    with psycopg.connect(TEST_DATABASE_URL or "") as conn:
        rows = conn.execute(
            "select status from rfq_recipient where rfq_id=%s order by created_at, id", (rfq_id,)
        ).fetchall()
    return [str(row[0]) for row in rows]


def test_a_cancel_that_commits_first_stops_the_send_before_any_email(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with _draft_rfq(monkeypatch) as seeded:
        outcomes: dict[str, object] = {}
        with psycopg.connect(TEST_DATABASE_URL or "") as holder:
            # The "cancel" is committed by this session while the send is queued on the row lock.
            holder.execute("select id from rfq where id=%s for update", (seeded.rfq_id,))
            sender = _run(
                outcomes,
                "send",
                lambda: seeded.service.send(
                    member=seeded.member, rfq_id=seeded.rfq_id, idempotency_key=uuid4()
                ),
            )
            _wait_until_blocked(seeded.rfq_id)
            holder.execute(
                "update rfq set status='cancelled', cancelled_at=now() where id=%s",
                (seeded.rfq_id,),
            )
            holder.commit()
        sender.join(timeout=20)
        assert not sender.is_alive()
        assert isinstance(outcomes["send"], ConflictError), outcomes["send"]
        assert FakeMailer.sent_messages == []
        assert _recipient_statuses(seeded.rfq_id) == ["draft"] * seeded.recipients
        assert _rfq_state(seeded.rfq_id)[0] == "cancelled"


def test_a_send_and_a_cancel_queued_together_never_email_after_the_cancel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with _draft_rfq(monkeypatch) as seeded:
        outcomes: dict[str, object] = {}
        with psycopg.connect(TEST_DATABASE_URL or "") as holder:
            holder.execute("select id from rfq where id=%s for update", (seeded.rfq_id,))
            sender = _run(
                outcomes,
                "send",
                lambda: seeded.service.send(
                    member=seeded.member, rfq_id=seeded.rfq_id, idempotency_key=uuid4()
                ),
            )
            canceller = _run(
                outcomes,
                "cancel",
                lambda: seeded.service.cancel(member=seeded.member, rfq_id=seeded.rfq_id),
            )
            _wait_until_blocked(seeded.rfq_id)
            holder.rollback()
        sender.join(timeout=30)
        canceller.join(timeout=30)
        assert not sender.is_alive() and not canceller.is_alive()
        _assert_all_or_nothing(seeded, outcomes)


def _assert_all_or_nothing(seeded: Seeded, outcomes: dict[str, object]) -> None:
    """Either the send won (every supplier emailed once, then the RFQ is cancelled) or the cancel
    won (the send was refused and nobody was emailed). Never a mixture, never a send after a
    cancel."""
    status, cancelled_at = _rfq_state(seeded.rfq_id)
    assert status == "cancelled" and cancelled_at is not None, outcomes
    send_outcome = outcomes["send"]
    if isinstance(send_outcome, ConflictError):
        assert FakeMailer.sent_messages == []
        assert _recipient_statuses(seeded.rfq_id) == ["draft"] * seeded.recipients
    else:
        assert not isinstance(send_outcome, Exception), send_outcome
        assert len(FakeMailer.sent_messages) == seeded.recipients
        assert len({message.to for message in FakeMailer.sent_messages}) == seeded.recipients
        assert _recipient_statuses(seeded.rfq_id) == ["sent"] * seeded.recipients
    assert not isinstance(outcomes["cancel"], Exception), outcomes["cancel"]


@pytest.mark.parametrize("round_number", range(6))
def test_racing_a_send_against_a_cancel_keeps_the_all_or_nothing_rule(
    monkeypatch: pytest.MonkeyPatch, round_number: int
) -> None:
    with _draft_rfq(monkeypatch) as seeded:
        outcomes: dict[str, object] = {}
        barrier = threading.Barrier(2)

        def send() -> object:
            barrier.wait(timeout=10)
            return seeded.service.send(
                member=seeded.member, rfq_id=seeded.rfq_id, idempotency_key=uuid4()
            )

        def cancel() -> object:
            barrier.wait(timeout=10)
            return seeded.service.cancel(member=seeded.member, rfq_id=seeded.rfq_id)

        first, second = (
            (_run(outcomes, "send", send), _run(outcomes, "cancel", cancel))
            if round_number % 2 == 0
            else (_run(outcomes, "cancel", cancel), _run(outcomes, "send", send))
        )
        first.join(timeout=30)
        second.join(timeout=30)
        assert not first.is_alive() and not second.is_alive()
        _assert_all_or_nothing(seeded, outcomes)

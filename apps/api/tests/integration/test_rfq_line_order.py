"""Buyer order survives draft reads, edits, replays and supplier email rendering."""

from __future__ import annotations

import os
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from integration.test_rfq_service_e2e import _seed_tenant
from procurepilot_api import db
from procurepilot_api.config import get_settings
from procurepilot_api.deps import CurrentMember
from procurepilot_api.errors import NotFoundError
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.rfq import service as rfq_service_module
from procurepilot_api.modules.rfq.router import RfqLineCreate
from procurepilot_api.modules.rfq.service import RfqService
from procurepilot_api.shared.mailer import FakeMailer

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="TEST_DATABASE_URL is not set")


@dataclass
class OrderWorkspace:
    member: CurrentMember
    other_member: CurrentMember
    products: list[UUID]
    names: dict[UUID, str]
    suppliers: dict[UUID, tuple[str, str]]


@pytest.fixture
def workspace() -> Iterator[OrderWorkspace]:
    products = sorted((uuid4() for _ in range(4)), reverse=True)
    # Neither UUID nor name sorting (in either direction) reproduces buyer order.
    names = dict(zip(products, ["Rice", "Oil", "Sugar", "Flour"], strict=True))
    products = [products[i] for i in (1, 3, 0, 2)]
    canonical_ids = [uuid4() for _ in products]
    suppliers = {uuid4(): (f"Supplier {i}", f"order-{uuid4().hex}@example.test") for i in range(2)}
    members = []
    invitation_ids = []
    with db.connect(TEST_DATABASE_URL or "") as conn, conn.cursor() as cur:
        for label in ("order", "other-order"):
            tenant_id, user_id, membership_id = _seed_tenant(cur, email_suffix=label)
            cur.execute("select platform_invitation_id from tenant where id=%s", (tenant_id,))
            invitation_ids.append(cur.fetchone()[0])
            members.append(
                CurrentMember(
                    tenant_id=tenant_id,
                    user_id=user_id,
                    membership_id=membership_id,
                    email=f"rfq-e2e-{label}-{user_id}@example.test",
                    role=MemberRole.owner,
                )
            )
        for product_id, canonical_id in zip(products, canonical_ids, strict=True):
            cur.execute(
                "insert into canonical_product (id,name,base_unit,variant) "
                "values (%s,%s,'kilogram',%s)",
                (canonical_id, names[product_id], "Organic" if product_id == products[0] else None),
            )
            cur.execute(
                "insert into workspace_product (id,tenant_id,canonical_product_id,tenant_name) "
                "values (%s,%s,%s,%s)",
                (product_id, members[0].tenant_id, canonical_id, names[product_id]),
            )
            cur.execute(
                "insert into pack_definition (tenant_id,workspace_product_id,pack_count,unit_size) "
                "values (%s,%s,1,25)",
                (members[0].tenant_id, product_id),
            )
        for supplier_id, (name, email) in suppliers.items():
            cur.execute(
                "insert into supplier (id,tenant_id,name,contact_email) values (%s,%s,%s,%s)",
                (supplier_id, members[0].tenant_id, name, email),
            )
    FakeMailer.clear()
    try:
        yield OrderWorkspace(members[0], members[1], products, names, suppliers)
    finally:
        # Same teardown pattern as test_rfq_email_send_db; only this fixture's data.
        with db.connect(TEST_DATABASE_URL or "") as conn, conn.cursor() as cur:
            cur.execute("set session_replication_role = replica")
            for member, invitation_id in zip(members, invitation_ids, strict=True):
                cur.execute("delete from tenant where id=%s", (member.tenant_id,))
                cur.execute("delete from auth.users where id=%s", (member.user_id,))
                cur.execute("delete from platform_invitation where id=%s", (invitation_id,))
            for canonical_id in canonical_ids:
                cur.execute("delete from canonical_product where id=%s", (canonical_id,))
            cur.execute("set session_replication_role = default")
        FakeMailer.clear()


def _lines(products: list[UUID], quantity: int = 10) -> list[RfqLineCreate]:
    return [
        RfqLineCreate(workspace_product_id=product_id, quantity=Decimal(quantity + i))
        for i, product_id in enumerate(products)
    ]


def _reverse_storage_order(rfq_id: UUID, products: list[UUID]) -> None:
    """Make timestamp and physical row order disagree with the buyer's order."""
    with db.connect(TEST_DATABASE_URL or "") as conn, conn.cursor() as cur:
        for i in reversed(range(len(products))):
            cur.execute(
                "update rfq_line set created_at = "
                "(select created_at from rfq where id=%s) - %s * interval '1 second' "
                "where rfq_id=%s and workspace_product_id=%s",
                (rfq_id, i, rfq_id, products[i]),
            )


@pytest.mark.parametrize("edit", [False, True], ids=["create", "update"])
def test_lines_keep_buyer_order(workspace: OrderWorkspace, edit: bool) -> None:
    service = RfqService(get_settings())
    create_key, update_key = uuid4(), uuid4()
    rfq, created, _, _ = service.create(
        member=workspace.member,
        lines_data=_lines(workspace.products),
        recipient_supplier_ids=list(workspace.suppliers),
        needed_by_date=date.today(),
        idempotency_key=create_key,
    )
    expected = workspace.products
    returned = created
    if edit:
        expected = [expected[i] for i in (2, 0, 3, 1)]
        _, returned, _, _ = service.update_draft(
            member=workspace.member,
            rfq_id=rfq.id,
            lines_data=_lines(expected, 20),
            recipient_supplier_ids=list(workspace.suppliers),
            needed_by_date=date.today(),
            tenant_terms=None,
            idempotency_key=update_key,
        )
    _reverse_storage_order(rfq.id, expected)
    detail = service.get_detail(member=workspace.member, rfq_id=rfq.id)
    assert [line.workspace_product_id for line in detail.lines] == expected
    assert [line.position for line in detail.lines] == list(range(4))
    assert [line.workspace_product_id for line in returned] == expected
    assert [line.position for line in returned] == list(range(4))
    assert [line.quantity for line in detail.lines] == [line.quantity for line in returned]
    if edit:
        _, replayed, _, _ = service.update_draft(
            member=workspace.member,
            rfq_id=rfq.id,
            lines_data=_lines(expected, 20),
            recipient_supplier_ids=list(workspace.suppliers),
            needed_by_date=date.today(),
            tenant_terms=None,
            idempotency_key=update_key,
        )
    else:
        _, replayed, _, _ = service.create(
            member=workspace.member,
            lines_data=_lines(expected),
            recipient_supplier_ids=list(workspace.suppliers),
            needed_by_date=date.today(),
            idempotency_key=create_key,
        )
    assert [line.workspace_product_id for line in replayed] == expected
    assert [line.position for line in replayed] == list(range(4))


def test_send_keeps_buyer_order(workspace: OrderWorkspace, monkeypatch: pytest.MonkeyPatch) -> None:
    service = RfqService(get_settings())
    rfq, _, _, _ = service.create(
        member=workspace.member,
        lines_data=_lines(workspace.products),
        recipient_supplier_ids=list(workspace.suppliers),
        needed_by_date=date.today(),
        idempotency_key=uuid4(),
    )
    _reverse_storage_order(rfq.id, workspace.products)
    monkeypatch.setattr(rfq_service_module, "get_mailer", FakeMailer)
    service.send(member=workspace.member, rfq_id=rfq.id, idempotency_key=uuid4())
    assert len(FakeMailer.sent_messages) == len(workspace.suppliers)
    for message in FakeMailer.sent_messages:
        for body in (message.body, message.html):
            offsets = [body.index(workspace.names[product]) for product in workspace.products]
            assert offsets == sorted(offsets)


def test_detail_names_and_isolation(workspace: OrderWorkspace) -> None:
    service = RfqService(get_settings())
    rfq, created, recipients, _ = service.create(
        member=workspace.member,
        lines_data=_lines(workspace.products),
        recipient_supplier_ids=list(workspace.suppliers),
        needed_by_date=date.today(),
        idempotency_key=uuid4(),
    )
    detail = service.get_detail(member=workspace.member, rfq_id=rfq.id)
    assert [line.product_name for line in detail.lines] == [
        workspace.names[product] for product in workspace.products
    ]
    assert [line.product_variant for line in detail.lines] == ["Organic", None, None, None]
    assert all("pack_label" not in line.model_dump() for line in detail.lines)
    for recipient in detail.recipients:
        assert (recipient.supplier_name, recipient.supplier_contact_email) == workspace.suppliers[
            recipient.supplier_id
        ]
    assert all(line.product_name is None for line in created)
    assert all(recipient.supplier_name is None for recipient in recipients)
    with pytest.raises(NotFoundError):
        service.get_detail(member=workspace.other_member, rfq_id=rfq.id)

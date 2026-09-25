import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from procurepilot_api.modules.rfq.schemas import (
    Rfq,
    RfqLine,
    RfqRecipient,
)
from procurepilot_api.modules.rfq.service import build_rfq_message


def test_build_rfq_message_content() -> None:
    tenant_id = uuid.uuid4()
    rfq_id = uuid.uuid4()
    recipient_id = uuid.uuid4()
    now = datetime.now(UTC)

    rfq = Rfq(
        id=rfq_id,
        tenant_id=tenant_id,
        created_by_membership_id=uuid.uuid4(),
        status="draft",
        needed_by_date=date(2026, 12, 1),
        idempotency_key=uuid.uuid4(),
        created_at=now,
    )

    line1 = RfqLine(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        rfq_id=rfq_id,
        workspace_product_id=uuid.uuid4(),
        quantity=Decimal("10.5"),
        created_at=now,
    )
    line2 = RfqLine(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        rfq_id=rfq_id,
        workspace_product_id=uuid.uuid4(),
        quantity=Decimal("100"),
        created_at=now,
    )

    recipient = RfqRecipient(
        id=recipient_id,
        tenant_id=tenant_id,
        rfq_id=rfq_id,
        supplier_id=uuid.uuid4(),
        status="draft",
        created_at=now,
    )

    product_names = {
        line1.workspace_product_id: "Steel Beams",
        line2.workspace_product_id: "Cement Bags",
    }

    subject, body, message_id = build_rfq_message(
        rfq=rfq,
        lines=[line1, line2],
        product_names=product_names,
        recipient=recipient,
        tenant_terms="Please deliver during business hours.",
    )

    assert "Request for Quotation" in subject
    assert "Steel Beams" in body
    assert "10.5" in body
    assert "Cement Bags" in body
    assert "100" in body
    assert "2026-12-01" in body
    assert "Please deliver during business hours." in body

    # Message-ID must be stable
    _, _, message_id2 = build_rfq_message(
        rfq=rfq,
        lines=[line1, line2],
        product_names=product_names,
        recipient=recipient,
        tenant_terms="Please deliver during business hours.",
    )
    assert message_id == message_id2

    assert str(tenant_id) in message_id or message_id.startswith("urn:uuid:") or "@" in message_id

"""RFQ cancellation through the real API, RLS, audit and ingestion paths."""

from datetime import date
from uuid import UUID, uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from httpx import Response
from unit.test_rfq_roles import _client

from integration.fixtures.round1_rfq import round1_rfq
from integration.test_rfq_expiry import ExpiryRfq
from integration.test_rfq_expiry import expiry_rfq as _cancel_fixture
from integration.test_rfq_response_capture import (
    _create_email_bytes,
    _seed_rfq_with_recipient,
    _seed_tenant_and_supplier,
)
from integration.test_rfq_response_capture import mock_supabase_client as _capture_fixture
from integration.test_rfq_service_e2e import _seed_tenant
from integration.test_rfq_split import _authenticate, _post
from integration.test_rfq_split import queue as _queue_fixture
from integration.test_rfq_split_prepare import _prepare
from procurepilot_api.config import get_settings
from procurepilot_api.deps import CurrentMember, current_member
from procurepilot_api.main import app
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.ingestion.orchestrator import process_inbound_email
from procurepilot_api.modules.rfq.guardrails import (
    AutoPreparationGuardrail,
    GuardrailEvaluationInput,
    evaluate_guardrail,
)

cancel_rfq = _cancel_fixture
capture_storage = _capture_fixture
split_queue = _queue_fixture


def _db() -> psycopg.Connection:
    return psycopg.connect(get_settings().database_url.get_secret_value())


def _buyer(tenant_id: UUID) -> CurrentMember:
    user_id, membership_id = uuid4(), uuid4()
    email = f"cancel-{user_id}@example.test"
    with _db() as conn:
        conn.execute("insert into auth.users (id,email) values (%s,%s)", (user_id, email))
        conn.execute(
            "insert into membership (id,tenant_id,user_id,email,role,is_active_workspace) "
            "values (%s,%s,%s,%s,'buyer',true)",
            (membership_id, tenant_id, user_id, email),
        )
    return CurrentMember(
        user_id=user_id,
        membership_id=membership_id,
        tenant_id=tenant_id,
        email=email,
        role=MemberRole.buyer,
    )


def _cancel(rfq_id: UUID) -> Response:
    return TestClient(app).post(f"/api/v1/rfq/{rfq_id}/cancel")


def _assert_cancelled(rfq_id: UUID) -> None:
    with _db() as conn:
        row = conn.execute("select status,cancelled_at from rfq where id=%s", (rfq_id,)).fetchone()
    assert row[0] == "cancelled"
    assert row[1] is not None


@pytest.mark.parametrize("status", ["draft", "sent", "responded"])
def test_owner_cancels_buyers_rfq_and_replays(
    cancel_rfq: ExpiryRfq,
    status: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rfq_id, _, _, owner = cancel_rfq
    buyer = _buyer(owner.tenant_id)

    def unexpected_mailer() -> None:
        pytest.fail("Cancellation must not invoke the mailer")

    monkeypatch.setattr("procurepilot_api.modules.rfq.service.get_mailer", unexpected_mailer)
    with _db() as conn:
        conn.execute(
            "update rfq set created_by_membership_id=%s,status=%s where id=%s",
            (buyer.membership_id, status, rfq_id),
        )
    first = _cancel(rfq_id)
    assert first.status_code == 200, first.text
    assert first.json()["status"] == "cancelled"
    assert first.json()["cancelled_at"] is not None
    replay = TestClient(app).post(
        f"/api/v1/rfq/{rfq_id}/cancel", headers={"Idempotency-Key": str(uuid4())}
    )
    assert replay.status_code == 200, replay.text
    assert replay.json() == first.json()
    _assert_cancelled(rfq_id)
    with _db() as conn:
        audits = conn.execute(
            "select actor_membership_id,target from audit_event "
            "where tenant_id=%s and action='rfq.cancelled'",
            (owner.tenant_id,),
        ).fetchall()
    assert len(audits) == 1
    assert audits[0] == (owner.membership_id, {"rfq_id": str(rfq_id)})
    detail = TestClient(app).get(f"/api/v1/rfq/{rfq_id}")
    assert detail.status_code == 200, detail.text
    assert detail.json()["rfq"] == first.json()
    listing = TestClient(app).get("/api/v1/rfq?status=cancelled")
    assert listing.status_code == 200, listing.text
    item = next(row for row in listing.json()["items"] if row["id"] == str(rfq_id))
    assert item["status"] == "cancelled"
    assert item["cancelled_at"] == first.json()["cancelled_at"]


@pytest.mark.parametrize("own", [True, False])
def test_buyer_cancel_creator_rule(
    cancel_rfq: ExpiryRfq,
    monkeypatch: pytest.MonkeyPatch,
    own: bool,
) -> None:
    rfq_id, _, _, owner = cancel_rfq
    creator, caller = _buyer(owner.tenant_id), _buyer(owner.tenant_id)
    with _db() as conn:
        conn.execute(
            "update rfq set created_by_membership_id=%s where id=%s",
            (creator.membership_id, rfq_id),
        )
    monkeypatch.setitem(
        app.dependency_overrides, current_member, lambda: creator if own else caller
    )
    response = _cancel(rfq_id)
    assert response.status_code == (200 if own else 403), response.text
    if own:
        _assert_cancelled(rfq_id)
    else:
        assert response.json()["details"] == {"resource": "rfq", "reason": "not_creator"}
        with _db() as conn:
            assert conn.execute("select status from rfq where id=%s", (rfq_id,)).fetchone() == (
                "sent",
            )


@pytest.mark.parametrize(
    "role", [MemberRole.viewer, MemberRole.approver, MemberRole.branch_manager]
)
def test_other_roles_cannot_cancel(role: MemberRole) -> None:
    with _client(role) as client:
        response = client.post(f"/api/v1/rfq/{uuid4()}/cancel")
    assert response.status_code == 403, response.text


def test_cancel_cross_tenant_is_not_found(
    cancel_rfq: ExpiryRfq,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rfq_id, _, _, _ = cancel_rfq
    with _db() as conn:
        tenant_id, user_id, membership_id = _seed_tenant(conn.cursor(), email_suffix="cancel-other")
    other = CurrentMember(
        tenant_id=tenant_id,
        user_id=user_id,
        membership_id=membership_id,
        email=f"other-{user_id}@example.test",
        role=MemberRole.owner,
    )
    monkeypatch.setitem(app.dependency_overrides, current_member, lambda: other)
    response = _cancel(rfq_id)
    assert response.status_code == 404, response.text
    with _db() as conn:
        assert conn.execute(
            "select status,cancelled_at from rfq where id=%s", (rfq_id,)
        ).fetchone() == ("sent", None)


@pytest.mark.parametrize("status", ["converted", "expired"])
def test_terminal_rfq_cannot_cancel(cancel_rfq: ExpiryRfq, status: str) -> None:
    rfq_id, _, _, _ = cancel_rfq
    with _db() as conn:
        conn.execute("update rfq set status=%s where id=%s", (status, rfq_id))
    response = _cancel(rfq_id)
    assert response.status_code == 409, response.text
    assert response.json()["details"] == {"resource": "rfq", "reason": "not_cancellable"}


def test_cancelled_rejects_send_update_and_prepare(cancel_rfq: ExpiryRfq) -> None:
    rfq_id, response_id, branch_id, _ = cancel_rfq
    # Set the terminal state independently so these guards also fail red without the endpoint.
    with _db() as conn:
        conn.execute("update rfq set status='cancelled',cancelled_at=now() where id=%s", (rfq_id,))
        product_id = conn.execute(
            "select workspace_product_id from rfq_line where rfq_id=%s limit 1", (rfq_id,)
        ).fetchone()[0]
    client = TestClient(app)
    headers = {"Idempotency-Key": str(uuid4()), "Authorization": "Bearer fixture"}
    sent = client.post(f"/api/v1/rfq/{rfq_id}/send", headers=headers)
    assert sent.status_code == 409, sent.text
    assert sent.json()["details"]["reason"] == "not_sendable"
    updated = client.put(
        f"/api/v1/rfq/{rfq_id}",
        headers=headers,
        json={
            "lines": [{"workspace_product_id": str(product_id), "quantity": 1}],
            "recipient_supplier_ids": [],
            "needed_by_date": str(date.today()),
        },
    )
    assert updated.status_code == 409, updated.text
    assert updated.json()["details"]["reason"] == "not_draft"
    prepared = client.post(
        f"/api/v1/rfq/{rfq_id}/prepare-request",
        headers=headers,
        json={
            "rfq_response_id": str(response_id),
            "branch_id": str(branch_id),
            "required_by_date": str(date.today()),
        },
    )
    assert prepared.status_code == 422, prepared.text
    assert prepared.json()["details"] == {"reason": "rfq_cancelled"}
    _assert_cancelled(rfq_id)


def test_cancelled_rejects_split_start_and_prepare(
    monkeypatch: pytest.MonkeyPatch,
    split_queue: list,
) -> None:
    with round1_rfq() as fixture:
        _authenticate(monkeypatch, fixture)
        started = _post(fixture)
        assert started.status_code == 202, started.text
        with _db() as conn:
            conn.execute(
                "update rfq set status='cancelled',cancelled_at=now() where id=%s",
                (fixture.rfq_id,),
            )
        rejected = _post(fixture)
        assert rejected.status_code == 422, rejected.text
        assert rejected.json()["details"] == {"reason": "rfq_cancelled"}
        prepared = _prepare(fixture, UUID(started.json()["id"]))
        assert prepared.status_code == 422, prepared.text
        assert prepared.json()["details"] == {"reason": "rfq_cancelled"}
        assert len(split_queue) == 1
        with _db() as conn:
            assert conn.execute(
                "select count(*) from purchase_request where tenant_id=%s",
                (fixture.workspace.tenant_id,),
            ).fetchone() == (0,)


def test_cancelled_guardrail_is_not_open() -> None:
    from decimal import Decimal

    guardrail = AutoPreparationGuardrail(
        id=uuid4(),
        tenant_id=uuid4(),
        enabled=True,
        min_response_count=1,
        max_order_value_amount=Decimal(100),
        max_order_value_currency="GBP",
        max_price_variance_pct=Decimal(1),
        supplier_allowlist=None,
        category_allowlist=None,
        default_branch_id=uuid4(),
        created_by_membership_id=uuid4(),
    )
    decision = evaluate_guardrail(
        GuardrailEvaluationInput(
            guardrail=guardrail,
            rfq_status="cancelled",
            total_response_count=1,
            candidates=[],
            recent_average_price_by_product={},
        )
    )
    assert not decision.fired
    assert decision.reason == "rfq_not_open"


def test_cancelled_late_reply_is_stored(capture_storage: None) -> None:
    with _db() as conn:
        tenant_id, supplier_id = _seed_tenant_and_supplier(conn.cursor())
        rfq_id, recipient_id, message_id = _seed_rfq_with_recipient(
            conn.cursor(), tenant_id, supplier_id
        )
        conn.execute("update rfq set status='cancelled',cancelled_at=now() where id=%s", (rfq_id,))
    result = process_inbound_email(
        get_settings(),
        tenant_id=tenant_id,
        raw_email_bytes=_create_email_bytes(f"<{uuid4()}@example.test>", in_reply_to=message_id),
        raw_email_ref="s3://fixture",
    )
    assert result["status"] == "completed"
    assert result["match_method"] == "rfq_reply"
    _assert_cancelled(rfq_id)
    with _db() as conn:
        assert (
            str(
                conn.execute(
                    "select quotation_id from rfq_response where rfq_recipient_id=%s",
                    (recipient_id,),
                ).fetchone()[0]
            )
            == result["quotation_id"]
        )

"""Derived RFQ expiry, using isolated tenants and the real API/database paths."""

from datetime import date
from uuid import UUID, uuid4

import psycopg
import pytest
from httpx import ASGITransport, AsyncClient

from integration.test_rfq_service_e2e import (
    _patch_requests_service_for_test,
    _seed_rfq_and_responses,
    _seed_tenant,
)
from procurepilot_api.config import get_settings
from procurepilot_api.deps import CurrentMember, current_member
from procurepilot_api.main import app
from procurepilot_api.modules.auth.jwt import MemberRole

ExpiryRfq = tuple[UUID, UUID, UUID, CurrentMember]


@pytest.fixture
def expiry_rfq(monkeypatch: pytest.MonkeyPatch) -> ExpiryRfq:
    settings = get_settings()
    with psycopg.connect(settings.database_url.get_secret_value(), prepare_threshold=None) as conn:
        with conn.cursor() as cur:
            tenant_id, user_id, membership_id = _seed_tenant(cur, email_suffix="expiry")
            rfq_id, response_id, _, branch_id = _seed_rfq_and_responses(
                cur, tenant_id, membership_id
            )
            cur.execute(
                "update rfq set status = 'sent', needed_by_date = current_date - 1 where id = %s",
                (rfq_id,),
            )
        conn.commit()
    member = CurrentMember(
        user_id=user_id,
        membership_id=membership_id,
        tenant_id=tenant_id,
        email=f"expiry-{user_id}@example.test",
        role=MemberRole.owner,
    )
    monkeypatch.setitem(app.dependency_overrides, current_member, lambda: member)
    return rfq_id, response_id, branch_id, member


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "stored,expected",
    [
        ("sent", "expired"),
        ("responded", "responded"),
        ("draft", "draft"),
        ("converted", "converted"),
    ],
)
async def test_expiry_reads(expiry_rfq: ExpiryRfq, stored: str, expected: str) -> None:
    rfq_id, _, _, _ = expiry_rfq
    with psycopg.connect(get_settings().database_url.get_secret_value()) as conn:
        conn.execute("update rfq set status = %s where id = %s", (stored, rfq_id))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        listing = await client.get("/api/v1/rfq")
        detail = await client.get(f"/api/v1/rfq/{rfq_id}")
    assert listing.status_code == detail.status_code == 200
    item = next(row for row in listing.json()["items"] if row["id"] == str(rfq_id))
    assert (item["status"], detail.json()["rfq"]["status"]) == (expected, expected)
    with psycopg.connect(get_settings().database_url.get_secret_value()) as conn:
        assert (
            conn.execute("select status from rfq where id = %s", (rfq_id,)).fetchone()[0] == stored
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,expected_code,included",
    [
        ("expired", 200, True),
        ("sent", 200, False),
        ("bogus", 422, False),
    ],
)
async def test_expiry_filter(
    expiry_rfq: ExpiryRfq, status: str, expected_code: int, included: bool
) -> None:
    rfq_id, _, _, _ = expiry_rfq
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        result = await client.get("/api/v1/rfq", params={"status": status})
    assert result.status_code == expected_code
    if expected_code == 200:
        assert (str(rfq_id) in [row["id"] for row in result.json()["items"]]) is included


@pytest.mark.asyncio
async def test_expiry_blocks_preparation(
    expiry_rfq: ExpiryRfq, monkeypatch: pytest.MonkeyPatch
) -> None:
    rfq_id, response_id, branch_id, member = expiry_rfq
    _patch_requests_service_for_test(
        monkeypatch,
        tenant_id=member.tenant_id,
        user_id=member.user_id,
        membership_id=member.membership_id,
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        result = await client.post(
            f"/api/v1/rfq/{rfq_id}/prepare-request",
            headers={"Authorization": "Bearer fixture", "Idempotency-Key": str(uuid4())},
            json={
                "rfq_response_id": str(response_id),
                "branch_id": str(branch_id),
                "required_by_date": date.today().isoformat(),
            },
        )
    assert result.status_code == 422, result.text
    assert result.json()["details"] == {"reason": "rfq_expired"}
    with psycopg.connect(get_settings().database_url.get_secret_value()) as conn:
        assert (
            conn.execute(
                "select count(*) from purchase_request where tenant_id = %s",
                (member.tenant_id,),
            ).fetchone()[0]
            == 0
        )
        assert (
            conn.execute(
                "select count(*) from purchase_request_line where tenant_id = %s",
                (member.tenant_id,),
            ).fetchone()[0]
            == 0
        )
        assert (
            conn.execute("select status from rfq where id = %s", (rfq_id,)).fetchone()[0] == "sent"
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("days,expected", [(-1, "expired"), (0, "sent"), (1, "sent")])
async def test_unanswered_expiry_deadline_boundary(
    expiry_rfq: ExpiryRfq, days: int, expected: str
) -> None:
    _, _, _, member = expiry_rfq
    rfq_id = uuid4()
    with psycopg.connect(get_settings().database_url.get_secret_value()) as conn:
        conn.execute(
            "insert into rfq (id, tenant_id, created_by_membership_id, status, "
            "needed_by_date, idempotency_key) "
            "values (%s, %s, %s, 'sent', current_date + %s, %s)",
            (rfq_id, member.tenant_id, member.membership_id, days, uuid4()),
        )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        listing = await client.get("/api/v1/rfq")
        detail = await client.get(f"/api/v1/rfq/{rfq_id}")
    assert listing.status_code == detail.status_code == 200
    item = next(row for row in listing.json()["items"] if row["id"] == str(rfq_id))
    assert item["response_count"] == 0
    assert (item["status"], detail.json()["rfq"]["status"]) == (expected, expected)

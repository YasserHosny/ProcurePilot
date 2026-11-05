"""A request line's estimate is read in the caller's workspace, not as the table owner (PPS-185).


`RequestsService._estimate_products` used to read `landed_cost`, `current_match_decision` and
`purchase_request` over a bare owner connection, so what it could see was decided only by the
product ids the caller had already passed through RLS. It now reads inside the caller's own
database role and claims, so a product or request of another workspace has no estimate.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import psycopg
import pytest

from integration.catalogue_helpers import TEST_DATABASE_URL
from integration.smart_compare_helpers import (
    add_costed_offer,
    committed_smart_context,
    member_from_workspace,
    settings_for_test_db,
)
from integration.test_pack_pricing_model import _request_row, _seed
from integration.test_rfq_service_e2e import _seed_tenant
from procurepilot_api.config import get_settings
from procurepilot_api.deps import CurrentMember
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.requests.service import RequestsService

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL not set; needs Postgres with the migrations applied",
)


def test_a_caller_gets_the_estimate_of_their_own_product(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = settings_for_test_db(monkeypatch)
    with committed_smart_context("p161-own") as own:
        add_costed_offer(own, supplier_id=own.supplier_ids[0], amount=Decimal("42.00"))
        (estimate,) = RequestsService(settings)._estimate_products(
            [own.product_id], member=member_from_workspace(own.workspace)
        )
    assert estimate.unit_price_amount == Decimal("42.00")
    assert estimate.source_landed_cost_id is not None


def test_a_product_of_another_workspace_has_no_estimate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = settings_for_test_db(monkeypatch)
    with committed_smart_context("p161-a") as caller, committed_smart_context("p161-b") as other:
        add_costed_offer(other, supplier_id=other.supplier_ids[0], amount=Decimal("77.00"))
        (estimate,) = RequestsService(settings)._estimate_products(
            [other.product_id], member=member_from_workspace(caller.workspace)
        )
    assert estimate.unit_price_amount is None
    assert estimate.source_landed_cost_id is None


def test_a_requester_who_can_no_longer_read_rfqs_keeps_the_source_response_price() -> None:
    """A request prepared from an RFQ response stays valued at that response's prices after the
    requester's role changes to one that cannot read RFQ tables (review finding)."""
    with psycopg.connect(TEST_DATABASE_URL or "", prepare_threshold=None) as conn:
        with conn.cursor() as cur:
            tenant_id, user_id, membership_id = _seed_tenant(
                cur, email_suffix=f"p161-demoted-{uuid4().hex[:8]}"
            )
            products, responses = _seed(cur, tenant_id, membership_id)
            rid = _request_row(cur, tenant_id, membership_id, responses["noor"])
            # The workspace keeps another owner, so the requester can be demoted.
            other_user = uuid4()
            cur.execute(
                "insert into auth.users (id,email) values (%s,%s)",
                (other_user, f"owner2-{other_user.hex[:8]}@example.test"),
            )
            cur.execute(
                "insert into membership (tenant_id,user_id,email,role) values (%s,%s,%s,'owner') "
                "returning id",
                (tenant_id, other_user, f"owner2-{other_user.hex[:8]}@example.test"),
            )
            other_membership = cur.fetchone()[0]
            # The RFQ was created by the other owner, so the demoted requester no longer reads it.
            cur.execute(
                "update rfq set created_by_membership_id = %s where tenant_id = %s",
                (other_membership, tenant_id),
            )
            cur.execute("update membership set role = 'viewer' where id = %s", (membership_id,))
        conn.commit()

    member = CurrentMember(
        membership_id=membership_id,
        tenant_id=tenant_id,
        user_id=user_id,
        email="demoted@example.test",
        role=MemberRole.viewer,
    )
    estimates = RequestsService(settings=get_settings())._estimate_products(
        products, member=member, request_id=rid
    )
    # The source response's (النور) per-pack prices, not the latest supplier's.
    assert [e.unit_price_amount for e in estimates] == [
        Decimal(1680),
        Decimal(940),
        Decimal(905),
        Decimal(545),
        Decimal(72),
    ]

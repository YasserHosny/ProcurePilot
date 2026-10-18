"""R4.3 Phase 6 (T032, T036): guardrail management endpoints, against real Postgres.

FR-013: a guardrail configuration whose max_order_value_amount could never realistically
trigger (zero, negative) must be refused at creation/update, never silently accepted.
FR-010: guardrail management is owner-only.
"""

from __future__ import annotations

import os
import uuid
from decimal import Decimal

import psycopg
import pytest

from procurepilot_api.config import get_settings
from procurepilot_api.deps import CurrentMember
from procurepilot_api.errors import (
    NotFoundError,
    PermissionDeniedError,
    UnprocessableEntityError,
)
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.rfq.router import create_guardrail, update_guardrail
from procurepilot_api.modules.rfq.schemas import GuardrailCreateInput, GuardrailUpdateInput
from procurepilot_api.modules.rfq.service import RfqService

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is not set; needs a Postgres with the migrations applied",
)


def _seed_tenant(cur: psycopg.Cursor) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID]:
    tenant_id, user_id, membership_id, invitation_id = (
        uuid.uuid4(),
        uuid.uuid4(),
        uuid.uuid4(),
        uuid.uuid4(),
    )
    email = f"guardrail-mgmt-{tenant_id}@example.test"
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
        (tenant_id, "Guardrail Mgmt Ltd", str(tenant_id), invitation_id),
    )
    cur.execute(
        "insert into membership (id,tenant_id,user_id,email,role,is_active_workspace) "
        "values (%s,%s,%s,%s,'owner',true)",
        (membership_id, tenant_id, user_id, email),
    )
    branch_id = uuid.uuid4()
    cur.execute(
        "insert into branch (id,tenant_id,name) values (%s,%s,'Main')", (branch_id, tenant_id)
    )
    return tenant_id, user_id, membership_id, branch_id


def _owner(tenant_id: uuid.UUID, user_id: uuid.UUID, membership_id: uuid.UUID) -> CurrentMember:
    return CurrentMember(
        membership_id=membership_id,
        tenant_id=tenant_id,
        user_id=user_id,
        email="owner@example.test",
        role=MemberRole.owner,
    )


def test_create_guardrail_rejects_non_positive_max_order_value() -> None:
    with psycopg.connect(TEST_DATABASE_URL or "", prepare_threshold=None) as conn:
        with conn.cursor() as cur:
            tenant_id, user_id, membership_id, branch_id = _seed_tenant(cur)
        conn.commit()

    member = _owner(tenant_id, user_id, membership_id)
    service = RfqService(settings=get_settings())

    for bad_amount in (Decimal("0"), Decimal("-1")):
        payload = GuardrailCreateInput(
            max_order_value_amount=bad_amount,
            max_order_value_currency="GBP",
            max_price_variance_pct=Decimal("0.10"),
            default_branch_id=branch_id,
        )
        with pytest.raises(UnprocessableEntityError):
            create_guardrail(payload=payload, member=member, service=service)

    with psycopg.connect(TEST_DATABASE_URL or "", prepare_threshold=None) as conn:
        with conn.cursor() as cur:
            cur.execute("set local role service_role")
            cur.execute(
                "select count(*) from auto_preparation_guardrail where tenant_id = %s",
                (tenant_id,),
            )
            assert cur.fetchone()[0] == 0


def test_create_guardrail_rejects_non_owner() -> None:
    with psycopg.connect(TEST_DATABASE_URL or "", prepare_threshold=None) as conn:
        with conn.cursor() as cur:
            tenant_id, user_id, membership_id, branch_id = _seed_tenant(cur)
        conn.commit()

    member = CurrentMember(
        membership_id=membership_id,
        tenant_id=tenant_id,
        user_id=user_id,
        email="buyer@example.test",
        role=MemberRole.buyer,
    )
    service = RfqService(settings=get_settings())
    payload = GuardrailCreateInput(
        max_order_value_amount=Decimal("1000.00"),
        max_order_value_currency="GBP",
        max_price_variance_pct=Decimal("0.10"),
        default_branch_id=branch_id,
    )
    with pytest.raises(PermissionDeniedError):
        create_guardrail(payload=payload, member=member, service=service)


def test_create_then_update_guardrail_round_trip() -> None:
    with psycopg.connect(TEST_DATABASE_URL or "", prepare_threshold=None) as conn:
        with conn.cursor() as cur:
            tenant_id, user_id, membership_id, branch_id = _seed_tenant(cur)
        conn.commit()

    member = _owner(tenant_id, user_id, membership_id)
    service = RfqService(settings=get_settings())

    created = create_guardrail(
        payload=GuardrailCreateInput(
            max_order_value_amount=Decimal("1000.00"),
            max_order_value_currency="GBP",
            max_price_variance_pct=Decimal("0.10"),
            default_branch_id=branch_id,
            enabled=False,
        ),
        member=member,
        service=service,
    )
    assert created.enabled is False
    assert created.default_branch_id == branch_id

    with pytest.raises(UnprocessableEntityError):
        update_guardrail(
            guardrail_id=created.id,
            payload=GuardrailUpdateInput(max_order_value_amount=Decimal("0")),
            member=member,
            service=service,
        )

    updated = update_guardrail(
        guardrail_id=created.id,
        payload=GuardrailUpdateInput(enabled=True),
        member=member,
        service=service,
    )
    assert updated.enabled is True
    assert updated.id == created.id


def _cost_centre(
    cur: psycopg.Cursor,
    tenant_id: uuid.UUID,
    branch_id: uuid.UUID | None,
    *,
    archived: bool = False,
) -> uuid.UUID:
    cost_centre_id = uuid.uuid4()
    cur.execute(
        "insert into cost_centre (id, tenant_id, name, code, branch_id, is_archived) "
        "values (%s, %s, 'CC', %s, %s, %s)",
        (cost_centre_id, tenant_id, f"CC-{cost_centre_id.hex[:8]}", branch_id, archived),
    )
    return cost_centre_id


def _guardrail_count(tenant_id: uuid.UUID) -> int:
    with psycopg.connect(TEST_DATABASE_URL or "", prepare_threshold=None) as conn:
        with conn.cursor() as cur:
            cur.execute("set local role service_role")
            cur.execute(
                "select count(*) from auto_preparation_guardrail where tenant_id = %s",
                (tenant_id,),
            )
            return int(cur.fetchone()[0])


def _payload(branch_id: uuid.UUID, cost_centre_id: uuid.UUID | None) -> GuardrailCreateInput:
    return GuardrailCreateInput(
        max_order_value_amount=Decimal("1000.00"),
        max_order_value_currency="GBP",
        max_price_variance_pct=Decimal("0.10"),
        default_branch_id=branch_id,
        default_cost_centre_id=cost_centre_id,
    )


def test_guardrail_default_cost_centre_must_be_active_and_on_the_default_branch() -> None:
    """Finding 38b: the guardrail carries an optional default cost centre, which must be an
    active one on its default branch -- and another workspace's cost centre or branch is not
    found, never accepted."""
    with psycopg.connect(TEST_DATABASE_URL or "", prepare_threshold=None) as conn:
        with conn.cursor() as cur:
            tenant_id, user_id, membership_id, branch_id = _seed_tenant(cur)
            other_branch = uuid.uuid4()
            cur.execute(
                "insert into branch (id,tenant_id,name) values (%s,%s,'Second')",
                (other_branch, tenant_id),
            )
            on_branch = _cost_centre(cur, tenant_id, branch_id)
            on_other_branch = _cost_centre(cur, tenant_id, other_branch)
            org_wide = _cost_centre(cur, tenant_id, None)
            archived = _cost_centre(cur, tenant_id, branch_id, archived=True)
            foreign_tenant, _, _, foreign_branch = _seed_tenant(cur)
            foreign_cost_centre = _cost_centre(cur, foreign_tenant, foreign_branch)
        conn.commit()

    member = _owner(tenant_id, user_id, membership_id)
    service = RfqService(settings=get_settings())

    with pytest.raises(NotFoundError):
        create_guardrail(
            payload=_payload(branch_id, foreign_cost_centre), member=member, service=service
        )
    with pytest.raises(NotFoundError):
        create_guardrail(payload=_payload(foreign_branch, None), member=member, service=service)
    for wrong in (on_other_branch, org_wide, archived):
        with pytest.raises(UnprocessableEntityError):
            create_guardrail(payload=_payload(branch_id, wrong), member=member, service=service)
    assert _guardrail_count(tenant_id) == 0

    created = create_guardrail(
        payload=_payload(branch_id, on_branch), member=member, service=service
    )
    assert created.default_cost_centre_id == on_branch
    assert service.list_guardrails(member=member)[0].default_cost_centre_id == on_branch

    # Moving the branch away from the cost centre's branch is refused; moving both together,
    # or clearing the cost centre, is fine.
    with pytest.raises(UnprocessableEntityError):
        update_guardrail(
            guardrail_id=created.id,
            payload=GuardrailUpdateInput(default_branch_id=other_branch),
            member=member,
            service=service,
        )
    with pytest.raises(NotFoundError):
        update_guardrail(
            guardrail_id=created.id,
            payload=GuardrailUpdateInput(default_cost_centre_id=foreign_cost_centre),
            member=member,
            service=service,
        )
    moved = update_guardrail(
        guardrail_id=created.id,
        payload=GuardrailUpdateInput(
            default_branch_id=other_branch, default_cost_centre_id=on_other_branch
        ),
        member=member,
        service=service,
    )
    assert (moved.default_branch_id, moved.default_cost_centre_id) == (
        other_branch,
        on_other_branch,
    )
    cleared = update_guardrail(
        guardrail_id=created.id,
        payload=GuardrailUpdateInput(default_cost_centre_id=None),
        member=member,
        service=service,
    )
    assert cleared.default_cost_centre_id is None


def test_another_workspaces_guardrail_is_not_found() -> None:
    with psycopg.connect(TEST_DATABASE_URL or "", prepare_threshold=None) as conn:
        with conn.cursor() as cur:
            tenant_a, user_a, membership_a, branch_a = _seed_tenant(cur)
            tenant_b, user_b, membership_b, branch_b = _seed_tenant(cur)
            cost_centre_b = _cost_centre(cur, tenant_b, branch_b)
        conn.commit()

    service = RfqService(settings=get_settings())
    owner_a = _owner(tenant_a, user_a, membership_a)
    owner_b = _owner(tenant_b, user_b, membership_b)
    guardrail_a = create_guardrail(
        payload=_payload(branch_a, None), member=owner_a, service=service
    )

    with pytest.raises(NotFoundError):
        update_guardrail(
            guardrail_id=guardrail_a.id,
            payload=GuardrailUpdateInput(
                default_branch_id=branch_b, default_cost_centre_id=cost_centre_b
            ),
            member=owner_b,
            service=service,
        )
    assert [g.id for g in service.list_guardrails(member=owner_b)] == []
    assert service.list_guardrails(member=owner_a)[0].default_cost_centre_id is None

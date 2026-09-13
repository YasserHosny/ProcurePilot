"""R2.4 optimisation and Supplier IQ audit coverage."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
import pytest

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")

R2_4_AUDIT_ACTIONS: tuple[str, ...] = (
    "offers.advanced_basket_submitted",
    "supplier_iq.scorecard_viewed",
    "alerts.anomaly_dismissed",
)


@pytest.fixture
def conn() -> Iterator[psycopg.Connection]:
    if not TEST_DATABASE_URL:
        pytest.skip("TEST_DATABASE_URL not set; needs Postgres with the R2.4 migrations")
    with psycopg.connect(TEST_DATABASE_URL) as connection:
        yield connection
        connection.rollback()


def make_tenant(cur: psycopg.Cursor, label: str) -> UUID:
    tenant_id, invitation_id = uuid4(), uuid4()
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
        (invitation_id, f"{label}@example.test", f"hash-{invitation_id}"),
    )
    cur.execute(
        "insert into tenant (id,name,slug,region,currency,tax_model,platform_invitation_id) "
        "values (%s,%s,%s,'GB','GBP','uk_vat',%s)",
        (tenant_id, f"{label} Ltd", f"{label}-{tenant_id.hex[:8]}", invitation_id),
    )
    return tenant_id


def act_as_owner(cur: psycopg.Cursor, tenant_id: UUID | str) -> None:
    cur.execute("set local role authenticated")
    cur.execute(
        "select set_config('request.jwt.claims', %s, true)",
        (f'{{"tenant_id":"{tenant_id}","role":"authenticated","member_role":"owner"}}',),
    )


def record_via_rpc(
    cur: psycopg.Cursor,
    *,
    action: str,
    target: str = "{}",
) -> None:
    cur.execute(
        "select record_audit_event(%s, 'success', null, null, null, %s::jsonb, null)",
        (action, target),
    )


@pytest.mark.parametrize("action", R2_4_AUDIT_ACTIONS)
def test_audit_event_accepts_and_stores_every_r2_4_action(
    conn: psycopg.Connection,
    action: str,
) -> None:
    with conn.cursor() as cur:
        tenant_id = make_tenant(cur, "supplier-iq-audit")
        act_as_owner(cur, tenant_id)
        record_via_rpc(cur, action=action, target='{"id": "test"}')
        cur.execute(
            "select action, outcome, target from audit_event "
            "where tenant_id = %s and action = %s",
            (tenant_id, action),
        )
        assert cur.fetchone() == (action, "success", {"id": "test"})


@pytest.mark.parametrize("action", R2_4_AUDIT_ACTIONS)
def test_r2_4_audit_events_are_immutable_like_every_other_action(
    conn: psycopg.Connection,
    action: str,
) -> None:
    with conn.cursor() as cur:
        tenant_id = make_tenant(cur, "supplier-iq-audit-immutable")
        act_as_owner(cur, tenant_id)
        record_via_rpc(cur, action=action)

        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cur.execute(
                "update audit_event set outcome = 'refused' where tenant_id = %s",
                (tenant_id,),
            )
        conn.rollback()

        act_as_owner(cur, tenant_id)
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cur.execute("delete from audit_event where tenant_id = %s", (tenant_id,))


def test_every_r2_4_action_is_distinct_and_searchable(
    conn: psycopg.Connection,
) -> None:
    assert len(R2_4_AUDIT_ACTIONS) == len(set(R2_4_AUDIT_ACTIONS))
    with conn.cursor() as cur:
        tenant_id = make_tenant(cur, "supplier-iq-audit-distinct")
        act_as_owner(cur, tenant_id)
        for action in R2_4_AUDIT_ACTIONS:
            record_via_rpc(cur, action=action)
        cur.execute(
            "select count(distinct action) from audit_event where tenant_id = %s",
            (tenant_id,),
        )
        assert cur.fetchone() == (len(R2_4_AUDIT_ACTIONS),)


def test_services_emit_every_r2_4_audit_action() -> None:
    repo_root = Path(__file__).resolve().parents[4]
    source_by_action = {
        "offers.advanced_basket_submitted": repo_root
        / "apps/api/src/procurepilot_api/modules/offers/basket_service.py",
        "supplier_iq.scorecard_viewed": repo_root
        / "apps/api/src/procurepilot_api/modules/offers/supplier_iq.py",
        "alerts.anomaly_dismissed": repo_root
        / "apps/api/src/procurepilot_api/modules/alerts/service.py",
    }
    for action, source_path in source_by_action.items():
        source = source_path.read_text(encoding="utf-8")
        assert f'action="{action}"' in source, f"{action} not emitted by {source_path}"

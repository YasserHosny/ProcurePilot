from __future__ import annotations

import os
from collections.abc import Iterator
from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest

psycopg = pytest.importorskip("psycopg")

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")


@dataclass(frozen=True)
class Workspace:
    tenant_id: UUID
    user_id: UUID
    membership_id: UUID
    role: str
    label: str

    def claims(self) -> str:
        return (
            f'{{"sub":"{self.user_id}","tenant_id":"{self.tenant_id}",'
            f'"role":"authenticated","member_role":"{self.role}"}}'
        )


def connection() -> Iterator[psycopg.Connection]:
    with psycopg.connect(TEST_DATABASE_URL or "") as conn:
        yield conn
        conn.rollback()


def make_workspace(cur: psycopg.Cursor, label: str, *, role: str = "owner") -> Workspace:
    tenant_id, user_id, membership_id, invitation_id = uuid4(), uuid4(), uuid4(), uuid4()
    cur.execute(
        "insert into supported_region (code,label_en,label_ar) values ('GB','UK','ب') "
        "on conflict do nothing"
    )
    cur.execute(
        "insert into supported_currency (code,label_en,label_ar) values ('GBP','Pound','ج') "
        "on conflict do nothing"
    )
    cur.execute(
        "insert into supported_currency (code,label_en,label_ar) values ('USD','Dollar','د') "
        "on conflict do nothing"
    )
    cur.execute(
        "insert into supported_tax_model (code,label_en,label_ar,region_code) "
        "values ('uk_vat','UK VAT','ض','GB') on conflict do nothing"
    )
    cur.execute(
        "insert into auth.users (id,email) values (%s,%s)",
        (user_id, f"{label}-{role}@example.test"),
    )
    cur.execute(
        "insert into platform_invitation (id,email,token_hash,expires_at) "
        "values (%s,%s,%s, now() + interval '7 days')",
        (invitation_id, f"{label}-{role}@example.test", f"hash-{invitation_id}"),
    )
    cur.execute(
        "insert into tenant (id,name,slug,region,currency,tax_model,platform_invitation_id) "
        "values (%s,%s,%s,'GB','GBP','uk_vat',%s)",
        (tenant_id, f"{label} Ltd", f"{label}-{tenant_id.hex[:8]}", invitation_id),
    )
    cur.execute(
        "insert into membership (id,tenant_id,user_id,email,role,is_active_workspace) "
        "values (%s,%s,%s,%s,%s,true)",
        (membership_id, tenant_id, user_id, f"{label}-{role}@example.test", role),
    )
    return Workspace(tenant_id, user_id, membership_id, role, label)


def act_as(cur: psycopg.Cursor, workspace: Workspace) -> None:
    cur.execute("set local role authenticated")
    cur.execute("select set_config('request.jwt.claims', %s, true)", (workspace.claims(),))


def reset_role(cur: psycopg.Cursor) -> None:
    cur.execute("reset role")
    cur.execute("select set_config('request.jwt.claims', '{}', true)")


def make_canonical_product(cur: psycopg.Cursor, name: str, *, gtin: str | None = None) -> UUID:
    product_id = uuid4()
    cur.execute("select current_role, current_setting('request.jwt.claims', true)")
    role_row = cur.fetchone()
    current_role = role_row[0] if role_row is not None else None
    claims = role_row[1] if role_row is not None else None
    cur.execute("reset role")
    try:
        cur.execute(
            "insert into canonical_product (id,name,gtin,base_unit) values (%s,%s,%s,'litre')",
            (product_id, name, gtin),
        )
    finally:
        if current_role == "authenticated":
            cur.execute("set local role authenticated")
            cur.execute("select set_config('request.jwt.claims', %s, true)", (claims or "{}",))
    return product_id


def make_workspace_product(
    cur: psycopg.Cursor,
    workspace: Workspace,
    *,
    name: str,
    canonical_product_id: UUID | None = None,
    supplier_id: UUID | None = None,
) -> UUID:
    product_id = uuid4()
    canonical_id = canonical_product_id or make_canonical_product(cur, f"{name} canonical")
    act_as(cur, workspace)
    cur.execute(
        "insert into workspace_product "
        "(id,tenant_id,canonical_product_id,tenant_name,preferred_supplier_id) "
        "values (%s,%s,%s,%s,%s)",
        (product_id, workspace.tenant_id, canonical_id, name, supplier_id),
    )
    cur.execute(
        "insert into pack_definition (tenant_id,workspace_product_id,pack_count,unit_size) "
        "values (%s,%s,6,5)",
        (workspace.tenant_id, product_id),
    )
    return product_id

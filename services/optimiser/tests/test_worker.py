from __future__ import annotations

import os
from uuid import uuid4

import pytest

from procurepilot_optimiser_worker.models import BasketItem
from procurepilot_optimiser_worker.settings import WorkerSettings
from procurepilot_optimiser_worker.solver import solve_two_supplier_split
from procurepilot_optimiser_worker.worker import process_basket_split_job


def test_commercial_infeasibility_is_completed_result_shape_not_failed_error() -> None:
    result = solve_two_supplier_split(
        supplier_ids=[uuid4(), uuid4()],
        items=[BasketItem(workspace_product_id=uuid4(), quantity="2.000000")],
        offers=[],
    )
    dumped = result.model_dump(mode="json")
    assert dumped["feasible"] is False
    assert dumped["infeasible_items"]
    assert dumped["solver_version"] == "basket-split-cp-sat-v1"


@pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"),
    reason="TEST_DATABASE_URL is not set; needs a migrated local Postgres",
)
def test_worker_failure_durably_marks_job_failed_after_exception_unwinds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    psycopg = pytest.importorskip("psycopg")
    database_url = os.environ["TEST_DATABASE_URL"]
    tenant_id, user_id, membership_id, invitation_id, job_id = (
        uuid4(),
        uuid4(),
        uuid4(),
        uuid4(),
        uuid4(),
    )
    email = f"optimiser-failure-{tenant_id.hex[:8]}@example.test"
    with psycopg.connect(database_url) as conn:
        from psycopg.types.json import Jsonb

        with conn.cursor() as cur:
            cur.execute(
                "insert into supported_region (code,label_en,label_ar) "
                "values ('GB','UK','ب') on conflict do nothing"
            )
            cur.execute(
                "insert into supported_currency (code,label_en,label_ar) "
                "values ('GBP','Pound','ج') on conflict do nothing"
            )
            cur.execute(
                "insert into supported_tax_model (code,label_en,label_ar,region_code) "
                "values ('uk_vat','UK VAT','ض','GB') on conflict do nothing"
            )
            cur.execute("insert into auth.users (id,email) values (%s,%s)", (user_id, email))
            cur.execute(
                "insert into platform_invitation (id,email,token_hash,expires_at) "
                "values (%s,%s,%s, now() + interval '7 days')",
                (invitation_id, email, f"hash-{invitation_id}"),
            )
            cur.execute(
                "insert into tenant "
                "(id,name,slug,region,currency,tax_model,platform_invitation_id) "
                "values (%s,'Optimiser Failure','optimiser-failure','GB','GBP','uk_vat',%s)",
                (tenant_id, invitation_id),
            )
            cur.execute(
                "insert into membership (id,tenant_id,user_id,email,role,is_active_workspace) "
                "values (%s,%s,%s,%s,'owner',true)",
                (membership_id, tenant_id, user_id, email),
            )
            cur.execute(
                "insert into basket_split_job "
                "(id, tenant_id, requested_by, supplier_ids, items, status) "
                "values (%s,%s,%s,%s,%s,'queued')",
                (
                    job_id,
                    tenant_id,
                    membership_id,
                    [uuid4(), uuid4()],
                    Jsonb(
                        [
                            {
                                "workspace_product_id": (
                                    "00000000-0000-4000-8000-000000000001"
                                ),
                                "quantity": "1.000000",
                            }
                        ]
                    ),
                ),
            )
        conn.commit()

    monkeypatch.setattr(
        "procurepilot_optimiser_worker.worker.get_settings",
        lambda: WorkerSettings(database_url=database_url),
    )
    monkeypatch.setattr(
        "procurepilot_optimiser_worker.worker.read_current_offers",
        lambda _conn, job: (_ for _ in ()).throw(RuntimeError(f"forced failure for {job.id}")),
    )
    try:
        with pytest.raises(RuntimeError, match="forced failure"):
            process_basket_split_job({"job_id": str(job_id), "tenant_id": str(tenant_id)})

        with psycopg.connect(database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "select status, error from basket_split_job where id = %s",
                    (job_id,),
                )
                status, error = cur.fetchone()
        assert status == "failed"
        assert error["code"] == "basket_split_failed"
        assert "forced failure" in error["message"]
    finally:
        with psycopg.connect(database_url) as conn:
            with conn.cursor() as cur:
                # The owner-guard trigger refuses to delete the last active owner's membership
                # row, even via cascade from a tenant delete.
                cur.execute("set session_replication_role = replica")
                try:
                    cur.execute("delete from tenant where id = %s", (tenant_id,))
                    cur.execute("delete from auth.users where id = %s", (user_id,))
                    cur.execute(
                        "delete from platform_invitation where id = %s", (invitation_id,)
                    )
                finally:
                    cur.execute("set session_replication_role = default")
            conn.commit()

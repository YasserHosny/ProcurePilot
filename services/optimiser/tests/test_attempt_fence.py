"""An expired delivery must not resurrect a failed row or overwrite a retried attempt."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest

from procurepilot_optimiser_worker import repository, worker
from procurepilot_optimiser_worker.settings import WorkerSettings

ATTEMPT = datetime(2026, 10, 18, 9, 0, tzinfo=UTC)


class _Cursor:
    def __init__(self, conn: _Conn) -> None:
        self.conn = conn
        self.rowcount = 0

    def __enter__(self) -> _Cursor:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def execute(self, sql: str, params: object = None) -> None:
        self.conn.sql.append((" ".join(sql.split()), params))
        self.rowcount = 1 if self.conn.claim else 0


class _Conn:
    def __init__(self, *, claim: bool) -> None:
        self.claim = claim
        self.sql: list[tuple[str, Any]] = []

    def cursor(self) -> _Cursor:
        return _Cursor(self)

    def commit(self) -> None: ...

    def __enter__(self) -> _Conn:
        return self

    def __exit__(self, *_: object) -> None:
        return None


def test_transitions_are_conditional_on_status_and_attempt() -> None:
    conn = _Conn(claim=True)
    job_id = uuid4()
    repository.mark_running(conn, job_id=job_id, attempt=ATTEMPT)  # type: ignore[arg-type]
    repository.mark_completed(conn, job_id=job_id, result={}, attempt=ATTEMPT)  # type: ignore[arg-type]
    repository.mark_failed(conn, job_id=job_id, error={}, attempt=ATTEMPT)  # type: ignore[arg-type]

    running, completed, failed = (s for s, _ in conn.sql)
    assert "status = 'queued'" in running and "created_at = %s" in running
    assert "status = 'running'" in completed and "created_at = %s" in completed
    assert "status = 'running'" in failed and "created_at = %s" in failed


def test_stale_delivery_is_skipped_without_solving(monkeypatch: pytest.MonkeyPatch) -> None:
    conn = _Conn(claim=False)
    monkeypatch.setattr(worker, "get_settings", lambda: WorkerSettings(database_url="x"))
    monkeypatch.setattr(worker.db, "connect", lambda _dsn: conn)

    def boom(*_: object, **__: object) -> None:
        raise AssertionError("a stale delivery must not load or solve the job")

    monkeypatch.setattr(worker, "load_job", boom)
    monkeypatch.setattr(worker, "load_advanced_optimisation_input", boom)

    worker.process_basket_split_job(
        {"job_id": str(uuid4()), "tenant_id": str(uuid4()), "attempt": ATTEMPT.isoformat()}
    )

    assert len(conn.sql) == 1  # only the failed claim; no completed/failed write


@pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"),
    reason="TEST_DATABASE_URL is not set; needs a migrated local Postgres",
)
def test_old_delivery_cannot_touch_a_retried_attempt() -> None:
    psycopg = pytest.importorskip("psycopg")
    from psycopg.types.json import Jsonb

    database_url = os.environ["TEST_DATABASE_URL"]
    tenant_id, user_id, membership_id, invitation_id, job_id = (uuid4() for _ in range(5))
    email = f"fence-{tenant_id.hex[:8]}@example.test"
    with psycopg.connect(database_url) as conn, conn.cursor() as cur:
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
        cur.execute("insert into auth.users (id,email) values (%s,%s)", (user_id, email))
        cur.execute(
            "insert into platform_invitation (id,email,token_hash,expires_at) "
            "values (%s,%s,%s, now() + interval '7 days')",
            (invitation_id, email, f"hash-{invitation_id}"),
        )
        cur.execute(
            "insert into tenant (id,name,slug,region,currency,tax_model,platform_invitation_id) "
            "values (%s,'Fence','fence-test','GB','GBP','uk_vat',%s)",
            (tenant_id, invitation_id),
        )
        cur.execute(
            "insert into membership (id,tenant_id,user_id,email,role,is_active_workspace) "
            "values (%s,%s,%s,%s,'owner',true)",
            (membership_id, tenant_id, user_id, email),
        )
        cur.execute(
            "insert into basket_split_job (id, tenant_id, requested_by, supplier_ids, items, "
            "status) values (%s,%s,%s,%s,%s,'queued') returning created_at",
            (job_id, tenant_id, membership_id, [uuid4(), uuid4()], Jsonb([])),
        )
        first_attempt = cur.fetchone()[0]
        conn.commit()
    try:
        with psycopg.connect(database_url) as conn:
            # Attempt 1 expires (API) and is retried: failed -> queued under a fresh created_at.
            with conn.cursor() as cur:
                cur.execute(
                    "update basket_split_job set status='failed', completed_at=now() where id=%s",
                    (job_id,),
                )
            # The expired delivery arrives while the row is failed: must not resurrect it.
            assert not repository.mark_running(conn, job_id=job_id, attempt=first_attempt)
            with conn.cursor() as cur:
                cur.execute(
                    "update basket_split_job set status='queued', completed_at=null, "
                    "started_at=null, created_at=now() + interval '1 second' where id=%s "
                    "returning created_at",
                    (job_id,),
                )
                second_attempt = cur.fetchone()[0]
            # ... and while the retry is queued: still must not claim it.
            assert not repository.mark_running(conn, job_id=job_id, attempt=first_attempt)
            assert repository.mark_running(conn, job_id=job_id, attempt=second_attempt)
            # A late result from the old attempt cannot overwrite the retry.
            assert not repository.mark_completed(
                conn, job_id=job_id, result={"stale": True}, attempt=first_attempt
            )
            assert repository.mark_completed(
                conn, job_id=job_id, result={"ok": True}, attempt=second_attempt
            )
            conn.commit()
            with conn.cursor() as cur:
                cur.execute("select status, result from basket_split_job where id=%s", (job_id,))
                status, result = cur.fetchone()
        assert status == "completed" and result == {"ok": True}
    finally:
        with psycopg.connect(database_url) as conn, conn.cursor() as cur:
            cur.execute("set session_replication_role = replica")
            try:
                cur.execute("delete from tenant where id = %s", (tenant_id,))
                cur.execute("delete from auth.users where id = %s", (user_id,))
                cur.execute("delete from platform_invitation where id = %s", (invitation_id,))
            finally:
                cur.execute("set session_replication_role = default")

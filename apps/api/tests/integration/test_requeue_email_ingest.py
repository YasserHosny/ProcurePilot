from __future__ import annotations

import pytest
from psycopg.rows import dict_row

from integration.catalogue_helpers import TEST_DATABASE_URL
from integration.smart_compare_helpers import committed_smart_context, settings_for_test_db
from integration.test_email_ingestion_worker import (
    _build_email,
    _insert_email_job,
    _patch_storage_and_queue,
    _seed_email_config,
)
from procurepilot_api.db import connect as db_connect
from procurepilot_api.workers import email_ingestion_worker
from procurepilot_api.workers.requeue_email_ingest import requeue

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL, reason="TEST_DATABASE_URL is not set; needs a migrated local Postgres"
)


def test_requeue_dry_run_skip_and_worker_completion(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = settings_for_test_db(monkeypatch)
    with committed_smart_context("requeue-email-ingest") as context:
        _seed_email_config(context.workspace.tenant_id, context.workspace.membership_id)
        raw_path = f"tenants/{context.workspace.tenant_id}/raw/requeue.eml"
        email = _build_email(from_addr="seller@example.test", message_id="<requeue@example.test>")
        _patch_storage_and_queue(monkeypatch, downloads={raw_path: email})
        failed_id = _insert_email_job(
            context.workspace.tenant_id,
            payload={"raw_email_path": raw_path},
            status="failed",
            attempts=3,
        )
        with db_connect(TEST_DATABASE_URL or "") as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "update ingestion_jobs set job_type='guardrail_eval' where id=%s",
                    (failed_id,),
                )
            conn.commit()
        wrong_type_id = _insert_email_job(
            context.workspace.tenant_id,
            payload={"raw_email_path": raw_path},
            status="failed",
        )
        pending_id = _insert_email_job(
            context.workspace.tenant_id,
            payload={"raw_email_path": raw_path},
            status="pending",
        )
        with db_connect(TEST_DATABASE_URL or "") as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "update ingestion_jobs set job_type='guardrail_eval' where id=%s",
                    (wrong_type_id,),
                )
                cur.execute(
                    "update ingestion_jobs set job_type='email_ingest' where id=%s", (failed_id,)
                )
            conn.commit()

        assert requeue(job_ids=[failed_id], tenant_id=None, dry_run=True) == 0
        with db_connect(TEST_DATABASE_URL or "", row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute("select status, attempts from ingestion_jobs where id=%s", (failed_id,))
                assert cur.fetchone() == {"status": "failed", "attempts": 3}
        assert (
            requeue(job_ids=[failed_id, wrong_type_id, pending_id], tenant_id=None, dry_run=False)
            == 1
        )
        with db_connect(TEST_DATABASE_URL or "") as conn:
            with conn.cursor() as cur:
                cur.execute("update ingestion_jobs set status='failed' where id=%s", (pending_id,))
            conn.commit()
        with db_connect(TEST_DATABASE_URL or "", row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute("select status, attempts from ingestion_jobs where id=%s", (failed_id,))
                assert cur.fetchone() == {"status": "pending", "attempts": 0}

        # The command reset the failed row; the regular worker consumes it from raw storage.
        stats = email_ingestion_worker.tick(settings)
        assert stats["completed"] == 1
        with db_connect(TEST_DATABASE_URL or "", row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute("select status from ingestion_jobs where id=%s", (failed_id,))
                assert cur.fetchone()["status"] == "completed"
                cur.execute(
                    "select count(*) from audit_event where tenant_id=%s "
                    "and action='email_ingest_requeued'",
                    (context.workspace.tenant_id,),
                )
                assert cur.fetchone()["count"] == 1

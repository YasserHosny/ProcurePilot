from __future__ import annotations

from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from integration.catalogue_helpers import TEST_DATABASE_URL, act_as
from integration.quotation_helpers import make_document, make_quotation
from integration.smart_compare_helpers import committed_smart_context, settings_for_test_db
from procurepilot_api.workers import requeue_extraction as command

pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="TEST_DATABASE_URL is required")


def test_requeue_failed_extraction_dry_run_and_enqueue(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = settings_for_test_db(monkeypatch)
    monkeypatch.setattr(command, "get_settings", lambda: settings)
    enqueued: list[dict[str, str]] = []
    monkeypatch.setattr(
        command, "enqueue_extraction_payload", lambda _settings, **payload: enqueued.append(payload)
    )
    with committed_smart_context("requeue-extraction") as context:
        with psycopg.connect(TEST_DATABASE_URL or "") as conn, conn.cursor() as cur:
            workspace = context.workspace
            document_id = make_document(cur, workspace)
            quotation_id = make_quotation(cur, workspace, document_id=document_id, status="refused")
            old_job_id = uuid4()
            cur.execute(
                "insert into extraction_job (id,tenant_id,quotation_id,status,error,completed_at) "
                "values (%s,%s,%s,'failed',%s,now())",
                (
                    old_job_id,
                    workspace.tenant_id,
                    quotation_id,
                    Jsonb({"code": "extraction_failed"}),
                ),
            )
            conn.commit()

        assert (
            command.requeue(
                quotation_ids=[quotation_id], tenant_id=None, all_refused=False, dry_run=True
            )
            == 0
        )
        with psycopg.connect(TEST_DATABASE_URL or "", row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute("select status from quotation where id=%s", (quotation_id,))
                assert cur.fetchone()["status"] == "refused"

        assert (
            command.requeue(
                quotation_ids=[quotation_id], tenant_id=None, all_refused=False, dry_run=False
            )
            == 0
        )
        assert len(enqueued) == 1
        assert enqueued[0] == {
            "job_id": enqueued[0]["job_id"],
            "tenant_id": str(workspace.tenant_id),
            "quotation_id": str(quotation_id),
            "document_id": str(document_id),
        }
        with psycopg.connect(TEST_DATABASE_URL or "", row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                act_as(cur, workspace)
                cur.execute("select status from quotation where id=%s", (quotation_id,))
                assert cur.fetchone()["status"] == "extracting"
                cur.execute(
                    "select status from extraction_job where quotation_id=%s "
                    "order by created_at desc limit 1",
                    (quotation_id,),
                )
                assert cur.fetchone()["status"] == "queued"
                cur.execute(
                    "select count(*) from audit_event where tenant_id=%s "
                    "and action='quotation_extraction_requeued'",
                    (workspace.tenant_id,),
                )
                assert cur.fetchone()["count"] == 1

        def make_failed_quote(status: str, code: str) -> tuple[UUID, UUID]:
            with psycopg.connect(TEST_DATABASE_URL or "") as conn, conn.cursor() as cur:
                document = make_document(cur, workspace)
                quote = make_quotation(cur, workspace, document_id=document, status=status)
                cur.execute(
                    "insert into extraction_job (tenant_id,quotation_id,status,error,completed_at) "
                    "values (%s,%s,'failed',%s,now())",
                    (workspace.tenant_id, quote, Jsonb({"code": code})),
                )
                conn.commit()
            return quote, document

        wrong_code_id, _ = make_failed_quote("refused", "provider_timeout")
        active_id, _ = make_failed_quote("extracting", "extraction_failed")
        assert (
            command.requeue(
                quotation_ids=[wrong_code_id, active_id],
                tenant_id=None,
                all_refused=False,
                dry_run=False,
            )
            == 1
        )

        enqueue_failure_id, _ = make_failed_quote("refused", "extraction_failed")
        monkeypatch.setattr(
            command,
            "enqueue_extraction_payload",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("redis down")),
        )
        assert (
            command.requeue(
                quotation_ids=[enqueue_failure_id],
                tenant_id=None,
                all_refused=False,
                dry_run=False,
            )
            == 1
        )
        with psycopg.connect(TEST_DATABASE_URL or "", row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute("select status from quotation where id=%s", (enqueue_failure_id,))
                assert cur.fetchone()["status"] == "refused"
                cur.execute(
                    "select status,error->>'code' as code from extraction_job "
                    "where quotation_id=%s order by created_at desc limit 1",
                    (enqueue_failure_id,),
                )
                assert cur.fetchone() == {"status": "failed", "code": "redis_enqueue_failed"}

from __future__ import annotations

import json
from uuid import UUID

import psycopg

from procurepilot_api.config import Settings

# Shared by every ingestion channel that hands its primary document to the existing extraction
# pipeline (email: T011, capture: T015) — factored out of the email orchestrator rather than
# copy-pasted a second time for capture.


def enqueue_extraction(
    settings: Settings, *, job_id: UUID, tenant_id: UUID, quotation_id: UUID, document_id: UUID
) -> None:
    from redis import Redis
    from rq import Queue

    queue = Queue(settings.extraction_queue_name, connection=Redis.from_url(settings.redis_url))
    queue.enqueue(
        "procurepilot_extraction_worker.worker.process_extraction_job",
        {
            "job_id": str(job_id),
            "tenant_id": str(tenant_id),
            "quotation_id": str(quotation_id),
            "document_id": str(document_id),
        },
        job_id=str(job_id),
    )


def release_failed_enqueue(conn: psycopg.Connection, *, job_id: UUID, quotation_id: UUID) -> None:
    """Undo `extracting` when the Redis push failed, as the web path's own compensation does.

    The job is marked failed and the quotation goes back to `pending`, so POST
    /quotations/{id}/extract can queue it again. The caller sets the tenant context and commits.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            update extraction_job
            set status = 'failed', error = %s::jsonb, completed_at = now()
            where id = %s and status = 'queued'
            """,
            (
                json.dumps(
                    {
                        "code": "redis_enqueue_failed",
                        "message": "Extraction job could not be queued in Redis.",
                    }
                ),
                job_id,
            ),
        )
        cur.execute(
            "update quotation set status = 'pending' where id = %s and status = 'extracting'",
            (quotation_id,),
        )

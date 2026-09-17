from __future__ import annotations

from uuid import UUID

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

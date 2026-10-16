from __future__ import annotations

from procurepilot_api.config import Settings
from procurepilot_api.errors import ServiceUnavailableError


def enqueue_extraction_payload(
    settings: Settings, *, job_id: str, tenant_id: str, quotation_id: str, document_id: str
) -> None:
    """Enqueue the canonical extraction worker function and payload."""
    try:
        from redis import Redis
        from rq import Queue
    except ImportError as exc:
        raise ServiceUnavailableError(details={"dependency": "rq"}) from exc
    try:
        queue = Queue(settings.extraction_queue_name, connection=Redis.from_url(settings.redis_url))
        queue.enqueue(
            "procurepilot_extraction_worker.worker.process_extraction_job",
            {
                "job_id": job_id,
                "tenant_id": tenant_id,
                "quotation_id": quotation_id,
                "document_id": document_id,
            },
            job_id=job_id,
        )
    except Exception as exc:
        raise ServiceUnavailableError(details={"dependency": "redis"}) from exc

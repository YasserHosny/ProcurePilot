from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from postgrest.exceptions import APIError

from procurepilot_api.config import Settings, get_settings
from procurepilot_api.deps import CurrentMember
from procurepilot_api.errors import ConflictError, ServiceUnavailableError
from procurepilot_api.modules.jobs.router import JOB_COLUMNS
from procurepilot_api.modules.jobs.schemas import Job
from procurepilot_api.modules.members.service import authenticated_client
from procurepilot_api.modules.quotations.service import _one_row


class ExtractionService:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    def enqueue_extraction(
        self,
        *,
        bearer_token: str,
        member: CurrentMember,
        quotation_id: UUID,
    ) -> Job:
        client = authenticated_client(self._settings, bearer_token)
        quote = _one_row(
            client.table("quotation")
            .select("id,document_id,status")
            .eq("id", str(quotation_id))
            .limit(2)
            .execute()
            .data,
            resource="quotation",
        )
        if quote["status"] not in {"pending", "refused"}:
            raise ConflictError(details={"reason": "quotation_not_extractable"})
        active = client.table("extraction_job").select("id").eq(
            "quotation_id", str(quotation_id)
        ).in_("status", ["queued", "running"]).limit(1).execute()
        if active.data:
            raise ConflictError(details={"reason": "extraction_already_running"})
        try:
            job_row = _one_row(
                client.table("extraction_job")
                .insert(
                    {
                        "tenant_id": str(member.tenant_id),
                        "quotation_id": str(quotation_id),
                        "status": "queued",
                    }
                )
                .execute()
                .data,
                resource="job",
            )
            client.table("quotation").update({"status": "extracting"}).eq(
                "id", str(quotation_id)
            ).execute()
        except APIError as exc:
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc

        try:
            _enqueue_redis_job(self._settings, job_row, quote, member)
        except ServiceUnavailableError:
            _compensate_failed_enqueue(
                client=client,
                job_id=UUID(str(job_row["id"])),
                quotation_id=quotation_id,
                prior_status=str(quote["status"]),
            )
            raise
        job = Job.model_validate({key: job_row.get(key) for key in JOB_COLUMNS.split(",")})
        return job


def get_extraction_service() -> ExtractionService:
    return ExtractionService()


def _enqueue_redis_job(
    settings: Settings,
    job_row: dict[str, object],
    quote: dict[str, object],
    member: CurrentMember,
) -> None:
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
                "job_id": str(job_row["id"]),
                "tenant_id": str(member.tenant_id),
                "quotation_id": str(quote["id"]),
                "document_id": str(quote["document_id"]),
            },
            job_id=str(job_row["id"]),
        )
    except Exception as exc:
        raise ServiceUnavailableError(details={"dependency": "redis"}) from exc


def _compensate_failed_enqueue(
    *,
    client: object,
    job_id: UUID,
    quotation_id: UUID,
    prior_status: str,
) -> None:
    try:
        client.table("extraction_job").update(
            {
                "status": "failed",
                "error": {
                    "code": "redis_enqueue_failed",
                    "message": "Extraction job could not be queued in Redis.",
                },
                "completed_at": datetime.now(UTC).isoformat(),
            }
        ).eq("id", str(job_id)).execute()
        client.table("quotation").update({"status": prior_status}).eq(
            "id", str(quotation_id)
        ).execute()
    except APIError as exc:
        raise ServiceUnavailableError(details={"dependency": "database"}) from exc

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from postgrest.exceptions import APIError

from procurepilot_api.config import Settings, get_settings
from procurepilot_api.deps import CurrentMember, bearer_token, current_member
from procurepilot_api.errors import NotFoundError, ServiceUnavailableError
from procurepilot_api.modules.jobs.schemas import Job
from procurepilot_api.modules.members.service import authenticated_client

router = APIRouter(tags=["jobs"])

JOB_COLUMNS = "id,quotation_id,status,attempted_provider,error,created_at,started_at,completed_at"


class JobService:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    def get_job(self, *, bearer_token: str, job_id: UUID) -> Job:
        client = authenticated_client(self._settings, bearer_token)
        try:
            response = (
                client.table("extraction_job")
                .select(JOB_COLUMNS)
                .eq("id", str(job_id))
                .limit(2)
                .execute()
            )
        except APIError as exc:
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc
        rows = response.data
        if not isinstance(rows, list) or len(rows) != 1:
            raise NotFoundError(details={"resource": "job"})
        row = rows[0]
        job = Job.model_validate(row)
        if job.status == "succeeded":
            job.result_url = f"/api/v1/quotations/{job.quotation_id}"
        return job


def get_job_service() -> JobService:
    return JobService()


@router.get("/jobs/{job_id}", response_model=Job)
def get_job(
    job_id: UUID,
    token: Annotated[str, Depends(bearer_token)],
    _member: Annotated[CurrentMember, Depends(current_member)],
    service: Annotated[JobService, Depends(get_job_service)],
) -> Job:
    return service.get_job(bearer_token=token, job_id=job_id)

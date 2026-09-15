from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Header, Query, Response, status

from procurepilot_api.deps import CurrentMember, bearer_token, current_member
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.auth.rbac import require_role
from procurepilot_api.modules.reports.schedules import ReportsService, get_reports_service
from procurepilot_api.modules.reports.schemas import (
    ReportArtifactList,
    ReportSchedule,
    ReportScheduleCreate,
    ReportScheduleList,
    ReportScheduleUpdate,
)

router = APIRouter(tags=["reports"])
WRITE_ROLES = (MemberRole.owner, MemberRole.buyer)


@router.get("/reports/schedules", response_model=ReportScheduleList)
def list_schedules(
    member: Annotated[CurrentMember, Depends(current_member)],
    service: Annotated[ReportsService, Depends(get_reports_service)],
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> ReportScheduleList:
    return service.list_schedules(member=member, cursor=cursor, limit=limit)


@router.post(
    "/reports/schedules",
    status_code=status.HTTP_201_CREATED,
    response_model=ReportSchedule,
)
def create_schedule(
    payload: Annotated[ReportScheduleCreate, Body()],
    member: Annotated[CurrentMember, Depends(require_role(*WRITE_ROLES))],
    service: Annotated[ReportsService, Depends(get_reports_service)],
    token: Annotated[str, Depends(bearer_token)],
    _idempotency_key: Annotated[UUID | None, Header(alias="Idempotency-Key")] = None,
) -> ReportSchedule:
    return service.create_schedule(
        member=member,
        kind=payload.kind,
        format=payload.format,
        filters=payload.filters,
        weekday=payload.weekday,
        locale=payload.locale,
        bearer_token=token,
    )


@router.get("/reports/schedules/{schedule_id}", response_model=ReportSchedule)
def get_schedule(
    schedule_id: UUID,
    member: Annotated[CurrentMember, Depends(current_member)],
    service: Annotated[ReportsService, Depends(get_reports_service)],
) -> ReportSchedule:
    return service.get_schedule(member=member, schedule_id=schedule_id)


@router.patch("/reports/schedules/{schedule_id}", response_model=ReportSchedule)
def update_schedule(
    schedule_id: UUID,
    payload: Annotated[ReportScheduleUpdate, Body()],
    member: Annotated[CurrentMember, Depends(require_role(*WRITE_ROLES))],
    service: Annotated[ReportsService, Depends(get_reports_service)],
    token: Annotated[str, Depends(bearer_token)],
    _idempotency_key: Annotated[UUID | None, Header(alias="Idempotency-Key")] = None,
) -> ReportSchedule:
    return service.update_schedule(
        member=member, schedule_id=schedule_id, payload=payload, bearer_token=token
    )


@router.delete("/reports/schedules/{schedule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_schedule(
    schedule_id: UUID,
    member: Annotated[CurrentMember, Depends(require_role(*WRITE_ROLES))],
    service: Annotated[ReportsService, Depends(get_reports_service)],
    token: Annotated[str, Depends(bearer_token)],
    _idempotency_key: Annotated[UUID | None, Header(alias="Idempotency-Key")] = None,
) -> Response:
    service.delete_schedule(member=member, schedule_id=schedule_id, bearer_token=token)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/reports/artifacts", response_model=ReportArtifactList)
def list_artifacts(
    member: Annotated[CurrentMember, Depends(current_member)],
    service: Annotated[ReportsService, Depends(get_reports_service)],
    kind: Annotated[
        Literal["savings_ledger", "spend_by_supplier", "alerts_summary"] | None, Query()
    ] = None,
    artifact_status: Annotated[
        Literal["queued", "running", "completed", "failed", "expired"] | None, Query(alias="status")
    ] = None,
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> ReportArtifactList:
    return service.list_artifacts(
        member=member,
        kind=kind,
        status=artifact_status,
        cursor=cursor,
        limit=limit,
    )

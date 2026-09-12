from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Header, Response, status

from procurepilot_api.deps import CurrentMember, bearer_token, current_member
from procurepilot_api.modules.devices.schemas import (
    DeviceRegistration,
    DeviceRegistrationCreate,
)
from procurepilot_api.modules.devices.service import (
    DevicesService,
    get_devices_service,
)

router = APIRouter(tags=["devices"])


@router.post("/devices", response_model=DeviceRegistration)
def register_device(
    payload: Annotated[DeviceRegistrationCreate, Body()],
    token: Annotated[str, Depends(bearer_token)],
    member: Annotated[CurrentMember, Depends(current_member)],
    service: Annotated[DevicesService, Depends(get_devices_service)],
    _idempotency_key: Annotated[
        UUID | None, Header(alias="Idempotency-Key")
    ] = None,
) -> DeviceRegistration:
    return service.register_device(
        bearer_token=token,
        member=member,
        payload=payload,
    )


@router.delete("/devices/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_device(
    device_id: UUID,
    token: Annotated[str, Depends(bearer_token)],
    member: Annotated[CurrentMember, Depends(current_member)],
    service: Annotated[DevicesService, Depends(get_devices_service)],
) -> Response:
    service.delete_device(
        bearer_token=token, member=member, device_id=device_id
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)

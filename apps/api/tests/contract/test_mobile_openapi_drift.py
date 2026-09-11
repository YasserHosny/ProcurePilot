from __future__ import annotations

from pathlib import Path

import yaml

from procurepilot_api.main import create_app
from procurepilot_api.modules.devices.schemas import (
    DeviceRegistration,
    DeviceRegistrationCreate,
)
from procurepilot_api.modules.requests.schemas import (
    LowStockReport,
    LowStockReportCreate,
)

IMPLEMENTED_APP_PATHS = [
    "/api/v1/devices",
    "/api/v1/devices/{device_id}",
]

CONTRACT_PATHS = [
    "/devices",
    "/devices/{device_id}",
    "/low-stock-reports",
]


def _contract() -> dict[str, object]:
    repo_root = Path(__file__).resolve().parents[4]
    path = (
        repo_root
        / "specs/009-mobile-app-mvp/contracts/mobile.openapi.yaml"
    )
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_mobile_contract_paths_are_declared() -> None:
    paths = _contract()["paths"]
    for path in CONTRACT_PATHS:
        assert path in paths, f"{path} missing from mobile contract"


def test_implemented_mobile_routes_are_registered() -> None:
    app_paths = {route.path for route in create_app().routes}
    for path in IMPLEMENTED_APP_PATHS:
        assert path in app_paths, f"{path} not registered in the app"


def test_devices_routes_use_contract_response_models() -> None:
    routes = {route.path: route for route in create_app().routes}
    assert routes["/api/v1/devices"].response_model is DeviceRegistration
    assert routes["/api/v1/devices/{device_id}"].status_code == 204


def test_mobile_contract_schema_names_exist_in_backend_models() -> None:
    contract_schemas = _contract()["components"]["schemas"]
    assert "DeviceRegistration" in contract_schemas
    assert "DeviceRegistrationCreate" in contract_schemas
    assert "LowStockReport" in contract_schemas
    assert "LowStockReportCreate" in contract_schemas

    assert DeviceRegistration.model_fields.keys() == {
        "id",
        "member_id",
        "platform",
        "push_token",
        "last_seen_at",
    }
    assert DeviceRegistrationCreate.model_fields.keys() == {
        "platform",
        "push_token",
    }
    assert LowStockReport.model_fields.keys() == {
        "id",
        "branch_id",
        "member_id",
        "workspace_product_id",
        "count_remaining",
        "created_at",
    }
    assert LowStockReportCreate.model_fields.keys() == {
        "branch_id",
        "workspace_product_id",
        "count_remaining",
    }

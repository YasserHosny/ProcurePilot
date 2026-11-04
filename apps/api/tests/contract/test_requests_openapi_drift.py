from __future__ import annotations

from pathlib import Path

from procurepilot_api.main import create_app

CONTRACT_PATHS = [
    "/requests",
    "/requests/{request_id}",
    "/requests/{request_id}/submit",
    "/requests/{request_id}/withdraw",
    "/requests/{request_id}/approve",
    "/requests/{request_id}/reject",
    "/approvals/pending",
    "/approvals/threshold-rules",
    "/approvals/threshold-rules/{rule_id}",
    "/approvals/delegations",
    "/approvals/delegations/{delegation_id}",
]

US1_ROUTES = [
    "/api/v1/requests",
    "/api/v1/requests/{request_id}",
    "/api/v1/requests/{request_id}/submit",
    "/api/v1/requests/{request_id}/withdraw",
]


def _contract_text() -> str:
    repo_root = Path(__file__).resolve().parents[4]
    contract = (
        repo_root / "specs/008-requests-approvals/contracts" / "requests-approvals.openapi.yaml"
    )
    return contract.read_text(encoding="utf-8")


def test_every_contract_path_is_declared_under_requests_or_approvals() -> None:
    text = _contract_text()
    for path in CONTRACT_PATHS:
        assert f"  {path}:" in text, f"{path} missing from the contract"
        assert path.startswith("/requests") or path.startswith("/approvals")


def test_us1_routes_are_registered() -> None:
    app_paths = {route.path for route in create_app().routes}
    for path in US1_ROUTES:
        assert path in app_paths, f"{path} not registered in the app"


def test_single_decisions_declare_optional_uuid_idempotency_header() -> None:
    contract = _contract_text()
    component = contract.split("    IdempotencyKey:\n", 1)[1].split("    RequestId:", 1)[0]
    assert "required: false" in component
    assert "format: uuid" in component
    schema = create_app().openapi()
    for action in ("approve", "reject"):
        path = f"/requests/{{request_id}}/{action}"
        operation = contract.split(f"  {path}:\n", 1)[1].split("\n  /", 1)[0]
        assert "$ref: '#/components/parameters/IdempotencyKey'" in operation
        parameters = schema["paths"][f"/api/v1{path}"]["post"]["parameters"]
        header = next(
            parameter for parameter in parameters if parameter["name"] == "Idempotency-Key"
        )
        assert header["in"] == "header"
        assert header["required"] is False
        assert {"type": "string", "format": "uuid"} in header["schema"]["anyOf"]


def test_self_approval_flag_and_decision_reason_are_documented() -> None:
    import yaml

    contract = yaml.safe_load(_contract_text())
    field = contract["components"]["schemas"]["ApprovalStep"]["properties"]["self_approval"]
    live = create_app().openapi()["components"]["schemas"]["ApprovalStep"]["properties"][
        "self_approval"
    ]
    assert field["type"] == live["type"] == "boolean"
    assert field["default"] is live["default"] is False
    for action in ("approve", "reject"):
        operation = contract["paths"][f"/requests/{{request_id}}/{action}"]["post"]
        assert "self_decision_not_allowed" in operation["description"]
        assert "403" in operation["responses"]
    split_path = (
        Path(__file__).resolve().parents[4]
        / "specs/024-rfq-basket-split/contracts/rfq-split.openapi.yaml"
    )
    split = yaml.safe_load(split_path.read_text())
    for action in ("approve", "reject"):
        response = split["paths"][f"/request-groups/{{group_id}}/{action}"]["post"]["responses"][
            "403"
        ]
        assert "self_decision_not_allowed" in response["description"]

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from procurepilot_api.main import create_app
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.members.models import Me, SessionResponse
from procurepilot_api.modules.tenants.models import SignupRequest, Tenant
from procurepilot_api.modules.tenants.router import signup


class _SignupService:
    def signup(self, request: SignupRequest) -> SessionResponse:
        tenant = Tenant(
            id=uuid4(),
            name=request.business_name,
            slug="acme-supplies",
            region=request.region,
            currency=request.currency,
            tax_model=request.tax_model,
            default_locale=request.default_locale,
        )
        return SessionResponse(
            access_token="access-token",
            refresh_token="refresh-token",
            expires_in=3600,
            user=Me(
                id=UUID("11111111-1111-1111-1111-111111111111"),
                email=request.email,
                role=MemberRole.owner,
                preferred_locale=None,
                mfa_enabled=False,
                tenant=tenant,
            ),
        )


@pytest.fixture
def openapi_schema() -> dict[str, object]:
    return create_app().openapi()


def test_signup_request_schema_matches_contract_required_fields(
    openapi_schema: dict[str, object],
) -> None:
    schema = openapi_schema
    request_schema = schema["paths"]["/api/v1/auth/signup"]["post"]["requestBody"]["content"][
        "application/json"
    ]["schema"]
    ref_name = request_schema["$ref"].rsplit("/", maxsplit=1)[-1]
    required = schema["components"]["schemas"][ref_name]["required"]
    assert required == [
        "invitation_token",
        "email",
        "password",
        "business_name",
        "region",
        "currency",
        "tax_model",
    ]


def test_signup_response_shape_matches_contract_session(openapi_schema: dict[str, object]) -> None:
    assert openapi_schema["paths"]["/api/v1/auth/signup"]["post"]["responses"]["201"]
    response = signup(
        SignupRequest(
            invitation_token="a" * 32,
            email="owner@example.test",
            password="correct-horse-password",
            business_name="Acme Supplies",
            region="GB",
            currency="GBP",
            tax_model="uk_vat_standard",
            default_locale="en",
        ),
        _SignupService(),
    )

    body = response.model_dump(mode="json")
    assert set(body) == {"access_token", "refresh_token", "expires_in", "user"}
    assert body["user"]["role"] == "owner"
    assert body["user"]["tenant"]["currency"] == "GBP"

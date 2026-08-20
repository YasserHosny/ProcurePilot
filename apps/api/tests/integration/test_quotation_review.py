from __future__ import annotations

from decimal import Decimal

import pytest

from integration.catalogue_helpers import TEST_DATABASE_URL, act_as, connection, make_workspace
from integration.quotation_helpers import (
    PsycopgSupabaseClient,
    make_extracted_quotation,
    make_field,
)
from procurepilot_api.deps import CurrentMember
from procurepilot_api.errors import ConflictError
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.quotations import (
    confirmation_service as confirmation_service_module,
)
from procurepilot_api.modules.quotations.confirmation_service import QuotationConfirmationService

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is required for quotation review integration tests",
)


@pytest.fixture
def conn() -> object:
    yield from connection()


def test_confirm_returns_409_until_required_review_work_is_resolved(
    conn: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with conn.cursor() as cur:
        workspace = make_workspace(cur, "quotation-review")
        fixture = make_extracted_quotation(cur, workspace)
        low_confidence_field = make_field(
            cur,
            workspace,
            fixture.quotation_id,
            field_name="issue_date",
            extracted_value="2026-08-21",
            confidence=Decimal("0.5000"),
        )
        act_as(cur, workspace)
        monkeypatch.setattr(
            confirmation_service_module,
            "authenticated_client",
            lambda _settings, _token: PsycopgSupabaseClient(conn),
        )
        member = CurrentMember(
            membership_id=workspace.membership_id,
            tenant_id=workspace.tenant_id,
            user_id=workspace.user_id,
            email="buyer@example.test",
            role=MemberRole.buyer,
        )

        with pytest.raises(ConflictError) as exc_info:
            QuotationConfirmationService().confirm(
                bearer_token="test-token",
                member=member,
                quotation_id=fixture.quotation_id,
                payload=None,
            )

        assert exc_info.value.details == {"reason": "low_confidence_unresolved"}
        cur.execute(
            "update field_extraction set corrected_value = '\"2026-08-21\"'::jsonb, "
            "corrected_by = %s, corrected_at = now() where id = %s",
            (workspace.membership_id, low_confidence_field),
        )
        reviewed = QuotationConfirmationService().confirm(
            bearer_token="test-token",
            member=member,
            quotation_id=fixture.quotation_id,
            payload=None,
        )
        assert reviewed.status == "reviewed"

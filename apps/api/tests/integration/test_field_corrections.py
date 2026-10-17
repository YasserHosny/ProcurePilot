from __future__ import annotations

import pytest

from integration.catalogue_helpers import TEST_DATABASE_URL, act_as, connection, make_workspace
from integration.quotation_helpers import (
    PsycopgSupabaseClient,
    make_extracted_quotation,
    make_field,
    make_review_task,
)
from procurepilot_api.deps import CurrentMember
from procurepilot_api.errors import ConflictError
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.quotations import review_service as review_service_module
from procurepilot_api.modules.quotations import service as quotation_service_module
from procurepilot_api.modules.quotations.review_service import QuotationReviewService
from procurepilot_api.modules.quotations.schemas import FieldCorrection, QuotationReviewPatch

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is required for field correction integration tests",
)


@pytest.fixture
def conn() -> object:
    yield from connection()


def test_correction_is_distinct_from_original_extracted_value(
    conn: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with conn.cursor() as cur:
        workspace = make_workspace(cur, "field-correction")
        fixture = make_extracted_quotation(cur, workspace)
        act_as(cur, workspace)
        monkeypatch.setattr(
            review_service_module,
            "authenticated_client",
            lambda _settings, _token: PsycopgSupabaseClient(conn),
        )
        monkeypatch.setattr(
            quotation_service_module,
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

        QuotationReviewService().apply_review_patch(
            bearer_token="test-token",
            member=member,
            quotation_id=fixture.quotation_id,
            patch=QuotationReviewPatch(
                corrections=[
                    FieldCorrection(
                        field_extraction_id=fixture.field_id,
                        corrected_value="USD",
                    )
                ]
            ),
        )

        cur.execute(
            "select extracted_value, corrected_value, corrected_by, corrected_at "
            "from field_extraction where id = %s",
            (fixture.field_id,),
        )
        extracted_value, corrected_value, corrected_by, corrected_at = cur.fetchone()
        assert extracted_value == "GBP"
        assert corrected_value == "USD"
        assert corrected_by == workspace.membership_id
        assert corrected_at is not None


def test_invalid_date_correction_prevalidates_entire_patch_without_writes(
    conn: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from decimal import Decimal

    with conn.cursor() as cur:
        workspace = make_workspace(cur, "atomic-date-correction")
        fixture = make_extracted_quotation(cur, workspace)
        date_field_id = make_field(
            cur,
            workspace,
            fixture.quotation_id,
            field_name="issue_date",
            extracted_value="16/10/2026",
            confidence=Decimal("0.9900"),
        )
        task_id = make_review_task(
            cur, workspace, fixture.quotation_id, reason="low_confidence"
        )
        act_as(cur, workspace)
        monkeypatch.setattr(
            review_service_module,
            "authenticated_client",
            lambda _settings, _token: PsycopgSupabaseClient(conn),
        )
        monkeypatch.setattr(
            quotation_service_module,
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
        before_supplier = fixture.supplier_id
        with pytest.raises(ConflictError) as exc_info:
            QuotationReviewService().apply_review_patch(
                bearer_token="test-token",
                member=member,
                quotation_id=fixture.quotation_id,
                patch=QuotationReviewPatch(
                    supplier_id=None,
                    reviewer_notes="must not persist",
                    corrections=[
                        FieldCorrection(
                            field_extraction_id=date_field_id,
                            corrected_value="not a date",
                        )
                    ],
                ),
            )
        assert getattr(exc_info.value, "details", None) == {
            "reason": "invalid_date_correction"
        }
        cur.execute(
            "select supplier_id, reviewer_notes from quotation where id=%s",
            (fixture.quotation_id,),
        )
        assert cur.fetchone() == (before_supplier, None)
        cur.execute(
            "select corrected_value, corrected_by from field_extraction where id=%s",
            (date_field_id,),
        )
        assert cur.fetchone() == (None, None)
        cur.execute("select reason,status from review_task where id=%s", (task_id,))
        assert cur.fetchone() == ("low_confidence", "open")

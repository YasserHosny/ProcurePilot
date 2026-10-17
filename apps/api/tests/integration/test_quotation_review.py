from __future__ import annotations

from decimal import Decimal

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
from procurepilot_api.modules.quotations import (
    confirmation_service as confirmation_service_module,
)
from procurepilot_api.modules.quotations import (
    review_service as review_service_module,
)
from procurepilot_api.modules.quotations import (
    service as quotation_service_module,
)
from procurepilot_api.modules.quotations.confirmation_service import QuotationConfirmationService
from procurepilot_api.modules.quotations.review_service import (
    QuotationReviewService,
    _current_review_blocker,
)
from procurepilot_api.modules.quotations.schemas import FieldCorrection, QuotationReviewPatch
from procurepilot_api.modules.quotations.service import QuotationService
from procurepilot_api.shared.audit import AuditEventCreate

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
    class AuditWriter:
        def record(
            self,
            event: AuditEventCreate,
            bearer_token: str | None = None,
        ) -> None:
            del event, bearer_token

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
        monkeypatch.setattr(
            confirmation_service_module,
            "get_audit_writer",
            lambda: AuditWriter(),
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


def test_parsed_raw_date_does_not_create_date_unparsed_blocker(
    conn: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with conn.cursor() as cur:
        workspace = make_workspace(cur, "parsed-date-blocker")
        fixture = make_extracted_quotation(cur, workspace)
        make_field(
            cur,
            workspace,
            fixture.quotation_id,
            field_name="issue_date",
            extracted_value="16/10/2026",
            confidence=Decimal("0.9900"),
        )
        cur.execute(
            "update quotation set issue_date='2026-10-16' where id=%s",
            (fixture.quotation_id,),
        )
        act_as(cur, workspace)
        assert (
            _current_review_blocker(PsycopgSupabaseClient(conn), fixture.quotation_id, 0.85) is None
        )


@pytest.mark.parametrize(
    "reason",
    [
        "merged_line_items",
        "line_count_mismatch",
        "total_unverified",
        "date_unparsed",
        "currency_unresolved",
        "read_failure",
    ],
)
def test_review_queue_preserves_sticky_task_reasons(
    conn: object, monkeypatch: pytest.MonkeyPatch, reason: str
) -> None:
    with conn.cursor() as cur:
        workspace = make_workspace(cur, f"sticky-review-{reason.replace('_', '-')}")
        fixture = make_extracted_quotation(cur, workspace)
        cur.execute("update quotation set status='in_review' where id=%s", (fixture.quotation_id,))
        make_review_task(cur, workspace, fixture.quotation_id, reason=reason)
        act_as(cur, workspace)
        monkeypatch.setattr(
            quotation_service_module,
            "authenticated_client",
            lambda _settings, _token: PsycopgSupabaseClient(conn),
        )

        tasks = QuotationService().list_review_tasks(bearer_token="test-token").items
        task = next(task for task in tasks if task.quotation_id == fixture.quotation_id)
        assert task.status == "open"
        assert task.reason == reason
        cur.execute("select status from quotation where id=%s", (fixture.quotation_id,))
        assert cur.fetchone() == ("in_review",)


def test_reviewer_patch_resolves_structural_task_and_list_resolves_stale_dynamic_task(
    conn: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    class AuditWriter:
        def record(self, event: AuditEventCreate, bearer_token: str | None = None) -> None:
            del event, bearer_token

    with conn.cursor() as cur:
        workspace = make_workspace(cur, "review-task-human-clear")
        fixture = make_extracted_quotation(cur, workspace)
        make_review_task(cur, workspace, fixture.quotation_id, reason="line_count_mismatch")
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
        monkeypatch.setattr(review_service_module, "get_audit_writer", lambda: AuditWriter())
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
                    FieldCorrection(field_extraction_id=fixture.field_id, corrected_value="GBP")
                ]
            ),
        )
        cur.execute("select status from review_task where quotation_id=%s", (fixture.quotation_id,))
        assert cur.fetchone() == ("resolved",)

        stale = make_extracted_quotation(cur, workspace)
        make_review_task(cur, workspace, stale.quotation_id, reason="low_confidence")
        tasks = QuotationService().list_review_tasks(bearer_token="test-token").items
        assert all(task.quotation_id != stale.quotation_id for task in tasks)

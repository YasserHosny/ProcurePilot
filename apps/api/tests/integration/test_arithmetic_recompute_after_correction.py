from __future__ import annotations

import pytest

from integration.catalogue_helpers import TEST_DATABASE_URL, act_as, connection, make_workspace
from integration.quotation_helpers import (
    PsycopgSupabaseClient,
    ensure_quotation_reference_data,
    make_document,
    make_field,
    make_line,
    make_quotation,
    make_review_task,
    make_supplier,
)
from procurepilot_api.deps import CurrentMember
from procurepilot_api.errors import ConflictError
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.quotations import (
    confirmation_service as confirmation_service_module,
)
from procurepilot_api.modules.quotations import review_service as review_service_module
from procurepilot_api.modules.quotations import service as quotation_service_module
from procurepilot_api.modules.quotations.confirmation_service import QuotationConfirmationService
from procurepilot_api.modules.quotations.review_service import QuotationReviewService
from procurepilot_api.modules.quotations.schemas import FieldCorrection, QuotationReviewPatch
from procurepilot_api.modules.quotations.service import QuotationService
from procurepilot_api.shared.audit import AuditEventCreate

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is required for arithmetic recompute integration tests",
)


@pytest.fixture
def conn() -> object:
    yield from connection()


class _NoopAuditWriter:
    def record(self, event: AuditEventCreate, bearer_token: str | None = None) -> None:
        del event, bearer_token


def test_correcting_a_line_reconciles_arithmetic_and_unblocks_confirmation(
    conn: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with conn.cursor() as cur:
        workspace = make_workspace(cur, "arithmetic-recompute")
        ensure_quotation_reference_data(cur)
        supplier_id = make_supplier(cur, workspace)
        document_id = make_document(cur, workspace)
        quotation_id = make_quotation(
            cur,
            workspace,
            document_id=document_id,
            supplier_id=supplier_id,
            status="extracted",
            arithmetic_status="mismatch",
        )
        act_as(cur, workspace)
        cur.execute(
            "update quotation set stated_total_amount = 88.00, stated_total_currency = 'GBP' "
            "where id = %s",
            (quotation_id,),
        )
        line_id = make_line(cur, workspace, quotation_id)
        task_id = make_review_task(
            cur,
            workspace,
            quotation_id,
            reason="arithmetic_mismatch",
            priority="high",
        )
        act_as(cur, workspace)
        cur.execute(
            "update quotation_line set quantity = 2, unit_price_amount = 10.00 where id = %s",
            (line_id,),
        )
        field_id = make_field(
            cur,
            workspace,
            quotation_id,
            entity_id=line_id,
            entity_type="quotation_line",
            field_name="unit_price",
            extracted_value={"amount": "10.00", "currency": "GBP"},
        )

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
        monkeypatch.setattr(
            review_service_module,
            "get_audit_writer",
            lambda: _NoopAuditWriter(),
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
            quotation_id=quotation_id,
            patch=QuotationReviewPatch(
                corrections=[
                    FieldCorrection(
                        field_extraction_id=field_id,
                        corrected_value={"amount": "44.00", "currency": "GBP"},
                    )
                ]
            ),
        )

        cur.execute(
            "select unit_price_amount from quotation_line where id = %s",
            (line_id,),
        )
        assert cur.fetchone() == (44.00,)

        cur.execute(
            "select arithmetic_status from quotation where id = %s",
            (quotation_id,),
        )
        assert cur.fetchone() == ("reconciled",)
        cur.execute(
            "select status, resolved_at from review_task where id = %s",
            (task_id,),
        )
        task_status, resolved_at = cur.fetchone()
        assert task_status == "resolved"
        assert resolved_at is not None

        monkeypatch.setattr(
            confirmation_service_module,
            "authenticated_client",
            lambda _settings, _token: PsycopgSupabaseClient(conn),
        )
        monkeypatch.setattr(
            confirmation_service_module,
            "get_audit_writer",
            lambda: _NoopAuditWriter(),
        )
        confirmed = QuotationConfirmationService().confirm(
            bearer_token="test-token",
            member=member,
            quotation_id=quotation_id,
            payload=None,
        )
        assert confirmed.status == "reviewed"


def test_reconciled_arithmetic_task_switches_to_missing_supplier_blocker(
    conn: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with conn.cursor() as cur:
        workspace = make_workspace(cur, "arithmetic-recompute-supplier")
        ensure_quotation_reference_data(cur)
        document_id = make_document(cur, workspace)
        quotation_id = make_quotation(
            cur,
            workspace,
            document_id=document_id,
            supplier_id=None,
            status="extracted",
            arithmetic_status="mismatch",
        )
        act_as(cur, workspace)
        cur.execute(
            "update quotation set stated_total_amount = 88.00, stated_total_currency = 'GBP' "
            "where id = %s",
            (quotation_id,),
        )
        line_id = make_line(cur, workspace, quotation_id)
        task_id = make_review_task(
            cur,
            workspace,
            quotation_id,
            reason="arithmetic_mismatch",
            priority="high",
        )
        act_as(cur, workspace)
        cur.execute(
            "update quotation_line set quantity = 2, unit_price_amount = 10.00 where id = %s",
            (line_id,),
        )
        field_id = make_field(
            cur,
            workspace,
            quotation_id,
            entity_id=line_id,
            entity_type="quotation_line",
            field_name="unit_price",
            extracted_value={"amount": "10.00", "currency": "GBP"},
        )
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
        monkeypatch.setattr(
            review_service_module,
            "get_audit_writer",
            lambda: _NoopAuditWriter(),
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
            quotation_id=quotation_id,
            patch=QuotationReviewPatch(
                corrections=[
                    FieldCorrection(
                        field_extraction_id=field_id,
                        corrected_value={"amount": "44.00", "currency": "GBP"},
                    )
                ]
            ),
        )

        cur.execute(
            "select status, priority, reason, resolved_at from review_task where id = %s",
            (task_id,),
        )
        assert cur.fetchone() == ("open", "normal", "no_supplier_match", None)


def test_review_queue_self_heals_stale_arithmetic_mismatch_tasks(
    conn: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with conn.cursor() as cur:
        workspace = make_workspace(cur, "review-queue-stale-arithmetic")
        ensure_quotation_reference_data(cur)
        document_id = make_document(cur, workspace)
        quotation_id = make_quotation(
            cur,
            workspace,
            document_id=document_id,
            supplier_id=None,
            status="in_review",
            arithmetic_status="reconciled",
        )
        task_id = make_review_task(
            cur,
            workspace,
            quotation_id,
            reason="arithmetic_mismatch",
            priority="high",
        )
        monkeypatch.setattr(
            quotation_service_module,
            "authenticated_client",
            lambda _settings, _token: PsycopgSupabaseClient(conn),
        )
        act_as(cur, workspace)

        tasks = QuotationService().list_review_tasks(bearer_token="test-token").items

        matching_task = next(task for task in tasks if task.id == task_id)
        assert matching_task.status == "open"
        assert matching_task.priority == "normal"
        assert matching_task.reason == "no_supplier_match"


def test_correcting_a_low_confidence_header_field_unblocks_confirmation(
    conn: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FR-013: reviewers must be able to correct any extracted field. Header fields
    (currency/issue_date/expiry_date/stated_total) were only ever readonly displays in the
    review UI, so a low-confidence header field extraction — the stub provider always rates
    issue_date at 62% or 78%, both below the 0.85 threshold — could never be corrected and
    therefore could never be confirmed."""
    with conn.cursor() as cur:
        workspace = make_workspace(cur, "header-field-correction")
        ensure_quotation_reference_data(cur)
        supplier_id = make_supplier(cur, workspace)
        document_id = make_document(cur, workspace)
        quotation_id = make_quotation(
            cur,
            workspace,
            document_id=document_id,
            supplier_id=supplier_id,
            status="extracted",
            arithmetic_status="not_applicable",
        )
        field_id = make_field(
            cur,
            workspace,
            quotation_id,
            entity_id=quotation_id,
            entity_type="quotation",
            field_name="issue_date",
            extracted_value="2026-08-21",
            confidence=0.6200,
        )

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
        monkeypatch.setattr(
            review_service_module,
            "get_audit_writer",
            lambda: _NoopAuditWriter(),
        )
        member = CurrentMember(
            membership_id=workspace.membership_id,
            tenant_id=workspace.tenant_id,
            user_id=workspace.user_id,
            email="buyer@example.test",
            role=MemberRole.buyer,
        )

        monkeypatch.setattr(
            confirmation_service_module,
            "authenticated_client",
            lambda _settings, _token: PsycopgSupabaseClient(conn),
        )
        monkeypatch.setattr(
            confirmation_service_module,
            "get_audit_writer",
            lambda: _NoopAuditWriter(),
        )

        with pytest.raises(ConflictError):
            QuotationConfirmationService().confirm(
                bearer_token="test-token",
                member=member,
                quotation_id=quotation_id,
                payload=None,
            )

        QuotationReviewService().apply_review_patch(
            bearer_token="test-token",
            member=member,
            quotation_id=quotation_id,
            patch=QuotationReviewPatch(
                corrections=[
                    FieldCorrection(
                        field_extraction_id=field_id,
                        corrected_value="2026-08-20",
                    )
                ]
            ),
        )

        cur.execute("select issue_date from quotation where id = %s", (quotation_id,))
        assert str(cur.fetchone()[0]) == "2026-08-20"

        confirmed = QuotationConfirmationService().confirm(
            bearer_token="test-token",
            member=member,
            quotation_id=quotation_id,
            payload=None,
        )
        assert confirmed.status == "reviewed"

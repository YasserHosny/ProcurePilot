from __future__ import annotations

import json
from decimal import Decimal
from uuid import UUID

import pytest

from integration.catalogue_helpers import (
    TEST_DATABASE_URL,
    Workspace,
    act_as,
    connection,
    make_workspace,
)
from integration.quotation_helpers import (
    PsycopgSupabaseClient,
    make_extracted_quotation,
    make_field,
    make_review_task,
)
from procurepilot_api.deps import CurrentMember
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.quotations import (
    confirmation_service as confirmation_service_module,
)
from procurepilot_api.modules.quotations import review_service as review_service_module
from procurepilot_api.modules.quotations import service as quotation_service_module
from procurepilot_api.modules.quotations.confirmation_service import QuotationConfirmationService
from procurepilot_api.modules.quotations.review_service import QuotationReviewService
from procurepilot_api.modules.quotations.schemas import (
    FieldCorrection,
    NewQuotationLine,
    QuotationReviewPatch,
)
from procurepilot_api.modules.quotations.service import QuotationService
from procurepilot_api.shared.audit import AuditEventCreate

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is required for quotation audit integration tests",
)


@pytest.fixture
def conn() -> object:
    yield from connection()


class _PsycopgAuditWriter:
    def __init__(self, conn: object) -> None:
        self._conn = conn

    def record(self, event: AuditEventCreate, bearer_token: str | None = None) -> None:
        del bearer_token
        with self._conn.cursor() as cur:
            cur.execute(
                "select record_audit_event("
                "%s, %s, %s::uuid, %s::uuid, %s, %s::jsonb, %s"
                ")",
                (
                    event.action,
                    event.outcome,
                    event.tenant_id,
                    event.actor_membership_id,
                    event.actor_email,
                    json.dumps(event.target),
                    event.trace_id,
                ),
            )


def _member(workspace: Workspace) -> CurrentMember:
    return CurrentMember(
        membership_id=workspace.membership_id,
        tenant_id=workspace.tenant_id,
        user_id=workspace.user_id,
        email=f"{workspace.label}-{workspace.role}@example.test",
        role=MemberRole(workspace.role),
    )


def _wire_services(conn: object, monkeypatch: pytest.MonkeyPatch) -> None:
    def client_factory(_settings: object, _token: str) -> PsycopgSupabaseClient:
        return PsycopgSupabaseClient(conn)

    audit_writer = _PsycopgAuditWriter(conn)
    monkeypatch.setattr(quotation_service_module, "authenticated_client", client_factory)
    monkeypatch.setattr(review_service_module, "authenticated_client", client_factory)
    monkeypatch.setattr(confirmation_service_module, "authenticated_client", client_factory)
    monkeypatch.setattr(quotation_service_module, "get_audit_writer", lambda: audit_writer)
    monkeypatch.setattr(review_service_module, "get_audit_writer", lambda: audit_writer)
    monkeypatch.setattr(confirmation_service_module, "get_audit_writer", lambda: audit_writer)


def _audit_actions_for(
    service: QuotationService,
    *,
    bearer_token: str,
    member: CurrentMember,
    quotation_id: UUID,
) -> list[str]:
    return [
        item.action
        for item in service.get_audit_trail(
            bearer_token=bearer_token,
            member=member,
            quotation_id=quotation_id,
        ).items
    ]


def test_quotation_review_page_actions_appear_in_quotation_audit_trail(
    conn: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _wire_services(conn, monkeypatch)
    with conn.cursor() as cur:
        workspace = make_workspace(cur, "quotation-audit")
        member = _member(workspace)
        fixture = make_extracted_quotation(cur, workspace)
        low_confidence_issue_date_id = make_field(
            cur,
            workspace,
            fixture.quotation_id,
            field_name="issue_date",
            extracted_value="2026-08-21",
            confidence=Decimal("0.6200"),
        )
        make_review_task(cur, workspace, fixture.quotation_id, reason="low_confidence")
        act_as(cur, workspace)

        QuotationReviewService().apply_review_patch(
            bearer_token="test-token",
            member=member,
            quotation_id=fixture.quotation_id,
            patch=QuotationReviewPatch(
                supplier_id=fixture.supplier_id,
                reviewer_notes="Checked supplier, issue date, and line arithmetic.",
                corrections=[
                    FieldCorrection(
                        field_extraction_id=low_confidence_issue_date_id,
                        corrected_value="2026-08-19",
                    )
                ],
                add_lines=[
                    NewQuotationLine(
                        original_text="Audited freight line",
                        quantity="1",
                        unit_price_amount="3.50",
                        unit_price_currency="GBP",
                    )
                ],
            ),
        )
        QuotationService().export_quotation_csv(
            bearer_token="test-token",
            member=member,
            quotation_id=fixture.quotation_id,
        )
        QuotationConfirmationService().confirm(
            bearer_token="test-token",
            member=member,
            quotation_id=fixture.quotation_id,
            payload=None,
        )

        actions = _audit_actions_for(
            QuotationService(),
            bearer_token="test-token",
            member=member,
            quotation_id=fixture.quotation_id,
        )

        assert "quotation.reviewed" in actions
        assert "quotation.exported" in actions
        assert "quotation.confirmed" in actions


def test_refuse_archive_and_restore_appear_in_quotation_audit_trail(
    conn: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _wire_services(conn, monkeypatch)
    with conn.cursor() as cur:
        workspace = make_workspace(cur, "quotation-audit-lifecycle")
        member = _member(workspace)
        refused = make_extracted_quotation(cur, workspace)
        archived = make_extracted_quotation(cur, workspace)
        act_as(cur, workspace)

        QuotationReviewService().refuse_quotation(
            bearer_token="test-token",
            member=member,
            quotation_id=refused.quotation_id,
            reason="Supplier data was not usable.",
        )
        QuotationService().archive_quotation(
            bearer_token="test-token",
            member=member,
            quotation_id=archived.quotation_id,
        )
        QuotationService().restore_quotation(
            bearer_token="test-token",
            member=member,
            quotation_id=archived.quotation_id,
        )

        refused_actions = _audit_actions_for(
            QuotationService(),
            bearer_token="test-token",
            member=member,
            quotation_id=refused.quotation_id,
        )
        archived_actions = _audit_actions_for(
            QuotationService(),
            bearer_token="test-token",
            member=member,
            quotation_id=archived.quotation_id,
        )

        assert "quotation.refused" in refused_actions
        assert "quotation.archived" in archived_actions
        assert "quotation.restored" in archived_actions

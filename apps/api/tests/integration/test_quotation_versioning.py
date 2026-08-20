from __future__ import annotations

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
    make_document,
    make_extracted_quotation,
    make_quotation,
)
from procurepilot_api.deps import CurrentMember
from procurepilot_api.errors import ConflictError, NotFoundError
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.quotations import (
    confirmation_service as confirmation_service_module,
)
from procurepilot_api.modules.quotations.confirmation_service import QuotationConfirmationService
from procurepilot_api.modules.quotations.schemas import ConfirmRequest

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is required for quotation versioning integration tests",
)


@pytest.fixture
def conn() -> object:
    yield from connection()


def member_for_workspace(workspace: Workspace) -> CurrentMember:
    return CurrentMember(
        membership_id=workspace.membership_id,
        tenant_id=workspace.tenant_id,
        user_id=workspace.user_id,
        email="buyer@example.test",
        role=MemberRole.buyer,
    )


def test_previous_quotation_id_is_persisted_only_at_confirm_time(
    conn: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with conn.cursor() as cur:
        workspace = make_workspace(cur, "quotation-versioning")
        current = make_extracted_quotation(cur, workspace)
        previous_id = make_quotation(
            cur,
            workspace,
            document_id=make_document(cur, workspace, filename="previous.pdf"),
            supplier_id=current.supplier_id,
            status="reviewed",
            arithmetic_status="reconciled",
        )
        act_as(cur, workspace)
        monkeypatch.setattr(
            confirmation_service_module,
            "authenticated_client",
            lambda _settings, _token: PsycopgSupabaseClient(conn),
        )

        cur.execute(
            "select previous_quotation_id from quotation where id = %s",
            (current.quotation_id,),
        )
        assert cur.fetchone() == (None,)

        reviewed = QuotationConfirmationService().confirm(
            bearer_token="test-token",
            member=member_for_workspace(workspace),
            quotation_id=current.quotation_id,
            payload=ConfirmRequest(previous_quotation_id=previous_id),
        )

        assert reviewed.previous_quotation_id == previous_id
        cur.execute(
            "select previous_quotation_id from quotation where id = %s",
            (current.quotation_id,),
        )
        assert cur.fetchone() == (previous_id,)


def test_previous_quotation_id_cannot_be_self_referential(
    conn: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with conn.cursor() as cur:
        workspace = make_workspace(cur, "quotation-version-self")
        current = make_extracted_quotation(cur, workspace)
        act_as(cur, workspace)
        monkeypatch.setattr(
            confirmation_service_module,
            "authenticated_client",
            lambda _settings, _token: PsycopgSupabaseClient(conn),
        )

        with pytest.raises(ConflictError):
            QuotationConfirmationService().confirm(
                bearer_token="test-token",
                member=member_for_workspace(workspace),
                quotation_id=current.quotation_id,
                payload=ConfirmRequest(previous_quotation_id=current.quotation_id),
            )


def test_previous_quotation_id_must_be_same_tenant(
    conn: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with conn.cursor() as cur:
        alpha = make_workspace(cur, "quotation-version-alpha")
        beta = make_workspace(cur, "quotation-version-beta")
        current = make_extracted_quotation(cur, alpha)
        beta_previous = make_extracted_quotation(cur, beta)
        act_as(cur, alpha)
        monkeypatch.setattr(
            confirmation_service_module,
            "authenticated_client",
            lambda _settings, _token: PsycopgSupabaseClient(conn),
        )

        with pytest.raises(NotFoundError):
            QuotationConfirmationService().confirm(
                bearer_token="test-token",
                member=member_for_workspace(alpha),
                quotation_id=current.quotation_id,
                payload=ConfirmRequest(previous_quotation_id=beta_previous.quotation_id),
            )

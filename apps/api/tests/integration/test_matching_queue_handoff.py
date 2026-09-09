from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from integration.catalogue_helpers import TEST_DATABASE_URL, act_as, connection, make_workspace
from integration.quotation_helpers import (
    PsycopgSupabaseClient,
    ensure_quotation_reference_data,
    make_document,
    make_line,
    make_quotation,
    make_supplier,
)
from procurepilot_api.errors import NotFoundError
from procurepilot_api.modules.matching import service as matching_service_module
from procurepilot_api.modules.matching.service import MatchingService

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is required for matching queue handoff tests",
)


@pytest.fixture
def conn() -> object:
    yield from connection()


def test_matching_queue_hides_unreviewed_quotation_lines(
    conn: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with conn.cursor() as cur:
        workspace = make_workspace(cur, "matching-handoff-unreviewed")
        ensure_quotation_reference_data(cur)
        supplier_id = make_supplier(cur, workspace, name="Unreviewed Supplier")
        quotation_id = make_quotation(
            cur,
            workspace,
            document_id=make_document(cur, workspace),
            supplier_id=supplier_id,
            status="in_review",
            arithmetic_status="reconciled",
        )
        line_id = make_line(cur, workspace, quotation_id)
        task_id = _make_match_task(cur, workspace, line_id)
        monkeypatch.setattr(
            matching_service_module,
            "authenticated_client",
            lambda _settings, _token: PsycopgSupabaseClient(conn),
        )
        act_as(cur, workspace)

        tasks = MatchingService().list_match_tasks(bearer_token="test-token").items

        assert task_id not in {task.id for task in tasks}
        cur.execute("select status, resolved_at from match_task where id = %s", (task_id,))
        status, resolved_at = cur.fetchone()
        assert status == "resolved"
        assert resolved_at is not None


def test_matching_queue_cells_match_reviewed_quotation_line(
    conn: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with conn.cursor() as cur:
        workspace = make_workspace(cur, "matching-handoff-reviewed")
        ensure_quotation_reference_data(cur)
        supplier_id = make_supplier(cur, workspace, name="Reviewed Supplier")
        quotation_id = make_quotation(
            cur,
            workspace,
            document_id=make_document(cur, workspace),
            supplier_id=supplier_id,
            status="reviewed",
            arithmetic_status="reconciled",
        )
        line_id = make_line(cur, workspace, quotation_id)
        act_as(cur, workspace)
        cur.execute(
            """
            update quotation_line
            set line_number = 4,
                original_text = 'Validated matching handoff cell',
                quantity = 7,
                unit_price_amount = 12.34,
                unit_price_currency = 'GBP'
            where id = %s
            """,
            (line_id,),
        )
        task_id = _make_match_task(cur, workspace, line_id, reason="no_candidate")
        monkeypatch.setattr(
            matching_service_module,
            "authenticated_client",
            lambda _settings, _token: PsycopgSupabaseClient(conn),
        )

        tasks = MatchingService().list_match_tasks(
            bearer_token="test-token",
            quotation_id=quotation_id,
        ).items

        task = next(item for item in tasks if item.id == task_id)
        assert task.quotation_id == quotation_id
        assert task.supplier_name == "Reviewed Supplier"
        assert task.quotation_line.id == line_id
        assert task.quotation_line.line_number == 4
        assert task.quotation_line.original_text == "Validated matching handoff cell"
        assert task.quotation_line.unit_price is not None
        assert task.quotation_line.unit_price.amount == "12.3400"
        assert task.quotation_line.unit_price.currency == "GBP"
        assert task.reason == "no_candidate"


def test_direct_match_task_lookup_hides_another_tenants_line(
    conn: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with conn.cursor() as cur:
        tenant_a = make_workspace(cur, "matching-direct-a")
        tenant_b = make_workspace(cur, "matching-direct-b")
        ensure_quotation_reference_data(cur)
        quotation_id = make_quotation(
            cur,
            tenant_a,
            document_id=make_document(cur, tenant_a),
            status="reviewed",
            arithmetic_status="reconciled",
        )
        line_id = make_line(cur, tenant_a, quotation_id)
        _make_match_task(cur, tenant_a, line_id)

        act_as(cur, tenant_b)
        monkeypatch.setattr(
            matching_service_module,
            "authenticated_client",
            lambda _settings, _token: PsycopgSupabaseClient(conn),
        )

        with pytest.raises(NotFoundError):
            MatchingService().match_task_for_line(
                bearer_token="tenant-b-token",
                line_id=line_id,
            )


def _make_match_task(
    cur: object,
    workspace: object,
    line_id: UUID,
    *,
    reason: str = "low_confidence",
) -> UUID:
    task_id = uuid4()
    act_as(cur, workspace)
    cur.execute(
        "insert into match_task (id,tenant_id,quotation_line_id,reason,priority) "
        "values (%s,%s,%s,%s,'normal')",
        (task_id, workspace.tenant_id, line_id, reason),
    )
    return task_id

"""Finding 38a/38b: guardrail provenance on purchase requests, the owner email, and the
worker's cost-centre fallback, without a database."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest

from procurepilot_api.modules.ingestion.orchestrator import (
    _email_guardrail_owner,
    _guardrail_cost_centre,
)
from procurepilot_api.modules.requests.service import RequestsService
from procurepilot_api.modules.rfq.auto_prepared_email import render_auto_prepared_email
from procurepilot_api.modules.rfq.guardrails import AutoPreparationGuardrail
from procurepilot_api.shared.mailer import FakeMailer


class _Query:
    def __init__(self, client: _Client, name: str, rows: list[dict[str, Any]]) -> None:
        self.client, self.name, self.rows = client, name, rows

    def select(self, _columns: str) -> _Query:
        return self

    def in_(self, column: str, values: list[str]) -> _Query:
        self.client.calls.append((self.name, column, sorted(values)))
        self.rows = [row for row in self.rows if str(row[column]) in set(values)]
        return self

    def execute(self) -> SimpleNamespace:
        return SimpleNamespace(data=self.rows)


class _Client:
    def __init__(self, tables: dict[str, list[dict[str, Any]]]) -> None:
        self.tables = tables
        self.calls: list[tuple[str, str, list[str]]] = []

    def table(self, name: str) -> _Query:
        return _Query(self, name, list(self.tables.get(name, [])))


def test_provenance_is_batched_and_names_the_winning_supplier() -> None:
    prepared, manual_from_rfq, manual = str(uuid4()), str(uuid4()), str(uuid4())
    guardrail_id, rfq_id, supplier_id = uuid4(), uuid4(), uuid4()
    created_at = datetime(2026, 10, 18, 9, 0, tzinfo=UTC)
    client = _Client(
        {
            "auto_preparation_event": [
                {
                    "purchase_request_id": prepared,
                    "guardrail_id": str(guardrail_id),
                    "rfq_id": str(rfq_id),
                    "supplier_id": str(supplier_id),
                    "created_at": created_at.isoformat(),
                }
            ],
            "supplier": [{"id": str(supplier_id), "name": "مخبز النور"}],
        }
    )
    rows = [
        {"id": prepared, "source_rfq_response_id": str(uuid4())},
        {"id": manual_from_rfq, "source_rfq_response_id": str(uuid4())},
        {"id": manual, "source_rfq_response_id": None},
    ]

    result = RequestsService.__new__(RequestsService)._fetch_auto_prepared_batch(client, rows)

    assert set(result) == {prepared}
    provenance = result[prepared]
    assert (provenance.guardrail_id, provenance.rfq_id, provenance.supplier_id) == (
        guardrail_id,
        rfq_id,
        supplier_id,
    )
    assert provenance.supplier_name == "مخبز النور"
    assert provenance.created_at == created_at
    # One query per table for the whole page; a request never prepared from an RFQ response
    # is not even asked about.
    assert client.calls == [
        ("auto_preparation_event", "purchase_request_id", sorted([prepared, manual_from_rfq])),
        ("supplier", "id", [str(supplier_id)]),
    ]


def test_requests_without_an_rfq_source_cost_no_query() -> None:
    client = _Client({})
    rows = [{"id": str(uuid4()), "source_rfq_response_id": None}]
    assert RequestsService.__new__(RequestsService)._fetch_auto_prepared_batch(client, rows) == {}
    assert client.calls == []


class _Cursor:
    def __init__(self, row: object) -> None:
        self.row, self.executed = row, []

    def execute(self, sql: str, params: tuple[object, ...]) -> None:
        self.executed.append((sql, params))

    def fetchone(self) -> object:
        return self.row


def _guardrail(cost_centre_id: UUID | None) -> AutoPreparationGuardrail:
    return AutoPreparationGuardrail(
        id=uuid4(),
        tenant_id=uuid4(),
        enabled=True,
        min_response_count=1,
        max_order_value_amount=1,
        max_order_value_currency="EGP",
        max_price_variance_pct=0,
        supplier_allowlist=None,
        category_allowlist=None,
        default_branch_id=uuid4(),
        created_by_membership_id=uuid4(),
        default_cost_centre_id=cost_centre_id,
    )


def test_worker_uses_the_cost_centre_only_while_it_is_still_valid() -> None:
    cost_centre_id = uuid4()
    guardrail = _guardrail(cost_centre_id)

    valid = _Cursor({"?column?": 1})
    assert _guardrail_cost_centre(valid, tenant_id=guardrail.tenant_id, guardrail=guardrail) == (
        cost_centre_id
    )
    sql, params = valid.executed[0]
    assert "branch_id = %s" in sql and "not is_archived" in sql
    assert params == (guardrail.tenant_id, cost_centre_id, guardrail.default_branch_id)

    stale = _Cursor(None)  # archived since, or moved to another branch
    assert _guardrail_cost_centre(stale, tenant_id=guardrail.tenant_id, guardrail=guardrail) is None

    none = _Cursor(None)
    assert _guardrail_cost_centre(none, tenant_id=uuid4(), guardrail=_guardrail(None)) is None
    assert none.executed == []


def _settings(**overrides: object) -> SimpleNamespace:
    values: dict[str, object] = {
        "rfq_mailer_mode": "stub",
        "mailgun_api_key": None,
        "mailgun_sending_domain": None,
        "web_origin": "https://app.example.test/",
        "api_cors_origins": ("http://localhost:4200",),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_owner_email_links_to_the_draft_in_the_owner_language(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RFQ_MAILER_MODE", "stub")
    FakeMailer.clear()
    request_id = uuid4()

    outcome = _email_guardrail_owner(
        _settings(),  # type: ignore[arg-type]
        to="owner@example.test",
        workspace_name="مطاعم تجربة",
        supplier_name="مخبز النور",
        locale="ar",
        purchase_request_id=request_id,
    )

    assert outcome == "sent"
    (message,) = FakeMailer.sent_messages
    assert message.to == "owner@example.test"
    assert message.subject == "مسودة طلب جاهزة للمراجعة — مخبز النور"
    assert f"https://app.example.test/requests/{request_id}" in message.body
    assert message.html is not None and 'dir="rtl"' in message.html


def test_owner_email_escapes_names_and_falls_back_to_english() -> None:
    rendered = render_auto_prepared_email(
        workspace_name="A & B <Ltd>",
        supplier_name="<script>",
        request_url="https://app.example.test/requests/1",
        locale="fr",
    )
    assert rendered.locale == "en"
    assert "<script>" not in rendered.html
    assert "&lt;script&gt;" in rendered.html
    assert "Nothing has been ordered" in rendered.text


def test_owner_email_reports_unconfigured_mailgun_without_sending(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RFQ_MAILER_MODE", "mailgun")
    FakeMailer.clear()
    outcome = _email_guardrail_owner(
        _settings(rfq_mailer_mode="mailgun"),  # type: ignore[arg-type]
        to="owner@example.test",
        workspace_name="W",
        supplier_name=None,
        locale="en",
        purchase_request_id=uuid4(),
    )
    assert outcome == "not_configured"
    assert FakeMailer.sent_messages == []


def test_owner_email_failure_is_reported_not_raised(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RFQ_MAILER_MODE", "stub")

    def boom(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("smtp down")

    monkeypatch.setattr(FakeMailer, "send", boom)
    outcome = _email_guardrail_owner(
        _settings(),  # type: ignore[arg-type]
        to="owner@example.test",
        workspace_name="W",
        supplier_name="S",
        locale="en",
        purchase_request_id=uuid4(),
    )
    assert outcome == "failed"

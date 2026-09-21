from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID

import pytest
from pydantic import SecretStr

from procurepilot_api.modules.accounting.connector import RawBill, RawBillLine
from procurepilot_api.modules.accounting.sync_service import (
    SyncService,
    TokenRefreshFailedError,
)
from procurepilot_api.modules.accounting.xero_client import XeroAuthError

TENANT_ID = UUID("00000000-0000-0000-0000-000000000001")
CONNECTION_ID = UUID("00000000-0000-0000-0000-000000000004")


class _Cursor:
    def __init__(self, row: dict[str, object] | None = None) -> None:
        self.row = row
        self.queries: list[tuple[str, object]] = []

    def execute(self, query: str, params: object = None) -> None:
        self.queries.append((query, params))

    def fetchone(self) -> dict[str, object] | None:
        return self.row

    def __enter__(self) -> _Cursor:
        return self

    def __exit__(self, *_args: object) -> None:
        pass


class _Connection:
    def __init__(self, cursor: _Cursor) -> None:
        self.cursor_obj = cursor

    def cursor(self, **_kwargs: object) -> _Cursor:
        return self.cursor_obj

    def commit(self) -> None:
        pass

    def __enter__(self) -> _Connection:
        return self

    def __exit__(self, *_args: object) -> None:
        pass


class _XeroConnector:
    def list_vendors(self) -> list[object]:
        raise XeroAuthError(
            "Xero API request unauthorized (401): safe-code",
            status_code=401,
            error_code="safe-code",
        )


def test_xero_vendor_auth_failure_marks_connection_and_records_safe_audit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = SimpleNamespace(
        accounting_provider_mode="xero",
        database_url=SecretStr("postgresql://unused"),
        accounting_token_encryption_key=None,
    )
    service_role_cursor = _Cursor(
        {"access_token": "encrypted-access", "refresh_token": "encrypted-refresh"}
    )
    worker_cursor = _Cursor()
    worker_connection = _Connection(worker_cursor)
    audit_events: list[dict[str, object]] = []

    @contextmanager
    def service_role_db(_settings: object) -> Iterator[_Connection]:
        yield _Connection(service_role_cursor)

    monkeypatch.setattr(
        "procurepilot_api.modules.accounting.sync_service._service_role_db",
        service_role_db,
    )
    monkeypatch.setattr(
        "procurepilot_api.modules.accounting.sync_service.psycopg.connect",
        lambda *_args, **_kwargs: worker_connection,
    )
    monkeypatch.setattr(
        "procurepilot_api.modules.accounting.sync_service._record_audit",
        lambda **kwargs: audit_events.append(kwargs),
    )
    service = SyncService()

    with pytest.raises(TokenRefreshFailedError, match="vendor_fetch") as error_info:
        service._run_sync_pipeline(
            settings=settings,
            tenant_id=TENANT_ID,
            connection_id=CONNECTION_ID,
            conn_row={
                "provider": "xero",
                "realm_id": "xero-tenant",
                "connected_at": datetime(2026, 9, 19),
                "last_synced_at": None,
            },
            connector_override=_XeroConnector(),
        )

    assert "safe-code" not in str(error_info.value)
    assert any(
        "update accounting_connection" in query.lower()
        for query, _ in worker_cursor.queries
    )
    assert audit_events == [
        {
            "tenant_id": TENANT_ID,
            "action": "accounting.sync_failed",
            "target": {
                "accounting_connection_id": str(CONNECTION_ID),
                "error": "provider_authentication_failed",
                "reason": "vendor_fetch_failed",
            },
            "outcome": "refused",
        }
    ]


def test_upsert_bill_replaces_lines_with_tenant_scoped_statements() -> None:
    cursor = _Cursor({"id": str(UUID("00000000-0000-0000-0000-000000000099"))})
    connection = _Connection(cursor)
    bill = RawBill(
        provider_bill_id="bill-1",
        provider_vendor_id="vendor-1",
        amount=Decimal("12.00"),
        currency="USD",
        bill_date=date(2026, 9, 20),
        status="open",
        provider_order_reference="PO-1",
        document_references=("INV-1",),
        lines=(RawBillLine(1, Decimal("2"), Decimal("6"), "USD", "Paper"),),
    )

    synced_id = SyncService()._upsert_bill(
        connection,
        tenant_id=TENANT_ID,
        connection_id=CONNECTION_ID,
        raw_bill=bill,
        vendor_map={"vendor-1": (UUID("00000000-0000-0000-0000-000000000098"), None)},
    )

    assert synced_id == UUID("00000000-0000-0000-0000-000000000099")
    assert "provider_order_reference" in cursor.queries[0][0]
    assert "delete from synced_bill_line" in cursor.queries[1][0].lower()
    assert cursor.queries[1][1]["tenant_id"] == TENANT_ID
    assert "insert into synced_bill_line" in cursor.queries[2][0].lower()
    assert cursor.queries[2][1]["unit_price_currency"] == "USD"


@pytest.mark.parametrize("balance", [None, Decimal("0"), Decimal("12.34")])
def test_upsert_payment_evidence(balance: Decimal | None) -> None:
    cursor = _Cursor({"id": str(CONNECTION_ID)})
    bill = RawBill(
        provider_bill_id="bill-1", provider_vendor_id="vendor-1",
        amount=Decimal("20"), currency="EUR", bill_date=date(2026, 7, 1),
        status="open", due_date=date(2026, 7, 31), remaining_balance=balance,
    )
    SyncService()._upsert_bill(
        _Connection(cursor), tenant_id=TENANT_ID, connection_id=CONNECTION_ID,
        raw_bill=bill, vendor_map={"vendor-1": (CONNECTION_ID, None)},
    )
    query, params = cursor.queries[0]
    expected = {
        "due_date": date(2026, 7, 31), "remaining_balance_amount": balance,
        "remaining_balance_currency": "EUR" if balance is not None else None,
    }
    for column, value in expected.items():
        assert params[column] == value
        assert f"%({column})s" in query
        assert f"{column} = excluded.{column}" in query
        assert column in query.split(") values (")[0]


@pytest.mark.parametrize("balance", [Decimal("-1"), Decimal("NaN"), Decimal("Infinity"), "1"])
def test_raw_bill_rejects_invalid_balance(balance: object) -> None:
    with pytest.raises(ValueError, match="remaining_balance"):
        RawBill(
            provider_bill_id="1", provider_vendor_id="1", amount=Decimal("20"),
            currency="USD", bill_date=date(2026, 7, 1), status="open",
            remaining_balance=balance,
        )


@pytest.mark.parametrize("balance", [None, Decimal("0"), Decimal("12.3400")])
def test_synced_bill_projection(monkeypatch: pytest.MonkeyPatch, balance: Decimal | None) -> None:
    from procurepilot_api.modules.accounting.service import ConnectionService

    row = {
        "id": CONNECTION_ID, "vendor_name": "Supplier", "amount": Decimal("20.00"),
        "currency": "EUR", "bill_date": date(2026, 7, 1), "provider_status": "open",
        "matched": False, "due_date": date(2026, 7, 31),
        "remaining_balance_amount": balance,
        "remaining_balance_currency": "EUR" if balance is not None else None,
    }
    cursor = _Cursor(row)
    monkeypatch.setattr(cursor, "fetchall", lambda: [row], raising=False)

    @contextmanager
    def authenticated_db(_settings: object, member: object) -> Iterator[_Connection]:
        assert member.tenant_id == TENANT_ID
        yield _Connection(cursor)

    monkeypatch.setattr(
        "procurepilot_api.modules.accounting.service._authenticated_db", authenticated_db,
    )
    result = ConnectionService(settings=SimpleNamespace()).list_bills(
        SimpleNamespace(tenant_id=TENANT_ID)
    ).model_dump(mode="json")
    bill = result["items"][0]
    assert bill["amount"] == "20.00"
    assert bill["currency"] == "EUR"
    assert bill["due_date"] == "2026-07-31"
    assert bill["remaining_balance"] == (
        {"amount": str(balance), "currency": "EUR"} if balance is not None else None
    )
    for field in ("due_date", "remaining_balance_amount", "remaining_balance_currency"):
        assert f"b.{field}" in cursor.queries[0][0]


def test_synced_bill_old_payload_defaults() -> None:
    from procurepilot_api.modules.accounting.schemas import SyncedBill

    bill = SyncedBill(
        id=CONNECTION_ID, vendor_name="Supplier", amount="20", currency="EUR",
        bill_date=date(2026, 7, 1), provider_status="open", matched=False,
    )
    assert bill.due_date is None
    assert bill.remaining_balance is None


def test_stub_payment_evidence() -> None:
    from datetime import timedelta

    from procurepilot_api.modules.accounting.connector import StubConnector

    reference_date = date(2026, 9, 20)
    bills = StubConnector(reference_date=reference_date).list_bills(date.min)
    repeat_bills = StubConnector(reference_date=reference_date).list_bills(date.min)
    for bill in bills:
        assert bill.due_date == bill.bill_date + timedelta(days=30)
        assert bill.remaining_balance == (Decimal("0") if bill.status == "paid" else bill.amount)
    assert bills == repeat_bills
    assert StubConnector().list_bills(date.min) == StubConnector().list_bills(date.min)

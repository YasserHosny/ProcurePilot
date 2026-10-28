"""An offer priced from an authorised quotation expires when the quotation does (PPS-50).

Smart Compare showed quote-derived offers as open-ended because ``landed_cost.valid_to`` was
never written, even when the reviewer had confirmed the quotation's expiry date.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4
from zoneinfo import ZoneInfo

from procurepilot_api.deps import CurrentMember
from procurepilot_api.modules.landed_cost.service import LandedCostService
from procurepilot_api.modules.matching.resolution_service import _BulkReadClient

TENANT_ID = uuid4()
QUOTATION_ID = uuid4()
LINE_ID = uuid4()
PRODUCT_ID = uuid4()
CANONICAL_ID = uuid4()


class _Query:
    def __init__(self, client: _FakeClient, table: str) -> None:
        self._client = client
        self._table = table
        self._filters: dict[str, str] = {}
        self._insert: dict[str, object] | None = None
        self._columns: list[str] | None = None

    def select(self, columns: str = "*", *_args: object) -> _Query:
        # Honour the projection, as PostgREST does, so a caller that narrows the columns
        # really loses the ones it left out.
        self._columns = None if columns == "*" else columns.split(",")
        return self

    def eq(self, column: str, value: object) -> _Query:
        self._filters[column] = str(value)
        return self

    def order(self, *_args: object, **_kwargs: object) -> _Query:
        return self

    def limit(self, *_args: object) -> _Query:
        return self

    def in_(self, column: str, values: list[str]) -> _Query:
        self._filters[column] = str(values[0])
        return self

    def insert(self, payload: dict[str, object]) -> _Query:
        self._insert = payload
        return self

    def execute(self) -> SimpleNamespace:
        rows = self._client.tables.setdefault(self._table, [])
        if self._insert is not None:
            row = {"id": str(uuid4()), "created_at": None, **self._insert}
            rows.append(row)
            return SimpleNamespace(data=[row])
        matched = [
            row
            for row in rows
            if all(str(row.get(column)) == value for column, value in self._filters.items())
        ]
        if self._columns is not None:
            matched = [{c: row.get(c) for c in self._columns if c in row} for row in matched]
        return SimpleNamespace(data=matched)


class _FakeClient:
    def __init__(self, *, expiry_date: str | None, timezone: str = "Africa/Cairo") -> None:
        self.tables: dict[str, list[dict[str, object]]] = {
            "tenant": [{"id": str(TENANT_ID), "reporting_timezone": timezone}],
            "quotation": [{"id": str(QUOTATION_ID), "currency": "EGP", "expiry_date": expiry_date}],
            "quotation_line": [
                {
                    "id": str(LINE_ID),
                    "tenant_id": str(TENANT_ID),
                    "quotation_id": str(QUOTATION_ID),
                    "quantity": "8",
                    "unit_price_amount": "1540.00",
                    "unit_price_currency": None,
                    "vat_rate": None,
                }
            ],
            "current_match_decision": [
                {
                    "id": str(uuid4()),
                    "quotation_line_id": str(LINE_ID),
                    "matched_workspace_product_id": str(PRODUCT_ID),
                }
            ],
            "workspace_product": [
                {"id": str(PRODUCT_ID), "canonical_product_id": str(CANONICAL_ID)}
            ],
            "canonical_product": [{"id": str(CANONICAL_ID), "base_unit": "litre"}],
            "pack_definition": [{"workspace_product_id": str(PRODUCT_ID), "base_quantity": "18"}],
            "landed_cost": [],
        }

    def table(self, name: str) -> _Query:
        return _Query(self, name)


def _member() -> CurrentMember:
    return CurrentMember(
        user_id=uuid4(),
        tenant_id=TENANT_ID,
        membership_id=uuid4(),
        email="buyer@example.test",
        role="owner",
    )


def _compute(client: _FakeClient, *, via: object | None = None) -> dict[str, object]:
    LandedCostService(settings=SimpleNamespace()).compute_for_line_with_client(
        client=via or client, member=_member(), line_id=LINE_ID
    )
    (row,) = client.tables["landed_cost"]
    return row


def _parse(value: object) -> datetime:
    return datetime.fromisoformat(str(value))


def test_offer_from_quotation_with_expiry_is_valid_through_the_expiry_day() -> None:
    expiry = (datetime.now(ZoneInfo("Africa/Cairo")) + timedelta(days=10)).date()
    row = _compute(_FakeClient(expiry_date=expiry.isoformat()))

    assert row["valid_to"] is not None
    valid_to = _parse(row["valid_to"])
    # Valid for the whole expiry day in the tenant's timezone, and not a moment past it.
    local_end = valid_to.astimezone(ZoneInfo("Africa/Cairo"))
    assert local_end.date() == expiry
    assert (valid_to + timedelta(microseconds=1)).astimezone(
        ZoneInfo("Africa/Cairo")
    ).date() == expiry + timedelta(days=1)
    assert _parse(row["valid_from"]) <= valid_to


def test_offer_from_quotation_without_expiry_stays_open_ended() -> None:
    row = _compute(_FakeClient(expiry_date=None))

    assert row.get("valid_to") is None


def test_offer_from_quotation_already_expired_is_recorded_as_expired() -> None:
    expiry = (datetime.now(UTC) - timedelta(days=3)).date()
    row = _compute(_FakeClient(expiry_date=expiry.isoformat(), timezone="UTC"))

    valid_to = _parse(row["valid_to"])
    assert valid_to < datetime.now(UTC)
    # landed_cost_valid_to_after_valid_from: an already-lapsed quote must not violate it.
    assert _parse(row["valid_from"]) <= valid_to


def test_bulk_confirm_read_cache_carries_the_quotation_expiry() -> None:
    # Bulk confirm of exact-name matches computes landed cost through a read-through cache
    # with fixed projections; it must not drop the expiry date.
    expiry = (datetime.now(UTC) - timedelta(days=3)).date()
    client = _FakeClient(expiry_date=expiry.isoformat(), timezone="UTC")
    row = _compute(client, via=_BulkReadClient(client))

    assert row.get("valid_to") is not None
    assert _parse(row["valid_to"]) < datetime.now(UTC)

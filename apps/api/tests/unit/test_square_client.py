"""Unit tests for SquareClient and PosConnector (tasks T007, T008, T009).

Covers:
- OAuth2 authorization URL generation and parameter encoding
- OAuth2 authorization code exchange (success and error paths)
- OAuth2 refresh token exchange (success and expired/revoked failure paths)
- REST query execution and JSON parsing for Merchant account info, Orders, and Inventory
- Verification that no write methods exist on connector classes (FR-002, FR-004)
- StubConnector fixture behavior and date filtering covering all 5 required test cases

All HTTP requests are mocked via httpx.MockTransport with zero real network calls.
"""

from __future__ import annotations

import inspect
import json
from datetime import date, timedelta
from decimal import Decimal
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from pydantic import SecretStr

from procurepilot_api.modules.pos.connector import (
    OAuthTokens,
    PosAccountInfo,
    PosConnector,
    RawInventoryLevel,
    RawSalesTransaction,
    StubConnector,
)
from procurepilot_api.modules.pos.square_client import (
    SquareApiError,
    SquareAuthError,
    SquareClient,
)

TEST_APPLICATION_ID = "sandbox-sq0idb-test-app-xyz"
TEST_APPLICATION_SECRET = "sandbox-sq0csb-test-secret-123"
TEST_REDIRECT_URI = "https://app.procurepilot.com/api/v1/pos/connect/callback"
TEST_ACCESS_TOKEN = "test-mock-square-access-token"


def _make_client(
    transport: httpx.BaseTransport,
    access_token: str | None = TEST_ACCESS_TOKEN,
) -> SquareClient:
    http_client = httpx.Client(transport=transport)
    return SquareClient(
        application_id=TEST_APPLICATION_ID,
        application_secret=SecretStr(TEST_APPLICATION_SECRET),
        redirect_uri=TEST_REDIRECT_URI,
        environment="sandbox",
        access_token=access_token,
        http_client=http_client,
    )


# --- OAuth2 Authorization URL Tests -----------------------------------------


def test_build_authorization_url() -> None:
    client = _make_client(httpx.MockTransport(lambda _: httpx.Response(200)))
    state = "csrf-protection-state-random-uuid-pos-9876"

    url = client.build_authorization_url(state=state)

    parsed = urlparse(url)
    assert parsed.scheme == "https"
    assert parsed.netloc == "connect.squareupsandbox.com"
    assert parsed.path == "/oauth2/authorize"

    params = parse_qs(parsed.query)
    assert params["client_id"] == [TEST_APPLICATION_ID]
    assert params["response_type"] == ["code"]
    assert params["redirect_uri"] == [TEST_REDIRECT_URI]
    assert params["state"] == [state]
    assert "ORDERS_READ" in params["scope"][0]
    assert "INVENTORY_READ" in params["scope"][0]


def test_build_authorization_url_missing_config() -> None:
    client_missing_id = SquareClient(
        application_id=None,
        redirect_uri=TEST_REDIRECT_URI,
        http_client=httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200))),
    )
    with pytest.raises(SquareAuthError, match="SQUARE_APPLICATION_ID"):
        client_missing_id.build_authorization_url("state")

    client_missing_uri = SquareClient(
        application_id=TEST_APPLICATION_ID,
        redirect_uri=None,
        http_client=httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200))),
    )
    with pytest.raises(SquareAuthError, match="SQUARE_REDIRECT_URI"):
        client_missing_uri.build_authorization_url("state")


# --- OAuth2 Token Exchange Tests --------------------------------------------


def test_exchange_code_for_tokens_success() -> None:
    captured_requests: list[httpx.Request] = []

    def handle_request(request: httpx.Request) -> httpx.Response:
        captured_requests.append(request)
        assert str(request.url) == "https://connect.squareupsandbox.com/oauth2/token"
        assert request.headers["Accept"] == "application/json"
        assert request.headers["Content-Type"] == "application/json"
        body = json.loads(request.content.decode("utf-8"))
        assert body["grant_type"] == "authorization_code"
        assert body["code"] == "valid-square-auth-code-123"
        assert body["redirect_uri"] == TEST_REDIRECT_URI
        assert body["client_id"] == TEST_APPLICATION_ID
        assert body["client_secret"] == TEST_APPLICATION_SECRET

        return httpx.Response(
            200,
            json={
                "access_token": "fresh-square-access-token-001",
                "refresh_token": "fresh-square-refresh-token-001",
                "expires_at": "2026-10-18T00:00:00Z",
                "merchant_id": "test-merchant-id-abc",
                "token_type": "bearer",
            },
        )

    client = _make_client(httpx.MockTransport(handle_request))
    tokens = client.exchange_code_for_tokens(code="valid-square-auth-code-123")

    assert isinstance(tokens, OAuthTokens)
    assert tokens.access_token == "fresh-square-access-token-001"
    assert tokens.refresh_token == "fresh-square-refresh-token-001"
    assert tokens.merchant_id == "test-merchant-id-abc"
    assert tokens.token_type == "bearer"
    assert client.access_token == "fresh-square-access-token-001"
    assert len(captured_requests) == 1


def test_exchange_code_for_tokens_error() -> None:
    def handle_request(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={
                "errors": [
                    {
                        "category": "AUTHENTICATION_ERROR",
                        "code": "INVALID_GRANT",
                        "detail": "Authorization code expired or invalid",
                    }
                ]
            },
        )

    client = _make_client(httpx.MockTransport(handle_request))

    with pytest.raises(SquareAuthError) as exc_info:
        client.exchange_code_for_tokens(code="expired-code")

    err = exc_info.value
    assert err.status_code == 400
    assert err.error_code == "INVALID_GRANT"
    assert "Authorization code expired" in str(err)


# --- OAuth2 Token Refresh Tests ---------------------------------------------


def test_refresh_access_token_success() -> None:
    def handle_request(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://connect.squareupsandbox.com/oauth2/token"
        body = json.loads(request.content.decode("utf-8"))
        assert body["grant_type"] == "refresh_token"
        assert body["refresh_token"] == "existing-square-refresh-token-999"

        return httpx.Response(
            200,
            json={
                "access_token": "refreshed-square-access-token-002",
                "refresh_token": "new-square-refresh-token-002",
                "merchant_id": "test-merchant-id-abc",
                "token_type": "bearer",
            },
        )

    client = _make_client(httpx.MockTransport(handle_request))
    tokens = client.refresh_access_token(refresh_token="existing-square-refresh-token-999")

    assert tokens.access_token == "refreshed-square-access-token-002"
    assert tokens.refresh_token == "new-square-refresh-token-002"
    assert client.access_token == "refreshed-square-access-token-002"


def test_refresh_access_token_failed_expired_surfaces_actionable_error() -> None:
    """When a refresh token has expired or been revoked, refresh fails with 401.

    ConnectionService / SyncService catches SquareAuthError to transition pos_connection
    to 'needs_reauth' (FR-008, spec Scenario 1.4).
    """

    def handle_request(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401,
            json={
                "errors": [
                    {
                        "category": "AUTHENTICATION_ERROR",
                        "code": "UNAUTHORIZED",
                        "detail": "The refresh token is invalid or expired. Re-auth required.",
                    }
                ]
            },
        )

    client = _make_client(httpx.MockTransport(handle_request))

    with pytest.raises(SquareAuthError) as exc_info:
        client.refresh_access_token(refresh_token="expired-refresh-token")

    err = exc_info.value
    assert err.status_code == 401
    assert err.error_code == "UNAUTHORIZED"
    assert "Re-auth required" in str(err)


# --- REST Response Parsing: Account / Merchant Info -------------------------


def test_get_account_info_query_and_parsing() -> None:
    captured_requests: list[httpx.Request] = []

    def handle_request(request: httpx.Request) -> httpx.Response:
        captured_requests.append(request)
        assert str(request.url) == "https://connect.squareupsandbox.com/v2/merchants/me"
        assert request.headers["Authorization"] == f"Bearer {TEST_ACCESS_TOKEN}"
        assert request.headers["Accept"] == "application/json"

        return httpx.Response(
            200,
            json={
                "merchant": {
                    "id": "MERCH_SQUARE_789",
                    "business_name": "ProcurePilot Demo Merchant",
                    "country": "US",
                    "status": "ACTIVE",
                }
            },
        )

    client = _make_client(httpx.MockTransport(handle_request))
    account_info = client.get_account_info()

    assert isinstance(account_info, PosAccountInfo)
    assert account_info.account_id == "MERCH_SQUARE_789"
    assert account_info.account_name == "ProcurePilot Demo Merchant"
    assert account_info.display_name == "ProcurePilot Demo Merchant"
    assert account_info.external_account_id == "MERCH_SQUARE_789"
    assert account_info.external_account_name == "ProcurePilot Demo Merchant"
    assert len(captured_requests) == 1


# --- REST Response Parsing: Sales Transactions (Orders API) ----------------


def test_list_sales_transactions_query_and_parsing() -> None:
    captured_requests: list[httpx.Request] = []

    def handle_request(request: httpx.Request) -> httpx.Response:
        captured_requests.append(request)
        assert str(request.url) == "https://connect.squareupsandbox.com/v2/orders/search"
        assert request.headers["Authorization"] == f"Bearer {TEST_ACCESS_TOKEN}"
        assert request.headers["Accept"] == "application/json"

        body = json.loads(request.content.decode("utf-8"))
        assert "filter" in body["query"]
        assert body["query"]["filter"]["state_filter"]["states"] == ["COMPLETED"]

        return httpx.Response(
            200,
            json={
                "orders": [
                    {
                        "id": "sq-order-001",
                        "created_at": "2026-09-01T14:30:00Z",
                        "state": "COMPLETED",
                        "line_items": [
                            {
                                "uid": "sq-li-001",
                                "name": "Organic Whole Milk 1 Gallon",
                                "quantity": "4",
                                "catalog_object_id": "catalog-item-milk-1",
                            },
                            {
                                "uid": "sq-li-002",
                                "name": "Cold Brew Concentrate 1L Bottle",
                                "quantity": "2",
                                "catalog_object_id": "catalog-item-coldbrew-1",
                            },
                        ],
                    },
                    {
                        "id": "sq-order-002",
                        "created_at": "2026-09-05T10:15:00Z",
                        "state": "COMPLETED",
                        "line_items": [
                            {
                                "uid": "sq-li-003",
                                "name": "Organic Whole Milk 1 Gallon",
                                "quantity": "6",
                                "catalog_object_id": "catalog-item-milk-1",
                            }
                        ],
                    },
                ]
            },
        )

    client = _make_client(httpx.MockTransport(handle_request))
    transactions = client.list_sales_transactions(since=date(2026, 8, 20))

    assert len(transactions) == 3
    assert all(isinstance(t, RawSalesTransaction) for t in transactions)

    assert transactions[0].transaction_id == "sq-li-001"
    assert transactions[0].external_item_id == "catalog-item-milk-1"
    assert transactions[0].item_name == "Organic Whole Milk 1 Gallon"
    assert transactions[0].quantity == Decimal("4")
    assert transactions[0].transaction_date == date(2026, 9, 1)

    assert transactions[1].transaction_id == "sq-li-002"
    assert transactions[1].external_item_id == "catalog-item-coldbrew-1"
    assert transactions[1].quantity == Decimal("2")

    assert transactions[2].transaction_id == "sq-li-003"
    assert transactions[2].external_item_id == "catalog-item-milk-1"
    assert transactions[2].quantity == Decimal("6")
    assert transactions[2].transaction_date == date(2026, 9, 5)


# --- REST Response Parsing: Inventory Levels --------------------------------


def test_list_inventory_levels_query_and_parsing() -> None:
    captured_requests: list[httpx.Request] = []

    def handle_request(request: httpx.Request) -> httpx.Response:
        captured_requests.append(request)
        assert str(request.url) == "https://connect.squareupsandbox.com/v2/inventory/counts"
        assert request.headers["Authorization"] == f"Bearer {TEST_ACCESS_TOKEN}"

        return httpx.Response(
            200,
            json={
                "counts": [
                    {
                        "catalog_object_id": "catalog-item-milk-1",
                        "catalog_object_type": "ITEM_VARIATION",
                        "state": "IN_STOCK",
                        "quantity": "45.0",
                        "item_name": "Organic Whole Milk 1 Gallon",
                    },
                    {
                        "catalog_object_id": "catalog-item-blender-1",
                        "catalog_object_type": "ITEM_VARIATION",
                        "state": "IN_STOCK",
                        "quantity": "12",
                        "item_name": "Stainless Steel Immersion Blender",
                    },
                    {
                        "catalog_object_id": "catalog-item-notracking-1",
                        "catalog_object_type": "ITEM_VARIATION",
                        "quantity": None,
                        "item_name": "Service Item No Inventory",
                    },
                ]
            },
        )

    client = _make_client(httpx.MockTransport(handle_request))
    levels = client.list_inventory_levels()

    assert len(levels) == 3
    assert all(isinstance(level, RawInventoryLevel) for level in levels)

    assert levels[0].external_item_id == "catalog-item-milk-1"
    assert levels[0].stock_on_hand == Decimal("45.0")
    assert levels[0].item_name == "Organic Whole Milk 1 Gallon"

    assert levels[1].external_item_id == "catalog-item-blender-1"
    assert levels[1].stock_on_hand == Decimal("12")

    # Item with null/untracked quantity
    assert levels[2].external_item_id == "catalog-item-notracking-1"
    assert levels[2].stock_on_hand is None


# --- REST Error Handling ----------------------------------------------------


def test_query_unauthorized_raises_square_auth_error() -> None:
    def handle_request(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401,
            json={
                "errors": [
                    {
                        "category": "AUTHENTICATION_ERROR",
                        "code": "UNAUTHORIZED",
                        "detail": "The access token has expired.",
                    }
                ]
            },
        )

    client = _make_client(httpx.MockTransport(handle_request))
    with pytest.raises(SquareAuthError) as exc_info:
        client.list_sales_transactions(since=date(2026, 1, 1))

    assert exc_info.value.status_code == 401
    assert exc_info.value.error_code == "UNAUTHORIZED"


def test_query_server_error_raises_square_api_error() -> None:
    def handle_request(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="Internal Server Error")

    client = _make_client(httpx.MockTransport(handle_request))
    with pytest.raises(SquareApiError) as exc_info:
        client.list_inventory_levels()

    assert exc_info.value.status_code == 500


# --- Read-Only Enforcement (FR-002, FR-004) ---------------------------------


def test_read_only_protocol_and_classes_enforce_no_write_methods() -> None:
    """Enforce read-only constraint at type/reflection level: no write methods exist."""
    forbidden_prefixes = ("create", "update", "delete", "post", "write", "put", "patch")

    for cls in (PosConnector, StubConnector, SquareClient):
        public_methods = [
            name
            for name, _ in inspect.getmembers(cls, predicate=inspect.isfunction)
            if not name.startswith("_")
        ]
        for method_name in public_methods:
            for prefix in forbidden_prefixes:
                assert not method_name.startswith(prefix), (
                    f"Class {cls.__name__} violates read-only rule by exposing "
                    f"write method '{method_name}'"
                )


# --- StubConnector Tests ----------------------------------------------------


def test_stub_connector_satisfies_protocol_and_covers_all_fixture_cases() -> None:
    client = _make_client(httpx.MockTransport(lambda _: httpx.Response(200)))
    stub = StubConnector()

    # Protocol checks
    assert isinstance(client, PosConnector)
    assert isinstance(stub, PosConnector)

    # Account info
    account = stub.get_account_info()
    assert isinstance(account, PosAccountInfo)
    assert account.account_id.startswith("stub-merchant")
    assert account.account_name != ""

    # Inventory levels covering fixture cases
    levels = stub.list_inventory_levels()
    assert len(levels) == 5
    assert all(isinstance(level, RawInventoryLevel) for level in levels)

    levels_by_id = {level.external_item_id: level for level in levels}

    # Case 1: Item with both stock and sales history
    assert "stub-item-001" in levels_by_id
    assert levels_by_id["stub-item-001"].stock_on_hand is not None
    assert levels_by_id["stub-item-001"].stock_on_hand > Decimal("0")

    # Case 2: Item with stock but zero sales
    assert "stub-item-002" in levels_by_id
    assert levels_by_id["stub-item-002"].stock_on_hand is not None

    # Case 3: Item with sales but NO inventory tracking (stock is None)
    assert "stub-item-003" in levels_by_id
    assert levels_by_id["stub-item-003"].stock_on_hand is None

    # Case 4: Ambiguous product name
    assert "stub-item-004" in levels_by_id

    # Case 5: Fewer days of history than 30-day window
    assert "stub-item-005" in levels_by_id

    # Sales transactions covering fixture cases
    today = date.today()
    all_txns = stub.list_sales_transactions(since=today - timedelta(days=35))
    txns_by_item = {}
    for t in all_txns:
        txns_by_item.setdefault(t.external_item_id, []).append(t)

    # Case 1: multiple days of sales history
    assert len(txns_by_item.get("stub-item-001", [])) >= 3

    # Case 2: zero sales transactions
    assert "stub-item-002" not in txns_by_item

    # Case 3: sales transactions exist despite stock being None
    assert len(txns_by_item.get("stub-item-003", [])) >= 2

    # Case 4: sales transactions exist
    assert len(txns_by_item.get("stub-item-004", [])) >= 1

    # Case 5: transaction history only within a narrow window (<30 days)
    case_5_txns = txns_by_item.get("stub-item-005", [])
    assert len(case_5_txns) >= 2
    for t in case_5_txns:
        assert t.transaction_date >= today - timedelta(days=5)

    # Date filtering on list_sales_transactions
    future_txns = stub.list_sales_transactions(since=today + timedelta(days=30))
    assert len(future_txns) == 0

"""Unit tests for QuickBooksClient and AccountingConnector (tasks T009, T010, T011).

Covers:
- OAuth2 authorization URL generation and parameter encoding
- OAuth2 authorization code exchange (success and error paths)
- OAuth2 refresh token exchange (success and expired/revoked failure paths)
- REST query execution and JSON parsing for Bill, Vendor, and CompanyInfo
- Verification that no write methods exist on connector classes (FR-013)
- StubConnector fixture behavior and date filtering

All HTTP requests are mocked via httpx.MockTransport with zero real network calls.
"""

from __future__ import annotations

import inspect
from datetime import date
from decimal import Decimal
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from pydantic import SecretStr

from procurepilot_api.modules.accounting.connector import (
    AccountingConnector,
    CompanyInfo,
    RawBill,
    RawVendor,
    StubConnector,
)
from procurepilot_api.modules.accounting.quickbooks_client import (
    OAuthTokens,
    QuickBooksApiError,
    QuickBooksAuthError,
    QuickBooksClient,
)

TEST_CLIENT_ID = "test-client-id-xyz"
TEST_CLIENT_SECRET = "test-client-secret-123"
TEST_REDIRECT_URI = "https://app.procurepilot.com/api/v1/accounting/connect/callback"
TEST_REALM_ID = "9130350444555666"
TEST_ACCESS_TOKEN = "test-mock-access-token-abc"


def _make_client(
    transport: httpx.BaseTransport,
    realm_id: str | None = TEST_REALM_ID,
    access_token: str | None = TEST_ACCESS_TOKEN,
) -> QuickBooksClient:
    http_client = httpx.Client(transport=transport)
    return QuickBooksClient(
        client_id=TEST_CLIENT_ID,
        client_secret=SecretStr(TEST_CLIENT_SECRET),
        redirect_uri=TEST_REDIRECT_URI,
        environment="sandbox",
        realm_id=realm_id,
        access_token=access_token,
        http_client=http_client,
    )


# --- OAuth2 Authorization URL Tests -----------------------------------------


def test_build_authorization_url() -> None:
    client = _make_client(httpx.MockTransport(lambda _: httpx.Response(200)))
    state = "csrf-protection-state-random-uuid-9876"

    url = client.build_authorization_url(state=state)

    parsed = urlparse(url)
    assert parsed.scheme == "https"
    assert parsed.netloc == "appcenter.intuit.com"
    assert parsed.path == "/connect/oauth2"

    params = parse_qs(parsed.query)
    assert params["client_id"] == [TEST_CLIENT_ID]
    assert params["response_type"] == ["code"]
    assert params["scope"] == ["com.intuit.quickbooks.accounting"]
    assert params["redirect_uri"] == [TEST_REDIRECT_URI]
    assert params["state"] == [state]


def test_build_authorization_url_missing_config() -> None:
    client_missing_id = QuickBooksClient(
        client_id=None,
        redirect_uri=TEST_REDIRECT_URI,
        http_client=httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200))),
    )
    with pytest.raises(QuickBooksAuthError, match="QUICKBOOKS_CLIENT_ID"):
        client_missing_id.build_authorization_url("state")

    client_missing_uri = QuickBooksClient(
        client_id=TEST_CLIENT_ID,
        redirect_uri=None,
        http_client=httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200))),
    )
    with pytest.raises(QuickBooksAuthError, match="QUICKBOOKS_REDIRECT_URI"):
        client_missing_uri.build_authorization_url("state")


# --- OAuth2 Token Exchange Tests --------------------------------------------


def test_exchange_code_for_tokens_success() -> None:
    captured_requests: list[httpx.Request] = []

    def handle_request(request: httpx.Request) -> httpx.Response:
        captured_requests.append(request)
        assert request.url == "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"
        assert request.headers["Accept"] == "application/json"
        assert request.headers["Authorization"].startswith("Basic ")
        body = parse_qs(request.content.decode("utf-8"))
        assert body["grant_type"] == ["authorization_code"]
        assert body["code"] == ["valid-auth-code-123"]
        assert body["redirect_uri"] == [TEST_REDIRECT_URI]

        return httpx.Response(
            200,
            json={
                "access_token": "fresh-access-token-001",
                "refresh_token": "fresh-refresh-token-001",
                "expires_in": 3600,
                "x_refresh_token_expires_in": 8726400,
                "token_type": "bearer",
            },
        )

    client = _make_client(httpx.MockTransport(handle_request))
    tokens = client.exchange_code_for_tokens(
        code="valid-auth-code-123",
        realm_id="new-realm-555",
    )

    assert isinstance(tokens, OAuthTokens)
    assert tokens.access_token == "fresh-access-token-001"
    assert tokens.refresh_token == "fresh-refresh-token-001"
    assert tokens.expires_in == 3600
    assert tokens.token_type == "bearer"
    assert client.access_token == "fresh-access-token-001"
    assert client.realm_id == "new-realm-555"
    assert len(captured_requests) == 1


def test_exchange_code_for_tokens_error() -> None:
    def handle_request(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={
                "error": "invalid_grant",
                "error_description": "Authorization code expired or invalid",
            },
        )

    client = _make_client(httpx.MockTransport(handle_request))

    with pytest.raises(QuickBooksAuthError) as exc_info:
        client.exchange_code_for_tokens(code="expired-code")

    err = exc_info.value
    assert err.status_code == 400
    assert err.error_code == "invalid_grant"
    assert "invalid_grant" in str(err)
    assert "Authorization code expired" in str(err)


# --- OAuth2 Token Refresh Tests ---------------------------------------------


def test_refresh_access_token_success() -> None:
    def handle_request(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"
        body = parse_qs(request.content.decode("utf-8"))
        assert body["grant_type"] == ["refresh_token"]
        assert body["refresh_token"] == ["existing-refresh-token-999"]

        return httpx.Response(
            200,
            json={
                "access_token": "refreshed-access-token-002",
                "refresh_token": "new-refresh-token-002",
                "expires_in": 3600,
                "token_type": "bearer",
            },
        )

    client = _make_client(httpx.MockTransport(handle_request))
    tokens = client.refresh_access_token(refresh_token="existing-refresh-token-999")

    assert tokens.access_token == "refreshed-access-token-002"
    assert tokens.refresh_token == "new-refresh-token-002"
    assert client.access_token == "refreshed-access-token-002"


def test_refresh_access_token_failed_expired_surfaces_actionable_error() -> None:
    """When a refresh token has expired (100 days) or been revoked, refresh fails.

    ConnectionService / SyncService must be able to catch QuickBooksAuthError and inspect
    it to transition the accounting_connection to 'needs_reauth' (FR-002, Scenario 1.4).
    """

    def handle_request(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={
                "error": "invalid_grant",
                "error_description": "Refresh token is expired or revoked. Re-auth required.",
            },
        )

    client = _make_client(httpx.MockTransport(handle_request))

    with pytest.raises(QuickBooksAuthError) as exc_info:
        client.refresh_access_token(refresh_token="expired-refresh-token")

    err = exc_info.value
    assert err.status_code == 400
    assert err.error_code == "invalid_grant"
    assert "invalid_grant" in str(err)
    assert "Re-auth required" in str(err)


# --- REST Response Parsing: CompanyInfo -------------------------------------


def test_company_info_query_and_parsing() -> None:
    captured_requests: list[httpx.Request] = []

    def handle_request(request: httpx.Request) -> httpx.Response:
        captured_requests.append(request)
        expected_url = f"https://sandbox-quickbooks.api.intuit.com/v3/company/{TEST_REALM_ID}/query"
        assert str(request.url).split("?")[0] == expected_url
        assert request.headers["Authorization"] == f"Bearer {TEST_ACCESS_TOKEN}"
        assert request.headers["Accept"] == "application/json"

        params = parse_qs(request.url.query.decode("utf-8"))
        assert params["query"] == ["SELECT * FROM CompanyInfo"]

        # Realistic QuickBooks CompanyInfo JSON payload
        return httpx.Response(
            200,
            json={
                "QueryResponse": {
                    "CompanyInfo": [
                        {
                            "Id": "1",
                            "CompanyName": "Acme Procurement Corp",
                            "LegalName": "Acme Procurement Corporation LLC",
                            "CompanyAddr": {
                                "Id": "1",
                                "Line1": "2500 Technology Dr",
                                "City": "San Jose",
                                "CountrySubDivisionCode": "CA",
                                "PostalCode": "95110",
                            },
                            "CustomerCommunicationEmailAddr": {
                                "Address": "admin@acmeprocurement.com"
                            },
                            "FiscalYearStartMonth": "January",
                            "domain": "QBO",
                        }
                    ],
                    "startPosition": 1,
                    "maxResults": 1,
                },
                "time": "2026-09-18T00:00:00.000Z",
            },
        )

    client = _make_client(httpx.MockTransport(handle_request))
    company = client.company_info()

    assert isinstance(company, CompanyInfo)
    assert company.realm_id == TEST_REALM_ID
    assert company.company_name == "Acme Procurement Corp"
    assert company.display_name == "Acme Procurement Corp"
    assert len(captured_requests) == 1


# --- REST Response Parsing: Vendor ------------------------------------------


def test_list_vendors_query_and_parsing() -> None:
    def handle_request(request: httpx.Request) -> httpx.Response:
        params = parse_qs(request.url.query.decode("utf-8"))
        assert params["query"] == ["SELECT * FROM Vendor"]

        # Realistic QuickBooks Vendor JSON payload
        return httpx.Response(
            200,
            json={
                "QueryResponse": {
                    "Vendor": [
                        {
                            "Id": "65",
                            "SyncToken": "0",
                            "DisplayName": "Staples Office Solutions",
                            "PrintOnCheckName": "Staples Office Solutions",
                            "Active": True,
                            "PrimaryEmailAddr": {"Address": "invoicing@staples.com"},
                            "BillAddr": {
                                "Line1": "500 Staples Dr",
                                "City": "Framingham",
                                "PostalCode": "01702",
                            },
                        },
                        {
                            "Id": "66",
                            "SyncToken": "2",
                            "DisplayName": "Grainger Industrial",
                            "CompanyName": "W.W. Grainger Inc",
                            "Active": True,
                        },
                    ],
                    "startPosition": 1,
                    "maxResults": 2,
                },
                "time": "2026-09-18T00:00:00.000Z",
            },
        )

    client = _make_client(httpx.MockTransport(handle_request))
    vendors = client.list_vendors()

    assert len(vendors) == 2
    assert all(isinstance(v, RawVendor) for v in vendors)

    assert vendors[0].provider_vendor_id == "65"
    assert vendors[0].display_name == "Staples Office Solutions"
    assert vendors[0].provider_id == "65"

    assert vendors[1].provider_vendor_id == "66"
    assert vendors[1].display_name == "Grainger Industrial"


# --- REST Response Parsing: Bill --------------------------------------------


def test_list_bills_query_and_parsing() -> None:
    captured_requests: list[httpx.Request] = []

    def handle_request(request: httpx.Request) -> httpx.Response:
        captured_requests.append(request)
        params = parse_qs(request.url.query.decode("utf-8"))
        assert params["query"] == ["SELECT * FROM Bill WHERE TxnDate >= '2026-06-20'"]

        # Realistic QuickBooks Bill JSON payload with open, paid, and void bills
        return httpx.Response(
            200,
            json={
                "QueryResponse": {
                    "Bill": [
                        {
                            "Id": "901",
                            "VendorRef": {
                                "value": "65",
                                "name": "Staples Office Solutions",
                            },
                            "TotalAmt": 1845.50,
                            "CurrencyRef": {
                                "value": "USD",
                                "name": "United States Dollar",
                            },
                            "TxnDate": "2026-07-01",
                            "DueDate": "2026-07-31",
                            "Balance": 1845.50,
                        },
                        {
                            "Id": "902",
                            "VendorRef": {
                                "value": "66",
                                "name": "Grainger Industrial",
                            },
                            "TotalAmt": 6200.00,
                            "CurrencyRef": {
                                "value": "USD",
                            },
                            "TxnDate": "2026-07-15",
                            "DueDate": "2026-08-15",
                            "Balance": 0,
                        },
                        {
                            "Id": "903",
                            "VendorRef": {
                                "value": "65",
                                "name": "Staples Office Solutions",
                            },
                            "TotalAmt": 250.00,
                            "CurrencyRef": {
                                "value": "USD",
                            },
                            "TxnDate": "2026-08-01",
                            "Balance": 0,
                            "Voided": True,
                        },
                    ],
                    "startPosition": 1,
                    "maxResults": 3,
                },
                "time": "2026-09-18T00:00:00.000Z",
            },
        )

    client = _make_client(httpx.MockTransport(handle_request))
    bills = client.list_bills(since=date(2026, 6, 20))

    assert len(bills) == 3
    assert all(isinstance(b, RawBill) for b in bills)

    # Bill 1: Open balance
    assert bills[0].provider_bill_id == "901"
    assert bills[0].provider_vendor_id == "65"
    assert bills[0].amount == Decimal("1845.50")
    assert bills[0].currency == "USD"
    assert bills[0].bill_date == date(2026, 7, 1)
    assert bills[0].status == "open"
    assert bills[0].provider_status == "open"
    assert bills[0].provider_id == "901"

    # Bill 2: Paid (Balance == 0)
    assert bills[1].provider_bill_id == "902"
    assert bills[1].provider_vendor_id == "66"
    assert bills[1].amount == Decimal("6200.00")
    assert bills[1].currency == "USD"
    assert bills[1].bill_date == date(2026, 7, 15)
    assert bills[1].status == "paid"

    # Bill 3: Voided
    assert bills[2].provider_bill_id == "903"
    assert bills[2].provider_vendor_id == "65"
    assert bills[2].amount == Decimal("250.00")
    assert bills[2].currency == "USD"
    assert bills[2].bill_date == date(2026, 8, 1)
    assert bills[2].status == "void"


# --- REST Error Handling ----------------------------------------------------


def test_query_unauthorized_raises_quickbooks_auth_error() -> None:
    def handle_request(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401,
            json={
                "fault": {
                    "error": [{"message": "Token expired", "detail": "Unauthorized"}],
                    "type": "AUTHENTICATION",
                }
            },
        )

    client = _make_client(httpx.MockTransport(handle_request))
    with pytest.raises(QuickBooksAuthError) as exc_info:
        client.list_bills(since=date(2026, 1, 1))

    assert exc_info.value.status_code == 401


def test_query_server_error_raises_quickbooks_api_error() -> None:
    def handle_request(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="Internal Server Error")

    client = _make_client(httpx.MockTransport(handle_request))
    with pytest.raises(QuickBooksApiError) as exc_info:
        client.list_vendors()

    assert exc_info.value.status_code == 500


# --- Read-Only Enforcement (FR-013) -----------------------------------------


def test_read_only_protocol_and_classes_enforce_no_write_methods() -> None:
    """Enforce FR-013 at type/reflection level: no write methods on connector classes."""
    forbidden_prefixes = ("create", "update", "delete", "post", "write", "put", "patch")

    for cls in (AccountingConnector, StubConnector, QuickBooksClient):
        public_methods = [
            name
            for name, member in inspect.getmembers(cls, predicate=inspect.isfunction)
            if not name.startswith("_")
        ]
        for method_name in public_methods:
            for prefix in forbidden_prefixes:
                assert not method_name.startswith(prefix), (
                    f"Class {cls.__name__} violates FR-013 by exposing write method '{method_name}'"
                )


# --- StubConnector Tests ----------------------------------------------------


def test_stub_connector_satisfies_protocol_and_filters_bills() -> None:
    client = _make_client(httpx.MockTransport(lambda _: httpx.Response(200)))
    stub = StubConnector()

    # Protocol checks
    assert isinstance(client, AccountingConnector)
    assert isinstance(stub, AccountingConnector)

    # Company info
    company = stub.company_info()
    assert isinstance(company, CompanyInfo)
    assert company.realm_id.startswith("stub-realm")
    assert company.company_name != ""

    # Vendors
    vendors = stub.list_vendors()
    assert len(vendors) >= 2
    assert all(isinstance(v, RawVendor) for v in vendors)

    # Bills - test date filtering
    all_bills = stub.list_bills(since=date(2000, 1, 1))
    assert len(all_bills) >= 2
    assert all(isinstance(b, RawBill) for b in all_bills)

    future_bills = stub.list_bills(since=date(2099, 1, 1))
    assert len(future_bills) == 0

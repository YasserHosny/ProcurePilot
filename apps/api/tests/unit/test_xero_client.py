"""Focused unit tests for the read-only Xero accounting connector."""

from __future__ import annotations

import inspect
from datetime import date
from decimal import Decimal
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from pydantic import SecretStr

from procurepilot_api.modules.accounting.connector import AccountingConnector
from procurepilot_api.modules.accounting.xero_client import (
    XeroApiError,
    XeroAuthError,
    XeroClient,
)

CLIENT_ID = "xero-test-client"
CLIENT_SECRET = "xero-test-secret"
REDIRECT_URI = "https://app.procurepilot.test/accounting/callback"
TENANT_ID = "tenant-123"
ACCESS_TOKEN = "access-token"


def _client(handler: httpx.BaseTransport, *, tenant_id: str | None = TENANT_ID) -> XeroClient:
    return XeroClient(
        client_id=CLIENT_ID,
        client_secret=SecretStr(CLIENT_SECRET),
        redirect_uri=REDIRECT_URI,
        realm_id=tenant_id,
        access_token=ACCESS_TOKEN,
        http_client=httpx.Client(transport=handler),
    )


def test_build_authorization_url() -> None:
    client = _client(httpx.MockTransport(lambda _: httpx.Response(200)))
    parsed = urlparse(client.build_authorization_url("csrf state"))
    params = parse_qs(parsed.query)

    assert parsed.netloc == "login.xero.com"
    assert parsed.path == "/identity/connect/authorize"
    assert params["client_id"] == [CLIENT_ID]
    assert params["response_type"] == ["code"]
    assert params["redirect_uri"] == [REDIRECT_URI]
    assert params["state"] == ["csrf state"]
    assert "accounting.invoices.read" in params["scope"][0]
    assert "accounting.contacts.read" in params["scope"][0]
    assert "accounting.transactions" not in params["scope"][0]
    assert " accounting.contacts " not in f" {params['scope'][0]} "
    assert " accounting.settings " not in f" {params['scope'][0]} "
    assert "offline_access" in params["scope"][0]


def test_exchange_and_refresh_tokens() -> None:
    requests: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        body = parse_qs(request.content.decode())
        if body["grant_type"] == ["authorization_code"]:
            assert body["code"] == ["auth-code"]
            assert body["redirect_uri"] == [REDIRECT_URI]
            return httpx.Response(
                200,
                json={
                    "access_token": "new-access",
                    "refresh_token": "new-refresh",
                    "expires_in": 1800,
                    "token_type": "Bearer",
                },
            )
        assert body["grant_type"] == ["refresh_token"]
        assert body["refresh_token"] == ["new-refresh"]
        return httpx.Response(
            200, json={"access_token": "refreshed-access", "expires_in": 1800}
        )

    client = _client(httpx.MockTransport(handle))
    exchanged = client.exchange_code_for_tokens("auth-code")
    refreshed = client.refresh_access_token(exchanged.refresh_token)

    assert exchanged.access_token == "new-access"
    assert exchanged.refresh_token == "new-refresh"
    assert exchanged.expires_in == 1800
    assert refreshed.access_token == "refreshed-access"
    assert refreshed.refresh_token == "new-refresh"
    assert client.access_token == "refreshed-access"
    assert len(requests) == 2


def test_company_info_parsing_selects_connected_tenant() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://api.xero.com/connections"
        assert request.headers["Authorization"] == f"Bearer {ACCESS_TOKEN}"
        return httpx.Response(
            200,
            json=[
                {"tenantId": "other", "tenantName": "Other Co"},
                {"tenantId": TENANT_ID, "tenantName": "Acme Supplies"},
            ],
        )

    company = _client(httpx.MockTransport(handle)).company_info()
    assert company.realm_id == TENANT_ID
    assert company.company_name == "Acme Supplies"


def test_company_info_rejects_missing_configured_tenant() -> None:
    client = _client(
        httpx.MockTransport(
            lambda _: httpx.Response(200, json=[{"tenantId": "other", "tenantName": "Other Co"}])
        )
    )
    with pytest.raises(XeroApiError, match="tenant-123.*not found"):
        client.company_info()


def test_company_info_requires_explicit_tenant_when_multiple_are_connected() -> None:
    client = _client(
        httpx.MockTransport(
            lambda _: httpx.Response(
                200,
                json=[
                    {"tenantId": "one", "tenantName": "One Co"},
                    {"tenantId": "two", "tenantName": "Two Co"},
                ],
            )
        ),
        tenant_id=None,
    )
    with pytest.raises(XeroApiError, match="explicit tenant_id"):
        client.company_info()


@pytest.mark.parametrize("payload", [{}, {"Contacts": {}}, {"Contacts": ["invalid"]}])
def test_vendor_envelope_must_be_valid(payload: dict[str, object]) -> None:
    client = _client(httpx.MockTransport(lambda _: httpx.Response(200, json=payload)))
    with pytest.raises(XeroApiError, match="Contacts"):
        client.list_vendors()


@pytest.mark.parametrize("payload", [{}, {"Invoices": {}}, {"Invoices": ["invalid"]}])
def test_invoice_envelope_must_be_valid(payload: dict[str, object]) -> None:
    client = _client(httpx.MockTransport(lambda _: httpx.Response(200, json=payload)))
    with pytest.raises(XeroApiError, match="Invoices"):
        client.list_bills(date(2026, 1, 1))


def test_company_connections_must_contain_valid_objects() -> None:
    client = _client(httpx.MockTransport(lambda _: httpx.Response(200, json=[{"tenantId": ""}])))
    with pytest.raises(XeroApiError, match="invalid connection"):
        client.company_info()


@pytest.mark.parametrize(
    "connection",
    [
        {"tenantId": True, "tenantName": "Acme"},
        {"tenantId": "tenant-1", "tenantName": ["Acme"]},
        {"tenantId": "tenant-1", "tenantNameShort": {"name": "Acme"}},
    ],
)
def test_company_connections_reject_wrong_field_types(connection: dict[str, object]) -> None:
    client = _client(httpx.MockTransport(lambda _: httpx.Response(200, json=[connection])))
    with pytest.raises(XeroApiError, match="invalid connection"):
        client.company_info()


def test_bill_requires_three_letter_currency_code() -> None:
    client = _client(
        httpx.MockTransport(
            lambda _: httpx.Response(
                200,
                json={
                    "Invoices": [
                        {
                            "InvoiceID": "bill-1",
                            "Contact": {"ContactID": "vendor-1"},
                            "Total": 0,
                            "CurrencyCode": "",
                            "DateString": "2026-09-01",
                        }
                    ]
                },
            )
        )
    )
    with pytest.raises(XeroApiError, match="invalid currency"):
        client.list_bills(date(2026, 1, 1))


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"Contacts": [{"Name": "Missing ID"}]}, "ContactID"),
        ({"Contacts": [{"ContactID": "vendor-1"}]}, "display name"),
    ],
)
def test_vendor_records_require_id_and_display_name(
    payload: dict[str, object], message: str
) -> None:
    client = _client(httpx.MockTransport(lambda _: httpx.Response(200, json=payload)))
    with pytest.raises(XeroApiError, match=message):
        client.list_vendors()


@pytest.mark.parametrize("field_value", [True, ["vendor-1"], {"id": "vendor-1"}])
def test_vendor_records_reject_wrong_id_type(field_value: object) -> None:
    client = _client(
        httpx.MockTransport(
            lambda _: httpx.Response(
                200, json={"Contacts": [{"ContactID": field_value, "Name": "Vendor"}]}
            )
        )
    )
    with pytest.raises(XeroApiError, match="ContactID"):
        client.list_vendors()


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("InvoiceID", "", "InvoiceID"),
        ("InvoiceID", True, "InvoiceID"),
        ("Contact", {}, "ContactID"),
        ("Contact", {"ContactID": ["vendor-1"]}, "ContactID"),
        ("Total", -1, "total"),
        ("Total", "not-a-number", "total"),
        ("Total", "NaN", "total"),
        ("DateString", "not-a-date", "provider date"),
        ("Status", None, "status"),
        ("Status", "UNKNOWN", "status"),
        ("CurrencyCode", ["USD"], "currency"),
    ],
)
def test_bill_records_require_valid_fields(field: str, value: object, message: str) -> None:
    invoice: dict[str, object] = {
        "InvoiceID": "bill-1",
        "Contact": {"ContactID": "vendor-1"},
        "Total": 0,
        "CurrencyCode": "USD",
        "DateString": "2026-09-01",
        "Status": "AUTHORISED",
    }
    if field == "Contact":
        invoice[field] = value
    else:
        invoice[field] = value
    client = _client(
        httpx.MockTransport(lambda _: httpx.Response(200, json={"Invoices": [invoice]}))
    )
    with pytest.raises(XeroApiError, match=message):
        client.list_bills(date(2026, 1, 1))


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {"access_token": "", "refresh_token": "refresh", "expires_in": 100},
        {"access_token": "access", "refresh_token": 42, "expires_in": 100},
        {"access_token": "access", "refresh_token": "refresh", "expires_in": 0},
        {"access_token": "access", "refresh_token": "refresh", "expires_in": "100"},
    ],
)
def test_token_response_must_have_valid_envelope(payload: object) -> None:
    client = _client(
        httpx.MockTransport(lambda _: httpx.Response(200, json=payload)),
    )
    with pytest.raises(XeroApiError):
        client.exchange_code_for_tokens("auth-code")
    assert client.access_token == ACCESS_TOKEN


def test_provider_error_fallback_does_not_include_response_body() -> None:
    secret_body = "access_token=do-not-leak"

    def handle(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text=secret_body)

    with pytest.raises(XeroApiError) as error_info:
        _client(httpx.MockTransport(handle)).list_vendors()
    assert secret_body not in str(error_info.value)


def test_invalid_token_json_does_not_include_response_body() -> None:
    secret_body = "refresh_token=do-not-leak"

    def handle(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=secret_body)

    with pytest.raises(XeroApiError) as error_info:
        _client(httpx.MockTransport(handle)).exchange_code_for_tokens("auth-code")
    assert secret_body not in str(error_info.value)


def test_vendor_and_bill_parsing() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        assert request.headers["Xero-tenant-id"] == TENANT_ID
        if request.url.path.endswith("/Contacts"):
            assert request.url.params["where"] == "IsSupplier==true"
            return httpx.Response(
                200,
                json={"Contacts": [{"ContactID": "vendor-1", "Name": "Acme Supplies"}]},
            )
        assert request.url.path.endswith("/Invoices")
        assert request.url.params["page"] == "1"
        assert "ACCPAY" in request.url.params["where"]
        return httpx.Response(
            200,
            json={
                "Invoices": [
                    {
                        "InvoiceID": "bill-1",
                        "Contact": {"ContactID": "vendor-1"},
                        "Total": 1234.5,
                        "CurrencyCode": "USD",
                        "DateString": "2026-09-01T00:00:00",
                        "Status": "PAID",
                    },
                    {
                        "InvoiceID": "bill-2",
                        "Contact": {"ContactID": "vendor-1"},
                        "Total": 20,
                        "CurrencyCode": "EUR",
                        "Date": "2026-09-02",
                        "Status": "VOIDED",
                    },
                ]
            },
        )

    client = _client(httpx.MockTransport(handle))
    vendors = client.list_vendors()
    bills = client.list_bills(date(2026, 1, 1))

    assert [(vendor.provider_id, vendor.display_name) for vendor in vendors] == [
        ("vendor-1", "Acme Supplies")
    ]
    assert bills[0].amount == Decimal("1234.5")
    assert bills[0].currency == "USD"
    assert bills[0].bill_date == date(2026, 9, 1)
    assert bills[0].status == "paid"
    assert bills[1].status == "void"


def test_pagination_continues_after_full_page() -> None:
    pages: list[int] = []

    def handle(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params["page"])
        pages.append(page)
        if page == 1:
            contacts = [
                {"ContactID": f"vendor-{index}", "Name": f"Vendor {index}"}
                for index in range(100)
            ]
        else:
            contacts = [{"ContactID": "vendor-last", "Name": "Last Vendor"}]
        return httpx.Response(200, json={"Contacts": contacts})

    vendors = _client(httpx.MockTransport(handle)).list_vendors()
    assert pages == [1, 2]
    assert len(vendors) == 101
    assert vendors[-1].provider_id == "vendor-last"


def test_bill_pagination_continues_after_full_page() -> None:
    pages: list[int] = []

    def handle(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params["page"])
        pages.append(page)
        invoices = [
            {
                "InvoiceID": f"bill-{index}",
                "Contact": {"ContactID": "vendor-1"},
                "Total": 0,
                "CurrencyCode": "USD",
                "DateString": "2026-09-01",
                "Status": "AUTHORISED",
            }
            for index in (range(100) if page == 1 else range(100, 101))
        ]
        return httpx.Response(200, json={"Invoices": invoices})

    bills = _client(httpx.MockTransport(handle)).list_bills(date(2026, 1, 1))
    assert pages == [1, 2]
    assert len(bills) == 101


def test_auth_and_api_errors_are_actionable() -> None:
    def unauthorized(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"Message": "Token expired"})

    with pytest.raises(XeroAuthError) as auth_info:
        _client(httpx.MockTransport(unauthorized)).list_vendors()
    assert auth_info.value.status_code == 401
    assert "Token expired" not in str(auth_info.value)

    def server_error(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="service unavailable")

    with pytest.raises(XeroApiError) as api_info:
        _client(httpx.MockTransport(server_error)).list_vendors()
    assert api_info.value.status_code == 500


def test_read_only_protocol_has_no_write_methods() -> None:
    assert isinstance(
        _client(httpx.MockTransport(lambda _: httpx.Response(200))), AccountingConnector
    )
    public_methods = [
        name
        for name, member in inspect.getmembers(XeroClient, predicate=inspect.isfunction)
        if not name.startswith("_")
    ]
    assert not any(
        name.startswith(("create", "update", "delete", "post", "write", "put", "patch"))
        for name in public_methods
    )

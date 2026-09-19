"""Read-only Xero accounting connector (R3.3).

Uses Xero OAuth 2.0 and REST APIs directly through httpx. Provider-specific response
shapes stay in this module; callers receive the accounting connector's normalized DTOs.
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Literal, Self
from urllib.parse import urlencode

import httpx
from pydantic import SecretStr

from procurepilot_api.config import Settings, get_settings
from procurepilot_api.modules.accounting.connector import (
    CompanyInfo,
    OAuthTokens,
    RawBill,
    RawVendor,
)


class XeroError(Exception):
    """Base exception for Xero client operations."""


class XeroAuthError(XeroError):
    """Raised when Xero OAuth or an authenticated API call fails."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        error_code: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code
        self.details = details or {}


class XeroApiError(XeroError):
    """Raised when a Xero API request or response fails."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        error_code: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code


def _parse_bill_status(value: object) -> Literal["open", "paid", "void"]:
    if not isinstance(value, str) or not value.strip():
        raise XeroApiError("Xero invoice must contain a supported bill status")
    status = value.strip().upper()
    if status in {"AUTHORISED", "OPEN", "DRAFT", "SUBMITTED"}:
        return "open"
    if status == "PAID":
        return "paid"
    if status in {"VOIDED", "DELETED"}:
        return "void"
    raise XeroApiError("Xero invoice has an unsupported bill status")


def _parse_xero_date(value: object) -> date | None:
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        candidate = value[:10]
        try:
            return date.fromisoformat(candidate)
        except ValueError:
            pass
    return None


class XeroClient:
    """Read-only Xero connector implementing AccountingConnector."""

    AUTH_URL = "https://login.xero.com/identity/connect/authorize"
    TOKEN_URL = "https://identity.xero.com/connect/token"
    API_BASE_URL = "https://api.xero.com/api.xro/2.0"
    CONNECTIONS_URL = "https://api.xero.com/connections"
    OAUTH_SCOPE = (
        "openid profile email offline_access accounting.invoices.read accounting.contacts.read"
    )
    PAGE_SIZE = 100

    def __init__(
        self,
        *,
        client_id: str | None = None,
        client_secret: SecretStr | str | None = None,
        redirect_uri: str | None = None,
        environment: Literal["sandbox", "production"] | None = None,
        realm_id: str | None = None,
        access_token: str | None = None,
        settings: Settings | None = None,
        http_client: httpx.Client | None = None,
    ) -> None:
        cfg = settings
        if cfg is None and client_id is None:
            try:
                cfg = get_settings()
            except Exception:
                cfg = None

        self._client_id = client_id or (cfg.xero_client_id if cfg else None)
        if client_secret is not None:
            self._client_secret = (
                client_secret.get_secret_value()
                if isinstance(client_secret, SecretStr)
                else client_secret
            )
        elif cfg and cfg.xero_client_secret:
            self._client_secret = cfg.xero_client_secret.get_secret_value()
        else:
            self._client_secret = None
        self._redirect_uri = redirect_uri or (cfg.xero_redirect_uri if cfg else None)
        self._environment = environment or (cfg.xero_environment if cfg else "sandbox")
        self._realm_id = realm_id
        self._access_token = access_token
        self._http_client = http_client or httpx.Client(timeout=30.0)
        self._owns_http_client = http_client is None

    @property
    def realm_id(self) -> str | None:
        return self._realm_id

    @realm_id.setter
    def realm_id(self, value: str) -> None:
        self._realm_id = value

    @property
    def access_token(self) -> str | None:
        return self._access_token

    @access_token.setter
    def access_token(self, value: str) -> None:
        self._access_token = value

    def close(self) -> None:
        if self._owns_http_client:
            self._http_client.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def build_authorization_url(self, state: str) -> str:
        if not self._client_id:
            raise XeroAuthError("XERO_CLIENT_ID is not configured")
        if not self._redirect_uri:
            raise XeroAuthError("XERO_REDIRECT_URI is not configured")
        params = {
            "response_type": "code",
            "client_id": self._client_id,
            "redirect_uri": self._redirect_uri,
            "scope": self.OAUTH_SCOPE,
            "state": state,
        }
        return f"{self.AUTH_URL}?{urlencode(params)}"

    def exchange_code_for_tokens(
        self,
        code: str,
        redirect_uri: str | None = None,
        realm_id: str | None = None,
    ) -> OAuthTokens:
        if not self._client_id or not self._client_secret:
            raise XeroAuthError("Xero client_id and client_secret are required for token exchange")
        target_redirect = redirect_uri or self._redirect_uri
        if not target_redirect:
            raise XeroAuthError("redirect_uri is required for token exchange")
        return self._exchange_token(
            {"grant_type": "authorization_code", "code": code, "redirect_uri": target_redirect},
            operation="exchange",
            realm_id=realm_id,
        )

    def refresh_access_token(self, refresh_token: str) -> OAuthTokens:
        if not self._client_id or not self._client_secret:
            raise XeroAuthError("Xero client_id and client_secret are required for token refresh")
        return self._exchange_token(
            {"grant_type": "refresh_token", "refresh_token": refresh_token},
            operation="refresh",
            fallback_refresh_token=refresh_token,
        )

    def _exchange_token(
        self,
        data: dict[str, str],
        *,
        operation: str,
        realm_id: str | None = None,
        fallback_refresh_token: str | None = None,
    ) -> OAuthTokens:
        try:
            response = self._http_client.post(
                self.TOKEN_URL,
                data=data,
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                auth=(self._client_id, self._client_secret),
            )
        except httpx.HTTPError as exc:
            raise XeroApiError(f"Network error during token {operation}: {exc}") from exc
        if response.is_error:
            error_code, _ = self._parse_error_payload(response)
            raise XeroAuthError(
                f"Xero token {operation} failed ({response.status_code}): {error_code}",
                status_code=response.status_code,
                error_code=error_code,
            )
        try:
            payload = response.json()
        except Exception as exc:
            raise XeroApiError("Invalid JSON in Xero token response") from exc
        if not isinstance(payload, dict):
            raise XeroApiError("Xero token response must be a JSON object")
        access_token = payload.get("access_token")
        refresh_token = payload.get("refresh_token") or fallback_refresh_token
        if not isinstance(access_token, str) or not access_token.strip():
            raise XeroApiError("Xero token response must contain a non-empty access_token")
        if not isinstance(refresh_token, str) or not refresh_token.strip():
            raise XeroApiError("Xero token response must contain a non-empty refresh_token")
        expires_in = payload.get("expires_in")
        if isinstance(expires_in, bool) or not isinstance(expires_in, int) or expires_in <= 0:
            raise XeroApiError("Xero token response must contain a positive integer expires_in")
        tokens = OAuthTokens(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=expires_in,
            token_type=(
                payload["token_type"]
                if isinstance(payload.get("token_type"), str)
                and payload["token_type"].strip()
                else "bearer"
            ),
        )
        self._access_token = tokens.access_token
        if realm_id is not None:
            self._realm_id = realm_id
        return tokens

    def _get(
        self, url: str, *, params: dict[str, object] | None = None
    ) -> dict[str, Any] | list[Any]:
        if not self._access_token:
            raise XeroAuthError("access_token is required to query Xero API", status_code=401)
        headers = {"Accept": "application/json", "Authorization": f"Bearer {self._access_token}"}
        if self._realm_id:
            headers["Xero-tenant-id"] = self._realm_id
        try:
            response = self._http_client.get(url, params=params, headers=headers)
        except httpx.HTTPError as exc:
            raise XeroApiError(f"Network error during Xero API request: {exc}") from exc
        if response.status_code == 401:
            code, _ = self._parse_error_payload(response)
            raise XeroAuthError(
                f"Xero API request unauthorized (401): {code}",
                status_code=401,
                error_code=code,
            )
        if response.is_error:
            code, _ = self._parse_error_payload(response)
            raise XeroApiError(
                f"Xero API request failed ({response.status_code}): {code}",
                status_code=response.status_code,
                error_code=code,
            )
        try:
            return response.json()
        except Exception as exc:
            raise XeroApiError("Invalid JSON from Xero API") from exc

    def company_info(self) -> CompanyInfo:
        connections = self._get(self.CONNECTIONS_URL)
        if not isinstance(connections, list) or not connections:
            raise XeroApiError("Xero connections response must contain at least one connection")
        if any(not isinstance(item, dict) or not _valid_connection(item) for item in connections):
            raise XeroApiError("Xero connections response contains an invalid connection object")

        if self._realm_id:
            selected = next(
                (item for item in connections if item["tenantId"].strip() == self._realm_id),
                None,
            )
            if selected is None:
                raise XeroApiError(
                    f"Configured Xero tenant '{self._realm_id}' was not found in "
                    "connected organisations"
                )
        elif len(connections) == 1:
            selected = connections[0]
        else:
            raise XeroApiError(
                "Multiple Xero organisations are connected; select an explicit tenant_id"
            )

        tenant_id = selected["tenantId"].strip()
        company_name = (selected.get("tenantName") or selected.get("tenantNameShort")).strip()
        self._realm_id = tenant_id
        return CompanyInfo(realm_id=tenant_id, company_name=company_name)

    def list_vendors(self) -> list[RawVendor]:
        vendors: list[RawVendor] = []
        page = 1
        while True:
            payload = self._get(
                f"{self.API_BASE_URL}/Contacts",
                params={"where": "IsSupplier==true", "page": page},
            )
            entries = payload.get("Contacts") if isinstance(payload, dict) else None
            if not isinstance(entries, list):
                raise XeroApiError("Missing or invalid 'Contacts' in Xero response")
            if any(not isinstance(item, dict) for item in entries):
                raise XeroApiError("'Contacts' response contains an invalid contact")
            for item in entries:
                vendor_id_value = item.get("ContactID")
                display_name_value = item.get("Name")
                if display_name_value is None:
                    display_name_value = item.get("ContactNumber")
                if not _non_empty_text(vendor_id_value) or not _non_empty_text(display_name_value):
                    raise XeroApiError("Xero contact must contain a ContactID and display name")
                vendor_id = vendor_id_value.strip()
                display_name = display_name_value.strip()
                vendors.append(
                    RawVendor(provider_vendor_id=vendor_id, display_name=display_name)
                )
            if len(entries) < self.PAGE_SIZE:
                return vendors
            page += 1

    def list_bills(self, since: date) -> list[RawBill]:
        bills: list[RawBill] = []
        page = 1
        where = f'Type=="ACCPAY"&&Date>=DateTime({since.year},{since.month:02d},{since.day:02d})'
        while True:
            payload = self._get(
                f"{self.API_BASE_URL}/Invoices",
                params={"where": where, "page": page},
            )
            entries = payload.get("Invoices") if isinstance(payload, dict) else None
            if not isinstance(entries, list):
                raise XeroApiError("Missing or invalid 'Invoices' in Xero response")
            for item in entries:
                if not isinstance(item, dict):
                    raise XeroApiError("Xero 'Invoices' response contains an invalid invoice")
                contact = item.get("Contact")
                contact_id_value = contact.get("ContactID") if isinstance(contact, dict) else None
                contact_id = (
                    contact_id_value.strip() if _non_empty_text(contact_id_value) else ""
                )
                invoice_id_value = item.get("InvoiceID")
                invoice_id = invoice_id_value.strip() if _non_empty_text(invoice_id_value) else ""
                if not invoice_id or not contact_id:
                    raise XeroApiError(
                        "Xero invoice must contain an InvoiceID and supplier ContactID"
                    )
                try:
                    amount = Decimal(str(item.get("Total")))
                except (InvalidOperation, TypeError, ValueError) as exc:
                    raise XeroApiError(f"Xero invoice {invoice_id} has an invalid total") from exc
                if not amount.is_finite() or amount < 0:
                    raise XeroApiError(f"Xero invoice {invoice_id} has an invalid total")
                currency_value = item.get("CurrencyCode")
                currency = currency_value.strip().upper() if isinstance(currency_value, str) else ""
                if not re.fullmatch(r"[A-Z]{3}", currency):
                    raise XeroApiError(
                        f"Xero invoice {invoice_id} has an invalid "
                        "currency code"
                    )
                bill_date = _parse_xero_date(item.get("DateString") or item.get("Date"))
                if bill_date is None:
                    raise XeroApiError(f"Xero invoice {invoice_id} has an invalid provider date")
                bills.append(
                    RawBill(
                        provider_bill_id=invoice_id,
                        provider_vendor_id=contact_id,
                        amount=amount,
                        currency=currency,
                        bill_date=bill_date,
                        status=_parse_bill_status(item.get("Status")),
                    )
                )
            if len(entries) < self.PAGE_SIZE:
                return bills
            page += 1

    @staticmethod
    def _parse_error_payload(response: httpx.Response) -> tuple[str, str]:
        try:
            payload = response.json()
            if isinstance(payload, dict):
                code_value = payload.get("error") or payload.get("ErrorNumber")
                if isinstance(code_value, str) and re.fullmatch(
                    r"[A-Za-z0-9_.-]{1,64}", code_value
                ):
                    return code_value, "Xero provider error"
        except Exception:
            pass
        return f"http_{response.status_code}", "Xero returned an unstructured provider error"


def _non_empty_text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _valid_connection(item: dict[str, Any]) -> bool:
    tenant_name = item.get("tenantName")
    short_name = item.get("tenantNameShort")
    return (
        _non_empty_text(item.get("tenantId"))
        and (tenant_name is None or isinstance(tenant_name, str))
        and (short_name is None or isinstance(short_name, str))
        and (_non_empty_text(tenant_name) or _non_empty_text(short_name))
    )

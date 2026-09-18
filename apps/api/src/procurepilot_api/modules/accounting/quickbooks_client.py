"""QuickBooks Online API client implementing AccountingConnector (R3.1).

Uses direct HTTP via httpx with no third-party SDK (research.md R1).
Supports OAuth 2.0 authorization code flow and refresh token flow (research.md R4).
Queries QuickBooks read-only REST endpoints for Bill, Vendor, and CompanyInfo (FR-013).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Literal, Self
from urllib.parse import urlencode

import httpx
from pydantic import SecretStr

from procurepilot_api.config import Settings, get_settings
from procurepilot_api.modules.accounting.connector import CompanyInfo, RawBill, RawVendor


@dataclass(frozen=True)
class OAuthTokens:
    """OAuth 2.0 access and refresh token pair returned by Intuit."""

    access_token: str
    refresh_token: str
    expires_in: int = 3600
    token_type: str = "bearer"


class QuickBooksError(Exception):
    """Base exception for QuickBooks client operations."""


class QuickBooksAuthError(QuickBooksError):
    """Raised when OAuth authentication, token exchange, or token refresh fails.

    This includes expired/revoked refresh tokens (FR-002, spec Acceptance Scenario 1.4),
    enabling callers such as ConnectionService or SyncService to transition the connection
    state to 'needs_reauth'.
    """

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


class QuickBooksApiError(QuickBooksError):
    """Raised when a QuickBooks REST API query or network call fails."""

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


def _parse_bill_status(data: dict[str, Any]) -> Literal["open", "paid", "void"]:
    """Derive the synced_bill_status from a QuickBooks Bill entity.

    QuickBooks Bills use Balance and TotalAmt, or an explicit status/void flag.
    - If status/provider_status is explicitly 'paid', 'open', or 'void', map to that.
    - If Voided is true or total/balance indicates voided, return 'void'.
    - If Balance is 0 and TotalAmt > 0, return 'paid'.
    - Otherwise, return 'open'.
    """
    raw_status = str(data.get("status") or data.get("provider_status") or "").lower()
    if raw_status in ("open", "paid", "void"):
        return raw_status  # type: ignore[return-value]
    if data.get("Voided") is True:
        return "void"
    balance = data.get("Balance")
    if balance is not None:
        try:
            if Decimal(str(balance)) == Decimal("0"):
                return "paid"
            return "open"
        except Exception:
            pass
    return "open"


class QuickBooksClient:
    """Read-only QuickBooks Online client implementing AccountingConnector."""

    AUTH_URL = "https://appcenter.intuit.com/connect/oauth2"
    TOKEN_URL = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"
    SANDBOX_BASE_URL = "https://sandbox-quickbooks.api.intuit.com"
    PRODUCTION_BASE_URL = "https://quickbooks.api.intuit.com"
    OAUTH_SCOPE = "com.intuit.quickbooks.accounting"

    def __init__(
        self,
        *,
        client_id: str | None = None,
        client_secret: SecretStr | str | None = None,
        redirect_uri: str | None = None,
        environment: Literal["sandbox", "production"] = "sandbox",
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

        self._client_id = client_id or (cfg.quickbooks_client_id if cfg else None)

        raw_secret: str | None = None
        if client_secret is not None:
            raw_secret = (
                client_secret.get_secret_value()
                if isinstance(client_secret, SecretStr)
                else client_secret
            )
        elif cfg and cfg.quickbooks_client_secret:
            raw_secret = cfg.quickbooks_client_secret.get_secret_value()
        self._client_secret = raw_secret

        self._redirect_uri = redirect_uri or (cfg.quickbooks_redirect_uri if cfg else None)
        self._environment = environment or (cfg.quickbooks_environment if cfg else "sandbox")
        self._realm_id = realm_id
        self._access_token = access_token

        self._base_url = (
            self.SANDBOX_BASE_URL
            if self._environment == "sandbox"
            else self.PRODUCTION_BASE_URL
        )

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
        """Build the QuickBooks OAuth 2.0 authorization URL for owner consent.

        Requires client_id and redirect_uri to be configured.
        """
        if not self._client_id:
            raise QuickBooksAuthError("QUICKBOOKS_CLIENT_ID is not configured")
        if not self._redirect_uri:
            raise QuickBooksAuthError("QUICKBOOKS_REDIRECT_URI is not configured")

        params = {
            "client_id": self._client_id,
            "response_type": "code",
            "scope": self.OAUTH_SCOPE,
            "redirect_uri": self._redirect_uri,
            "state": state,
        }
        return f"{self.AUTH_URL}?{urlencode(params)}"

    def exchange_code_for_tokens(
        self,
        code: str,
        redirect_uri: str | None = None,
        realm_id: str | None = None,
    ) -> OAuthTokens:
        """Exchange authorization callback code for access and refresh tokens.

        Sends HTTP Basic auth using client_id and client_secret to the Intuit token endpoint.
        """
        if not self._client_id or not self._client_secret:
            raise QuickBooksAuthError(
                "QuickBooks client_id and client_secret are required for token exchange"
            )

        target_redirect = redirect_uri or self._redirect_uri
        if not target_redirect:
            raise QuickBooksAuthError("redirect_uri is required for token exchange")

        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": target_redirect,
        }
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        }

        try:
            response = self._http_client.post(
                self.TOKEN_URL,
                data=data,
                headers=headers,
                auth=(self._client_id, self._client_secret),
            )
        except httpx.HTTPError as exc:
            raise QuickBooksApiError(f"Network error during token exchange: {exc}") from exc

        if response.is_error:
            error_code, error_desc = self._parse_error_payload(response)
            raise QuickBooksAuthError(
                f"QuickBooks token exchange failed ({response.status_code}): "
                f"{error_code} - {error_desc}",
                status_code=response.status_code,
                error_code=error_code,
            )

        tokens = self._parse_token_response(response)
        self._access_token = tokens.access_token
        if realm_id is not None:
            self._realm_id = realm_id
        return tokens

    def refresh_access_token(self, refresh_token: str) -> OAuthTokens:
        """Exchange a refresh token for a fresh access token (research.md R4).

        QuickBooks refresh tokens are valid for ~100 days; access tokens expire hourly.
        A failure indicates the connection needs re-authorization (FR-002, spec Scenario 1.4).
        """
        if not self._client_id or not self._client_secret:
            raise QuickBooksAuthError(
                "QuickBooks client_id and client_secret are required for token refresh"
            )

        data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        }
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        }

        try:
            response = self._http_client.post(
                self.TOKEN_URL,
                data=data,
                headers=headers,
                auth=(self._client_id, self._client_secret),
            )
        except httpx.HTTPError as exc:
            raise QuickBooksApiError(f"Network error during token refresh: {exc}") from exc

        if response.is_error:
            error_code, error_desc = self._parse_error_payload(response)
            raise QuickBooksAuthError(
                f"QuickBooks token refresh failed ({response.status_code}): "
                f"{error_code} - {error_desc}",
                status_code=response.status_code,
                error_code=error_code,
            )

        tokens = self._parse_token_response(response, fallback_refresh_token=refresh_token)
        self._access_token = tokens.access_token
        return tokens

    def _query(self, query_string: str) -> dict[str, Any]:
        """Execute a read-only query against QuickBooks REST /v3/company/{realmId}/query."""
        if not self._realm_id:
            raise QuickBooksApiError("realm_id is required to query QuickBooks API")
        if not self._access_token:
            raise QuickBooksAuthError(
                "access_token is required to query QuickBooks API", status_code=401
            )

        url = f"{self._base_url}/v3/company/{self._realm_id}/query"
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self._access_token}",
        }

        try:
            response = self._http_client.get(
                url,
                params={"query": query_string},
                headers=headers,
            )
        except httpx.HTTPError as exc:
            raise QuickBooksApiError(f"Network error during query '{query_string}': {exc}") from exc

        if response.status_code == 401:
            error_code, error_desc = self._parse_error_payload(response)
            raise QuickBooksAuthError(
                f"QuickBooks API query unauthorized (401): {error_code} - {error_desc}",
                status_code=401,
                error_code=error_code,
            )

        if response.is_error:
            error_code, error_desc = self._parse_error_payload(response)
            raise QuickBooksApiError(
                f"QuickBooks API query failed ({response.status_code}): "
                f"{error_code} - {error_desc}",
                status_code=response.status_code,
                error_code=error_code,
            )

        try:
            data = response.json()
        except Exception as exc:
            raise QuickBooksApiError(
                f"Invalid JSON from QuickBooks query: {response.text}"
            ) from exc

        query_response = data.get("QueryResponse")
        if not isinstance(query_response, dict):
            raise QuickBooksApiError(f"Missing or invalid 'QueryResponse' in API response: {data}")

        return query_response

    def company_info(self) -> CompanyInfo:
        """Fetch company/realm metadata from QuickBooks."""
        query_response = self._query("SELECT * FROM CompanyInfo")
        entries = query_response.get("CompanyInfo", [])
        if not entries:
            raise QuickBooksApiError(f"No CompanyInfo found for realm {self._realm_id}")

        first = entries[0]
        company_name = str(first.get("CompanyName") or first.get("LegalName") or "")
        return CompanyInfo(
            realm_id=str(self._realm_id),
            company_name=company_name,
        )

    def list_vendors(self) -> list[RawVendor]:
        """Fetch all vendors/suppliers from QuickBooks."""
        query_response = self._query("SELECT * FROM Vendor")
        entries = query_response.get("Vendor", [])
        vendors: list[RawVendor] = []
        for item in entries:
            vendor_id = str(item.get("Id") or "")
            display_name = str(item.get("DisplayName") or item.get("CompanyName") or "")
            vendors.append(
                RawVendor(
                    provider_vendor_id=vendor_id,
                    display_name=display_name,
                )
            )
        return vendors

    def list_bills(self, since: date) -> list[RawBill]:
        """Fetch bills recorded on or after `since` date from QuickBooks."""
        query = f"SELECT * FROM Bill WHERE TxnDate >= '{since.isoformat()}'"
        query_response = self._query(query)
        entries = query_response.get("Bill", [])
        bills: list[RawBill] = []
        for item in entries:
            bill_id = str(item.get("Id") or "")
            vendor_ref = item.get("VendorRef")
            if isinstance(vendor_ref, dict):
                vendor_id = str(vendor_ref.get("value") or "")
            elif vendor_ref is not None:
                vendor_id = str(vendor_ref)
            else:
                vendor_id = ""

            amount_val = item.get("TotalAmt", 0)
            amount = Decimal(str(amount_val))

            currency_ref = item.get("CurrencyRef")
            if isinstance(currency_ref, dict):
                currency = str(currency_ref.get("value") or "USD")
            elif currency_ref:
                currency = str(currency_ref)
            else:
                currency = str(item.get("currency") or "USD")

            txn_date_raw = item.get("TxnDate") or item.get("bill_date")
            if isinstance(txn_date_raw, date):
                bill_date = txn_date_raw
            elif isinstance(txn_date_raw, str):
                bill_date = date.fromisoformat(txn_date_raw)
            else:
                bill_date = since

            status = _parse_bill_status(item)
            bills.append(
                RawBill(
                    provider_bill_id=bill_id,
                    provider_vendor_id=vendor_id,
                    amount=amount,
                    currency=currency,
                    bill_date=bill_date,
                    status=status,
                )
            )
        return bills

    @staticmethod
    def _parse_error_payload(response: httpx.Response) -> tuple[str, str]:
        try:
            body = response.json()
            error_code = str(body.get("error") or body.get("fault", {}).get("type") or "error")
            error_desc = str(
                body.get("error_description")
                or body.get("fault", {}).get("error", [{}])[0].get("message")
                or response.text
            )
            return error_code, error_desc
        except Exception:
            return f"http_{response.status_code}", response.text

    @staticmethod
    def _parse_token_response(
        response: httpx.Response,
        fallback_refresh_token: str | None = None,
    ) -> OAuthTokens:
        try:
            data = response.json()
        except Exception as exc:
            raise QuickBooksApiError(f"Invalid JSON in token response: {response.text}") from exc

        access_token = data.get("access_token")
        if not access_token:
            raise QuickBooksApiError("Token response missing 'access_token'")

        refresh_token = data.get("refresh_token") or fallback_refresh_token
        if not refresh_token:
            raise QuickBooksApiError("Token response missing 'refresh_token'")

        return OAuthTokens(
            access_token=str(access_token),
            refresh_token=str(refresh_token),
            expires_in=int(data.get("expires_in", 3600)),
            token_type=str(data.get("token_type", "bearer")),
        )

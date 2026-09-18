"""Square POS and Inventory API client implementing PosConnector (R3.2).

Uses direct HTTP via httpx with no third-party SDK (research.md R1).
Supports OAuth 2.0 authorization code flow and refresh token flow (research.md R1/R3).
Queries Square read-only REST endpoints for Merchants, Orders, and Inventory (FR-002, FR-004).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Literal, Self
from urllib.parse import urlencode

import httpx
from pydantic import SecretStr

from procurepilot_api.config import Settings, get_settings
from procurepilot_api.modules.pos.connector import (
    OAuthTokens,
    PosAccountInfo,
    RawInventoryLevel,
    RawSalesTransaction,
)


class SquareError(Exception):
    """Base exception for Square client operations."""


class SquareAuthError(SquareError):
    """Raised when OAuth authentication, token exchange, or token refresh fails.

    This includes expired/revoked tokens (FR-008, spec Acceptance Scenario 1.4),
    enabling callers such as ConnectionService or SyncService to transition the
    connection state to 'needs_reauth'.
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


class SquareApiError(SquareError):
    """Raised when a Square REST API query or network call fails."""

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


def _parse_date(value: object, fallback: date) -> date:
    """Parse an ISO-8601 date or datetime string to a date."""
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            date_str = value.split("T")[0]
            return date.fromisoformat(date_str)
        except Exception:
            return fallback
    return fallback


class SquareClient:
    """Read-only Square API client implementing PosConnector."""

    SANDBOX_BASE_URL = "https://connect.squareupsandbox.com"
    PRODUCTION_BASE_URL = "https://connect.squareup.com"
    SQUARE_VERSION = "2024-09-18"
    OAUTH_SCOPE = "ITEMS_READ ORDERS_READ INVENTORY_READ MERCHANT_PROFILE_READ"

    def __init__(
        self,
        *,
        application_id: str | None = None,
        application_secret: SecretStr | str | None = None,
        redirect_uri: str | None = None,
        environment: Literal["sandbox", "production"] = "sandbox",
        access_token: str | None = None,
        settings: Settings | None = None,
        http_client: httpx.Client | None = None,
    ) -> None:
        cfg = settings
        if cfg is None and application_id is None:
            try:
                cfg = get_settings()
            except Exception:
                cfg = None

        self._application_id = application_id or (cfg.square_application_id if cfg else None)

        raw_secret: str | None = None
        if application_secret is not None:
            raw_secret = (
                application_secret.get_secret_value()
                if isinstance(application_secret, SecretStr)
                else str(application_secret)
            )
        elif cfg and cfg.square_application_secret:
            raw_secret = cfg.square_application_secret.get_secret_value()
        self._application_secret = raw_secret

        self._redirect_uri = redirect_uri or (cfg.square_redirect_uri if cfg else None)
        self._environment = environment or (cfg.square_environment if cfg else "sandbox")
        self._access_token = access_token

        self._base_url = (
            self.SANDBOX_BASE_URL
            if self._environment == "sandbox"
            else self.PRODUCTION_BASE_URL
        )

        self._http_client = http_client or httpx.Client(timeout=30.0)
        self._owns_http_client = http_client is None

    @property
    def application_id(self) -> str | None:
        return self._application_id

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
        """Build the Square OAuth 2.0 authorization URL for owner consent.

        Requires application_id and redirect_uri to be configured.
        """
        if not self._application_id:
            raise SquareAuthError("SQUARE_APPLICATION_ID is not configured")
        if not self._redirect_uri:
            raise SquareAuthError("SQUARE_REDIRECT_URI is not configured")

        params = {
            "client_id": self._application_id,
            "response_type": "code",
            "scope": self.OAUTH_SCOPE,
            "redirect_uri": self._redirect_uri,
            "state": state,
        }
        return f"{self._base_url}/oauth2/authorize?{urlencode(params)}"

    def exchange_code_for_tokens(
        self,
        code: str,
        redirect_uri: str | None = None,
    ) -> OAuthTokens:
        """Exchange authorization callback code for access and refresh tokens.

        Posts client credentials and authorization code to Square's OAuth endpoint.
        """
        if not self._application_id or not self._application_secret:
            raise SquareAuthError(
                "Square application_id and application_secret are required for token exchange"
            )

        target_redirect = redirect_uri or self._redirect_uri
        if not target_redirect:
            raise SquareAuthError("redirect_uri is required for token exchange")

        payload = {
            "client_id": self._application_id,
            "client_secret": self._application_secret,
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": target_redirect,
        }
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Square-Version": self.SQUARE_VERSION,
        }

        try:
            response = self._http_client.post(
                f"{self._base_url}/oauth2/token",
                json=payload,
                headers=headers,
            )
        except httpx.HTTPError as exc:
            raise SquareApiError(f"Network error during token exchange: {exc}") from exc

        if response.is_error:
            error_code, error_desc = self._parse_error_payload(response)
            raise SquareAuthError(
                f"Square token exchange failed ({response.status_code}): "
                f"{error_code} - {error_desc}",
                status_code=response.status_code,
                error_code=error_code,
            )

        tokens = self._parse_token_response(response)
        self._access_token = tokens.access_token
        return tokens

    def refresh_access_token(self, refresh_token: str) -> OAuthTokens:
        """Exchange a refresh token for a fresh access token.

        A 401 or invalid_grant response indicates the connection needs re-authorization (FR-008).
        """
        if not self._application_id or not self._application_secret:
            raise SquareAuthError(
                "Square application_id and application_secret are required for token refresh"
            )

        payload = {
            "client_id": self._application_id,
            "client_secret": self._application_secret,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        }
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Square-Version": self.SQUARE_VERSION,
        }

        try:
            response = self._http_client.post(
                f"{self._base_url}/oauth2/token",
                json=payload,
                headers=headers,
            )
        except httpx.HTTPError as exc:
            raise SquareApiError(f"Network error during token refresh: {exc}") from exc

        if response.is_error:
            error_code, error_desc = self._parse_error_payload(response)
            raise SquareAuthError(
                f"Square token refresh failed ({response.status_code}): "
                f"{error_code} - {error_desc}",
                status_code=response.status_code,
                error_code=error_code,
            )

        tokens = self._parse_token_response(response, fallback_refresh_token=refresh_token)
        self._access_token = tokens.access_token
        return tokens

    def get_account_info(self) -> PosAccountInfo:
        """Fetch merchant/account metadata for the connected Square account."""
        data = self._request("GET", "/v2/merchants/me")
        merchant_raw = data.get("merchant")

        if isinstance(merchant_raw, list):
            merchant = merchant_raw[0] if merchant_raw else {}
        elif isinstance(merchant_raw, dict):
            merchant = merchant_raw
        else:
            merchant = {}

        account_id = str(merchant.get("id") or "unknown")
        account_name = str(
            merchant.get("business_name")
            or merchant.get("name")
            or account_id
        )
        return PosAccountInfo(
            account_id=account_id,
            account_name=account_name,
        )

    def list_sales_transactions(self, since: date) -> list[RawSalesTransaction]:
        """Fetch completed sales transactions recorded on or after `since` via Square Orders API."""
        payload = {
            "query": {
                "filter": {
                    "date_time_filter": {
                        "created_at": {
                            "start_at": f"{since.isoformat()}T00:00:00Z"
                        }
                    },
                    "state_filter": {
                        "states": ["COMPLETED"]
                    },
                },
                "sort": {
                    "sort_field": "CREATED_AT",
                    "sort_order": "DESC",
                },
            }
        }
        data = self._request("POST", "/v2/orders/search", json=payload)
        orders = data.get("orders", [])
        transactions: list[RawSalesTransaction] = []

        for order in orders:
            order_id = str(order.get("id") or "")
            created_at_raw = order.get("created_at") or order.get("closed_at")
            txn_date = _parse_date(created_at_raw, fallback=since)

            for line_item in order.get("line_items", []):
                external_item_id = str(
                    line_item.get("catalog_object_id")
                    or line_item.get("item_id")
                    or line_item.get("uid")
                    or ""
                )
                item_name = str(line_item.get("name") or "")
                quantity_val = line_item.get("quantity", "1")
                try:
                    quantity = Decimal(str(quantity_val))
                except Exception:
                    quantity = Decimal("1")

                uid = str(line_item.get("uid") or f"{order_id}-{external_item_id}")
                transactions.append(
                    RawSalesTransaction(
                        transaction_id=uid,
                        external_item_id=external_item_id,
                        item_name=item_name,
                        quantity=quantity,
                        transaction_date=txn_date,
                    )
                )

        return transactions

    def list_inventory_levels(self) -> list[RawInventoryLevel]:
        """Fetch stock-on-hand levels for tracked items via Square Inventory API."""
        data = self._request("GET", "/v2/inventory/counts")
        counts = data.get("counts") or data.get("inventory_levels") or []
        levels: list[RawInventoryLevel] = []

        for count in counts:
            external_item_id = str(count.get("catalog_object_id") or "")
            qty_raw = count.get("quantity")
            stock: Decimal | None
            if qty_raw is not None:
                try:
                    stock = Decimal(str(qty_raw))
                except Exception:
                    stock = None
            else:
                stock = None

            item_name = str(count.get("item_name") or "")
            levels.append(
                RawInventoryLevel(
                    external_item_id=external_item_id,
                    stock_on_hand=stock,
                    item_name=item_name,
                )
            )

        return levels

    def _request(
        self,
        method: Literal["GET", "POST"],
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute an authenticated request against the Square REST API."""
        if not self._access_token:
            raise SquareAuthError(
                "access_token is required to call Square API",
                status_code=401,
            )

        url = f"{self._base_url}{path}"
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self._access_token}",
            "Square-Version": self.SQUARE_VERSION,
        }
        if json is not None:
            headers["Content-Type"] = "application/json"

        try:
            response = self._http_client.request(
                method,
                url,
                params=params,
                json=json,
                headers=headers,
            )
        except httpx.HTTPError as exc:
            raise SquareApiError(f"Network error during {method} {path}: {exc}") from exc

        if response.status_code == 401:
            error_code, error_desc = self._parse_error_payload(response)
            raise SquareAuthError(
                f"Square API unauthorized (401): {error_code} - {error_desc}",
                status_code=401,
                error_code=error_code,
            )

        if response.is_error:
            error_code, error_desc = self._parse_error_payload(response)
            raise SquareApiError(
                f"Square API request failed ({response.status_code}): "
                f"{error_code} - {error_desc}",
                status_code=response.status_code,
                error_code=error_code,
            )

        try:
            return response.json()
        except Exception as exc:
            raise SquareApiError(f"Invalid JSON from Square API: {response.text}") from exc

    @staticmethod
    def _parse_error_payload(response: httpx.Response) -> tuple[str, str]:
        try:
            body = response.json()
            if "errors" in body and isinstance(body["errors"], list) and body["errors"]:
                first = body["errors"][0]
                code = str(first.get("code") or first.get("category") or "error")
                detail = str(first.get("detail") or response.text)
                return code, detail
            error_code = str(body.get("error") or "error")
            error_desc = str(body.get("error_description") or response.text)
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
            raise SquareApiError(f"Invalid JSON in token response: {response.text}") from exc

        access_token = data.get("access_token")
        if not access_token:
            raise SquareApiError("Token response missing 'access_token'")

        refresh_token = data.get("refresh_token") or fallback_refresh_token
        if not refresh_token:
            raise SquareApiError("Token response missing 'refresh_token'")

        return OAuthTokens(
            access_token=str(access_token),
            refresh_token=str(refresh_token),
            expires_in=int(data.get("expires_in", 3600)),
            token_type=str(data.get("token_type", "bearer")),
            merchant_id=str(data.get("merchant_id")) if data.get("merchant_id") else None,
        )

"""Accounting connector interface, types, and stub implementation (R3.1).

Defines the read-only AccountingConnector protocol, data transfer objects mirroring
synced_bill and synced_vendor schema shapes, and an in-memory StubConnector for testing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Literal, Protocol, runtime_checkable

from procurepilot_api.config import Settings, get_settings


def _validate_decimal(value: Decimal, field_name: str) -> None:
    if not isinstance(value, Decimal) or not value.is_finite() or value < 0:
        raise ValueError(f"{field_name} must be a finite non-negative Decimal")


def _validate_currency(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Z]{3}", value.upper()):
        raise ValueError(f"{field_name} must be an uppercase 3-letter currency")
    return value.upper()


@dataclass(frozen=True)
class RawBillLine:
    """Normalized, read-only evidence for one provider bill line."""

    line_number: int
    quantity: Decimal
    unit_price_amount: Decimal
    unit_price_currency: str
    description: str
    provider_line_reference: str | None = None
    provider_product_reference: str | None = None

    def __post_init__(self) -> None:
        if isinstance(self.line_number, bool) or self.line_number <= 0:
            raise ValueError("line_number must be positive")
        _validate_decimal(self.quantity, "quantity")
        _validate_decimal(self.unit_price_amount, "unit_price_amount")
        object.__setattr__(
            self,
            "unit_price_currency",
            _validate_currency(self.unit_price_currency, "unit_price_currency"),
        )


def _validate_references(value: tuple[str, ...], field_name: str) -> tuple[str, ...]:
    if not isinstance(value, tuple) or any(not isinstance(item, str) or not item for item in value):
        raise ValueError(f"{field_name} must be a tuple of non-empty strings")
    return value


@dataclass(frozen=True)
class RawBill:
    """A supplier bill as extracted from an accounting provider (FR-005).

    Matches the database schema of synced_bill (migration 20260918000004).
    """

    provider_bill_id: str
    provider_vendor_id: str
    amount: Decimal
    currency: str
    bill_date: date
    status: Literal["open", "paid", "void"]
    provider_order_reference: str | None = None
    document_references: tuple[str, ...] = ()
    lines: tuple[RawBillLine, ...] = ()

    def __post_init__(self) -> None:
        _validate_decimal(self.amount, "amount")
        object.__setattr__(self, "currency", _validate_currency(self.currency, "currency"))
        object.__setattr__(
            self,
            "document_references",
            _validate_references(self.document_references, "document_references"),
        )
        if not isinstance(self.lines, tuple) or any(
            not isinstance(line, RawBillLine) for line in self.lines
        ):
            raise ValueError("lines must be a tuple of RawBillLine")

    @property
    def provider_id(self) -> str:
        """Alias for provider_bill_id."""
        return self.provider_bill_id

    @property
    def provider_status(self) -> Literal["open", "paid", "void"]:
        """Alias for status."""
        return self.status


@dataclass(frozen=True)
class RawVendor:
    """A vendor/supplier as extracted from an accounting provider (FR-006).

    Matches the database schema of synced_vendor (migration 20260918000003).
    """

    provider_vendor_id: str
    display_name: str

    @property
    def provider_id(self) -> str:
        """Alias for provider_vendor_id."""
        return self.provider_vendor_id


@dataclass(frozen=True)
class CompanyInfo:
    """Connected accounting tenant/company details (FR-002).

    Matches realm_id and display_name in accounting_connection (migration 20260918000002).
    """

    realm_id: str
    company_name: str

    @property
    def display_name(self) -> str:
        """Alias for company_name."""
        return self.company_name


@dataclass(frozen=True)
class OAuthTokens:
    """OAuth 2.0 access and refresh token pair."""

    access_token: str
    refresh_token: str
    expires_in: int = 3600
    token_type: str = "bearer"


@runtime_checkable
class AccountingConnector(Protocol):
    """Protocol for reading from an external accounting system (QuickBooks, Stub).

    Deliberately read-only: no create, update, or delete methods exist on this protocol,
    enforcing FR-013 at the type level. All reconciliation decisions live solely in
    ProcurePilot; nothing is ever written back to the accounting system.
    """

    def build_authorization_url(self, state: str) -> str:
        """Build the OAuth authorization URL for user consent."""
        ...

    def exchange_code_for_tokens(
        self,
        code: str,
        redirect_uri: str | None = None,
        realm_id: str | None = None,
    ) -> OAuthTokens:
        """Exchange authorization code for access and refresh tokens."""
        ...

    def list_bills(self, since: date) -> list[RawBill]:
        """Fetch bills recorded on or after the specified date."""
        ...

    def list_vendors(self) -> list[RawVendor]:
        """Fetch the full list of vendors/suppliers."""
        ...

    def company_info(self) -> CompanyInfo:
        """Fetch metadata for the connected company/realm."""
        ...


class StubConnector:
    """In-memory stub implementation of AccountingConnector.

    Provides deterministic fixtures so sync, matching, and discrepancy flows can be developed
    and tested without requiring real QuickBooks credentials (research.md R5).
    """

    def __init__(
        self,
        bills: list[RawBill] | None = None,
        vendors: list[RawVendor] | None = None,
        company: CompanyInfo | None = None,
    ) -> None:
        self._bills = list(bills) if bills is not None else self._default_bills()
        self._vendors = list(vendors) if vendors is not None else self._default_vendors()
        self._company = company or CompanyInfo(
            realm_id="stub-realm-12345",
            company_name="ProcurePilot Demo Company",
        )

    @staticmethod
    def _default_vendors() -> list[RawVendor]:
        return [
            RawVendor(
                provider_vendor_id="stub-vendor-001",
                display_name="Global Office Supplies",
            ),
            RawVendor(
                provider_vendor_id="stub-vendor-002",
                display_name="Industrial Parts Direct",
            ),
            RawVendor(
                provider_vendor_id="stub-vendor-003",
                display_name="Apex Logistics",
            ),
        ]

    @staticmethod
    def _default_bills() -> list[RawBill]:
        today = date.today()
        return [
            RawBill(
                provider_bill_id="stub-bill-101",
                provider_vendor_id="stub-vendor-001",
                amount=Decimal("1250.00"),
                currency="USD",
                bill_date=today - timedelta(days=15),
                status="open",
            ),
            RawBill(
                provider_bill_id="stub-bill-102",
                provider_vendor_id="stub-vendor-002",
                amount=Decimal("3450.50"),
                currency="USD",
                bill_date=today - timedelta(days=30),
                status="paid",
            ),
            RawBill(
                provider_bill_id="stub-bill-103",
                provider_vendor_id="stub-vendor-003",
                amount=Decimal("890.25"),
                currency="USD",
                bill_date=today - timedelta(days=5),
                status="open",
            ),
        ]

    def build_authorization_url(self, state: str) -> str:
        from urllib.parse import urlencode

        params = {
            "client_id": "stub-client-id",
            "response_type": "code",
            "scope": "com.intuit.quickbooks.accounting",
            "redirect_uri": "http://localhost:8000/api/v1/accounting/connect/callback",
            "state": state,
        }
        return f"https://appcenter.intuit.com/connect/oauth2?{urlencode(params)}"

    def exchange_code_for_tokens(
        self,
        code: str,
        redirect_uri: str | None = None,
        realm_id: str | None = None,
    ) -> OAuthTokens:
        if realm_id is not None:
            self._company = CompanyInfo(
                realm_id=realm_id,
                company_name=self._company.company_name,
            )
        return OAuthTokens(
            access_token="stub-access-token",
            refresh_token="stub-refresh-token",
        )

    def list_bills(self, since: date) -> list[RawBill]:
        return [b for b in self._bills if b.bill_date >= since]

    def list_vendors(self) -> list[RawVendor]:
        return list(self._vendors)

    def company_info(self) -> CompanyInfo:
        return self._company


def get_accounting_connector(
    settings: Settings | None = None,
    *,
    realm_id: str | None = None,
    access_token: str | None = None,
) -> AccountingConnector:
    """Factory returning the active AccountingConnector based on configuration."""
    cfg = settings or get_settings()
    if cfg.accounting_provider_mode == "quickbooks":
        from procurepilot_api.modules.accounting.quickbooks_client import QuickBooksClient

        return QuickBooksClient(
            settings=cfg,
            realm_id=realm_id,
            access_token=access_token,
        )
    if cfg.accounting_provider_mode == "xero":
        from procurepilot_api.modules.accounting.xero_client import XeroClient

        return XeroClient(
            settings=cfg,
            realm_id=realm_id,
            access_token=access_token,
        )
    return StubConnector()

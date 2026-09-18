"""POS connector interface, types, and stub implementation (R3.2).

Defines the read-only PosConnector protocol, data transfer objects mirroring
synced_product_signal and pos_connection schema shapes, and an in-memory
StubConnector with comprehensive fixture scenarios for testing.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Protocol, runtime_checkable

from procurepilot_api.config import Settings, get_settings


@dataclass(frozen=True)
class RawSalesTransaction:
    """A sales transaction record from a POS provider (FR-002, FR-003)."""

    transaction_id: str
    external_item_id: str
    item_name: str
    quantity: Decimal
    transaction_date: date


@dataclass(frozen=True)
class RawInventoryLevel:
    """A stock-on-hand record from a POS/inventory provider (FR-004)."""

    external_item_id: str
    stock_on_hand: Decimal | None
    item_name: str = ""


@dataclass(frozen=True)
class PosAccountInfo:
    """Connected POS account details (FR-001).

    Matches external_account_id and external_account_name in pos_connection.
    """

    account_id: str
    account_name: str

    @property
    def external_account_id(self) -> str:
        """Alias for account_id."""
        return self.account_id

    @property
    def external_account_name(self) -> str:
        """Alias for account_name."""
        return self.account_name

    @property
    def display_name(self) -> str:
        """Alias for account_name."""
        return self.account_name


@dataclass(frozen=True)
class OAuthTokens:
    """OAuth 2.0 access and refresh token pair."""

    access_token: str
    refresh_token: str
    expires_in: int = 3600
    token_type: str = "bearer"
    merchant_id: str | None = None


@runtime_checkable
class PosConnector(Protocol):
    """Protocol for reading from an external POS/inventory system (Square, Stub).

    Deliberately read-only: no create, update, or delete methods exist on this protocol,
    enforcing FR-002/FR-004's read-only constraint at the type level.
    """

    def build_authorization_url(self, state: str) -> str:
        """Build the OAuth authorization URL for user consent."""
        ...

    def exchange_code_for_tokens(
        self,
        code: str,
        redirect_uri: str | None = None,
    ) -> OAuthTokens:
        """Exchange authorization code for access and refresh tokens."""
        ...

    def list_sales_transactions(self, since: date) -> list[RawSalesTransaction]:
        """Fetch sales transactions recorded on or after the specified date."""
        ...

    def list_inventory_levels(self) -> list[RawInventoryLevel]:
        """Fetch current stock-on-hand levels for tracked items."""
        ...

    def get_account_info(self) -> PosAccountInfo:
        """Fetch metadata for the connected POS account / merchant."""
        ...


class StubConnector:
    """In-memory stub implementation of PosConnector.

    Provides deterministic fixtures covering all required test scenarios:
    1. An item with both stock and multiple days of sales history (stub-item-001)
    2. An item with stock but zero sales transactions (stub-item-002)
    3. An item with sales transactions but no inventory tracking (stock is None) (stub-item-003)
    4. An item whose name is ambiguous between two plausible products (stub-item-004)
    5. An item with fewer days of history than a 30-day window (provisional figure) (stub-item-005)
    """

    def __init__(
        self,
        transactions: list[RawSalesTransaction] | None = None,
        inventory_levels: list[RawInventoryLevel] | None = None,
        account_info: PosAccountInfo | None = None,
    ) -> None:
        self._transactions = (
            list(transactions) if transactions is not None else self._default_transactions()
        )
        self._inventory_levels = (
            list(inventory_levels)
            if inventory_levels is not None
            else self._default_inventory_levels()
        )
        self._account_info = account_info or PosAccountInfo(
            account_id="stub-merchant-12345",
            account_name="ProcurePilot Demo POS Store",
        )

    @staticmethod
    def _default_inventory_levels() -> list[RawInventoryLevel]:
        return [
            # Case 1: Stock + sales history
            RawInventoryLevel(
                external_item_id="stub-item-001",
                item_name="Organic Whole Milk 1 Gallon",
                stock_on_hand=Decimal("45.0000"),
            ),
            # Case 2: Stock but zero sales
            RawInventoryLevel(
                external_item_id="stub-item-002",
                item_name="Stainless Steel Immersion Blender",
                stock_on_hand=Decimal("12.0000"),
            ),
            # Case 3: Sales transactions but no inventory tracking (stock is None)
            RawInventoryLevel(
                external_item_id="stub-item-003",
                item_name="Bakery Counter Custom Slicing Service",
                stock_on_hand=None,
            ),
            # Case 4: Ambiguous product name
            RawInventoryLevel(
                external_item_id="stub-item-004",
                item_name="Eco Friendly Hot Coffee Paper Cups 12oz",
                stock_on_hand=Decimal("150.0000"),
            ),
            # Case 5: Fewer days of history than 30-day window
            RawInventoryLevel(
                external_item_id="stub-item-005",
                item_name="Cold Brew Concentrate 1L Bottle",
                stock_on_hand=Decimal("20.0000"),
            ),
        ]

    @staticmethod
    def _default_transactions() -> list[RawSalesTransaction]:
        today = date.today()
        return [
            # Case 1: stub-item-001 has multiple days of sales history across 30 days
            RawSalesTransaction(
                transaction_id="stub-txn-101",
                external_item_id="stub-item-001",
                item_name="Organic Whole Milk 1 Gallon",
                quantity=Decimal("4.0000"),
                transaction_date=today - timedelta(days=25),
            ),
            RawSalesTransaction(
                transaction_id="stub-txn-102",
                external_item_id="stub-item-001",
                item_name="Organic Whole Milk 1 Gallon",
                quantity=Decimal("6.0000"),
                transaction_date=today - timedelta(days=20),
            ),
            RawSalesTransaction(
                transaction_id="stub-txn-103",
                external_item_id="stub-item-001",
                item_name="Organic Whole Milk 1 Gallon",
                quantity=Decimal("5.0000"),
                transaction_date=today - timedelta(days=15),
            ),
            RawSalesTransaction(
                transaction_id="stub-txn-104",
                external_item_id="stub-item-001",
                item_name="Organic Whole Milk 1 Gallon",
                quantity=Decimal("5.0000"),
                transaction_date=today - timedelta(days=10),
            ),
            RawSalesTransaction(
                transaction_id="stub-txn-105",
                external_item_id="stub-item-001",
                item_name="Organic Whole Milk 1 Gallon",
                quantity=Decimal("4.0000"),
                transaction_date=today - timedelta(days=3),
            ),
            # Case 2: stub-item-002 has ZERO sales transactions (deliberately omitted)
            # Case 3: stub-item-003 has sales transactions but no inventory tracking
            RawSalesTransaction(
                transaction_id="stub-txn-301",
                external_item_id="stub-item-003",
                item_name="Bakery Counter Custom Slicing Service",
                quantity=Decimal("2.0000"),
                transaction_date=today - timedelta(days=14),
            ),
            RawSalesTransaction(
                transaction_id="stub-txn-302",
                external_item_id="stub-item-003",
                item_name="Bakery Counter Custom Slicing Service",
                quantity=Decimal("3.0000"),
                transaction_date=today - timedelta(days=7),
            ),
            RawSalesTransaction(
                transaction_id="stub-txn-303",
                external_item_id="stub-item-003",
                item_name="Bakery Counter Custom Slicing Service",
                quantity=Decimal("4.0000"),
                transaction_date=today - timedelta(days=2),
            ),
            # Case 4: stub-item-004 has sales transactions
            RawSalesTransaction(
                transaction_id="stub-txn-401",
                external_item_id="stub-item-004",
                item_name="Eco Friendly Hot Coffee Paper Cups 12oz",
                quantity=Decimal("10.0000"),
                transaction_date=today - timedelta(days=18),
            ),
            RawSalesTransaction(
                transaction_id="stub-txn-402",
                external_item_id="stub-item-004",
                item_name="Eco Friendly Hot Coffee Paper Cups 12oz",
                quantity=Decimal("15.0000"),
                transaction_date=today - timedelta(days=6),
            ),
            # Case 5: stub-item-005 has fewer days of history than 30 days (only last 4 days)
            RawSalesTransaction(
                transaction_id="stub-txn-501",
                external_item_id="stub-item-005",
                item_name="Cold Brew Concentrate 1L Bottle",
                quantity=Decimal("3.0000"),
                transaction_date=today - timedelta(days=4),
            ),
            RawSalesTransaction(
                transaction_id="stub-txn-502",
                external_item_id="stub-item-005",
                item_name="Cold Brew Concentrate 1L Bottle",
                quantity=Decimal("2.0000"),
                transaction_date=today - timedelta(days=2),
            ),
            RawSalesTransaction(
                transaction_id="stub-txn-503",
                external_item_id="stub-item-005",
                item_name="Cold Brew Concentrate 1L Bottle",
                quantity=Decimal("5.0000"),
                transaction_date=today - timedelta(days=1),
            ),
        ]

    def build_authorization_url(self, state: str) -> str:
        from urllib.parse import urlencode

        params = {
            "client_id": "stub-square-app-id",
            "response_type": "code",
            "scope": "ITEMS_READ ORDERS_READ INVENTORY_READ MERCHANT_PROFILE_READ",
            "redirect_uri": "http://localhost:8000/api/v1/pos/connect/callback",
            "state": state,
        }
        return f"https://connect.squareup.com/oauth2/authorize?{urlencode(params)}"

    def exchange_code_for_tokens(
        self,
        code: str,
        redirect_uri: str | None = None,
    ) -> OAuthTokens:
        return OAuthTokens(
            access_token="stub-access-token",
            refresh_token="stub-refresh-token",
            merchant_id=self._account_info.account_id,
        )

    def refresh_access_token(self, refresh_token: str) -> OAuthTokens:
        return OAuthTokens(
            access_token="stub-refreshed-access-token",
            refresh_token="stub-new-refresh-token",
            merchant_id=self._account_info.account_id,
        )

    def list_sales_transactions(self, since: date) -> list[RawSalesTransaction]:
        return [t for t in self._transactions if t.transaction_date >= since]

    def list_inventory_levels(self) -> list[RawInventoryLevel]:
        return list(self._inventory_levels)

    def get_account_info(self) -> PosAccountInfo:
        return self._account_info


def get_pos_connector(
    settings: Settings | None = None,
    *,
    access_token: str | None = None,
) -> PosConnector:
    """Factory returning the active PosConnector based on configuration."""
    cfg = settings or get_settings()
    if cfg.pos_provider_mode == "square":
        from procurepilot_api.modules.pos.square_client import SquareClient

        return SquareClient(
            settings=cfg,
            access_token=access_token,
        )
    return StubConnector()

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from procurepilot_api.config import Settings, get_settings
from procurepilot_api.modules.catalogue.models import ProductList, ProductListStatus
from procurepilot_api.modules.catalogue.service import CatalogueService
from procurepilot_api.modules.orders.schemas import OrderEvidenceProjection, PurchaseOrderList
from procurepilot_api.modules.orders.service import OrdersService


class _OrdersReader(Protocol):
    def list_orders(
        self, *, bearer_token: str, cursor: str | None, limit: int
    ) -> PurchaseOrderList: ...

    def get_order(self, *, bearer_token: str, order_id: UUID) -> OrderEvidenceProjection: ...


class _CatalogueReader(Protocol):
    def list_products(
        self,
        *,
        bearer_token: str,
        cursor: str | None,
        limit: int,
        status: ProductListStatus,
        q: str | None,
    ) -> ProductList: ...


class PartnerService:
    """Provider-neutral read facade for external consumers.

    The delegated services retain the verified JWT and RLS boundary. This facade deliberately
    contains no mutation methods, API-key parsing, or tenant selection from request parameters.
    """

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        orders: _OrdersReader | None = None,
        catalogue: _CatalogueReader | None = None,
    ) -> None:
        active_settings = settings or get_settings()
        self._orders = orders or OrdersService(active_settings)
        self._catalogue = catalogue or CatalogueService(active_settings)

    def list_orders(
        self, *, bearer_token: str, cursor: str | None, limit: int
    ) -> PurchaseOrderList:
        return self._orders.list_orders(bearer_token=bearer_token, cursor=cursor, limit=limit)

    def get_order(self, *, bearer_token: str, order_id: UUID) -> OrderEvidenceProjection:
        return self._orders.get_order(bearer_token=bearer_token, order_id=order_id)

    def list_products(
        self,
        *,
        bearer_token: str,
        cursor: str | None,
        limit: int,
        status: ProductListStatus,
        q: str | None,
    ) -> ProductList:
        return self._catalogue.list_products(
            bearer_token=bearer_token,
            cursor=cursor,
            limit=limit,
            status=status,
            q=q,
        )


def get_partner_service() -> PartnerService:
    return PartnerService()

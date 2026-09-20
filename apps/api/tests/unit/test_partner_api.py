from __future__ import annotations

from uuid import UUID

from procurepilot_api.modules.partner.service import PartnerService

TENANT = UUID("00000000-0000-0000-0000-000000000001")
ORDER = UUID("00000000-0000-0000-0000-000000000003")


class _Orders:
    def list_orders(
        self, *, bearer_token: str, cursor: str | None, limit: int
    ) -> dict[str, object]:
        assert bearer_token == "partner-jwt"
        assert cursor == "cursor-1"
        assert limit == 25
        return {"items": [], "next_cursor": None}

    def get_order(self, *, bearer_token: str, order_id: UUID) -> dict[str, object]:
        assert bearer_token == "partner-jwt"
        assert order_id == ORDER
        return {"order": {"id": str(order_id), "tenant_id": str(TENANT)}}


class _Catalogue:
    def list_products(
        self,
        *,
        bearer_token: str,
        cursor: str | None,
        limit: int,
        status: str,
        q: str | None,
    ) -> dict[str, object]:
        assert bearer_token == "partner-jwt"
        assert (cursor, limit, status, q) == (None, 10, "active", "paper")
        return {"items": [], "next_cursor": None}


def test_partner_service_delegates_read_only_calls_with_verified_bearer_context() -> None:
    service = PartnerService(orders=_Orders(), catalogue=_Catalogue())

    assert service.list_orders(bearer_token="partner-jwt", cursor="cursor-1", limit=25) == {
        "items": [],
        "next_cursor": None,
    }
    order = service.get_order(bearer_token="partner-jwt", order_id=ORDER)
    assert order["order"]["tenant_id"] == str(TENANT)
    assert service.list_products(
        bearer_token="partner-jwt", cursor=None, limit=10, status="active", q="paper"
    ) == {"items": [], "next_cursor": None}

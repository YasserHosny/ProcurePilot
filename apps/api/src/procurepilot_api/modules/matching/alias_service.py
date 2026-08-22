from __future__ import annotations

from uuid import UUID

from postgrest.exceptions import APIError

from procurepilot_api.errors import ConflictError, ServiceUnavailableError

ALIAS_COLUMNS = "id,tenant_id,workspace_product_id,supplier_id,alias_text,created_by,created_at"


class AliasLearningService:
    def learn_or_reuse_alias(
        self,
        *,
        client: object,
        tenant_id: UUID,
        membership_id: UUID,
        workspace_product_id: UUID,
        supplier_id: UUID | None,
        alias_text: str,
    ) -> UUID:
        existing = self._find_alias(client, alias_text)
        if existing is not None:
            existing_product_id = UUID(str(existing["workspace_product_id"]))
            if existing_product_id != workspace_product_id:
                raise ConflictError(details={"reason": "alias_conflict"})
            return UUID(str(existing["id"]))
        try:
            response = (
                client.table("product_alias")
                .insert(
                    {
                        "tenant_id": str(tenant_id),
                        "workspace_product_id": str(workspace_product_id),
                        "supplier_id": str(supplier_id) if supplier_id else None,
                        "alias_text": alias_text,
                        "created_by": str(membership_id),
                    }
                )
                .execute()
            )
        except APIError as exc:
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc
        rows = _rows(response.data)
        if len(rows) != 1:
            raise ServiceUnavailableError(details={"reason": "alias_write_failed"})
        return UUID(str(rows[0]["id"]))

    def _find_alias(self, client: object, alias_text: str) -> dict[str, object] | None:
        try:
            response = (
                client.table("product_alias")
                .select(ALIAS_COLUMNS)
                .ilike("alias_text", alias_text)
                .limit(2)
                .execute()
            )
        except APIError as exc:
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc
        rows = [
            row
            for row in _rows(response.data)
            if str(row["alias_text"]).casefold() == alias_text.casefold()
        ]
        if len(rows) > 1:
            raise ServiceUnavailableError(details={"reason": "duplicate_alias_rows"})
        return rows[0] if rows else None


def _rows(data: object) -> list[dict[str, object]]:
    if isinstance(data, list) and all(isinstance(row, dict) for row in data):
        return data
    raise ServiceUnavailableError(details={"reason": "invalid_database_response"})

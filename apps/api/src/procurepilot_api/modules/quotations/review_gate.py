from __future__ import annotations

from uuid import UUID

from postgrest.exceptions import APIError

from procurepilot_api.errors import ServiceUnavailableError


def blocking_low_confidence_fields(
    client: object, quotation_id: UUID, confidence_threshold: float, *, supplier_id: object
) -> list[dict[str, object]]:
    """Return unresolved extraction evidence that must be acknowledged before confirmation."""
    try:
        rows = (
            client.table("field_extraction")
            .select("id,entity_type,entity_id,field_name")
            .eq("quotation_id", str(quotation_id))
            .lt("confidence", confidence_threshold)
            .is_("corrected_by", "null")
            .order("id")
            .execute()
            .data
        )
    except APIError as exc:
        raise ServiceUnavailableError(details={"dependency": "database"}) from exc
    return [
        {key: row[key] for key in ("id", "entity_type", "entity_id", "field_name")}
        for row in rows
        if row.get("field_name") != "suggested_currency"
        and not (row.get("field_name") == "supplier_name" and supplier_id is not None)
    ]

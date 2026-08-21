from __future__ import annotations

import base64
import json
from uuid import UUID

from postgrest.exceptions import APIError
from supabase import Client, create_client

from procurepilot_api.config import Settings, get_settings
from procurepilot_api.deps import CurrentMember
from procurepilot_api.errors import (
    ConflictError,
    NotFoundError,
    ServiceUnavailableError,
    UnprocessableEntityError,
    UnsupportedMediaTypeError,
)
from procurepilot_api.modules.billing.service import BillingService
from procurepilot_api.modules.catalogue.csv_import import (
    DuplicateAction,
    ImportErrorDetail,
    ImportValidationReport,
    commit_import,
    validate_import_file,
)
from procurepilot_api.modules.catalogue.import_repository import (
    PostgresImportRepository,
    with_database_duplicates,
)
from procurepilot_api.modules.catalogue.models import (
    Alias,
    AliasCreate,
    AliasList,
    BaseUnit,
    BaseUnitList,
    ImportErrorItem,
    ImportKind,
    ImportPreview,
    ImportResult,
    Money,
    PackDefinition,
    Product,
    ProductCreate,
    ProductList,
    ProductListStatus,
    ProductUpdate,
    SubstituteCreate,
    Supplier,
    SupplierCreate,
    SupplierList,
    SupplierListStatus,
    SupplierUpdate,
    money_columns,
)
from procurepilot_api.modules.catalogue.normalisation import decimal_to_string
from procurepilot_api.modules.matching.embeddings import StubEmbeddingProvider, vector_literal
from procurepilot_api.modules.members.service import authenticated_client
from procurepilot_api.shared.audit import AuditEventCreate, get_audit_writer

PRODUCT_COLUMNS = (
    "id,tenant_id,canonical_product_id,tenant_name,preferred_supplier_id,status,created_at"
)
CANONICAL_COLUMNS = "id,brand,name,variant,gtin,base_unit,created_at"
PACK_COLUMNS = "id,tenant_id,workspace_product_id,pack_count,unit_size,base_quantity,created_at"
SUBSTITUTE_COLUMNS = "workspace_product_id,substitute_product_id"
SUPPLIER_COLUMNS = (
    "id,tenant_id,name,payment_terms,lead_time_days,minimum_order_value_amount,"
    "minimum_order_value_currency,delivery_fee_amount,delivery_fee_currency,"
    "reliability_score,status,created_at"
)
ALIAS_COLUMNS = "id,tenant_id,workspace_product_id,supplier_id,alias_text,created_by,created_at"


class CatalogueService:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    def list_products(
        self,
        *,
        bearer_token: str,
        cursor: str | None = None,
        limit: int = 50,
        status: ProductListStatus = "active",
        q: str | None = None,
    ) -> ProductList:
        client = authenticated_client(self._settings, bearer_token)
        capped_limit = _cap_limit(limit)
        offset = _decode_cursor(cursor)
        try:
            query = client.table("workspace_product").select(PRODUCT_COLUMNS)
            if status != "all":
                query = query.eq("status", status)
            if q:
                query = query.ilike("tenant_name", f"%{q}%")
            response = query.order("created_at").order("id").range(
                offset,
                offset + capped_limit,
            ).execute()
        except APIError as exc:
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc

        rows = _rows(response.data)
        visible_rows = rows[:capped_limit]
        next_cursor = _encode_cursor(offset + capped_limit) if len(rows) > capped_limit else None
        return ProductList(
            items=self._products_from_rows(client, visible_rows),
            next_cursor=next_cursor,
        )

    def get_product(self, *, bearer_token: str, product_id: UUID) -> Product:
        client = authenticated_client(self._settings, bearer_token)
        row = self._product_row(client, product_id)
        return self._products_from_rows(client, [row])[0]

    def create_product(
        self,
        *,
        bearer_token: str,
        member: CurrentMember,
        payload: ProductCreate,
    ) -> Product:
        BillingService(self._settings).ensure_can_add_active_product(member=member)
        client = authenticated_client(self._settings, bearer_token)
        self._require_supplier_visible(client, payload.preferred_supplier_id)
        canonical = self._resolve_or_create_canonical(payload)
        product_payload = {
            "tenant_id": str(member.tenant_id),
            "canonical_product_id": str(canonical["id"]),
            "tenant_name": payload.tenant_name,
            "tenant_name_embedding": _embedding_literal(
                self._embedding_provider(), payload.tenant_name
            ),
            "tenant_name_embedding_model": self._embedding_provider().model,
            "preferred_supplier_id": (
                str(payload.preferred_supplier_id) if payload.preferred_supplier_id else None
            ),
        }
        try:
            product_response = client.table("workspace_product").insert(product_payload).execute()
            product = _one_row(product_response.data, reason="product_write_failed")
            pack_response = client.table("pack_definition").insert(
                {
                    "tenant_id": str(member.tenant_id),
                    "workspace_product_id": str(product["id"]),
                    "pack_count": payload.pack.pack_count,
                    "unit_size": payload.pack.unit_size,
                }
            ).execute()
            _one_row(pack_response.data, reason="pack_write_failed")
        except APIError as exc:
            raise _write_error(exc, duplicate_reason="product_exists") from exc

        created = self.get_product(bearer_token=bearer_token, product_id=UUID(str(product["id"])))
        self._record(
            bearer_token=bearer_token,
            member=member,
            action="catalogue.product_created",
            target={"product_id": str(created.id), "canonical_product_id": str(canonical["id"])},
        )
        return created

    def update_product(
        self,
        *,
        bearer_token: str,
        member: CurrentMember,
        product_id: UUID,
        patch: ProductUpdate,
    ) -> Product:
        client = authenticated_client(self._settings, bearer_token)
        existing = self._product_row(client, product_id)
        updates: dict[str, object] = {}
        if "tenant_name" in patch.model_fields_set:
            updates["tenant_name"] = patch.tenant_name
            if patch.tenant_name is not None:
                updates["tenant_name_embedding"] = _embedding_literal(
                    self._embedding_provider(), patch.tenant_name
                )
                updates["tenant_name_embedding_model"] = self._embedding_provider().model
        if "preferred_supplier_id" in patch.model_fields_set:
            self._require_supplier_visible(client, patch.preferred_supplier_id)
            updates["preferred_supplier_id"] = (
                str(patch.preferred_supplier_id) if patch.preferred_supplier_id else None
            )
        if "gtin" in patch.model_fields_set:
            canonical = self._canonical_row(UUID(str(existing["canonical_product_id"])))
            replacement = self._resolve_or_create_canonical_from_values(
                brand=_nullable_str(canonical.get("brand")),
                name=str(canonical["name"]),
                variant=_nullable_str(canonical.get("variant")),
                gtin=patch.gtin,
                base_unit=str(canonical["base_unit"]),
            )
            updates["canonical_product_id"] = str(replacement["id"])
        try:
            if updates:
                (
                    client.table("workspace_product")
                    .update(updates)
                    .eq("id", str(product_id))
                    .execute()
                )
            if patch.pack is not None:
                pack = self._single_pack_row(client, product_id)
                pack_payload = {
                    "pack_count": patch.pack.pack_count,
                    "unit_size": patch.pack.unit_size,
                }
                if pack is None:
                    client.table("pack_definition").insert(
                        {
                            "tenant_id": str(member.tenant_id),
                            "workspace_product_id": str(product_id),
                            **pack_payload,
                        }
                    ).execute()
                else:
                    client.table("pack_definition").update(pack_payload).eq(
                        "id",
                        str(pack["id"]),
                    ).execute()
        except APIError as exc:
            raise _write_error(exc, duplicate_reason="product_update_conflict") from exc

        updated = self.get_product(bearer_token=bearer_token, product_id=product_id)
        self._record(
            bearer_token=bearer_token,
            member=member,
            action="catalogue.product_updated",
            target={"product_id": str(product_id)},
        )
        return updated

    def archive_product(
        self,
        *,
        bearer_token: str,
        member: CurrentMember,
        product_id: UUID,
    ) -> None:
        client = authenticated_client(self._settings, bearer_token)
        try:
            response = (
                client.table("workspace_product")
                .update({"status": "archived"})
                .eq("id", str(product_id))
                .execute()
            )
        except APIError as exc:
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc
        _one_row_or_not_found(response.data, resource="product")
        self._record(
            bearer_token=bearer_token,
            member=member,
            action="catalogue.product_archived",
            target={"product_id": str(product_id)},
        )

    def add_substitute(
        self,
        *,
        bearer_token: str,
        member: CurrentMember,
        product_id: UUID,
        payload: SubstituteCreate,
    ) -> None:
        if product_id == payload.substitute_product_id:
            raise UnprocessableEntityError(
                details={"substitute_product_id": "cannot_match_product"}
            )
        client = authenticated_client(self._settings, bearer_token)
        self._product_row(client, product_id)
        self._product_row(client, payload.substitute_product_id)
        try:
            client.table("product_substitute").insert(
                {
                    "tenant_id": str(member.tenant_id),
                    "workspace_product_id": str(product_id),
                    "substitute_product_id": str(payload.substitute_product_id),
                }
            ).execute()
        except APIError as exc:
            raise _write_error(exc, duplicate_reason="substitute_exists") from exc
        self._record(
            bearer_token=bearer_token,
            member=member,
            action="catalogue.product_substitute_added",
            target={
                "product_id": str(product_id),
                "substitute_product_id": str(payload.substitute_product_id),
            },
        )

    def list_base_units(self, *, bearer_token: str) -> BaseUnitList:
        client = authenticated_client(self._settings, bearer_token)
        try:
            response = (
                client.table("supported_base_unit")
                .select("code,label_en,label_ar,dimension")
                .eq("is_enabled", True)
                .order("code")
                .execute()
            )
        except APIError as exc:
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc
        return BaseUnitList(items=[BaseUnit.model_validate(row) for row in _rows(response.data)])

    def list_suppliers(
        self,
        *,
        bearer_token: str,
        cursor: str | None = None,
        limit: int = 50,
        status: SupplierListStatus = "active",
    ) -> SupplierList:
        client = authenticated_client(self._settings, bearer_token)
        capped_limit = _cap_limit(limit)
        offset = _decode_cursor(cursor)
        try:
            query = client.table("supplier").select(SUPPLIER_COLUMNS)
            if status != "all":
                query = query.eq("status", status)
            response = query.order("created_at").order("id").range(
                offset,
                offset + capped_limit,
            ).execute()
        except APIError as exc:
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc
        rows = _rows(response.data)
        visible_rows = rows[:capped_limit]
        next_cursor = _encode_cursor(offset + capped_limit) if len(rows) > capped_limit else None
        return SupplierList(
            items=[_supplier(row) for row in visible_rows],
            next_cursor=next_cursor,
        )

    def get_supplier(self, *, bearer_token: str, supplier_id: UUID) -> Supplier:
        client = authenticated_client(self._settings, bearer_token)
        return _supplier(self._supplier_row(client, supplier_id))

    def create_supplier(
        self,
        *,
        bearer_token: str,
        member: CurrentMember,
        payload: SupplierCreate,
    ) -> Supplier:
        client = authenticated_client(self._settings, bearer_token)
        row = {
            "tenant_id": str(member.tenant_id),
            "name": payload.name,
            "payment_terms": payload.payment_terms,
            "lead_time_days": payload.lead_time_days,
            **money_columns("minimum_order_value", payload.minimum_order_value),
            **money_columns("delivery_fee", payload.delivery_fee),
        }
        try:
            response = client.table("supplier").insert(row).execute()
        except APIError as exc:
            raise _write_error(exc, duplicate_reason="supplier_conflict") from exc
        supplier = _supplier(_one_row(response.data, reason="supplier_write_failed"))
        self._record(
            bearer_token=bearer_token,
            member=member,
            action="catalogue.supplier_created",
            target={"supplier_id": str(supplier.id)},
        )
        return supplier

    def update_supplier(
        self,
        *,
        bearer_token: str,
        member: CurrentMember,
        supplier_id: UUID,
        patch: SupplierUpdate,
    ) -> Supplier:
        client = authenticated_client(self._settings, bearer_token)
        updates: dict[str, object] = {}
        for field in ("name", "payment_terms", "lead_time_days", "status"):
            if field in patch.model_fields_set:
                updates[field] = getattr(patch, field)
        if "minimum_order_value" in patch.model_fields_set:
            updates.update(money_columns("minimum_order_value", patch.minimum_order_value))
        if "delivery_fee" in patch.model_fields_set:
            updates.update(money_columns("delivery_fee", patch.delivery_fee))
        if not updates:
            return self.get_supplier(bearer_token=bearer_token, supplier_id=supplier_id)
        try:
            response = client.table("supplier").update(updates).eq("id", str(supplier_id)).execute()
        except APIError as exc:
            raise _write_error(exc, duplicate_reason="supplier_update_conflict") from exc
        supplier = _supplier(_one_row_or_not_found(response.data, resource="supplier"))
        self._record(
            bearer_token=bearer_token,
            member=member,
            action="catalogue.supplier_updated",
            target={"supplier_id": str(supplier_id)},
        )
        return supplier

    def archive_supplier(
        self,
        *,
        bearer_token: str,
        member: CurrentMember,
        supplier_id: UUID,
    ) -> None:
        client = authenticated_client(self._settings, bearer_token)
        self._supplier_row(client, supplier_id)
        if self._supplier_is_referenced(client, supplier_id):
            raise ConflictError(
                details={"reason": "supplier_referenced", "archive_available": True}
            )
        try:
            response = (
                client.table("supplier")
                .update({"status": "archived"})
                .eq("id", str(supplier_id))
                .execute()
            )
        except APIError as exc:
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc
        _one_row_or_not_found(response.data, resource="supplier")
        self._record(
            bearer_token=bearer_token,
            member=member,
            action="catalogue.supplier_archived",
            target={"supplier_id": str(supplier_id)},
        )

    def list_aliases(self, *, bearer_token: str) -> AliasList:
        client = authenticated_client(self._settings, bearer_token)
        try:
            response = (
                client.table("product_alias")
                .select(ALIAS_COLUMNS)
                .order("created_at", desc=True)
                .execute()
            )
        except APIError as exc:
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc
        return AliasList(items=[_alias(row) for row in _rows(response.data)])

    def create_alias(
        self,
        *,
        bearer_token: str,
        member: CurrentMember,
        payload: AliasCreate,
    ) -> Alias:
        client = authenticated_client(self._settings, bearer_token)
        self._product_row(client, payload.workspace_product_id)
        self._require_supplier_visible(client, payload.supplier_id)
        try:
            response = client.table("product_alias").insert(
                {
                    "tenant_id": str(member.tenant_id),
                    "workspace_product_id": str(payload.workspace_product_id),
                    "supplier_id": str(payload.supplier_id) if payload.supplier_id else None,
                    "alias_text": payload.alias_text,
                    "created_by": str(member.membership_id),
                }
            ).execute()
        except APIError as exc:
            raise _write_error(exc, duplicate_reason="alias_exists") from exc
        alias = _alias(_one_row(response.data, reason="alias_write_failed"))
        self._record(
            bearer_token=bearer_token,
            member=member,
            action="catalogue.alias_created",
            target={"alias_id": str(alias.id), "product_id": str(alias.workspace_product_id)},
        )
        return alias

    def remove_alias(
        self,
        *,
        bearer_token: str,
        member: CurrentMember,
        alias_id: UUID,
    ) -> None:
        client = authenticated_client(self._settings, bearer_token)
        try:
            response = client.table("product_alias").delete().eq("id", str(alias_id)).execute()
        except APIError as exc:
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc
        _one_row_or_not_found(response.data, resource="alias")
        self._record(
            bearer_token=bearer_token,
            member=member,
            action="catalogue.alias_removed",
            target={"alias_id": str(alias_id)},
        )

    def preview_import(
        self,
        *,
        member: CurrentMember,
        kind: ImportKind,
        filename: str,
        content: bytes,
        content_type: str | None,
    ) -> ImportPreview:
        report = validate_import_file(
            kind=kind,
            filename=filename,
            content=content,
            content_type=content_type,
        )
        if report.file_error == "not an accepted CSV file type":
            raise UnsupportedMediaTypeError(details={"file": "not_accepted_csv"})

        repository = PostgresImportRepository(self._settings, member)
        report = with_database_duplicates(report, repository)
        import_id = repository.create_import_job(report)
        return _import_preview(import_id, report)

    def commit_import_job(
        self,
        *,
        bearer_token: str,
        member: CurrentMember,
        import_id: UUID,
        on_duplicate: DuplicateAction = "skip",
    ) -> ImportResult:
        repository = PostgresImportRepository(self._settings, member)
        job = repository.load_import_job(import_id)
        if job["status"] == "committed":
            raise ConflictError(details={"reason": "import_already_committed"})
        if job["status"] != "previewed":
            raise ConflictError(details={"reason": "import_not_committable"})

        report = repository.load_import_report(job)
        if report is None:
            raise ConflictError(details={"reason": "import_payload_unavailable"})
        if not report.valid:
            raise ConflictError(details={"reason": "import_has_errors"})

        try:
            result = commit_import(
                report,
                repository,
                on_duplicate=on_duplicate,
                after_rows=lambda repo: repository.mark_committed(import_id),
            )
        except ValueError as exc:
            raise ConflictError(details={"reason": str(exc)}) from exc
        self._record(
            bearer_token=bearer_token,
            member=member,
            action="catalogue.import_committed",
            target={
                "import_id": str(import_id),
                "kind": job["kind"],
                "created": result.created,
                "skipped": result.skipped,
                "updated": result.updated,
            },
        )
        return ImportResult(
            import_id=import_id,
            created=result.created,
            skipped=result.skipped,
            updated=result.updated,
        )

    def _products_from_rows(self, client: Client, rows: list[dict[str, object]]) -> list[Product]:
        if not rows:
            return []
        canonical_ids = [str(row["canonical_product_id"]) for row in rows]
        product_ids = [str(row["id"]) for row in rows]
        try:
            canonical_rows = _rows(
                client.table("canonical_product")
                .select(CANONICAL_COLUMNS)
                .in_("id", canonical_ids)
                .execute()
                .data
            )
            pack_rows = _rows(
                client.table("pack_definition")
                .select(PACK_COLUMNS)
                .in_("workspace_product_id", product_ids)
                .order("created_at")
                .execute()
                .data
            )
            outgoing_substitute_rows = _rows(
                client.table("product_substitute")
                .select(SUBSTITUTE_COLUMNS)
                .in_("workspace_product_id", product_ids)
                .execute()
                .data
            )
            incoming_substitute_rows = _rows(
                client.table("product_substitute")
                .select(SUBSTITUTE_COLUMNS)
                .in_("substitute_product_id", product_ids)
                .execute()
                .data
            )
        except APIError as exc:
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc
        canonical_by_id = {str(row["id"]): row for row in canonical_rows}
        packs_by_product: dict[str, dict[str, object]] = {}
        for pack in pack_rows:
            product_id = str(pack["workspace_product_id"])
            if product_id in packs_by_product:
                raise ServiceUnavailableError(details={"reason": "multiple_pack_definitions"})
            packs_by_product[product_id] = pack
        substitutes_by_product: dict[str, list[UUID]] = {
            product_id: [] for product_id in product_ids
        }
        for substitute in outgoing_substitute_rows:
            product_id = str(substitute["workspace_product_id"])
            if product_id in substitutes_by_product:
                substitutes_by_product[product_id].append(
                    UUID(str(substitute["substitute_product_id"]))
                )
        for substitute in incoming_substitute_rows:
            product_id = str(substitute["substitute_product_id"])
            if product_id in substitutes_by_product:
                substitutes_by_product[product_id].append(
                    UUID(str(substitute["workspace_product_id"]))
                )
        return [
            _product(
                row,
                canonical_by_id.get(str(row["canonical_product_id"])),
                packs_by_product.get(str(row["id"])),
                substitutes_by_product.get(str(row["id"]), []),
            )
            for row in rows
        ]

    def _product_row(self, client: Client, product_id: UUID) -> dict[str, object]:
        try:
            response = (
                client.table("workspace_product")
                .select(PRODUCT_COLUMNS)
                .eq("id", str(product_id))
                .limit(2)
                .execute()
            )
        except APIError as exc:
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc
        return _one_row_or_not_found(response.data, resource="product")

    def _single_pack_row(self, client: Client, product_id: UUID) -> dict[str, object] | None:
        try:
            response = (
                client.table("pack_definition")
                .select(PACK_COLUMNS)
                .eq("workspace_product_id", str(product_id))
                .limit(2)
                .execute()
            )
        except APIError as exc:
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc
        rows = _rows(response.data)
        if len(rows) > 1:
            raise ServiceUnavailableError(details={"reason": "multiple_pack_definitions"})
        return rows[0] if rows else None

    def _supplier_row(self, client: Client, supplier_id: UUID) -> dict[str, object]:
        try:
            response = (
                client.table("supplier")
                .select(SUPPLIER_COLUMNS)
                .eq("id", str(supplier_id))
                .limit(2)
                .execute()
            )
        except APIError as exc:
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc
        return _one_row_or_not_found(response.data, resource="supplier")

    def _require_supplier_visible(
        self,
        client: Client,
        supplier_id: UUID | None,
    ) -> None:
        if supplier_id is None:
            return
        self._supplier_row(client, supplier_id)

    def _supplier_is_referenced(self, client: Client, supplier_id: UUID) -> bool:
        try:
            product_refs = _rows(
                client.table("workspace_product")
                .select("id")
                .eq("preferred_supplier_id", str(supplier_id))
                .limit(1)
                .execute()
                .data
            )
            alias_refs = _rows(
                client.table("product_alias")
                .select("id")
                .eq("supplier_id", str(supplier_id))
                .limit(1)
                .execute()
                .data
            )
        except APIError as exc:
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc
        return bool(product_refs or alias_refs)

    def _resolve_or_create_canonical(self, payload: ProductCreate) -> dict[str, object]:
        return self._resolve_or_create_canonical_from_values(
            brand=payload.brand,
            name=payload.canonical_name or payload.tenant_name,
            variant=payload.variant,
            gtin=payload.gtin,
            base_unit=payload.base_unit,
        )

    def _resolve_or_create_canonical_from_values(
        self,
        *,
        brand: str | None,
        name: str,
        variant: str | None,
        gtin: str | None,
        base_unit: str,
    ) -> dict[str, object]:
        row = self._find_canonical(
            brand=brand,
            name=name,
            variant=variant,
            gtin=gtin,
            base_unit=base_unit,
        )
        if row is not None:
            self._ensure_canonical_embedding(row)
            return row
        try:
            response = self._service_role_client().table("canonical_product").insert(
                {
                    "brand": brand,
                    "name": name,
                    "variant": variant,
                    "gtin": gtin,
                    "base_unit": base_unit,
                    "canonical_embedding": _embedding_literal(
                        self._embedding_provider(),
                        _canonical_embedding_text(
                            brand=brand,
                            name=name,
                            variant=variant,
                        ),
                    ),
                    "canonical_embedding_model": self._embedding_provider().model,
                }
            ).execute()
        except APIError as exc:
            if _api_error_code(exc) == "23505" and gtin:
                row = self._find_canonical(
                    brand=brand,
                    name=name,
                    variant=variant,
                    gtin=gtin,
                    base_unit=base_unit,
                )
                if row is not None:
                    self._ensure_canonical_embedding(row)
                    return row
            raise _write_error(exc, duplicate_reason="canonical_product_conflict") from exc
        return _one_row(response.data, reason="canonical_product_write_failed")

    def _canonical_row(self, canonical_product_id: UUID) -> dict[str, object]:
        try:
            response = (
                self._service_role_client()
                .table("canonical_product")
                .select(CANONICAL_COLUMNS)
                .eq("id", str(canonical_product_id))
                .limit(2)
                .execute()
            )
        except APIError as exc:
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc
        return _one_row(response.data, reason="canonical_product_not_found")

    def _find_canonical(
        self,
        *,
        brand: str | None,
        name: str,
        variant: str | None,
        gtin: str | None,
        base_unit: str,
    ) -> dict[str, object] | None:
        client = self._service_role_client()
        try:
            query = (
                client.table("canonical_product")
                .select(CANONICAL_COLUMNS)
                .eq("base_unit", base_unit)
            )
            if gtin:
                query = query.eq("gtin", gtin)
            else:
                query = query.eq("name", name)
                query = query.is_("gtin", "null")
                query = (
                    query.eq("brand", brand)
                    if brand is not None
                    else query.is_("brand", "null")
                )
                query = (
                    query.eq("variant", variant)
                    if variant is not None
                    else query.is_("variant", "null")
                )
            response = query.order("created_at").order("id").limit(1).execute()
        except APIError as exc:
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc
        rows = _rows(response.data)
        return rows[0] if rows else None

    def _service_role_client(self) -> Client:
        return create_client(
            self._settings.supabase_url,
            self._settings.supabase_service_role_key.get_secret_value(),
        )

    def _embedding_provider(self) -> StubEmbeddingProvider:
        return StubEmbeddingProvider(self._settings.matching_embedding_model)

    def _ensure_canonical_embedding(self, canonical: dict[str, object]) -> None:
        provider = self._embedding_provider()
        try:
            self._service_role_client().table("canonical_product").update(
                {
                    "canonical_embedding": _embedding_literal(
                        provider,
                        _canonical_embedding_text(
                            brand=_nullable_str(canonical.get("brand")),
                            name=str(canonical["name"]),
                            variant=_nullable_str(canonical.get("variant")),
                        ),
                    ),
                    "canonical_embedding_model": provider.model,
                }
            ).eq("id", str(canonical["id"])).execute()
        except APIError as exc:
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc

    def _record(
        self,
        *,
        bearer_token: str,
        member: CurrentMember,
        action: str,
        target: dict[str, object],
    ) -> None:
        get_audit_writer().record(
            AuditEventCreate(
                tenant_id=member.tenant_id,
                actor_membership_id=member.membership_id,
                actor_email=member.email,
                action=action,
                target=target,
                outcome="success",
            ),
            bearer_token=bearer_token,
        )


def _product(
    row: dict[str, object],
    canonical: dict[str, object] | None,
    pack: dict[str, object] | None,
    substitute_ids: list[UUID],
) -> Product:
    if canonical is None:
        raise ServiceUnavailableError(details={"reason": "canonical_product_not_readable"})
    if pack is None:
        raise ServiceUnavailableError(details={"reason": "pack_definition_not_readable"})
    return Product(
        id=UUID(str(row["id"])),
        tenant_name=str(row["tenant_name"]),
        brand=_nullable_str(canonical.get("brand")),
        canonical_name=str(canonical["name"]),
        variant=_nullable_str(canonical.get("variant")),
        gtin=_nullable_str(canonical.get("gtin")),
        base_unit=str(canonical["base_unit"]),
        pack=PackDefinition(
            pack_count=int(pack["pack_count"]),
            unit_size=decimal_to_string(pack["unit_size"], places=6) or "0.000000",
            base_quantity=decimal_to_string(pack["base_quantity"], places=6) or "0.000000",
        ),
        preferred_supplier_id=(
            UUID(str(row["preferred_supplier_id"])) if row.get("preferred_supplier_id") else None
        ),
        substitute_ids=substitute_ids,
        status=str(row["status"]),
        created_at=row.get("created_at"),
    )


def _supplier(row: dict[str, object]) -> Supplier:
    return Supplier(
        id=UUID(str(row["id"])),
        name=str(row["name"]),
        payment_terms=_nullable_str(row.get("payment_terms")),
        lead_time_days=(
            int(row["lead_time_days"]) if row.get("lead_time_days") is not None else None
        ),
        minimum_order_value=_money(
            row.get("minimum_order_value_amount"),
            row.get("minimum_order_value_currency"),
        ),
        delivery_fee=_money(row.get("delivery_fee_amount"), row.get("delivery_fee_currency")),
        reliability_score=decimal_to_string(row.get("reliability_score"), places=3),
        status=str(row["status"]),
        created_at=row.get("created_at"),
    )


def _alias(row: dict[str, object]) -> Alias:
    return Alias(
        id=UUID(str(row["id"])),
        workspace_product_id=UUID(str(row["workspace_product_id"])),
        supplier_id=UUID(str(row["supplier_id"])) if row.get("supplier_id") else None,
        alias_text=str(row["alias_text"]),
        created_at=row.get("created_at"),
    )


def _import_preview(import_id: UUID, report: ImportValidationReport) -> ImportPreview:
    return ImportPreview(
        import_id=import_id,
        kind=report.kind,
        row_count=report.row_count,
        valid=report.valid,
        missing_columns=list(report.missing_columns),
        unrecognised_columns=list(report.unrecognised_columns),
        duplicates=[_import_error(error) for error in report.duplicates],
        errors=[
            *[_import_error(error) for error in report.errors],
            *(
                [ImportErrorItem(line=0, column=None, reason=report.file_error)]
                if report.file_error
                else []
            ),
        ],
        preview=list(report.preview),
    )


def _import_error(error: ImportErrorDetail) -> ImportErrorItem:
    column = error.column
    return ImportErrorItem(
        line=int(error.line),
        column=str(column) if column is not None else None,
        reason=str(error.reason),
    )


def _money(amount: object, currency: object) -> Money | None:
    if amount is None and currency is None:
        return None
    if amount is None or currency is None:
        raise ServiceUnavailableError(details={"reason": "money_columns_inconsistent"})
    return Money(amount=decimal_to_string(amount, places=4) or "0.0000", currency=str(currency))


def _nullable_str(value: object) -> str | None:
    return str(value) if value is not None else None


def _embedding_literal(provider: StubEmbeddingProvider, text: str) -> str:
    return vector_literal(provider.embed(text))


def _canonical_embedding_text(
    *,
    brand: str | None,
    name: str,
    variant: str | None,
) -> str:
    return " ".join(part for part in (brand, name, variant) if part).strip()


def _rows(data: object) -> list[dict[str, object]]:
    if isinstance(data, list) and all(isinstance(row, dict) for row in data):
        return data
    raise ServiceUnavailableError(details={"dependency": "database"})


def _one_row(data: object, *, reason: str) -> dict[str, object]:
    rows = _rows(data)
    if len(rows) != 1:
        raise ServiceUnavailableError(details={"reason": reason})
    return rows[0]


def _one_row_or_not_found(data: object, *, resource: str) -> dict[str, object]:
    rows = _rows(data)
    if len(rows) == 0:
        raise NotFoundError(details={"resource": resource})
    if len(rows) != 1:
        raise ServiceUnavailableError(details={"reason": f"{resource}_write_ambiguous"})
    return rows[0]


def _cap_limit(limit: int) -> int:
    return max(1, min(limit, 100))


def _encode_cursor(offset: int) -> str:
    raw = json.dumps({"offset": offset}, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def _decode_cursor(cursor: str | None) -> int:
    if cursor is None:
        return 0
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii"))
        payload = json.loads(raw.decode("utf-8"))
        offset = payload["offset"]
    except (KeyError, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise UnprocessableEntityError(details={"cursor": "invalid"}) from exc
    if not isinstance(offset, int) or offset < 0:
        raise UnprocessableEntityError(details={"cursor": "invalid"})
    return offset


def _write_error(
    exc: APIError,
    *,
    duplicate_reason: str,
) -> ConflictError | ServiceUnavailableError | UnprocessableEntityError:
    code = _api_error_code(exc)
    if code in {"23503", "23514", "22P02"}:
        return UnprocessableEntityError(details={"reason": "database_constraint"})
    if code == "23505":
        return ConflictError(details={"reason": duplicate_reason})
    return ServiceUnavailableError(details={"dependency": "database"})


def _api_error_code(exc: APIError) -> str | None:
    code = getattr(exc, "code", None)
    return str(code) if code else None


def get_catalogue_service() -> CatalogueService:
    return CatalogueService()

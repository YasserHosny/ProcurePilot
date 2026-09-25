from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictStr, field_validator

from procurepilot_api.modules.catalogue.normalisation import (
    normalised_base_quantity_from_string,
    parse_decimal_string,
)

type ProductStatus = Literal["active", "archived"]
type ProductListStatus = Literal["active", "archived", "all"]
type SupplierStatus = Literal["active", "preferred", "blocked", "archived"]
type SupplierListStatus = Literal["active", "preferred", "blocked", "archived", "all"]
type UnitDimension = Literal["volume", "mass", "count"]
type ImportKind = Literal["products", "suppliers"]
type DuplicateAction = Literal["skip", "update"]

GTIN_PATTERN = re.compile(r"^(?:[0-9]{8}|[0-9]{12,14})$")


class StrictApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Money(StrictApiModel):
    amount: StrictStr = Field(pattern=r"^-?\d+(\.\d{1,4})?$")
    currency: StrictStr = Field(pattern=r"^[A-Z]{3}$")

    def decimal_amount(self) -> Decimal:
        return parse_decimal_string(self.amount, field="amount", max_scale=4)


class BaseUnit(BaseModel):
    code: str
    label_en: str
    label_ar: str
    dimension: UnitDimension


class BaseUnitList(BaseModel):
    items: list[BaseUnit]


class PackInput(StrictApiModel):
    pack_count: int = Field(ge=1, strict=True)
    unit_size: StrictStr

    @field_validator("pack_count")
    @classmethod
    def _pack_count_is_not_bool(cls, value: int) -> int:
        if isinstance(value, bool):
            raise ValueError("pack_count must be an integer")
        return value

    @field_validator("unit_size")
    @classmethod
    def _unit_size_is_positive_decimal(cls, value: str) -> str:
        normalised_base_quantity_from_string(1, value)
        return value


class PackDefinition(PackInput):
    base_quantity: str


class Product(BaseModel):
    id: UUID
    tenant_name: str
    brand: str | None = None
    canonical_name: str
    variant: str | None = None
    gtin: str | None = None
    base_unit: str
    pack: PackDefinition
    preferred_supplier_id: UUID | None = None
    substitute_ids: list[UUID] = Field(default_factory=list)
    status: ProductStatus
    created_at: datetime | None = None


class ProductList(BaseModel):
    items: list[Product]
    next_cursor: str | None = None


class ProductCreate(StrictApiModel):
    tenant_name: str = Field(min_length=1, max_length=200)
    brand: str | None = None
    canonical_name: str | None = Field(default=None, max_length=200)
    variant: str | None = None
    gtin: str | None = None
    base_unit: str
    pack: PackInput
    preferred_supplier_id: UUID | None = None

    @field_validator("gtin")
    @classmethod
    def _gtin_shape(cls, value: str | None) -> str | None:
        return _validate_gtin(value)


class ProductUpdate(StrictApiModel):
    tenant_name: str | None = Field(default=None, min_length=1, max_length=200)
    gtin: str | None = None
    pack: PackInput | None = None
    preferred_supplier_id: UUID | None = None

    @field_validator("gtin")
    @classmethod
    def _gtin_shape(cls, value: str | None) -> str | None:
        return _validate_gtin(value)


class SubstituteCreate(StrictApiModel):
    substitute_product_id: UUID


class Supplier(BaseModel):
    id: UUID
    name: str
    payment_terms: str | None = None
    lead_time_days: int | None = None
    minimum_order_value: Money | None = None
    delivery_fee: Money | None = None
    reliability_score: str | None = None
    contact_email: str | None = None
    status: SupplierStatus
    created_at: datetime | None = None


class SupplierList(BaseModel):
    items: list[Supplier]
    next_cursor: str | None = None


class SupplierCreate(StrictApiModel):
    name: str = Field(min_length=1, max_length=200)
    payment_terms: str | None = None
    lead_time_days: int | None = Field(default=None, ge=0)
    minimum_order_value: Money | None = None
    delivery_fee: Money | None = None
    contact_email: str | None = None


class SupplierUpdate(StrictApiModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    payment_terms: str | None = None
    lead_time_days: int | None = Field(default=None, ge=0)
    minimum_order_value: Money | None = None
    delivery_fee: Money | None = None
    contact_email: str | None = None
    status: SupplierStatus | None = None


class Alias(BaseModel):
    id: UUID
    workspace_product_id: UUID
    supplier_id: UUID | None = None
    alias_text: str
    created_at: datetime | None = None


class AliasList(BaseModel):
    items: list[Alias]


class AliasCreate(StrictApiModel):
    workspace_product_id: UUID
    supplier_id: UUID | None = None
    alias_text: str = Field(min_length=1, max_length=500)


class ImportErrorItem(BaseModel):
    line: int
    column: str | None = None
    reason: str


class ImportPreview(BaseModel):
    import_id: UUID
    kind: ImportKind
    row_count: int
    valid: bool
    missing_columns: list[str] = Field(default_factory=list)
    unrecognised_columns: list[str] = Field(default_factory=list)
    duplicates: list[ImportErrorItem] = Field(default_factory=list)
    errors: list[ImportErrorItem] = Field(default_factory=list)
    preview: list[dict[str, object]] = Field(default_factory=list)


class ImportCommitRequest(StrictApiModel):
    on_duplicate: DuplicateAction = "skip"


class ImportResult(BaseModel):
    import_id: UUID
    created: int
    skipped: int
    updated: int


def _validate_gtin(value: str | None) -> str | None:
    if value is None:
        return None
    if not GTIN_PATTERN.fullmatch(value):
        raise ValueError("gtin must be GTIN-8, GTIN-12, GTIN-13 or GTIN-14 digits")
    return value


def money_columns(prefix: str, money: Money | None) -> dict[str, str | None]:
    if money is None:
        return {f"{prefix}_amount": None, f"{prefix}_currency": None}
    return {
        f"{prefix}_amount": str(money.decimal_amount()),
        f"{prefix}_currency": money.currency,
    }

"""Provider-neutral supplier catalogue connector boundary (R3.4)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Protocol, runtime_checkable

from procurepilot_api.config import Settings, get_settings
from procurepilot_api.modules.ingestion.catalogue_parser import parse_catalogue_file


def _currency(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Z]{3}", value.upper()):
        raise ValueError("currency must be an uppercase 3-letter code")
    return value.upper()


def _amount(value: Decimal) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite() or value < 0:
        raise ValueError("unit_price_amount must be a finite non-negative Decimal")
    return value


@dataclass(frozen=True)
class NormalizedCatalogueRow:
    """One provider-neutral catalogue price observation."""

    provider_record_id: str
    product_name: str
    unit_price_amount: Decimal
    unit_price_currency: str
    base_unit: str
    observed_at: datetime
    valid_from: datetime
    valid_to: datetime | None = None
    supplier_sku: str | None = None

    def __post_init__(self) -> None:
        if not self.provider_record_id.strip():
            raise ValueError("provider_record_id must not be empty")
        if not self.product_name.strip():
            raise ValueError("product_name must not be empty")
        if not self.base_unit.strip():
            raise ValueError("base_unit must not be empty")
        _amount(self.unit_price_amount)
        object.__setattr__(self, "unit_price_currency", _currency(self.unit_price_currency))
        if self.valid_to is not None and self.valid_to < self.valid_from:
            raise ValueError("valid_to must not precede valid_from")
        for field_name in ("observed_at", "valid_from"):
            value = getattr(self, field_name)
            if value.tzinfo is None:
                object.__setattr__(self, field_name, value.replace(tzinfo=UTC))


@dataclass(frozen=True)
class CataloguePage:
    rows: tuple[NormalizedCatalogueRow, ...]
    next_cursor: str | None = None
    errors: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.rows, tuple) or any(
            not isinstance(row, NormalizedCatalogueRow) for row in self.rows
        ):
            raise ValueError("rows must be a tuple of NormalizedCatalogueRow")


@runtime_checkable
class CatalogueConnector(Protocol):
    """Read-only provider interface for supplier catalogue observations."""

    def list_catalogue(
        self,
        *,
        since: datetime | None = None,
        cursor: str | None = None,
        limit: int = 100,
    ) -> CataloguePage:
        ...


class StubCatalogueConnector:
    """Deterministic no-network connector for tests and development."""

    def __init__(self, rows: tuple[NormalizedCatalogueRow, ...] = ()) -> None:
        self._rows = rows

    def list_catalogue(
        self,
        *,
        since: datetime | None = None,
        cursor: str | None = None,
        limit: int = 100,
    ) -> CataloguePage:
        del cursor
        if limit < 1 or limit > 100:
            raise ValueError("limit must be between 1 and 100")
        rows = tuple(row for row in self._rows if since is None or row.observed_at > since)
        page = rows[:limit]
        return CataloguePage(rows=page, next_cursor=str(limit) if len(rows) > limit else None)


class CsvCatalogueConnector:
    """Normalize an uploaded supplier CSV using the established catalogue parser."""

    def __init__(
        self,
        content: bytes,
        *,
        filename: str,
        observed_at: datetime,
        default_base_unit: str,
        valid_to: datetime | None = None,
    ) -> None:
        if not default_base_unit.strip():
            raise ValueError("default_base_unit must not be empty")
        self._filename = filename
        self._observed_at = observed_at if observed_at.tzinfo else observed_at.replace(tzinfo=UTC)
        report = parse_catalogue_file(content, file_format="csv")
        self._rows = tuple(
            NormalizedCatalogueRow(
                provider_record_id=f"{filename}:{row.row_number}",
                product_name=row.product_name,
                unit_price_amount=row.unit_price_amount,
                unit_price_currency=row.unit_price_currency,
                base_unit=row.unit or default_base_unit,
                observed_at=self._observed_at,
                valid_from=self._observed_at,
                valid_to=valid_to,
            )
            for row in report.valid_rows
        )
        self._errors = tuple(
            f"row {error.row_number}: {error.error}" for error in report.error_rows
        )

    def list_catalogue(
        self,
        *,
        since: datetime | None = None,
        cursor: str | None = None,
        limit: int = 100,
    ) -> CataloguePage:
        del cursor
        if limit < 1 or limit > 100:
            raise ValueError("limit must be between 1 and 100")
        if since is not None and self._observed_at <= since:
            rows: tuple[NormalizedCatalogueRow, ...] = ()
        else:
            rows = self._rows[:limit]
        return CataloguePage(
            rows=rows,
            next_cursor=None,
            errors=self._errors,
        )


def get_catalogue_connector(settings: Settings | None = None) -> CatalogueConnector:
    cfg = settings or get_settings()
    if cfg.catalogue_provider_mode == "stub":
        return StubCatalogueConnector()
    raise ValueError(f"Unsupported catalogue provider mode: {cfg.catalogue_provider_mode}")

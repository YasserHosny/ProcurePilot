from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from procurepilot_api.config import Settings
from procurepilot_api.deps import CurrentMember
from procurepilot_api.errors import ConflictError, NotFoundError, ServiceUnavailableError
from procurepilot_api.modules.catalogue.csv_import import (
    ImportErrorDetail,
    ImportRepository,
    ImportValidationReport,
    MoneyValue,
    ProductImportRow,
    SupplierImportRow,
)

IMPORT_JOB_COLUMNS = (
    "id,tenant_id,kind,filename,status,row_count,error_report,created_by,created_at,committed_at"
)


class PostgresImportRepository(ImportRepository):
    def __init__(self, settings: Settings, member: CurrentMember) -> None:
        self._database_url = settings.database_url.get_secret_value()
        self._member = member
        self._conn: psycopg.Connection[dict[str, Any]] | None = None
        self._tx: object | None = None

    def create_import_job(self, report: ImportValidationReport) -> UUID:
        status = "previewed" if report.valid else "refused"
        with self._connection() as conn:
            with conn.transaction():
                _act_as(conn, self._member)
                row = conn.execute(
                    "insert into import_job "
                    "(tenant_id,kind,filename,status,row_count,error_report,created_by) "
                    "values (%s,%s,%s,'validating',0,'[]'::jsonb,%s) "
                    f"returning {IMPORT_JOB_COLUMNS}",
                    (
                        self._member.tenant_id,
                        report.kind,
                        report.filename,
                        self._member.membership_id,
                    ),
                ).fetchone()
                if row is None:
                    raise ServiceUnavailableError(details={"reason": "import_job_write_failed"})
                row = conn.execute(
                    "update import_job set status = %s, row_count = %s, error_report = %s "
                    "where id = %s "
                    f"returning {IMPORT_JOB_COLUMNS}",
                    (
                        status,
                        report.row_count,
                        json.dumps(_stored_error_report(report)),
                        row["id"],
                    ),
                ).fetchone()
                if row is None:
                    raise ServiceUnavailableError(details={"reason": "import_job_write_failed"})

        import_id = UUID(str(row["id"]))
        return import_id

    def load_import_job(self, import_id: UUID) -> dict[str, Any]:
        with self._connection() as conn:
            _act_as(conn, self._member)
            row = conn.execute(
                f"select {IMPORT_JOB_COLUMNS} from import_job where id = %s limit 1",
                (import_id,),
            ).fetchone()
        if row is None:
            raise NotFoundError(details={"resource": "import"})
        return row

    def load_import_report(self, job: dict[str, Any]) -> ImportValidationReport | None:
        error_report = job.get("error_report")
        if not isinstance(error_report, dict):
            return None
        payload = error_report.get("validated_report")
        if not isinstance(payload, dict):
            return None
        return _report_from_payload(payload, job)

    @contextmanager
    def transaction(self) -> Iterator[None]:
        with self._connection() as conn:
            with conn.transaction() as tx:
                self._conn = conn
                self._tx = tx
                try:
                    _act_as(conn, self._member)
                    yield
                finally:
                    self._tx = None
                    self._conn = None

    def find_product_duplicate(self, row: ProductImportRow) -> dict[str, Any] | None:
        conn = self._active_conn()
        if row.gtin:
            duplicate = conn.execute(
                "select wp.id, wp.canonical_product_id "
                "from workspace_product wp "
                "join canonical_product cp on cp.id = wp.canonical_product_id "
                "where wp.tenant_id = %s and cp.gtin = %s "
                "order by wp.created_at, wp.id limit 1",
                (self._member.tenant_id, row.gtin),
            ).fetchone()
        else:
            duplicate = conn.execute(
                "select wp.id, wp.canonical_product_id "
                "from workspace_product wp "
                "join canonical_product cp on cp.id = wp.canonical_product_id "
                "where wp.tenant_id = %s and cp.name = %s and cp.base_unit = %s "
                "and cp.gtin is null "
                "order by wp.created_at, wp.id limit 1",
                (
                    self._member.tenant_id,
                    row.canonical_name or row.tenant_name,
                    row.base_unit,
                ),
            ).fetchone()
        return duplicate

    def create_product(self, row: ProductImportRow) -> None:
        conn = self._active_conn()
        canonical_id = self._resolve_or_create_canonical(row)
        product = conn.execute(
            "insert into workspace_product "
            "(tenant_id,canonical_product_id,tenant_name,preferred_supplier_id) "
            "values (%s,%s,%s,%s) returning id",
            (
                self._member.tenant_id,
                canonical_id,
                row.tenant_name,
                row.preferred_supplier_id,
            ),
        ).fetchone()
        if product is None:
            raise ServiceUnavailableError(details={"reason": "product_write_failed"})
        conn.execute(
            "insert into pack_definition "
            "(tenant_id,workspace_product_id,pack_count,unit_size) values (%s,%s,%s,%s)",
            (self._member.tenant_id, product["id"], row.pack_count, row.unit_size),
        )

    def update_product(self, duplicate: object, row: ProductImportRow) -> None:
        conn = self._active_conn()
        duplicate_row = _dict_duplicate(duplicate)
        canonical_id = self._resolve_or_create_canonical(row)
        conn.execute(
            "update workspace_product "
            "set canonical_product_id = %s, tenant_name = %s, preferred_supplier_id = %s "
            "where id = %s",
            (
                canonical_id,
                row.tenant_name,
                row.preferred_supplier_id,
                duplicate_row["id"],
            ),
        )
        updated_pack = conn.execute(
            "update pack_definition set pack_count = %s, unit_size = %s "
            "where workspace_product_id = %s returning id",
            (row.pack_count, row.unit_size, duplicate_row["id"]),
        ).fetchone()
        if updated_pack is None:
            conn.execute(
                "insert into pack_definition "
                "(tenant_id,workspace_product_id,pack_count,unit_size) values (%s,%s,%s,%s)",
                (self._member.tenant_id, duplicate_row["id"], row.pack_count, row.unit_size),
            )

    def find_supplier_duplicate(self, row: SupplierImportRow) -> dict[str, Any] | None:
        return self._active_conn().execute(
            "select id from supplier where tenant_id = %s and lower(name) = lower(%s) "
            "order by created_at, id limit 1",
            (self._member.tenant_id, row.name),
        ).fetchone()

    def create_supplier(self, row: SupplierImportRow) -> None:
        self._active_conn().execute(
            "insert into supplier "
            "(tenant_id,name,payment_terms,lead_time_days,"
            "minimum_order_value_amount,minimum_order_value_currency,"
            "delivery_fee_amount,delivery_fee_currency,status) "
            "values (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                self._member.tenant_id,
                row.name,
                row.payment_terms,
                row.lead_time_days,
                _money_amount(row.minimum_order_value),
                _money_currency(row.minimum_order_value),
                _money_amount(row.delivery_fee),
                _money_currency(row.delivery_fee),
                row.status,
            ),
        )

    def update_supplier(self, duplicate: object, row: SupplierImportRow) -> None:
        duplicate_row = _dict_duplicate(duplicate)
        self._active_conn().execute(
            "update supplier set "
            "name = %s, payment_terms = %s, lead_time_days = %s, "
            "minimum_order_value_amount = %s, minimum_order_value_currency = %s, "
            "delivery_fee_amount = %s, delivery_fee_currency = %s, status = %s "
            "where id = %s",
            (
                row.name,
                row.payment_terms,
                row.lead_time_days,
                _money_amount(row.minimum_order_value),
                _money_currency(row.minimum_order_value),
                _money_amount(row.delivery_fee),
                _money_currency(row.delivery_fee),
                row.status,
                duplicate_row["id"],
            ),
        )

    def mark_committed(self, import_id: UUID) -> None:
        conn = self._active_conn()
        row = conn.execute(
            "update import_job set status = 'committed', committed_at = %s "
            "where id = %s and tenant_id = %s and status = 'previewed' "
            f"returning {IMPORT_JOB_COLUMNS}",
            (datetime.now(UTC), import_id, self._member.tenant_id),
        ).fetchone()
        if row is None:
            raise ConflictError(details={"reason": "import_not_committable"})

    def _resolve_or_create_canonical(self, row: ProductImportRow) -> UUID:
        conn = self._active_conn()
        name = row.canonical_name or row.tenant_name
        if row.gtin:
            existing = conn.execute(
                "select id from canonical_product where gtin = %s limit 1",
                (row.gtin,),
            ).fetchone()
        else:
            existing = conn.execute(
                "select id from canonical_product "
                "where name = %s and base_unit = %s and gtin is null "
                "and brand is not distinct from %s and variant is not distinct from %s "
                "limit 1",
                (name, row.base_unit, row.brand, row.variant),
            ).fetchone()
        if existing is not None:
            return UUID(str(existing["id"]))

        # canonical_product is the deliberate non-tenant shared spine; it has no tenant policy.
        current_role = conn.execute("select current_role").fetchone()
        conn.execute("reset role")
        try:
            inserted = conn.execute(
                "insert into canonical_product (brand,name,variant,gtin,base_unit) "
                "values (%s,%s,%s,%s,%s) returning id",
                (row.brand, name, row.variant, row.gtin, row.base_unit),
            ).fetchone()
        finally:
            if current_role is not None and current_role["current_role"] == "authenticated":
                _act_as(conn, self._member)
        if inserted is None:
            raise ServiceUnavailableError(details={"reason": "canonical_product_write_failed"})
        return UUID(str(inserted["id"]))

    def _connection(self) -> psycopg.Connection[dict[str, Any]]:
        return psycopg.connect(self._database_url, row_factory=dict_row)

    def _active_conn(self) -> psycopg.Connection[dict[str, Any]]:
        if self._conn is None:
            raise RuntimeError("import repository write called outside a transaction")
        return self._conn


def with_database_duplicates(
    report: ImportValidationReport,
    repository: PostgresImportRepository,
) -> ImportValidationReport:
    if not report.valid:
        return report
    duplicates: list[ImportErrorDetail] = list(report.duplicates)
    with repository.transaction():
        for row in report.rows:
            duplicate = (
                repository.find_product_duplicate(row)
                if isinstance(row, ProductImportRow)
                else repository.find_supplier_duplicate(row)
            )
            if duplicate is not None:
                duplicates.append(
                    ImportErrorDetail(
                        line=row.line,
                        column=None,
                        reason="duplicate existing record",
                    )
                )
    return replace(report, duplicates=tuple(duplicates))


def _act_as(conn: psycopg.Connection[dict[str, Any]], member: CurrentMember) -> None:
    claims = {
        "sub": str(member.user_id),
        "tenant_id": str(member.tenant_id),
        "role": "authenticated",
        "member_role": member.role.value,
    }
    conn.execute("set local role authenticated")
    conn.execute("select set_config('request.jwt.claims', %s, true)", (json.dumps(claims),))


def _error_report(report: ImportValidationReport) -> list[dict[str, object]]:
    details = [
        _error_detail(error)
        for error in (*report.errors, *report.duplicates)
    ]
    if report.file_error is not None:
        details.append({"line": 0, "column": None, "reason": report.file_error})
    return details


def _stored_error_report(report: ImportValidationReport) -> dict[str, object]:
    return {
        "errors": _error_report(report),
        "duplicates": [_error_detail(error) for error in report.duplicates],
        "file_error": report.file_error,
        "validated_report": _report_payload(report) if report.valid else None,
    }


def _report_payload(report: ImportValidationReport) -> dict[str, object]:
    return {
        "kind": report.kind,
        "filename": report.filename,
        "row_count": report.row_count,
        "missing_columns": list(report.missing_columns),
        "unrecognised_columns": list(report.unrecognised_columns),
        "duplicates": [_error_detail(error) for error in report.duplicates],
        "errors": [_error_detail(error) for error in report.errors],
        "rows": [_row_payload(row) for row in report.rows],
    }


def _row_payload(row: ProductImportRow | SupplierImportRow) -> dict[str, object]:
    if isinstance(row, ProductImportRow):
        return {
            "type": "product",
            "line": row.line,
            "tenant_name": row.tenant_name,
            "base_unit": row.base_unit,
            "pack_count": row.pack_count,
            "unit_size": str(row.unit_size),
            "canonical_name": row.canonical_name,
            "brand": row.brand,
            "variant": row.variant,
            "gtin": row.gtin,
            "preferred_supplier_id": (
                str(row.preferred_supplier_id) if row.preferred_supplier_id else None
            ),
        }
    return {
        "type": "supplier",
        "line": row.line,
        "name": row.name,
        "payment_terms": row.payment_terms,
        "lead_time_days": row.lead_time_days,
        "minimum_order_value": _money_payload(row.minimum_order_value),
        "delivery_fee": _money_payload(row.delivery_fee),
        "status": row.status,
    }


def _money_payload(value: MoneyValue | None) -> dict[str, str] | None:
    if value is None:
        return None
    return {"amount": str(value.amount), "currency": value.currency}


def _report_from_payload(
    payload: dict[str, object],
    job: dict[str, Any],
) -> ImportValidationReport:
    return ImportValidationReport(
        kind=_payload_str(payload, "kind"),  # type: ignore[arg-type]
        filename=str(job["filename"]),
        row_count=int(payload["row_count"]),
        rows=tuple(_row_from_payload(row) for row in _payload_list(payload, "rows")),
        missing_columns=tuple(str(value) for value in _payload_list(payload, "missing_columns")),
        unrecognised_columns=tuple(
            str(value) for value in _payload_list(payload, "unrecognised_columns")
        ),
        duplicates=tuple(
            _error_from_payload(error) for error in _payload_list(payload, "duplicates")
        ),
        errors=tuple(_error_from_payload(error) for error in _payload_list(payload, "errors")),
    )


def _row_from_payload(payload: object) -> ProductImportRow | SupplierImportRow:
    if not isinstance(payload, dict):
        raise ValueError("invalid stored import row")
    row_type = payload.get("type")
    if row_type == "product":
        preferred_supplier_id = payload.get("preferred_supplier_id")
        return ProductImportRow(
            line=int(payload["line"]),
            tenant_name=str(payload["tenant_name"]),
            base_unit=str(payload["base_unit"]),
            pack_count=int(payload["pack_count"]),
            unit_size=Decimal(str(payload["unit_size"])),
            canonical_name=_optional_payload_str(payload.get("canonical_name")),
            brand=_optional_payload_str(payload.get("brand")),
            variant=_optional_payload_str(payload.get("variant")),
            gtin=_optional_payload_str(payload.get("gtin")),
            preferred_supplier_id=UUID(str(preferred_supplier_id))
            if preferred_supplier_id
            else None,
        )
    if row_type == "supplier":
        return SupplierImportRow(
            line=int(payload["line"]),
            name=str(payload["name"]),
            payment_terms=_optional_payload_str(payload.get("payment_terms")),
            lead_time_days=int(payload["lead_time_days"])
            if payload.get("lead_time_days") is not None
            else None,
            minimum_order_value=_money_from_payload(payload.get("minimum_order_value")),
            delivery_fee=_money_from_payload(payload.get("delivery_fee")),
            status=str(payload.get("status") or "active"),  # type: ignore[arg-type]
        )
    raise ValueError("invalid stored import row type")


def _money_from_payload(payload: object) -> MoneyValue | None:
    if payload is None:
        return None
    if not isinstance(payload, dict):
        raise ValueError("invalid stored money value")
    return MoneyValue(amount=Decimal(str(payload["amount"])), currency=str(payload["currency"]))


def _error_from_payload(payload: object) -> ImportErrorDetail:
    if not isinstance(payload, dict):
        raise ValueError("invalid stored import error")
    column = payload.get("column")
    return ImportErrorDetail(
        line=int(payload["line"]),
        column=str(column) if column is not None else None,
        reason=str(payload["reason"]),
    )


def _payload_list(payload: dict[str, object], key: str) -> list[object]:
    value = payload.get(key, [])
    if isinstance(value, list):
        return value
    raise ValueError(f"invalid stored import {key}")


def _payload_str(payload: dict[str, object], key: str) -> str:
    value = payload.get(key)
    if isinstance(value, str):
        return value
    raise ValueError(f"invalid stored import {key}")


def _optional_payload_str(value: object) -> str | None:
    return str(value) if value is not None else None


def _error_detail(error: ImportErrorDetail) -> dict[str, object]:
    return {"line": error.line, "column": error.column, "reason": error.reason}


def _money_amount(value: MoneyValue | None) -> Decimal | None:
    return value.amount if value is not None else None


def _money_currency(value: MoneyValue | None) -> str | None:
    return value.currency if value is not None else None


def _dict_duplicate(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    raise TypeError("expected duplicate row mapping")

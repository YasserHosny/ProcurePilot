from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb

from integration.catalogue_helpers import Workspace, act_as


@dataclass(frozen=True)
class QuotationFixture:
    document_id: UUID
    quotation_id: UUID
    supplier_id: UUID
    line_id: UUID
    field_id: UUID
    storage_path: str


def ensure_quotation_reference_data(cur: psycopg.Cursor) -> None:
    """`supported_base_unit` grants INSERT to service_role only (chunk 4.2 RLS). Callers may
    already be mid-test in `authenticated` role from an earlier fixture in the same connection,
    so this must not assume it is the first statement run — reset role first, every time."""
    current_role = cur.execute("select current_role").fetchone()
    cur.execute("reset role")
    try:
        cur.execute(
            "insert into supported_base_unit (code,label_en,label_ar,dimension,is_enabled) "
            "values ('kg','Kilogram','كيلوغرام','mass',true) on conflict do nothing"
        )
        cur.execute(
            "insert into supported_base_unit (code,label_en,label_ar,dimension,is_enabled) "
            "values ('litre','Litre','لتر','volume',true) on conflict do nothing"
        )
    finally:
        if current_role is not None and current_role[0] == "authenticated":
            cur.execute("set local role authenticated")


def make_supplier(cur: psycopg.Cursor, workspace: Workspace, name: str = "Fresh Supplier") -> UUID:
    supplier_id = uuid4()
    act_as(cur, workspace)
    cur.execute(
        "insert into supplier (id,tenant_id,name) values (%s,%s,%s)",
        (supplier_id, workspace.tenant_id, name),
    )
    return supplier_id


def make_document(
    cur: psycopg.Cursor,
    workspace: Workspace,
    *,
    mime_type: str = "application/pdf",
    filename: str = "quote.pdf",
) -> UUID:
    document_id = uuid4()
    storage_path = f"tenants/{workspace.tenant_id}/quotations/{document_id}/{filename}"
    act_as(cur, workspace)
    cur.execute(
        "insert into document "
        "(id,tenant_id,storage_bucket,storage_path,mime_type,content_hash,created_by) "
        "values (%s,%s,'quotation-documents',%s,%s,%s,%s)",
        (
            document_id,
            workspace.tenant_id,
            storage_path,
            mime_type,
            f"hash-{document_id}",
            workspace.membership_id,
        ),
    )
    return document_id


def make_quotation(
    cur: psycopg.Cursor,
    workspace: Workspace,
    *,
    document_id: UUID | None = None,
    supplier_id: UUID | None = None,
    status: str = "pending",
    arithmetic_status: str | None = None,
) -> UUID:
    quotation_id = uuid4()
    document_id = document_id or make_document(cur, workspace)
    act_as(cur, workspace)
    cur.execute(
        "insert into quotation "
        "(id,tenant_id,document_id,supplier_id,status,currency,arithmetic_status) "
        "values (%s,%s,%s,%s,%s,'GBP',%s)",
        (quotation_id, workspace.tenant_id, document_id, supplier_id, status, arithmetic_status),
    )
    return quotation_id


def make_line(cur: psycopg.Cursor, workspace: Workspace, quotation_id: UUID) -> UUID:
    line_id = uuid4()
    act_as(cur, workspace)
    cur.execute(
        "insert into quotation_line "
        "(id,tenant_id,quotation_id,line_number,original_text,quantity,pack_count,unit_size,"
        "pack_unit,unit_price_amount,unit_price_currency) "
        "values (%s,%s,%s,1,'Tomatoes case 10 kg',2,1,10,'kg',12,'GBP')",
        (line_id, workspace.tenant_id, quotation_id),
    )
    return line_id


def make_field(
    cur: psycopg.Cursor,
    workspace: Workspace,
    quotation_id: UUID,
    *,
    entity_id: UUID | None = None,
    entity_type: str = "quotation",
    field_name: str = "currency",
    extracted_value: object = "GBP",
    confidence: Decimal = Decimal("0.9000"),
) -> UUID:
    field_id = uuid4()
    act_as(cur, workspace)
    cur.execute(
        "insert into field_extraction "
        "(id,tenant_id,quotation_id,entity_type,entity_id,field_name,extracted_value,"
        "confidence,extraction_method,model_version) "
        "values (%s,%s,%s,%s,%s,%s,%s,%s,'structured_parse','test-fixture-v1')",
        (
            field_id,
            workspace.tenant_id,
            quotation_id,
            entity_type,
            entity_id or quotation_id,
            field_name,
            Jsonb(extracted_value),
            confidence,
        ),
    )
    return field_id


def make_review_task(
    cur: psycopg.Cursor,
    workspace: Workspace,
    quotation_id: UUID,
    *,
    reason: str,
    priority: str = "normal",
) -> UUID:
    task_id = uuid4()
    act_as(cur, workspace)
    cur.execute(
        "insert into review_task (id,tenant_id,quotation_id,reason,priority) "
        "values (%s,%s,%s,%s,%s)",
        (task_id, workspace.tenant_id, quotation_id, reason, priority),
    )
    return task_id


def make_job(cur: psycopg.Cursor, workspace: Workspace, quotation_id: UUID) -> UUID:
    job_id = uuid4()
    act_as(cur, workspace)
    cur.execute(
        "insert into extraction_job (id,tenant_id,quotation_id,status) values (%s,%s,%s,'queued')",
        (job_id, workspace.tenant_id, quotation_id),
    )
    return job_id


def make_extracted_quotation(cur: psycopg.Cursor, workspace: Workspace) -> QuotationFixture:
    ensure_quotation_reference_data(cur)
    supplier_id = make_supplier(cur, workspace)
    document_id = make_document(cur, workspace)
    quotation_id = make_quotation(
        cur,
        workspace,
        document_id=document_id,
        supplier_id=supplier_id,
        status="extracted",
        arithmetic_status="reconciled",
    )
    line_id = make_line(cur, workspace, quotation_id)
    field_id = make_field(cur, workspace, quotation_id, entity_id=quotation_id)
    storage_path = f"tenants/{workspace.tenant_id}/quotations/{document_id}/quote.pdf"
    return QuotationFixture(document_id, quotation_id, supplier_id, line_id, field_id, storage_path)


class PsycopgSupabaseClient:
    def __init__(self, conn: psycopg.Connection) -> None:
        self._conn = conn

    def table(self, name: str) -> PsycopgTableQuery:
        return PsycopgTableQuery(self._conn, name)


class PsycopgTableQuery:
    def __init__(self, conn: psycopg.Connection, table: str) -> None:
        self._conn = conn
        self._table = table
        self._operation = "select"
        self._payload: dict[str, object] | None = None
        self._where: list[tuple[str, str, object]] = []
        self._limit: int | None = None
        self._offset: int | None = None

    def select(self, _columns: str = "*") -> PsycopgTableQuery:
        self._operation = "select"
        return self

    def insert(self, payload: dict[str, object]) -> PsycopgTableQuery:
        self._operation = "insert"
        self._payload = payload
        return self

    def update(self, payload: dict[str, object]) -> PsycopgTableQuery:
        self._operation = "update"
        self._payload = payload
        return self

    def eq(self, column: str, value: object) -> PsycopgTableQuery:
        self._where.append((column, "=", value))
        return self

    def neq(self, column: str, value: object) -> PsycopgTableQuery:
        self._where.append((column, "!=", value))
        return self

    def lt(self, column: str, value: object) -> PsycopgTableQuery:
        self._where.append((column, "<", value))
        return self

    def gte(self, column: str, value: object) -> PsycopgTableQuery:
        self._where.append((column, ">=", value))
        return self

    def lte(self, column: str, value: object) -> PsycopgTableQuery:
        self._where.append((column, "<=", value))
        return self

    def is_(self, column: str, value: str) -> PsycopgTableQuery:
        if value != "null":
            raise NotImplementedError("test adapter only supports is_(..., 'null')")
        self._where.append((column, "is", None))
        return self

    def in_(self, column: str, values: list[object]) -> PsycopgTableQuery:
        self._where.append((column, "in", values))
        return self

    def limit(self, value: int) -> PsycopgTableQuery:
        self._limit = value
        return self

    def range(self, start: int, end: int) -> PsycopgTableQuery:
        self._offset = start
        self._limit = end - start + 1
        return self

    def order(self, _column: str, *, desc: bool = False) -> PsycopgTableQuery:
        del desc
        return self

    def execute(self) -> object:
        if self._operation == "insert":
            return self._execute_insert()
        if self._operation == "update":
            return self._execute_update()
        return self._execute_select()

    def _execute_select(self) -> object:
        query = sql.SQL("select * from {}").format(sql.Identifier(self._table))
        params: list[object] = []
        where_sql, where_params = self._where_sql()
        params.extend(where_params)
        if where_sql is not None:
            query += sql.SQL(" where ") + where_sql
        if self._limit is not None:
            query += sql.SQL(" limit %s")
            params.append(self._limit)
        if self._offset is not None:
            query += sql.SQL(" offset %s")
            params.append(self._offset)
        return _Response(self._fetch(query, params))

    def _execute_insert(self) -> object:
        if self._payload is None:
            raise AssertionError("insert payload is required")
        keys = list(self._payload)
        query = sql.SQL("insert into {} ({}) values ({}) returning *").format(
            sql.Identifier(self._table),
            sql.SQL(",").join(sql.Identifier(key) for key in keys),
            sql.SQL(",").join(sql.Placeholder() for _key in keys),
        )
        return _Response(
            self._fetch(query, [_adapt_value(key, self._payload[key]) for key in keys])
        )

    def _execute_update(self) -> object:
        if self._payload is None:
            raise AssertionError("update payload is required")
        keys = list(self._payload)
        params = [_adapt_value(key, self._payload[key]) for key in keys]
        query = sql.SQL("update {} set {}").format(
            sql.Identifier(self._table),
            sql.SQL(",").join(
                sql.SQL("{} = {}").format(sql.Identifier(key), sql.Placeholder())
                for key in keys
            ),
        )
        where_sql, where_params = self._where_sql()
        if where_sql is not None:
            query += sql.SQL(" where ") + where_sql
            params.extend(where_params)
        query += sql.SQL(" returning *")
        return _Response(self._fetch(query, params))

    def _where_sql(self) -> tuple[sql.SQL | None, list[object]]:
        clauses: list[sql.SQL] = []
        params: list[object] = []
        for column, operator, value in self._where:
            column_sql = _column_sql(column)
            if operator == "is":
                clauses.append(sql.SQL("{} is null").format(column_sql))
            elif operator == "in":
                values = list(value) if isinstance(value, list) else []
                placeholders = sql.SQL(",").join(sql.Placeholder() for _item in values)
                clauses.append(
                    sql.SQL("{} in ({})").format(column_sql, placeholders)
                )
                params.extend(values)
            else:
                clauses.append(
                    sql.SQL("{} {} {}").format(
                        column_sql,
                        sql.SQL(operator),
                        sql.Placeholder(),
                    )
                )
                params.append(value)
        if not clauses:
            return None, params
        return sql.SQL(" and ").join(clauses), params

    def _fetch(self, query: sql.SQL, params: list[object]) -> list[dict[str, object]]:
        with self._conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
            cur.execute(query, params)
            rows = cur.fetchall()
        return [
            {key: _adapt_response_value(value) for key, value in dict(row).items()}
            for row in rows
        ]


@dataclass(frozen=True)
class _Response:
    data: list[dict[str, object]]


# Columns typed jsonb that this fake client's callers write scalar (not just dict/list) Python
# values into. The real Supabase REST client JSON-encodes every payload value regardless of type,
# so a caller passing a bare string to a jsonb column works there; this raw-SQL stand-in must wrap
# it explicitly or Postgres sees invalid, unquoted JSON.
_JSONB_COLUMNS = {"extracted_value", "corrected_value", "source_region", "error"}


def _adapt_value(column: str, value: object) -> object:
    if value is not None and (isinstance(value, dict | list) or column in _JSONB_COLUMNS):
        return Jsonb(value)
    return value


def _adapt_response_value(value: object) -> object:
    if isinstance(value, datetime | date):
        return value.isoformat()
    return value


def _column_sql(column: str) -> sql.SQL | sql.Identifier:
    if "->>" in column:
        json_column, json_key = column.split("->>", maxsplit=1)
        return sql.SQL("{}->>{}").format(sql.Identifier(json_column), sql.Literal(json_key))
    return sql.Identifier(column)

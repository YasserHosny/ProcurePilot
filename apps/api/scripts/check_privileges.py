"""Check a migrated database's client-role privileges against what the migrations intend.

Read-only. ``pnpm db:migrate`` runs it after ``supabase migration up``; run it on its own with
``pnpm db:check-privileges``. It exits non-zero if any check fails.

Why it exists: deploys never run migrations, and Supabase projects' default privileges can grant
ALL to anon and authenticated on new tables (see
``supabase/migrations/20261018000005_public_table_least_privilege.sql``). CI's isolation suite runs
against a stand-in database with neither problem, so a hosted database can fall behind or drift
while CI stays green. The checks mirror the schema-wide privilege tests in
``tests/integration/test_tenant_isolation.py``, without creating test tenants:

1. every migration file in ``supabase/migrations`` is recorded as applied;
2. anon can only SELECT the shared reference tables;
3. no table grants TRUNCATE, REFERENCES, TRIGGER or MAINTAIN to anon or authenticated;
4. no client role can SELECT or UPDATE integration access/refresh tokens;
5. the default privileges of role postgres grant nothing to anon or authenticated;
6. every other table a client role can access has row-level security enabled and forced;
7. no client role can UPDATE, DELETE or TRUNCATE audit_event (it is append-only).

Checks 2, 3, 6 and 7 use effective privileges (``has_table_privilege``), so a right reaching a
client role through PUBLIC or through an inherited role counts the same as a direct grant.

The default privileges of role supabase_admin are reported as a warning only: on hosted the
migrating role cannot change them, and migrations create no tables as supabase_admin.

The repo-root ``.env`` is loaded automatically (exported variables win).
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import psycopg
from dotenv import load_dotenv

from procurepilot_api.db import connect

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_ENV_FILE = REPO_ROOT / ".env"
MIGRATIONS_DIR = REPO_ROOT / "supabase" / "migrations"

# Shared, non-tenant lookup tables: anon may read them, and they need no forced RLS.
REFERENCE_TABLES = (
    "supported_base_unit",
    "supported_currency",
    "supported_region",
    "supported_tax_model",
)

TABLE_PRIVILEGES = ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER")


def migration_versions(directory: Path) -> set[str]:
    return {path.stem.split("_", maxsplit=1)[0] for path in directory.glob("*.sql")}


def unapplied_migrations(local: Iterable[str], applied: Iterable[str]) -> list[str]:
    return sorted(set(local) - set(applied))


def _rows(cur: psycopg.Cursor[Any], sql: str) -> list[tuple[Any, ...]]:
    cur.execute(sql)
    return [tuple(row) for row in cur.fetchall()]


def run(conn: psycopg.Connection[Any], migrations_dir: Path | None) -> tuple[list[str], list[str]]:
    """Return (failures, warnings) as human-readable lines.

    migrations_dir=None skips check 1, for databases migrated without the Supabase CLI (CI's
    stand-in applies the files with psql and has no supabase_migrations schema).
    """
    failures: list[str] = []
    warnings: list[str] = []
    with conn.cursor() as cur:
        if migrations_dir is not None:
            cur.execute("select to_regclass('supabase_migrations.schema_migrations')")
            row = cur.fetchone()
            if row is None or row[0] is None:
                failures.append("supabase_migrations.schema_migrations does not exist")
            else:
                applied = [
                    r[0]
                    for r in _rows(cur, "select version from supabase_migrations.schema_migrations")
                ]
                for version in unapplied_migrations(migration_versions(migrations_dir), applied):
                    failures.append(f"migration {version} is not applied")

        privileges = list(TABLE_PRIVILEGES)
        cur.execute("select current_setting('server_version_num')::int >= 170000")
        row = cur.fetchone()
        if row is not None and row[0]:
            privileges.append("MAINTAIN")
        effective = _rows(
            cur,
            f"""
            select c.relname, r.role, p.privilege
            from pg_class c
            cross join unnest(array['anon', 'authenticated']) r(role)
            cross join unnest(array[{", ".join(f"'{p}'" for p in privileges)}]) p(privilege)
            where c.relnamespace = 'public'::regnamespace
              and c.relkind in ('r', 'p', 'v', 'm', 'f')
              and has_table_privilege(r.role, c.oid, p.privilege)
            union all
            select c.relname, r.role, p.privilege
            from pg_class c
            cross join unnest(array['anon', 'authenticated']) r(role)
            cross join unnest(array['SELECT', 'UPDATE', 'USAGE']) p(privilege)
            where c.relnamespace = 'public'::regnamespace
              and c.relkind = 'S'
              and has_sequence_privilege(r.role, c.oid, p.privilege)
            order by 1, 2, 3
            """,
        )

        for name, role, privilege in effective:
            if role == "anon" and (name not in REFERENCE_TABLES or privilege != "SELECT"):
                failures.append(f"anon holds {privilege} on {name}")

        for name, role, privilege in effective:
            if privilege in ("TRUNCATE", "REFERENCES", "TRIGGER", "MAINTAIN"):
                failures.append(f"{role} holds {privilege} on {name}")

        for name, role, privilege in effective:
            if name == "audit_event" and privilege in ("UPDATE", "DELETE"):
                failures.append(f"{role} holds {privilege} on audit_event, which is append-only")

        for table, column, privilege, role, granted in _rows(
            cur,
            """
            select t, col, priv, r, has_column_privilege(r, t, col, priv)
            from unnest(array['accounting_connection', 'pos_connection']) t
            cross join unnest(array['access_token', 'refresh_token']) col
            cross join unnest(array['SELECT', 'UPDATE']) priv
            cross join unnest(array['anon', 'authenticated']) r
            order by 1, 2, 3, 4
            """,
        ):
            if granted:
                failures.append(f"{role} can {privilege} {table}.{column}")

        default_acl = """
            select d.defaclobjtype, a.grantee::regrole::text, a.privilege_type
            from pg_default_acl d
            cross join lateral aclexplode(d.defaclacl) a
            where d.defaclrole = %s::regrole
              and d.defaclnamespace = 'public'::regnamespace
              and d.defaclobjtype in ('r', 'S')
              and a.grantee in ('anon'::regrole, 'authenticated'::regrole)
            order by 1, 2, 3
        """
        kinds = {"r": "tables", "S": "sequences"}
        cur.execute(default_acl, ("postgres",))
        for kind, grantee, privilege in cur.fetchall():
            failures.append(
                f"postgres's default privileges grant {privilege} on new {kinds[kind]} to {grantee}"
            )
        cur.execute("select 1 from pg_roles where rolname = 'supabase_admin'")
        if cur.fetchone():
            cur.execute(default_acl, ("supabase_admin",))
            grants = sorted({f"{grantee} ({kinds[kind]})" for kind, grantee, _ in cur.fetchall()})
            if grants:
                warnings.append(
                    "supabase_admin's default privileges grant rights on new public objects to "
                    + ", ".join(grants)
                    + "; a table created outside migrations (dashboard, SQL editor) needs an "
                    "explicit REVOKE"
                )

        for (name,) in _rows(
            cur,
            """
            select c.relname
            from pg_class c
            where c.relnamespace = 'public'::regnamespace
              and c.relkind in ('r', 'p')
              and not (c.relrowsecurity and c.relforcerowsecurity)
              and exists (
                select 1
                from unnest(array['anon', 'authenticated']) r(role)
                cross join unnest(array['SELECT', 'INSERT', 'UPDATE', 'DELETE']) p(privilege)
                where has_table_privilege(r.role, c.oid, p.privilege)
              )
            order by 1
            """,
        ):
            if name not in REFERENCE_TABLES:
                failures.append(
                    f"{name} is accessible to a client role without ENABLE + FORCE "
                    "row-level security"
                )
    return failures, warnings


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--env-file",
        type=Path,
        default=DEFAULT_ENV_FILE,
        help="Path to .env file to load (defaults to repo-root .env).",
    )
    parser.add_argument("--migrations-dir", type=Path, default=MIGRATIONS_DIR)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    if args.env_file.is_file():
        load_dotenv(dotenv_path=args.env_file, override=False)
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        print("DATABASE_URL is not set.", file=sys.stderr)
        return 2
    with connect(dsn) as conn:
        conn.read_only = True
        failures, warnings = run(conn, args.migrations_dir)
    for line in warnings:
        print(f"WARNING: {line}")
    for line in failures:
        print(f"FAIL: {line}")
    if failures:
        print(f"Privilege check failed: {len(failures)} problem(s).", file=sys.stderr)
        return 1
    print("Privilege check passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

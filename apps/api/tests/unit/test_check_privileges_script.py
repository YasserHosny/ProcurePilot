from __future__ import annotations

import runpy
from pathlib import Path

_SCRIPT = Path(__file__).parents[2] / "scripts" / "check_privileges.py"
_MODULE = runpy.run_path(_SCRIPT)
migration_versions = _MODULE["migration_versions"]
unapplied_migrations = _MODULE["unapplied_migrations"]
MIGRATIONS_DIR = _MODULE["MIGRATIONS_DIR"]


def test_migration_versions_are_the_timestamp_prefixes(tmp_path: Path) -> None:
    (tmp_path / "20261018000005_public_table_least_privilege.sql").write_text("")
    (tmp_path / "20261018000006_purchase_request_line_pack_snapshot.sql").write_text("")
    (tmp_path / "README.md").write_text("")
    assert migration_versions(tmp_path) == {"20261018000005", "20261018000006"}


def test_default_migrations_dir_is_the_repo_supabase_migrations() -> None:
    assert MIGRATIONS_DIR.parts[-2:] == ("supabase", "migrations")
    assert migration_versions(MIGRATIONS_DIR)


def test_unapplied_migrations_lists_local_versions_missing_from_history_in_order() -> None:
    local = {"20261018000004", "20261018000006", "20261018000005"}
    applied = ["20261018000004", "20260101000000"]
    assert unapplied_migrations(local, applied) == ["20261018000005", "20261018000006"]


def test_nothing_unapplied_when_history_covers_every_file() -> None:
    assert unapplied_migrations({"20261018000004"}, ["20261018000004", "20261018000005"]) == []

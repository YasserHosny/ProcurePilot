from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest

from integration.catalogue_helpers import (
    TEST_DATABASE_URL,
    act_as,
    connection,
    delete_tenant_scoped_rows,
    make_workspace,
    psycopg,
)
from procurepilot_api.config import get_settings
from procurepilot_api.deps import CurrentMember
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.catalogue.csv_import import (
    ImportValidationReport,
    ProductImportRow,
    commit_import,
    validate_import_file,
)
from procurepilot_api.modules.catalogue.import_repository import (
    PostgresImportRepository,
    with_database_duplicates,
)

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is not set; needs a Postgres with catalogue migrations applied",
)


@pytest.fixture
def conn() -> object:
    yield from connection()


def test_failed_import_commit_leaves_catalogue_unchanged(conn: object) -> None:
    with conn.cursor() as cur:
        workspace = make_workspace(cur, "import-atomicity")
        conn.commit()
        act_as(cur, workspace)
        member = CurrentMember(
            membership_id=workspace.membership_id,
            tenant_id=workspace.tenant_id,
            user_id=workspace.user_id,
            email="import-atomicity-owner@example.test",
            role=MemberRole.owner,
        )
        report = ImportValidationReport(
            kind="products",
            filename="atomic.csv",
            row_count=2,
            rows=(
                ProductImportRow(
                    line=2,
                    tenant_name="Atomic first product",
                    base_unit="litre",
                    pack_count=6,
                    unit_size=Decimal("5"),
                ),
                ProductImportRow(
                    line=3,
                    tenant_name="Atomic failing product",
                    base_unit="litre",
                    pack_count=6,
                    unit_size=Decimal("5"),
                    preferred_supplier_id=uuid4(),
                ),
            ),
        )
        repository = PostgresImportRepository(get_settings(), member)

        try:
            import_id = repository.create_import_job(report)

            act_as(cur, workspace)
            cur.execute("select count(*) from workspace_product")
            before_products = cur.fetchone()
            cur.execute("select count(*) from pack_definition")
            before_packs = cur.fetchone()
            cur.execute("select count(*) from canonical_product")
            before_canonical_products = cur.fetchone()

            with pytest.raises(psycopg.errors.ForeignKeyViolation):
                commit_import(
                    report,
                    repository,
                    after_rows=lambda repo: repository.mark_committed(import_id),
                )

            act_as(cur, workspace)
            cur.execute("select status, committed_at from import_job where id = %s", (import_id,))
            assert cur.fetchone() == ("previewed", None)
            cur.execute(
                "select id from workspace_product where tenant_name in (%s,%s)",
                ("Atomic first product", "Atomic failing product"),
            )
            assert cur.fetchall() == []
            cur.execute(
                "select id from canonical_product where name in (%s,%s)",
                ("Atomic first product", "Atomic failing product"),
            )
            assert cur.fetchall() == []
            cur.execute("select count(*) from workspace_product")
            assert cur.fetchone() == before_products
            cur.execute("select count(*) from pack_definition")
            assert cur.fetchone() == before_packs
            cur.execute("select count(*) from canonical_product")
            assert cur.fetchone() == before_canonical_products
        finally:
            cur.execute("reset role")
            # The owner-guard trigger (migration 20260819000005) refuses to delete the last
            # active owner's membership row, including via cascade from a tenant delete — by
            # design, for the normal application paths it protects. Test-only cleanup of a
            # fully-committed workspace needs to bypass it explicitly. SET LOCAL reverts on
            # commit or rollback, preserving the original delete error if cleanup fails.
            cur.execute("set local session_replication_role = replica")
            delete_tenant_scoped_rows(cur, workspace.tenant_id)
            cur.execute("delete from tenant where id = %s", (workspace.tenant_id,))
            cur.execute("delete from auth.users where id = %s", (workspace.user_id,))
            cur.execute(
                "delete from canonical_product where name in (%s,%s)",
                ("Atomic first product", "Atomic failing product"),
            )
            conn.commit()


def test_kg_csv_preview_commit_and_repeat_skip(conn: object) -> None:
    with conn.cursor() as cur:
        workspace = make_workspace(cur, "import-kg-alias")
        conn.commit()
        act_as(cur, workspace)
        cur.execute("select 1 from supported_base_unit where code = 'kg'")
        assert cur.fetchone() is None
        member = CurrentMember(
            membership_id=workspace.membership_id,
            tenant_id=workspace.tenant_id,
            user_id=workspace.user_id,
            email="import-kg-alias-owner@example.test",
            role=MemberRole.owner,
        )
        content = (
            b"tenant_name,canonical_name,base_unit,pack_count,unit_size\n"
            b"Olive Oil,Olive Oil,kg,1,1\n"
        )
        repository = PostgresImportRepository(get_settings(), member)
        report = validate_import_file(
            kind="products",
            filename="demo.csv",
            content=content,
            content_type="text/csv",
        )
        assert report.valid
        assert report.preview[0]["base_unit"] == "kilogram"
        try:
            import_id = repository.create_import_job(report)
            assert import_id
            first = commit_import(report, repository)
            assert first.created == 1 and first.skipped == 0

            with conn.cursor() as verify:
                act_as(verify, workspace)
                verify.execute(
                    "select cp.base_unit from workspace_product wp "
                    "join canonical_product cp on cp.id = wp.canonical_product_id "
                    "where wp.tenant_id = %s and wp.tenant_name = 'Olive Oil'",
                    (workspace.tenant_id,),
                )
                assert verify.fetchone()[0] == "kilogram"
            repeated = with_database_duplicates(report, repository)
            assert any(item.reason == "duplicate existing record" for item in repeated.duplicates)
            second = commit_import(repeated, repository)
            assert second.created == 0 and second.skipped == 1
        finally:
            cur.execute("reset role")
            cur.execute("set local session_replication_role = replica")
            delete_tenant_scoped_rows(cur, workspace.tenant_id)
            cur.execute("delete from tenant where id = %s", (workspace.tenant_id,))
            cur.execute("delete from auth.users where id = %s", (workspace.user_id,))
            cur.execute("delete from canonical_product where name = 'Olive Oil'")
            conn.commit()

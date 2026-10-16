from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import psycopg
import pytest

from integration.catalogue_helpers import TEST_DATABASE_URL, make_workspace

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is not set; needs a migrated Postgres",
)


def test_merge_kg_migration_remaps_product_and_quotation_line_then_rolls_back() -> None:
    migration = (
        Path(__file__).parents[4]
        / "supabase/migrations/20261017000001_merge_duplicate_kg_base_unit.sql"
    )
    with psycopg.connect(TEST_DATABASE_URL or "", prepare_threshold=None) as conn:
        try:
            with conn.cursor() as cur:
                workspace = make_workspace(cur, "kg-merge-migration")
                alias = "k" + "g"
                cur.execute(
                    "insert into supported_base_unit "
                    "(code,label_en,label_ar,dimension,is_enabled) "
                    "values (%s,'Kilogram','كيلوغرام','mass',true) on conflict do nothing",
                    (alias,),
                )
                canonical_id = uuid4()
                cur.execute(
                    "insert into canonical_product (id,name,base_unit) "
                    "values (%s,'Migration kg product',%s)",
                    (canonical_id, alias),
                )
                document_id, quotation_id, line_id = uuid4(), uuid4(), uuid4()
                cur.execute(
                    "insert into document "
                    "(id,tenant_id,storage_bucket,storage_path,mime_type,created_by) "
                    "values (%s,%s,'quotation-documents',%s,'application/pdf',%s)",
                    (
                        document_id,
                        workspace.tenant_id,
                        f"tenants/{workspace.tenant_id}/quotations/kg-migration.pdf",
                        workspace.membership_id,
                    ),
                )
                cur.execute(
                    "insert into quotation (id,tenant_id,document_id) values (%s,%s,%s)",
                    (quotation_id, workspace.tenant_id, document_id),
                )
                cur.execute(
                    "insert into quotation_line "
                    "(id,tenant_id,quotation_id,line_number,original_text,pack_unit) "
                    "values (%s,%s,%s,1,'25 kg',%s)",
                    (line_id, workspace.tenant_id, quotation_id, alias),
                )
                cur.execute(migration.read_text())
                cur.execute(
                    "select base_unit from canonical_product where id = %s", (canonical_id,)
                )
                assert cur.fetchone()[0] == "kilogram"
                cur.execute("select pack_unit from quotation_line where id = %s", (line_id,))
                assert cur.fetchone()[0] == "kilogram"
                cur.execute("select count(*) from supported_base_unit where code = %s", (alias,))
                assert cur.fetchone()[0] == 0
        finally:
            conn.rollback()

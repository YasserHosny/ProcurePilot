from __future__ import annotations

import psycopg
import pytest

from integration.catalogue_helpers import TEST_DATABASE_URL
from integration.smart_compare_helpers import committed_smart_context, settings_for_test_db
from procurepilot_api.errors import UnprocessableEntityError
from procurepilot_api.modules.ingestion import catalogue_import_service
from procurepilot_api.modules.matching.service import MatchingService

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is not set; needs a migrated local Postgres",
)

import_catalogue = catalogue_import_service.import_catalogue


class _FakeBucket:
    def upload(self, *_args: object, **_kwargs: object) -> None:
        return None


class _FakeStorage:
    def from_(self, _bucket: str) -> _FakeBucket:
        return _FakeBucket()


class _FakeSupabaseClient:
    storage = _FakeStorage()


@pytest.fixture(autouse=True)
def _fake_storage(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        catalogue_import_service, "create_client", lambda *_a, **_k: _FakeSupabaseClient()
    )


@pytest.fixture(autouse=True)
def _fake_matching(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, object]]:
    """MatchingService.quotation_matches() itself talks to Postgres via the older
    postgrest-client architecture (authenticated_client -> real Supabase/PostgREST), which this
    disposable-Postgres-only test environment does not provide — matching this codebase's own
    established precedent (test_matching_routing.py) of testing MatchingService's internals in
    its own dedicated suite via a psycopg-backed fake client, not by driving the full
    quotation_matches() entry point from an unrelated feature's integration tests. These tests
    instead prove catalogue import correctly BUILDS the reviewed quotation + lines and correctly
    CALLS the existing, separately-tested pipeline — not that the pipeline's own matching logic
    is correct, which is already covered elsewhere.
    """
    calls: list[dict[str, object]] = []

    def _fake(
        self: MatchingService, *, bearer_token: str, member: object, quotation_id: object
    ) -> None:
        calls.append(
            {"bearer_token": bearer_token, "member": member, "quotation_id": quotation_id}
        )

    monkeypatch.setattr(MatchingService, "quotation_matches", _fake)
    return calls


def _csv(rows: list[str]) -> bytes:
    return ("\n".join(rows) + "\n").encode("utf-8")


def test_import_creates_a_reviewed_quotation_with_one_line_per_row(
    monkeypatch: pytest.MonkeyPatch, _fake_matching: list[dict[str, object]]
) -> None:
    settings = settings_for_test_db(monkeypatch)
    with committed_smart_context("catalogue-import-basic", supplier_count=1) as context:
        supplier_id = context.supplier_ids[0]
        token = "test-bearer-token"
        content = _csv(
            [
                "product_name,unit_price,currency",
                "Whole Milk 2L,1.75,USD",
                "Sourdough Loaf,3.25,USD",
            ]
        )

        row = import_catalogue(
            settings,
            member=context.member,
            supplier_id=supplier_id,
            file_content=content,
            filename="prices.csv",
            file_format="csv",
            bearer_token=token,
        )

        assert row["status"] == "completed"
        assert row["total_rows"] == 2
        assert row["imported_rows"] == 2
        assert row["error_rows"] == 0
        assert row["supplier_id"] == supplier_id

        # Matching was invoked for the synthesized quotation, with the caller's real token.
        assert len(_fake_matching) == 1
        assert _fake_matching[0]["bearer_token"] == token

        with psycopg.connect(TEST_DATABASE_URL or "", row_factory=psycopg.rows.dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "select id, status, source, supplier_id, reviewed_by, reviewed_at "
                    "from quotation where tenant_id = %s and source = 'catalogue_import'",
                    (context.workspace.tenant_id,),
                )
                quotation = cur.fetchone()
                assert quotation is not None
                assert _fake_matching[0]["quotation_id"] == quotation["id"]
                assert quotation["status"] == "reviewed"
                assert quotation["source"] == "catalogue_import"
                assert quotation["supplier_id"] == supplier_id
                assert quotation["reviewed_by"] == context.workspace.membership_id
                assert quotation["reviewed_at"] is not None

                cur.execute(
                    "select line_number, original_text, unit_price_amount, unit_price_currency "
                    "from quotation_line where quotation_id = %s order by line_number",
                    (quotation["id"],),
                )
                lines = cur.fetchall()
                assert [line_row["original_text"] for line_row in lines] == [
                    "Whole Milk 2L",
                    "Sourdough Loaf",
                ]
                assert lines[0]["unit_price_currency"] == "USD"

                cur.execute(
                    "select storage_path, source_channel from document where id = "
                    "(select document_id from quotation where id = %s)",
                    (quotation["id"],),
                )
                document = cur.fetchone()
                assert document["source_channel"] == "catalogue_import"
                assert document["storage_path"].startswith(
                    f"tenants/{context.workspace.tenant_id}/quotations/"
                )


def test_unsupported_currency_is_a_row_error_not_a_whole_file_failure(
    monkeypatch: pytest.MonkeyPatch, _fake_matching: list[dict[str, object]]
) -> None:
    settings = settings_for_test_db(monkeypatch)
    with committed_smart_context("catalogue-import-badcurrency", supplier_count=1) as context:
        supplier_id = context.supplier_ids[0]
        content = _csv(
            [
                "product_name,unit_price,currency",
                "Good Row,1.00,USD",
                "Bad Currency Row,2.00,ZZZ",
            ]
        )

        row = import_catalogue(
            settings,
            member=context.member,
            supplier_id=supplier_id,
            file_content=content,
            filename="prices.csv",
            file_format="csv",
            bearer_token="test-bearer-token",
        )

        assert row["status"] == "completed"
        assert row["imported_rows"] == 1
        assert row["error_rows"] == 1
        assert row["error_details"][0]["error"] == "unsupported_currency"
        assert row["error_details"][0]["row"] == 3


def test_all_rows_bad_currency_skips_matching_and_records_failed(
    monkeypatch: pytest.MonkeyPatch, _fake_matching: list[dict[str, object]]
) -> None:
    settings = settings_for_test_db(monkeypatch)
    with committed_smart_context("catalogue-import-allbad", supplier_count=1) as context:
        supplier_id = context.supplier_ids[0]
        content = _csv(["product_name,unit_price,currency", "Widget,1.00,ZZZ"])

        row = import_catalogue(
            settings,
            member=context.member,
            supplier_id=supplier_id,
            file_content=content,
            filename="prices.csv",
            file_format="csv",
            bearer_token="test-bearer-token",
        )

        assert row["status"] == "failed"
        assert row["imported_rows"] == 0
        assert row["error_rows"] == 1
        assert _fake_matching == []


def test_unmappable_required_column_raises_and_records_a_failed_import(
    monkeypatch: pytest.MonkeyPatch, _fake_matching: list[dict[str, object]]
) -> None:
    settings = settings_for_test_db(monkeypatch)
    with committed_smart_context("catalogue-import-badheaders", supplier_count=1) as context:
        supplier_id = context.supplier_ids[0]
        content = _csv(["some_column,other_column", "a,b"])

        with pytest.raises(Exception):  # noqa: B017 - UnprocessableEntityError
            import_catalogue(
                settings,
                member=context.member,
                supplier_id=supplier_id,
                file_content=content,
                filename="bad.csv",
                file_format="csv",
                bearer_token="test-bearer-token",
            )

        with psycopg.connect(TEST_DATABASE_URL or "", row_factory=psycopg.rows.dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "select status from catalogue_imports where tenant_id = %s",
                    (context.workspace.tenant_id,),
                )
                imports = cur.fetchall()
                assert len(imports) == 1
                assert imports[0]["status"] == "failed"
        assert _fake_matching == []


def test_cross_tenant_supplier_id_resolves_not_found(
    monkeypatch: pytest.MonkeyPatch, _fake_matching: list[dict[str, object]]
) -> None:
    settings = settings_for_test_db(monkeypatch)
    with committed_smart_context("catalogue-import-tenant-a", supplier_count=1) as tenant_a:
        with committed_smart_context("catalogue-import-tenant-b", supplier_count=1) as tenant_b:
            content = _csv(["product_name,unit_price,currency", "Widget,1.00,USD"])

            with pytest.raises(Exception):  # noqa: B017 - NotFoundError
                import_catalogue(
                    settings,
                    member=tenant_b.member,
                    supplier_id=tenant_a.supplier_ids[0],
                    file_content=content,
                    filename="prices.csv",
                    file_format="csv",
                    bearer_token="test-bearer-token",
                )
        assert _fake_matching == []


def test_importing_the_same_file_twice_creates_two_independent_quotations(
    monkeypatch: pytest.MonkeyPatch, _fake_matching: list[dict[str, object]]
) -> None:
    settings = settings_for_test_db(monkeypatch)
    with committed_smart_context("catalogue-import-reimport", supplier_count=1) as context:
        supplier_id = context.supplier_ids[0]
        token = "test-bearer-token"
        content = _csv(
            [
                "product_name,unit_price,currency",
                "Whole Milk 2L,1.75,USD",
                "Sourdough Loaf,3.25,USD",
            ]
        )

        first = import_catalogue(
            settings,
            member=context.member,
            supplier_id=supplier_id,
            file_content=content,
            filename="prices.csv",
            file_format="csv",
            bearer_token=token,
        )
        second = import_catalogue(
            settings,
            member=context.member,
            supplier_id=supplier_id,
            file_content=content,
            filename="prices.csv",
            file_format="csv",
            bearer_token=token,
        )

        for row in (first, second):
            assert row["status"] == "completed"
            assert row["total_rows"] == 2
            assert row["imported_rows"] == 2
            assert row["error_rows"] == 0

        assert first["id"] != second["id"]

        history = catalogue_import_service.list_imports(
            member=context.member,
            supplier_id=supplier_id,
            settings=settings,
        )
        assert len(history.items) == 2
        assert {item.id for item in history.items} == {first["id"], second["id"]}

        assert len(_fake_matching) == 2
        matching_quotation_ids = {
            _fake_matching[0]["quotation_id"],
            _fake_matching[1]["quotation_id"],
        }
        assert len(matching_quotation_ids) == 2

        with psycopg.connect(TEST_DATABASE_URL or "", row_factory=psycopg.rows.dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "select id, status, source, supplier_id "
                    "from quotation where tenant_id = %s and source = 'catalogue_import' "
                    "and supplier_id = %s order by created_at",
                    (context.workspace.tenant_id, supplier_id),
                )
                quotations = cur.fetchall()
                assert len(quotations) == 2
                quotation_ids = {q["id"] for q in quotations}
                assert len(quotation_ids) == 2
                assert quotation_ids == matching_quotation_ids
                for quotation in quotations:
                    assert quotation["status"] == "reviewed"
                    assert quotation["source"] == "catalogue_import"
                    assert quotation["supplier_id"] == supplier_id

                    cur.execute(
                        "select line_number, original_text "
                        "from quotation_line where quotation_id = %s order by line_number",
                        (quotation["id"],),
                    )
                    lines = cur.fetchall()
                    assert [line_row["original_text"] for line_row in lines] == [
                        "Whole Milk 2L",
                        "Sourdough Loaf",
                    ]


def test_import_header_only_csv_results_in_completed_with_zero_counts(
    monkeypatch: pytest.MonkeyPatch, _fake_matching: list[dict[str, object]]
) -> None:
    settings = settings_for_test_db(monkeypatch)
    with committed_smart_context("catalogue-import-empty", supplier_count=1) as context:
        supplier_id = context.supplier_ids[0]
        token = "test-bearer-token"
        content = _csv(["product_name,unit_price,currency"])

        row = import_catalogue(
            settings,
            member=context.member,
            supplier_id=supplier_id,
            file_content=content,
            filename="empty.csv",
            file_format="csv",
            bearer_token=token,
        )

        assert row["status"] == "completed"
        assert row["total_rows"] == 0
        assert row["imported_rows"] == 0
        assert row["skipped_rows"] == 0
        assert row["error_rows"] == 0
        assert row["error_details"] == []
        assert _fake_matching == []


def test_import_non_utf8_csv_raises_and_records_a_failed_import(
    monkeypatch: pytest.MonkeyPatch, _fake_matching: list[dict[str, object]]
) -> None:
    settings = settings_for_test_db(monkeypatch)
    with committed_smart_context("catalogue-import-nonutf8", supplier_count=1) as context:
        supplier_id = context.supplier_ids[0]
        content = b"product_name,unit_price,currency\nCaf\xe9,1.00,USD\n"

        with pytest.raises(UnprocessableEntityError) as excinfo:
            import_catalogue(
                settings,
                member=context.member,
                supplier_id=supplier_id,
                file_content=content,
                filename="bad_encoding.csv",
                file_format="csv",
                bearer_token="test-bearer-token",
            )

        assert excinfo.value.status_code == 422
        assert excinfo.value.details == {"reason": "file could not be decoded as UTF-8 text"}

        with psycopg.connect(TEST_DATABASE_URL or "", row_factory=psycopg.rows.dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "select status, error_details from catalogue_imports where tenant_id = %s",
                    (context.workspace.tenant_id,),
                )
                imports = cur.fetchall()
                assert len(imports) == 1
                assert imports[0]["status"] == "failed"
                assert "file could not be decoded as UTF-8 text" in str(imports[0]["error_details"])
        assert _fake_matching == []


def test_import_corrupted_xlsx_raises_and_records_a_failed_import(
    monkeypatch: pytest.MonkeyPatch, _fake_matching: list[dict[str, object]]
) -> None:
    settings = settings_for_test_db(monkeypatch)
    with committed_smart_context("catalogue-import-corruptxlsx", supplier_count=1) as context:
        supplier_id = context.supplier_ids[0]
        content = b"not a valid zip or xlsx file content"

        with pytest.raises(UnprocessableEntityError) as excinfo:
            import_catalogue(
                settings,
                member=context.member,
                supplier_id=supplier_id,
                file_content=content,
                filename="corrupted.xlsx",
                file_format="xlsx",
                bearer_token="test-bearer-token",
            )

        assert excinfo.value.status_code == 422
        assert excinfo.value.details == {"reason": "file is not a valid XLSX workbook"}

        with psycopg.connect(TEST_DATABASE_URL or "", row_factory=psycopg.rows.dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "select status, error_details from catalogue_imports where tenant_id = %s",
                    (context.workspace.tenant_id,),
                )
                imports = cur.fetchall()
                assert len(imports) == 1
                assert imports[0]["status"] == "failed"
                assert "file is not a valid XLSX workbook" in str(imports[0]["error_details"])
        assert _fake_matching == []

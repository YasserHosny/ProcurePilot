from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from integration.catalogue_helpers import TEST_DATABASE_URL
from integration.smart_compare_helpers import committed_smart_context, settings_for_test_db
from procurepilot_api.deps import bearer_token, current_member
from procurepilot_api.errors import NotFoundError
from procurepilot_api.main import create_app
from procurepilot_api.modules.ingestion import catalogue_import_service
from procurepilot_api.modules.ingestion.catalogue_import_service import (
    import_catalogue,
    list_imports,
)
from procurepilot_api.modules.matching.service import MatchingService

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is not set; needs a migrated local Postgres",
)


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


def _client(monkeypatch: pytest.MonkeyPatch, member: object) -> TestClient:
    app = create_app(settings_for_test_db(monkeypatch))
    app.dependency_overrides[current_member] = lambda: member
    app.dependency_overrides[bearer_token] = lambda: "test-bearer-token"
    return TestClient(app, raise_server_exceptions=False)


def test_empty_list(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = settings_for_test_db(monkeypatch)
    with committed_smart_context("import-history-empty", supplier_count=1) as context:
        supplier_id = context.supplier_ids[0]

        # 1. Direct service call
        res = list_imports(
            member=context.member,
            supplier_id=supplier_id,
            settings=settings,
        )
        assert res.items == []
        assert res.next_cursor is None

        # 2. HTTP endpoint
        client = _client(monkeypatch, context.member)
        http_res = client.get(f"/api/v1/suppliers/{supplier_id}/catalogue-imports")
        assert http_res.status_code == 200
        body = http_res.json()
        assert body["items"] == []
        assert body["next_cursor"] is None


def test_real_import_row_appears_with_correct_summary_counts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = settings_for_test_db(monkeypatch)
    with committed_smart_context("import-history-counts", supplier_count=1) as context:
        supplier_id = context.supplier_ids[0]
        token = "test-bearer-token"
        content = _csv(
            [
                "product_name,unit_price,currency",
                "Whole Milk 2L,1.75,USD",
                "Sourdough Loaf,3.25,USD",
            ]
        )

        seeded_row = import_catalogue(
            settings,
            member=context.member,
            supplier_id=supplier_id,
            file_content=content,
            filename="prices.csv",
            file_format="csv",
            bearer_token=token,
        )

        client = _client(monkeypatch, context.member)
        http_res = client.get(f"/api/v1/suppliers/{supplier_id}/catalogue-imports")
        assert http_res.status_code == 200
        body = http_res.json()
        assert len(body["items"]) == 1
        item = body["items"][0]

        assert item["id"] == str(seeded_row["id"])
        assert item["supplier_id"] == str(supplier_id)
        assert item["file_name"] == "prices.csv"
        assert item["file_format"] == "csv"
        assert item["file_size_bytes"] == len(content)
        assert item["status"] == "completed"
        assert item["total_rows"] == 2
        assert item["imported_rows"] == 2
        assert item["skipped_rows"] == 0
        assert item["error_rows"] == 0
        assert item["error_details"] == []
        assert isinstance(item["column_mapping"], dict)
        assert item["created_at"] is not None
        assert item["completed_at"] is not None
        assert item["created_by"] == str(context.workspace.membership_id)
        assert body["next_cursor"] is None

        # Add a second import with row errors to verify error counts and ordering
        partial_content = _csv(
            [
                "product_name,unit_price,currency",
                "Item 1,10.00,USD",
                "Item 2,20.00,ZZZ",
            ]
        )
        partial_row = import_catalogue(
            settings,
            member=context.member,
            supplier_id=supplier_id,
            file_content=partial_content,
            filename="partial.csv",
            file_format="csv",
            bearer_token=token,
        )

        http_res2 = client.get(f"/api/v1/suppliers/{supplier_id}/catalogue-imports")
        assert http_res2.status_code == 200
        body2 = http_res2.json()
        assert len(body2["items"]) == 2
        # Newest first
        first = body2["items"][0]
        second = body2["items"][1]
        assert first["id"] == str(partial_row["id"])
        assert first["file_name"] == "partial.csv"
        assert first["status"] == "completed"
        assert first["imported_rows"] == 1
        assert first["error_rows"] == 1
        assert len(first["error_details"]) == 1
        assert first["error_details"][0]["error"] == "unsupported_currency"
        assert second["id"] == str(seeded_row["id"])


def test_pagination_across_multiple_pages(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = settings_for_test_db(monkeypatch)
    with committed_smart_context("import-history-pagination", supplier_count=1) as context:
        supplier_id = context.supplier_ids[0]
        token = "test-bearer-token"

        # Seed 3 imports
        seeded_ids: list[str] = []
        for i in range(1, 4):
            content = _csv([f"product_name,unit_price,currency\nProduct {i},1.00,USD"])
            row = import_catalogue(
                settings,
                member=context.member,
                supplier_id=supplier_id,
                file_content=content,
                filename=f"file{i}.csv",
                file_format="csv",
                bearer_token=token,
            )
            seeded_ids.append(str(row["id"]))

        client = _client(monkeypatch, context.member)

        # Page 1: limit 2
        res_p1 = client.get(f"/api/v1/suppliers/{supplier_id}/catalogue-imports?limit=2")
        assert res_p1.status_code == 200
        p1 = res_p1.json()
        assert len(p1["items"]) == 2
        assert p1["next_cursor"] is not None
        p1_ids = [item["id"] for item in p1["items"]]
        # Newest first: file3 then file2
        assert p1_ids == [seeded_ids[2], seeded_ids[1]]

        # Page 2: with cursor
        cursor = p1["next_cursor"]
        res_p2 = client.get(
            f"/api/v1/suppliers/{supplier_id}/catalogue-imports?limit=2&cursor={cursor}"
        )
        assert res_p2.status_code == 200
        p2 = res_p2.json()
        assert len(p2["items"]) == 1
        assert p2["next_cursor"] is None
        p2_ids = [item["id"] for item in p2["items"]]
        assert p2_ids == [seeded_ids[0]]

        # Both pages combined cover all seeded imports with no overlap
        assert p1_ids + p2_ids == list(reversed(seeded_ids))

        # Invalid cursor returns 422
        res_bad = client.get(
            f"/api/v1/suppliers/{supplier_id}/catalogue-imports?cursor=not-valid-base64!!!"
        )
        assert res_bad.status_code == 422


def test_cross_tenant_supplier_id_resolves_404(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = settings_for_test_db(monkeypatch)
    with committed_smart_context("import-history-tenant-a", supplier_count=1) as tenant_a:
        with committed_smart_context("import-history-tenant-b", supplier_count=1) as tenant_b:
            supplier_a = tenant_a.supplier_ids[0]
            supplier_b = tenant_b.supplier_ids[0]

            # Seed an import in Tenant A
            content = _csv(["product_name,unit_price,currency\nWidget,1.00,USD"])
            import_catalogue(
                settings,
                member=tenant_a.member,
                supplier_id=supplier_a,
                file_content=content,
                filename="a_prices.csv",
                file_format="csv",
                bearer_token="test-token",
            )

            # Tenant B tries to list Tenant A's supplier imports -> 404
            client_b = _client(monkeypatch, tenant_b.member)
            res = client_b.get(f"/api/v1/suppliers/{supplier_a}/catalogue-imports")
            assert res.status_code == 404
            assert res.json()["code"] == "not_found"

            # Direct service call raises NotFoundError
            with pytest.raises(NotFoundError):
                list_imports(
                    member=tenant_b.member,
                    supplier_id=supplier_a,
                    settings=settings,
                )

            # Random unknown supplier resolves 404
            unknown_id = uuid4()
            res_unknown = client_b.get(f"/api/v1/suppliers/{unknown_id}/catalogue-imports")
            assert res_unknown.status_code == 404

            # Tenant B's own supplier has empty list (not leaking Tenant A's import)
            res_b = client_b.get(f"/api/v1/suppliers/{supplier_b}/catalogue-imports")
            assert res_b.status_code == 200
            assert res_b.json()["items"] == []


def test_supplier_scoping_within_same_tenant(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = settings_for_test_db(monkeypatch)
    with committed_smart_context("import-history-supplierscope", supplier_count=2) as context:
        s1 = context.supplier_ids[0]
        s2 = context.supplier_ids[1]

        content = _csv(["product_name,unit_price,currency\nApple,0.50,USD"])
        row = import_catalogue(
            settings,
            member=context.member,
            supplier_id=s1,
            file_content=content,
            filename="s1_prices.csv",
            file_format="csv",
            bearer_token="test-token",
        )

        client = _client(monkeypatch, context.member)

        # S1 has the import
        res1 = client.get(f"/api/v1/suppliers/{s1}/catalogue-imports")
        assert res1.status_code == 200
        items1 = res1.json()["items"]
        assert len(items1) == 1
        assert items1[0]["id"] == str(row["id"])

        # S2 has no imports
        res2 = client.get(f"/api/v1/suppliers/{s2}/catalogue-imports")
        assert res2.status_code == 200
        assert res2.json()["items"] == []

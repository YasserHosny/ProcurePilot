"""RFQ history search and stable offset paging through the real API and RLS."""

from collections.abc import Iterator
from uuid import UUID, uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg.abc import Params, Query

from integration.test_rfq_db_set import _seed_product, _seed_supplier, _seed_tenant
from procurepilot_api.config import get_settings
from procurepilot_api.deps import CurrentMember, current_member
from procurepilot_api.main import app
from procurepilot_api.modules.auth.jwt import MemberRole

SORTS = {
    "created_desc": [1, 20, 12, 2],
    "created_asc": [2, 12, 20, 1],
    "needed_asc": [12, 20, 1, 2],
    "needed_desc": [2, 1, 20, 12],
    "reference_desc": [20, 12, 2, 1],
    "reference_asc": [1, 2, 12, 20],
}


@pytest.fixture
def history(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    with psycopg.connect(get_settings().database_url.get_secret_value()) as conn:
        with conn.cursor() as cur:
            for tenant_index in range(2):
                tenant, user, membership = _seed_tenant(cur, f"history-{tenant_index}")
                prefix = uuid4().int & ~255
                if tenant_index == 0:
                    member = CurrentMember(
                        tenant_id=tenant,
                        user_id=user,
                        membership_id=membership,
                        email="history@example.test",
                        role=MemberRole.owner,
                    )
                for index, reference in enumerate([1, 2, 12, 20]):
                    supplier = _seed_supplier(cur, tenant)
                    product = _seed_product(cur, tenant)
                    supplier_name = [
                        "Orchard Supply",
                        "شركة النور",
                        "Plain Supply",
                        "Other Supply",
                    ][index]
                    product_name = ["Green Apples", "Fresh Pears", "Rice", "Flour"][index]
                    if index == 1:
                        supplier_name += r" 50% A_B C\D"
                        product_name += r" 50% A_B C\D"
                    if tenant_index:
                        supplier_name += " foreignonly"
                        product_name += " foreignonly"
                    cur.execute(
                        "update supplier set name = %s where id = %s", (supplier_name, supplier)
                    )
                    cur.execute(
                        "update workspace_product set tenant_name = %s where id = %s",
                        (product_name, product),
                    )
                    # Increasing UUIDs make tied timestamps/dates testable without relying
                    # on insertion order. Reference numbers are unique within a tenant.
                    rfq = UUID(int=prefix + index)
                    cur.execute(
                        "insert into rfq (id, tenant_id, created_by_membership_id, status, "
                        "needed_by_date, created_at, idempotency_key, "
                        "reference_number, tenant_terms) "
                        "values (%s,%s,%s,%s,current_date + %s, "
                        "'2026-01-01'::timestamptz + %s * interval '1 day',%s,%s,'termsonly')",
                        (
                            rfq,
                            tenant,
                            membership,
                            "sent" if index == 2 else "draft",
                            10 if index < 2 else 5,
                            [2, 0, 1, 1][index],
                            uuid4(),
                            reference,
                        ),
                    )
                    cur.execute(
                        "insert into rfq_recipient (id,tenant_id,rfq_id,supplier_id,status) "
                        "values (%s,%s,%s,%s,'draft')",
                        (uuid4(), tenant, rfq, supplier),
                    )
                    cur.execute(
                        "insert into rfq_line (id,tenant_id,rfq_id,workspace_product_id,quantity) "
                        "values (%s,%s,%s,%s,1)",
                        (uuid4(), tenant, rfq, product),
                    )
    monkeypatch.setitem(app.dependency_overrides, current_member, lambda: member)
    with TestClient(app) as client:
        yield client


@pytest.mark.parametrize(
    "q,expected",
    [
        ("CHARD", [1]),
        ("pPlEs", [1]),
        ("RFQ-000002", [2]),
        ("rfq-2", [2]),
        ("2", [2]),
        ("0002", [2]),
        ("النور", [2]),
        ("%", [2]),
        ("_", [2]),
        ("\\", [2]),
        ("", [1, 20, 12, 2]),
        ("   ", [1, 20, 12, 2]),
        ("  rfq-2  ", [2]),
        ("missing", []),
        ("termsonly", []),
        ("foreignonly", []),
        ("9" * 100, []),
        ("' OR true --", []),
    ],
)
def test_search(history: TestClient, q: str, expected: list[int]) -> None:
    response = history.get("/api/v1/rfq", params={"q": q})
    assert response.status_code == 200, response.text
    body = response.json()
    assert [row["reference_number"] for row in body["items"]] == expected
    assert body["next_cursor"] is None


@pytest.mark.parametrize("sort", SORTS)
def test_sort_and_paging(history: TestClient, sort: str) -> None:
    response = history.get("/api/v1/rfq", params={"sort": sort})
    assert response.status_code == 200, response.text
    assert [row["reference_number"] for row in response.json()["items"]] == SORTS[sort]
    seen: list[str] = []
    references: list[int] = []
    params = {"sort": sort, "limit": "1"}
    for _ in range(5):
        response = history.get("/api/v1/rfq", params=params)
        assert response.status_code == 200, response.text
        body = response.json()
        assert len(body["items"]) == 1
        seen.append(body["items"][0]["id"])
        references.append(body["items"][0]["reference_number"])
        if body["next_cursor"] is None:
            break
        params["cursor"] = body["next_cursor"]
    assert references == SORTS[sort]
    assert len(set(seen)) == 4


@pytest.mark.parametrize(
    "params,reason,field",
    [
        ({"q": "x" * 101}, "invalid_query", "q"),
        ({"sort": "unknown"}, "invalid_sort", "sort"),
    ],
)
def test_invalid_query(
    history: TestClient, params: dict[str, str], reason: str, field: str
) -> None:
    response = history.get("/api/v1/rfq", params=params)
    assert response.status_code == 422, response.text
    assert response.json()["details"] == {"reason": reason, "field": field}


def test_trim_before_length_validation(history: TestClient) -> None:
    response = history.get("/api/v1/rfq", params={"q": " " + "x" * 100 + " "})
    assert response.status_code == 200
    assert response.json() == {"items": [], "next_cursor": None}


def test_combined_filters(history: TestClient) -> None:
    response = history.get(
        "/api/v1/rfq",
        params={"q": "supply", "status": "draft", "sort": "reference_asc"},
    )
    assert response.status_code == 200, response.text
    assert [row["reference_number"] for row in response.json()["items"]] == [1, 20]


def test_search_keeps_statement_count_flat(
    history: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    statements: list[Query] = []
    execute = psycopg.Cursor.execute

    def counted_execute(
        cur: psycopg.Cursor, query: Query, params: Params | None = None, **kwargs: object
    ) -> psycopg.Cursor:
        statements.append(query)
        return execute(cur, query, params, **kwargs)

    monkeypatch.setattr(psycopg.Cursor, "execute", counted_execute)
    for params in ({}, {"q": "supply", "status": "draft", "sort": "needed_asc"}):
        statements.clear()
        response = history.get("/api/v1/rfq", params=params)
        assert response.status_code == 200, response.text
        # Two existing role/claim setup statements, followed by one list statement.
        assert len(statements) == 3
        assert "FROM rfq r" in str(statements[-1])

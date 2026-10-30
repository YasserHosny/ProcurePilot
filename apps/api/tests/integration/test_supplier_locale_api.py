"""Supplier HTTP/service persistence using the hosted DB through a narrow SQL adapter."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from types import SimpleNamespace
from uuid import uuid4

import psycopg
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from psycopg import sql
from psycopg.rows import dict_row

from integration.catalogue_helpers import (
    TEST_DATABASE_URL,
    act_as,
    connection,
    make_workspace,
)
from procurepilot_api.config import get_settings
from procurepilot_api.deps import CurrentMember, bearer_token, current_member
from procurepilot_api.errors import register_exception_handlers
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.catalogue.router import router
from procurepilot_api.modules.catalogue.service import CatalogueService, get_catalogue_service


class SupplierQuery:
    """Replace PostgREST transport only; run real service queries under authenticated RLS."""

    def __init__(self, conn: psycopg.Connection) -> None:
        self.conn = conn
        self.operation = "select"
        self.columns = "*"
        self.values: dict[str, object] = {}
        self.filters: dict[str, object] = {}

    def table(self, name: str) -> SupplierQuery:
        assert name == "supplier"
        return self

    def select(self, columns: str) -> SupplierQuery:
        self.columns = columns
        return self

    def insert(self, values: dict[str, object]) -> SupplierQuery:
        self.operation, self.values = "insert", values
        return self

    def update(self, values: dict[str, object]) -> SupplierQuery:
        self.operation, self.values = "update", values
        return self

    def eq(self, key: str, value: object) -> SupplierQuery:
        self.filters[key] = value
        return self

    def limit(self, _limit: int) -> SupplierQuery:
        return self

    def execute(self) -> SimpleNamespace:
        params = list(self.values.values()) + list(self.filters.values())
        where = sql.SQL(" and ").join(
            sql.SQL("{} = %s").format(sql.Identifier(key)) for key in self.filters
        )
        if self.operation == "insert":
            query = sql.SQL("insert into supplier ({}) values ({}) returning *").format(
                sql.SQL(",").join(map(sql.Identifier, self.values)),
                sql.SQL(",").join(sql.Placeholder() for _ in self.values),
            )
        elif self.operation == "update":
            query = sql.SQL("update supplier set {} where {} returning *").format(
                sql.SQL(",").join(
                    sql.SQL("{} = %s").format(sql.Identifier(key)) for key in self.values
                ),
                where,
            )
        else:
            query = sql.SQL("select {} from supplier where {}").format(
                sql.SQL(",").join(map(sql.Identifier, self.columns.split(","))), where
            )
        with self.conn.cursor(row_factory=dict_row) as cur:
            cur.execute(query, params)
            return SimpleNamespace(data=cur.fetchall())


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    if not TEST_DATABASE_URL:
        pytest.skip("TEST_DATABASE_URL is not set")
    with contextmanager(connection)() as conn:
        with conn.cursor() as cur:
            workspace = make_workspace(cur, "supplier-locale")
            act_as(cur, workspace)
        member = CurrentMember(
            tenant_id=workspace.tenant_id,
            user_id=workspace.user_id,
            membership_id=workspace.membership_id,
            email="supplier-locale@example.test",
            role=MemberRole.owner,
        )
        service = CatalogueService(settings=get_settings())
        monkeypatch.setattr(
            "procurepilot_api.modules.catalogue.service.authenticated_client",
            lambda *_args: SupplierQuery(conn),
        )
        monkeypatch.setattr(service, "_record", lambda **_kwargs: None)
        app = FastAPI()
        register_exception_handlers(app)
        app.include_router(router, prefix="/api/v1")
        app.dependency_overrides[current_member] = lambda: member
        app.dependency_overrides[bearer_token] = lambda: "test-token"
        app.dependency_overrides[get_catalogue_service] = lambda: service
        with TestClient(app) as http:
            yield http


def test_supplier_locale_create_get_patch_and_clear(client: TestClient) -> None:
    response = client.post(
        "/api/v1/suppliers", json={"name": "Locale Supplier", "preferred_locale": "ar"}
    )
    assert response.status_code == 201, response.text
    supplier = response.json()
    assert supplier["preferred_locale"] == "ar"
    path = f"/api/v1/suppliers/{supplier['id']}"
    assert client.get(path).json()["preferred_locale"] == "ar"
    response = client.patch(path, json={"preferred_locale": "en"})
    assert response.status_code == 200, response.text
    assert response.json()["preferred_locale"] == "en"
    assert client.get(path).json()["preferred_locale"] == "en"
    # An omitted locale preserves the override; explicit null removes it.
    assert client.patch(path, json={"name": "Renamed Supplier"}).json()["preferred_locale"] == "en"
    response = client.patch(path, json={"preferred_locale": None})
    assert response.status_code == 200, response.text
    assert response.json()["preferred_locale"] is None
    assert client.get(path).json()["preferred_locale"] is None


@pytest.mark.parametrize("method", ["post", "patch"])
def test_supplier_locale_rejects_unknown_language(client: TestClient, method: str) -> None:
    path = "/api/v1/suppliers" if method == "post" else f"/api/v1/suppliers/{uuid4()}"
    response = client.request(method, path, json={"name": "Supplier", "preferred_locale": "fr"})
    assert response.status_code == 422
    error = response.json()
    assert set(error) == {"code", "message", "details", "trace_id"}
    assert error["code"] == "validation.invalid_request"
    assert any(
        detail["loc"] == ["body", "preferred_locale"] and detail["type"] == "literal_error"
        for detail in error["details"]
    ), error

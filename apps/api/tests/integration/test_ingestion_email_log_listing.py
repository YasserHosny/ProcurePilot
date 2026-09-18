from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import psycopg
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from integration.catalogue_helpers import TEST_DATABASE_URL
from integration.quotation_helpers import make_quotation, make_supplier
from integration.smart_compare_helpers import (
    committed_smart_context,
    member_from_workspace,
    settings_for_test_db,
)
from procurepilot_api.deps import bearer_token, current_member
from procurepilot_api.main import create_app
from procurepilot_api.modules.auth.jwt import MemberRole

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is not set; needs a migrated local Postgres",
)


def _app(monkeypatch: pytest.MonkeyPatch, member: object) -> FastAPI:
    app = create_app(settings_for_test_db(monkeypatch))
    app.dependency_overrides[current_member] = lambda: member
    app.dependency_overrides[bearer_token] = lambda: "test-token"
    return app


def _insert_email_log(
    conn: psycopg.Connection,
    *,
    tenant_id: UUID,
    message_id: str | None = None,
    from_address: str = "supplier@example.com",
    from_domain: str = "example.com",
    subject: str | None = "Quote #123",
    received_at: datetime | None = None,
    processed_at: datetime | None = None,
    status: str = "completed",
    error_message: str | None = None,
    attachment_count: int = 1,
    quotation_id: UUID | None = None,
    supplier_id: UUID | None = None,
    match_method: str | None = "domain",
) -> UUID:
    log_id = uuid4()
    msg_id = message_id or f"<{uuid4()}@{from_domain}>"
    with conn.cursor() as cur:
        cur.execute(
            """
            insert into ingestion_email_log (
                id, tenant_id, message_id, from_address, from_domain,
                subject, received_at, processed_at, status, error_message,
                attachment_count, quotation_id, supplier_id, match_method
            ) values (
                %(id)s, %(tenant_id)s, %(message_id)s, %(from_address)s, %(from_domain)s,
                %(subject)s, coalesce(%(received_at)s, now()), %(processed_at)s,
                %(status)s::ingestion_email_status, %(error_message)s,
                %(attachment_count)s, %(quotation_id)s, %(supplier_id)s, %(match_method)s
            )
            """,
            {
                "id": log_id,
                "tenant_id": tenant_id,
                "message_id": msg_id,
                "from_address": from_address,
                "from_domain": from_domain,
                "subject": subject,
                "received_at": received_at,
                "processed_at": processed_at,
                "status": status,
                "error_message": error_message,
                "attachment_count": attachment_count,
                "quotation_id": quotation_id,
                "supplier_id": supplier_id,
                "match_method": match_method,
            },
        )
    return log_id


def test_list_email_logs_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    with committed_smart_context("email-log-empty") as context:
        member = member_from_workspace(context.workspace)
        client = TestClient(_app(monkeypatch, member), raise_server_exceptions=False)

        res = client.get("/api/v1/ingestion/emails")

        assert res.status_code == 200, res.text
        data = res.json()
        assert data["items"] == []
        assert data["next_cursor"] is None


def test_list_email_logs_pagination_across_pages(monkeypatch: pytest.MonkeyPatch) -> None:
    with committed_smart_context("email-log-pagination") as context:
        member = member_from_workspace(context.workspace)
        client = TestClient(_app(monkeypatch, member), raise_server_exceptions=False)

        base_time = datetime(2026, 9, 17, 10, 0, 0, tzinfo=UTC)
        created_ids: list[UUID] = []

        with psycopg.connect(TEST_DATABASE_URL or "") as conn:
            for i in range(5):
                log_id = _insert_email_log(
                    conn,
                    tenant_id=context.workspace.tenant_id,
                    received_at=base_time + timedelta(hours=i),
                    subject=f"Quote Batch {i}",
                )
                created_ids.append(log_id)
            conn.commit()

        # Expected newest-first ordering: index 4, 3, 2, 1, 0
        expected_order = [str(created_ids[i]) for i in (4, 3, 2, 1, 0)]

        # Page 1: limit 2
        page1_res = client.get("/api/v1/ingestion/emails", params={"limit": 2})
        assert page1_res.status_code == 200, page1_res.text
        page1 = page1_res.json()
        assert len(page1["items"]) == 2
        assert page1["items"][0]["id"] == expected_order[0]
        assert page1["items"][1]["id"] == expected_order[1]
        assert page1["next_cursor"] is not None

        # Page 2: limit 2 with cursor
        page2_res = client.get(
            "/api/v1/ingestion/emails",
            params={"limit": 2, "cursor": page1["next_cursor"]},
        )
        assert page2_res.status_code == 200, page2_res.text
        page2 = page2_res.json()
        assert len(page2["items"]) == 2
        assert page2["items"][0]["id"] == expected_order[2]
        assert page2["items"][1]["id"] == expected_order[3]
        assert page2["next_cursor"] is not None

        # Page 3: limit 2 with cursor
        page3_res = client.get(
            "/api/v1/ingestion/emails",
            params={"limit": 2, "cursor": page2["next_cursor"]},
        )
        assert page3_res.status_code == 200, page3_res.text
        page3 = page3_res.json()
        assert len(page3["items"]) == 1
        assert page3["items"][0]["id"] == expected_order[4]
        assert page3["next_cursor"] is None


def test_list_email_logs_invalid_cursor(monkeypatch: pytest.MonkeyPatch) -> None:
    with committed_smart_context("email-log-bad-cursor") as context:
        member = member_from_workspace(context.workspace)
        client = TestClient(_app(monkeypatch, member), raise_server_exceptions=False)

        res = client.get("/api/v1/ingestion/emails", params={"cursor": "not-valid-base64!!!"})
        assert res.status_code == 422, res.text


def test_list_email_logs_filter_status(monkeypatch: pytest.MonkeyPatch) -> None:
    with committed_smart_context("email-log-status") as context:
        member = member_from_workspace(context.workspace)
        client = TestClient(_app(monkeypatch, member), raise_server_exceptions=False)

        with psycopg.connect(TEST_DATABASE_URL or "") as conn:
            id_completed = _insert_email_log(
                conn, tenant_id=context.workspace.tenant_id, status="completed"
            )
            id_failed = _insert_email_log(
                conn, tenant_id=context.workspace.tenant_id, status="failed"
            )
            id_rejected = _insert_email_log(
                conn, tenant_id=context.workspace.tenant_id, status="rejected"
            )
            id_processing = _insert_email_log(
                conn, tenant_id=context.workspace.tenant_id, status="processing"
            )
            conn.commit()

        # Test filtering by status="completed"
        res_completed = client.get("/api/v1/ingestion/emails", params={"status": "completed"})
        assert res_completed.status_code == 200
        items = res_completed.json()["items"]
        assert len(items) == 1
        assert items[0]["id"] == str(id_completed)
        assert items[0]["status"] == "completed"

        # Test filtering by status="failed"
        res_failed = client.get("/api/v1/ingestion/emails", params={"status": "failed"})
        assert res_failed.status_code == 200
        items = res_failed.json()["items"]
        assert len(items) == 1
        assert items[0]["id"] == str(id_failed)
        assert items[0]["status"] == "failed"

        # Test filtering by status="rejected"
        res_rejected = client.get("/api/v1/ingestion/emails", params={"status": "rejected"})
        assert res_rejected.status_code == 200
        items = res_rejected.json()["items"]
        assert len(items) == 1
        assert items[0]["id"] == str(id_rejected)
        assert items[0]["status"] == "rejected"

        # Test filtering by status="processing"
        res_processing = client.get("/api/v1/ingestion/emails", params={"status": "processing"})
        assert res_processing.status_code == 200
        items = res_processing.json()["items"]
        assert len(items) == 1
        assert items[0]["id"] == str(id_processing)
        assert items[0]["status"] == "processing"

        # Test invalid status returns 422
        res_invalid = client.get("/api/v1/ingestion/emails", params={"status": "unknown_status"})
        assert res_invalid.status_code == 422


def test_list_email_logs_filter_from_domain(monkeypatch: pytest.MonkeyPatch) -> None:
    with committed_smart_context("email-log-domain") as context:
        member = member_from_workspace(context.workspace)
        client = TestClient(_app(monkeypatch, member), raise_server_exceptions=False)

        with psycopg.connect(TEST_DATABASE_URL or "") as conn:
            id_alpha = _insert_email_log(
                conn,
                tenant_id=context.workspace.tenant_id,
                from_domain="supplier-alpha.com",
                from_address="quotes@supplier-alpha.com",
            )
            id_beta = _insert_email_log(
                conn,
                tenant_id=context.workspace.tenant_id,
                from_domain="supplier-beta.com",
                from_address="orders@supplier-beta.com",
            )
            conn.commit()

        # Test filter for supplier-alpha.com
        res_alpha = client.get(
            "/api/v1/ingestion/emails", params={"from_domain": "supplier-alpha.com"}
        )
        assert res_alpha.status_code == 200
        items = res_alpha.json()["items"]
        assert len(items) == 1
        assert items[0]["id"] == str(id_alpha)
        assert items[0]["from_domain"] == "supplier-alpha.com"

        # Test filter for supplier-beta.com
        res_beta = client.get(
            "/api/v1/ingestion/emails", params={"from_domain": "supplier-beta.com"}
        )
        assert res_beta.status_code == 200
        items = res_beta.json()["items"]
        assert len(items) == 1
        assert items[0]["id"] == str(id_beta)
        assert items[0]["from_domain"] == "supplier-beta.com"

        # Test non-matching domain
        res_gamma = client.get(
            "/api/v1/ingestion/emails", params={"from_domain": "nonexistent.com"}
        )
        assert res_gamma.status_code == 200
        assert res_gamma.json()["items"] == []


def test_list_email_logs_filter_date_range(monkeypatch: pytest.MonkeyPatch) -> None:
    with committed_smart_context("email-log-dates") as context:
        member = member_from_workspace(context.workspace)
        client = TestClient(_app(monkeypatch, member), raise_server_exceptions=False)

        t1 = datetime(2026, 9, 1, 10, 0, 0, tzinfo=UTC)
        t2 = datetime(2026, 9, 10, 12, 0, 0, tzinfo=UTC)
        t3 = datetime(2026, 9, 20, 14, 0, 0, tzinfo=UTC)

        with psycopg.connect(TEST_DATABASE_URL or "") as conn:
            id_1 = _insert_email_log(conn, tenant_id=context.workspace.tenant_id, received_at=t1)
            id_2 = _insert_email_log(conn, tenant_id=context.workspace.tenant_id, received_at=t2)
            id_3 = _insert_email_log(conn, tenant_id=context.workspace.tenant_id, received_at=t3)
            conn.commit()

        # date_from only: >= 2026-09-05 should return log 2 and 3
        res_from = client.get("/api/v1/ingestion/emails", params={"date_from": "2026-09-05"})
        assert res_from.status_code == 200
        ids_from = [item["id"] for item in res_from.json()["items"]]
        assert ids_from == [str(id_3), str(id_2)]

        # date_to only: <= 2026-09-15 should return log 1 and 2
        res_to = client.get("/api/v1/ingestion/emails", params={"date_to": "2026-09-15"})
        assert res_to.status_code == 200
        ids_to = [item["id"] for item in res_to.json()["items"]]
        assert ids_to == [str(id_2), str(id_1)]

        # date_from and date_to: 2026-09-05 to 2026-09-15 should return only log 2
        res_both = client.get(
            "/api/v1/ingestion/emails",
            params={"date_from": "2026-09-05", "date_to": "2026-09-15"},
        )
        assert res_both.status_code == 200
        ids_both = [item["id"] for item in res_both.json()["items"]]
        assert ids_both == [str(id_2)]

        # Specific ISO timestamps: exact match on log 2
        res_iso = client.get(
            "/api/v1/ingestion/emails",
            params={
                "date_from": "2026-09-10T12:00:00Z",
                "date_to": "2026-09-10T12:00:00Z",
            },
        )
        assert res_iso.status_code == 200
        ids_iso = [item["id"] for item in res_iso.json()["items"]]
        assert ids_iso == [str(id_2)]

        # Out of range: returns empty
        res_out = client.get("/api/v1/ingestion/emails", params={"date_from": "2026-09-25"})
        assert res_out.status_code == 200
        assert res_out.json()["items"] == []

        # Invalid date format: returns 422
        res_invalid = client.get("/api/v1/ingestion/emails", params={"date_from": "not-a-date"})
        assert res_invalid.status_code == 422


def test_list_email_logs_cross_tenant_isolation(monkeypatch: pytest.MonkeyPatch) -> None:
    with (
        committed_smart_context("email-iso-tenant-a") as ctx_a,
        committed_smart_context("email-iso-tenant-b") as ctx_b,
    ):
        member_a = member_from_workspace(ctx_a.workspace)
        member_b = member_from_workspace(ctx_b.workspace)

        client_a = TestClient(_app(monkeypatch, member_a), raise_server_exceptions=False)
        client_b = TestClient(_app(monkeypatch, member_b), raise_server_exceptions=False)

        with psycopg.connect(TEST_DATABASE_URL or "") as conn:
            id_a1 = _insert_email_log(
                conn, tenant_id=ctx_a.workspace.tenant_id, subject="Tenant A Log 1"
            )
            id_a2 = _insert_email_log(
                conn, tenant_id=ctx_a.workspace.tenant_id, subject="Tenant A Log 2"
            )
            id_b1 = _insert_email_log(
                conn, tenant_id=ctx_b.workspace.tenant_id, subject="Tenant B Log 1"
            )
            id_b2 = _insert_email_log(
                conn, tenant_id=ctx_b.workspace.tenant_id, subject="Tenant B Log 2"
            )
            conn.commit()

        # Tenant A sees only Tenant A rows
        res_a = client_a.get("/api/v1/ingestion/emails")
        assert res_a.status_code == 200
        items_a = res_a.json()["items"]
        ids_seen_a = {item["id"] for item in items_a}
        assert ids_seen_a == {str(id_a1), str(id_a2)}
        assert str(id_b1) not in ids_seen_a
        assert str(id_b2) not in ids_seen_a

        # Tenant B sees only Tenant B rows
        res_b = client_b.get("/api/v1/ingestion/emails")
        assert res_b.status_code == 200
        items_b = res_b.json()["items"]
        ids_seen_b = {item["id"] for item in items_b}
        assert ids_seen_b == {str(id_b1), str(id_b2)}
        assert str(id_a1) not in ids_seen_b
        assert str(id_a2) not in ids_seen_b


def test_list_email_logs_quotation_and_supplier_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with committed_smart_context("email-log-fields") as context:
        member = member_from_workspace(context.workspace)
        client = TestClient(_app(monkeypatch, member), raise_server_exceptions=False)

        with psycopg.connect(TEST_DATABASE_URL or "") as conn:
            with conn.cursor() as cur:
                sup_id = make_supplier(cur, context.workspace, "Produce Supplier Ltd")
                quote_id = make_quotation(cur, context.workspace, supplier_id=sup_id)
            conn.commit()

            # Row 1: Populated quotation_id and supplier_id
            log_id_matched = _insert_email_log(
                conn,
                tenant_id=context.workspace.tenant_id,
                quotation_id=quote_id,
                supplier_id=sup_id,
                match_method="domain",
                status="completed",
                subject="Quote for Apples",
                attachment_count=2,
            )

            # Row 2: Null quotation_id and supplier_id (e.g. rejected row before supplier match)
            log_id_rejected = _insert_email_log(
                conn,
                tenant_id=context.workspace.tenant_id,
                quotation_id=None,
                supplier_id=None,
                match_method=None,
                status="rejected",
                error_message="Sender domain not in allowlist",
                subject="Spam Email",
                attachment_count=0,
            )
            conn.commit()

        res = client.get("/api/v1/ingestion/emails")
        assert res.status_code == 200, res.text
        items_by_id = {item["id"]: item for item in res.json()["items"]}

        # Check matched row has populated quotation and supplier links
        matched = items_by_id[str(log_id_matched)]
        assert matched["quotation_id"] == str(quote_id)
        assert matched["supplier_id"] == str(sup_id)
        assert matched["match_method"] == "domain"
        assert matched["status"] == "completed"
        assert matched["error_message"] is None
        assert matched["attachment_count"] == 2

        # Check rejected row has null quotation and supplier links
        rejected = items_by_id[str(log_id_rejected)]
        assert rejected["quotation_id"] is None
        assert rejected["supplier_id"] is None
        assert rejected["match_method"] is None
        assert rejected["status"] == "rejected"
        assert rejected["error_message"] == "Sender domain not in allowlist"
        assert rejected["attachment_count"] == 0


def test_list_email_logs_buyer_and_owner_rbac(monkeypatch: pytest.MonkeyPatch) -> None:
    with committed_smart_context("email-log-rbac") as context:
        owner = member_from_workspace(context.workspace, role=MemberRole.owner)
        buyer = member_from_workspace(context.workspace, role=MemberRole.buyer)

        with psycopg.connect(TEST_DATABASE_URL or "") as conn:
            log_id = _insert_email_log(
                conn, tenant_id=context.workspace.tenant_id, subject="RBAC check"
            )
            conn.commit()

        owner_client = TestClient(_app(monkeypatch, owner), raise_server_exceptions=False)
        owner_res = owner_client.get("/api/v1/ingestion/emails")
        assert owner_res.status_code == 200
        assert any(item["id"] == str(log_id) for item in owner_res.json()["items"])

        buyer_client = TestClient(_app(monkeypatch, buyer), raise_server_exceptions=False)
        buyer_res = buyer_client.get("/api/v1/ingestion/emails")
        assert buyer_res.status_code == 200
        assert any(item["id"] == str(log_id) for item in buyer_res.json()["items"])

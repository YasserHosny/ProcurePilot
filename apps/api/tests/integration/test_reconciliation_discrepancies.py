"""Integration tests for reconciliation discrepancies (R3.1, US3, tasks T028-T030).

Covers:
- Amount mismatch on matched pair is detected and shows both figures side-by-side (Scenario 3.1)
- Unmatched bill appears immediately while unmatched purchase appears only after 30 days
  (Scenario 3.2, testing 29-day vs 31-day boundary)
- Resolving records resolver, timestamp, and optional note (Scenario 3.3)
- Resolved discrepancy reopens (not duplicates) when underlying records change on later sync
  (Scenario 3.4)
- Resolving an already-resolved discrepancy returns 409 ConflictError
- Cross-tenant discrepancy lookup resolves 404 Not Found (never 403)
- Open discrepancy whose condition clears is auto-resolved with resolved_by=null (decision #3)
- unmatched_purchase correctly excludes purchase record whose supplier has no synced_vendor
  (decision #2)
- RBAC: owner and buyer can resolve; other roles get 403
- Cursor pagination and status filtering on GET /accounting/discrepancies
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import psycopg
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from psycopg.rows import dict_row

from integration.catalogue_helpers import TEST_DATABASE_URL
from integration.smart_compare_helpers import (
    committed_smart_context,
    member_from_workspace,
    settings_for_test_db,
)
from procurepilot_api.deps import bearer_token, current_member
from procurepilot_api.main import create_app
from procurepilot_api.modules.accounting.reconciliation_service import ReconciliationService
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.shared.audit import AuditEventCreate

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is not set; needs a migrated local Postgres",
)


class RecordingAuditWriter:
    def __init__(self) -> None:
        self.events: list[AuditEventCreate] = []

    def record(self, event: AuditEventCreate, bearer_token: str | None = None) -> None:
        self.events.append(event)


def _app(
    monkeypatch: pytest.MonkeyPatch,
    member: object,
) -> tuple[FastAPI, RecordingAuditWriter]:
    monkeypatch.setenv("ACCOUNTING_PROVIDER_MODE", "stub")
    settings = settings_for_test_db(monkeypatch)
    writer = RecordingAuditWriter()
    monkeypatch.setattr(
        "procurepilot_api.modules.accounting.service.get_audit_writer",
        lambda: writer,
    )
    app = create_app(settings)
    app.dependency_overrides[current_member] = lambda: member
    app.dependency_overrides[bearer_token] = lambda: "test-token"
    return app, writer


def _act_as_tenant_sync(conn: psycopg.Connection, tenant_id: UUID) -> None:
    with conn.cursor() as cur:
        cur.execute("set local role authenticated")
        cur.execute(
            "select set_config('request.jwt.claims', %s, true)",
            (json.dumps({"tenant_id": str(tenant_id), "role": "authenticated"}),),
        )


def _seed_connection(
    tenant_id: UUID,
    membership_id: UUID,
    *,
    connection_id: UUID | None = None,
    status: str = "active",
) -> UUID:
    cid = connection_id or uuid4()
    with psycopg.connect(TEST_DATABASE_URL or "") as conn:
        with conn.cursor() as cur:
            cur.execute("set local role service_role")
            cur.execute(
                """
                insert into accounting_connection (
                    id, tenant_id, provider, realm_id, display_name,
                    access_token, refresh_token, status, connected_by,
                    connected_at
                ) values (
                    %s, %s, 'quickbooks', 'stub-realm-12345', 'Demo Company',
                    'test-access-token', 'test-refresh-token', %s, %s,
                    now()
                )
                """,
                (cid, tenant_id, status, membership_id),
            )
        conn.commit()
    return cid


def _seed_vendor(
    tenant_id: UUID,
    connection_id: UUID,
    *,
    provider_vendor_id: str = "v-001",
    display_name: str = "Vendor Display",
    matched_supplier_id: UUID | None = None,
    vendor_id: UUID | None = None,
) -> UUID:
    vid = vendor_id or uuid4()
    with psycopg.connect(TEST_DATABASE_URL or "") as conn:
        with conn.cursor() as cur:
            cur.execute("set local role service_role")
            cur.execute(
                """
                insert into synced_vendor (
                    id, tenant_id, connection_id, provider_vendor_id,
                    display_name, matched_supplier_id
                ) values (
                    %s, %s, %s, %s,
                    %s, %s
                )
                """,
                (
                    vid, tenant_id, connection_id,
                    provider_vendor_id, display_name, matched_supplier_id,
                ),
            )
        conn.commit()
    return vid


def _seed_bill(
    tenant_id: UUID,
    connection_id: UUID,
    vendor_id: UUID,
    *,
    amount: Decimal,
    currency: str = "USD",
    bill_date: date | None = None,
    provider_status: str = "open",
    provider_bill_id: str | None = None,
    matched_supplier_id: UUID | None = None,
    bill_id: UUID | None = None,
    updated_at: datetime | None = None,
) -> UUID:
    bid = bill_id or uuid4()
    bdate = bill_date or date.today()
    p_bid = provider_bill_id or f"bill-{bid}"
    u_at = updated_at or datetime.now(UTC)
    with psycopg.connect(TEST_DATABASE_URL or "") as conn:
        with conn.cursor() as cur:
            cur.execute("set local role service_role")
            cur.execute(
                """
                insert into synced_bill (
                    id, tenant_id, connection_id, provider_bill_id, vendor_id,
                    matched_supplier_id, amount, currency, bill_date, provider_status,
                    created_at, updated_at
                ) values (
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    now(), %s
                )
                """,
                (
                    bid,
                    tenant_id,
                    connection_id,
                    p_bid,
                    vendor_id,
                    matched_supplier_id,
                    amount,
                    currency,
                    bdate,
                    provider_status,
                    u_at,
                ),
            )
        conn.commit()
    return bid


def _seed_purchase_record(
    tenant_id: UUID,
    membership_id: UUID,
    product_id: UUID,
    supplier_id: UUID,
    *,
    amount: Decimal,
    currency: str = "USD",
    ordered_at: datetime | None = None,
    recorded_at: datetime | None = None,
    purchase_id: UUID | None = None,
    updated_at: datetime | None = None,
) -> UUID:
    pid = purchase_id or uuid4()
    p_ordered = ordered_at or datetime.now(UTC)
    p_recorded = recorded_at or p_ordered
    u_at = updated_at or datetime.now(UTC)
    with psycopg.connect(TEST_DATABASE_URL or "") as conn:
        with conn.cursor() as cur:
            cur.execute("set local role service_role")
            cur.execute(
                """
                insert into purchase_record (
                    id, tenant_id, workspace_product_id, supplier_id,
                    recorded_by, quantity, base_unit, unit_price_amount,
                    unit_price_currency, total_paid_amount, total_paid_currency,
                    delivery_result, ordered_at, delivered_at, recorded_at,
                    updated_at
                ) values (
                    %s, %s, %s, %s,
                    %s, 1.000000, 'each', %s,
                    %s, %s, %s,
                    'delivered', %s, %s, %s,
                    %s
                )
                """,
                (
                    pid,
                    tenant_id,
                    product_id,
                    supplier_id,
                    membership_id,
                    amount,
                    currency,
                    amount,
                    currency,
                    p_ordered,
                    p_ordered,
                    p_recorded,
                    u_at,
                ),
            )
        conn.commit()
    return pid


def _seed_match(
    tenant_id: UUID,
    synced_bill_id: UUID,
    purchase_record_id: UUID,
    *,
    match_method: str = "manual",
    matched_by: UUID | None = None,
) -> UUID:
    mid = uuid4()
    with psycopg.connect(TEST_DATABASE_URL or "") as conn:
        with conn.cursor() as cur:
            cur.execute("set local role service_role")
            cur.execute(
                """
                insert into purchase_bill_match (
                    id, tenant_id, synced_bill_id, purchase_record_id,
                    match_method, matched_by, matched_at
                ) values (
                    %s, %s, %s, %s,
                    %s, %s, now()
                )
                """,
                (mid, tenant_id, synced_bill_id, purchase_record_id, match_method, matched_by),
            )
        conn.commit()
    return mid


def _run_recompute(tenant_id: UUID, connection_id: UUID) -> dict[str, int]:
    with psycopg.connect(TEST_DATABASE_URL or "") as conn:
        _act_as_tenant_sync(conn, tenant_id)
        service = ReconciliationService()
        result = service.recompute_discrepancies(
            conn,
            tenant_id=tenant_id,
            connection_id=connection_id,
        )
        conn.commit()
        return result


def test_amount_mismatch_detected_and_shows_both_figures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Acceptance Scenario 3.1: Amount mismatch detected on matched pair, showing both figures."""
    with committed_smart_context("disc-amount-mismatch", supplier_count=1) as context:
        tenant_id = context.workspace.tenant_id
        membership_id = context.workspace.membership_id
        supplier_id = context.supplier_ids[0]
        product_id = context.product_id

        with psycopg.connect(TEST_DATABASE_URL or "") as conn:
            with conn.cursor() as cur:
                cur.execute("set local role service_role")
                cur.execute(
                    "update supplier set name = 'Supplier Alpha' where id = %s",
                    (supplier_id,),
                )
            conn.commit()

        conn_id = _seed_connection(tenant_id, membership_id)
        vendor_id = _seed_vendor(
            tenant_id,
            conn_id,
            display_name="Vendor Alpha QB",
            matched_supplier_id=supplier_id,
        )

        # Seed bill for 100.00 USD
        bill_id = _seed_bill(
            tenant_id,
            conn_id,
            vendor_id,
            amount=Decimal("100.00"),
            currency="USD",
            bill_date=date(2026, 9, 1),
            matched_supplier_id=supplier_id,
        )

        # Seed purchase record for 125.50 USD
        purchase_id = _seed_purchase_record(
            tenant_id,
            membership_id,
            product_id,
            supplier_id,
            amount=Decimal("125.50"),
            currency="USD",
            ordered_at=datetime(2026, 9, 1, 12, 0, tzinfo=UTC),
        )

        # Seed manual match linking them
        _seed_match(
            tenant_id,
            bill_id,
            purchase_id,
            match_method="manual",
            matched_by=membership_id,
        )

        # Run recompute
        counts = _run_recompute(tenant_id, conn_id)
        assert counts["amount_mismatches"] == 1
        assert counts["inserted"] == 1

        # Query API as owner
        owner = member_from_workspace(context.workspace, role=MemberRole.owner)
        app, _ = _app(monkeypatch, owner)
        client = TestClient(app, raise_server_exceptions=False)

        res = client.get("/api/v1/accounting/discrepancies")
        assert res.status_code == 200, res.text
        data = res.json()
        assert len(data["items"]) == 1

        item = data["items"][0]
        assert item["discrepancy_type"] == "amount_mismatch"
        assert item["status"] == "open"
        assert item["synced_bill_id"] == str(bill_id)
        assert item["purchase_record_id"] == str(purchase_id)

        # Scenario 3.1 & decision #1: both figures side-by-side in their explicit currencies
        bill_detail = item["synced_bill_detail"]
        assert bill_detail is not None
        assert bill_detail["vendor_name"] == "Vendor Alpha QB"
        assert Decimal(bill_detail["amount"]) == Decimal("100.00")
        assert bill_detail["currency"] == "USD"
        assert bill_detail["bill_date"] == "2026-09-01"

        pr_detail = item["purchase_record_detail"]
        assert pr_detail is not None
        assert pr_detail["supplier_name"] == "Supplier Alpha"
        assert Decimal(pr_detail["amount"]) == Decimal("125.50")
        assert pr_detail["currency"] == "USD"
        assert pr_detail["date"] == "2026-09-01"


def test_unmatched_bill_immediate_and_unmatched_purchase_30_day_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Acceptance Scenario 3.2: Unmatched bill appears immediately; purchase appears after 30d."""
    with committed_smart_context("disc-boundaries", supplier_count=1) as context:
        tenant_id = context.workspace.tenant_id
        membership_id = context.workspace.membership_id
        supplier_id = context.supplier_ids[0]
        product_id = context.product_id

        conn_id = _seed_connection(tenant_id, membership_id)
        vendor_id = _seed_vendor(
            tenant_id,
            conn_id,
            display_name="Supplier Beta",
            matched_supplier_id=supplier_id,
        )

        # 1. Unmatched bill (today) -> flagged immediately
        bill_id = _seed_bill(
            tenant_id,
            conn_id,
            vendor_id,
            amount=Decimal("50.00"),
            currency="USD",
            bill_date=date.today(),
            matched_supplier_id=supplier_id,
        )

        now = datetime.now(UTC)

        # 2. Purchase record 29 days old -> NOT flagged (under 30-day threshold)
        pr_29d = _seed_purchase_record(
            tenant_id,
            membership_id,
            product_id,
            supplier_id,
            amount=Decimal("200.00"),
            ordered_at=now - timedelta(days=29),
        )

        # 3. Purchase record 31 days old -> IS flagged (> 30 days)
        pr_31d = _seed_purchase_record(
            tenant_id,
            membership_id,
            product_id,
            supplier_id,
            amount=Decimal("300.00"),
            ordered_at=now - timedelta(days=31),
        )

        counts = _run_recompute(tenant_id, conn_id)
        assert counts["unmatched_bills"] == 1
        assert counts["unmatched_purchases"] == 1
        assert counts["total_open"] == 2

        owner = member_from_workspace(context.workspace, role=MemberRole.owner)
        app, _ = _app(monkeypatch, owner)
        client = TestClient(app, raise_server_exceptions=False)

        res = client.get("/api/v1/accounting/discrepancies")
        assert res.status_code == 200, res.text
        items = res.json()["items"]
        assert len(items) == 2

        types_by_id = {item["discrepancy_type"]: item for item in items}
        assert "unmatched_bill" in types_by_id
        assert "unmatched_purchase" in types_by_id

        unmatched_bill_item = types_by_id["unmatched_bill"]
        assert unmatched_bill_item["synced_bill_id"] == str(bill_id)
        assert unmatched_bill_item["purchase_record_id"] is None
        assert unmatched_bill_item["synced_bill_detail"] is not None
        assert unmatched_bill_item["purchase_record_detail"] is None

        unmatched_pr_item = types_by_id["unmatched_purchase"]
        assert unmatched_pr_item["purchase_record_id"] == str(pr_31d)
        assert unmatched_pr_item["synced_bill_id"] is None
        assert unmatched_pr_item["synced_bill_detail"] is None
        assert unmatched_pr_item["purchase_record_detail"] is not None

        # Confirm pr_29d was NOT flagged
        assert not any(item["purchase_record_id"] == str(pr_29d) for item in items)


def test_resolve_records_resolver_timestamp_and_note(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Acceptance Scenario 3.3: Resolving records resolver, timestamp, and optional note."""
    with committed_smart_context("disc-resolve-record", supplier_count=1) as context:
        tenant_id = context.workspace.tenant_id
        membership_id = context.workspace.membership_id
        supplier_id = context.supplier_ids[0]

        conn_id = _seed_connection(tenant_id, membership_id)
        vendor_id = _seed_vendor(
            tenant_id,
            conn_id,
            display_name="Supplier Gamma",
            matched_supplier_id=supplier_id,
        )
        _seed_bill(
            tenant_id,
            conn_id,
            vendor_id,
            amount=Decimal("75.00"),
            currency="USD",
        )

        _run_recompute(tenant_id, conn_id)

        buyer = member_from_workspace(context.workspace, role=MemberRole.buyer)
        app, audit_writer = _app(monkeypatch, buyer)
        client = TestClient(app, raise_server_exceptions=False)

        list_res = client.get("/api/v1/accounting/discrepancies")
        assert list_res.status_code == 200
        disc_id = list_res.json()["items"][0]["id"]

        resolve_res = client.post(
            f"/api/v1/accounting/discrepancies/{disc_id}/resolve",
            json={"note": "Approved discrepancy after manual check"},
        )
        assert resolve_res.status_code == 200, resolve_res.text
        resolved_data = resolve_res.json()

        assert resolved_data["status"] == "resolved"
        assert resolved_data["resolved_by"] == str(buyer.membership_id)
        assert resolved_data["resolved_at"] is not None
        assert resolved_data["resolution_note"] == "Approved discrepancy after manual check"

        # Check DB state directly
        with psycopg.connect(TEST_DATABASE_URL or "", row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute("set local role service_role")
                cur.execute(
                    "select status, resolved_by, resolved_at, resolution_note "
                    "from reconciliation_discrepancy where id = %s",
                    (disc_id,),
                )
                db_row = cur.fetchone()

        assert db_row is not None
        assert db_row["status"] == "resolved"
        assert str(db_row["resolved_by"]) == str(buyer.membership_id)
        assert db_row["resolution_note"] == "Approved discrepancy after manual check"

        # Check audit event
        audit_events = [
            e for e in audit_writer.events if e.action == "accounting.discrepancy_resolved"
        ]
        assert len(audit_events) >= 1
        assert audit_events[0].target["reconciliation_discrepancy_id"] == str(disc_id)
        assert audit_events[0].target["note"] == "Approved discrepancy after manual check"


def test_resolved_discrepancy_reopens_when_underlying_record_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Acceptance Scenario 3.4: Resolved discrepancy reopens (not duplicates) if records change."""
    with committed_smart_context("disc-reopen", supplier_count=1) as context:
        tenant_id = context.workspace.tenant_id
        membership_id = context.workspace.membership_id
        supplier_id = context.supplier_ids[0]

        conn_id = _seed_connection(tenant_id, membership_id)
        vendor_id = _seed_vendor(
            tenant_id,
            conn_id,
            display_name="Supplier Delta",
            matched_supplier_id=supplier_id,
        )
        bill_id = _seed_bill(
            tenant_id,
            conn_id,
            vendor_id,
            amount=Decimal("99.00"),
            currency="USD",
        )

        _run_recompute(tenant_id, conn_id)

        owner = member_from_workspace(context.workspace, role=MemberRole.owner)
        app, _ = _app(monkeypatch, owner)
        client = TestClient(app, raise_server_exceptions=False)

        disc_id = client.get("/api/v1/accounting/discrepancies").json()["items"][0]["id"]

        # Resolve the discrepancy
        client.post(
            f"/api/v1/accounting/discrepancies/{disc_id}/resolve",
            json={"note": "Initial resolution"},
        )

        # Immediate recompute without changes -> remains resolved
        counts_second = _run_recompute(tenant_id, conn_id)
        assert counts_second["reopened"] == 0
        assert counts_second["inserted"] == 0

        with psycopg.connect(TEST_DATABASE_URL or "", row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute("set local role service_role")
                cur.execute(
                    "select status, detected_at, resolved_at "
                    "from reconciliation_discrepancy where id = %s",
                    (disc_id,),
                )
                r_state = cur.fetchone()
                assert r_state["status"] == "resolved"
                orig_detected_at = r_state["detected_at"]
                orig_resolved_at = r_state["resolved_at"]

                # Simulate provider-side change updating bill updated_at past resolved_at
                cur.execute(
                    "update synced_bill set updated_at = %s where id = %s",
                    (orig_resolved_at + timedelta(seconds=10), bill_id),
                )
            conn.commit()

        # Recompute on later sync -> should REOPEN the existing row
        counts_third = _run_recompute(tenant_id, conn_id)
        assert counts_third["reopened"] == 1
        assert counts_third["inserted"] == 0

        with psycopg.connect(TEST_DATABASE_URL or "", row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute("set local role service_role")
                cur.execute(
                    "select count(*) from reconciliation_discrepancy where tenant_id = %s",
                    (tenant_id,),
                )
                total_count = cur.fetchone()["count"]
                assert total_count == 1  # Reopened, NOT duplicated!

                cur.execute(
                    "select status, detected_at, resolved_by, resolved_at, resolution_note "
                    "from reconciliation_discrepancy where id = %s",
                    (disc_id,),
                )
                reopened_row = cur.fetchone()

        assert reopened_row["status"] == "open"
        assert reopened_row["detected_at"] == orig_detected_at  # detected_at preserved
        assert reopened_row["resolved_by"] is None
        assert reopened_row["resolved_at"] is None
        assert reopened_row["resolution_note"] is None


def test_resolving_already_resolved_discrepancy_returns_409(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Refuse resolving an already-resolved discrepancy with 409 Conflict."""
    with committed_smart_context("disc-already-resolved", supplier_count=1) as context:
        tenant_id = context.workspace.tenant_id
        membership_id = context.workspace.membership_id
        supplier_id = context.supplier_ids[0]

        conn_id = _seed_connection(tenant_id, membership_id)
        vendor_id = _seed_vendor(
            tenant_id,
            conn_id,
            display_name="Supplier Epsilon",
            matched_supplier_id=supplier_id,
        )
        _seed_bill(tenant_id, conn_id, vendor_id, amount=Decimal("150.00"), currency="USD")

        _run_recompute(tenant_id, conn_id)

        owner = member_from_workspace(context.workspace, role=MemberRole.owner)
        app, _ = _app(monkeypatch, owner)
        client = TestClient(app, raise_server_exceptions=False)

        disc_id = client.get("/api/v1/accounting/discrepancies").json()["items"][0]["id"]

        # First resolution succeeds (200)
        res1 = client.post(
            f"/api/v1/accounting/discrepancies/{disc_id}/resolve",
            json={"note": "First resolution"},
        )
        assert res1.status_code == 200

        # Second resolution returns 409
        res2 = client.post(
            f"/api/v1/accounting/discrepancies/{disc_id}/resolve",
            json={"note": "Duplicate resolution attempt"},
        )
        assert res2.status_code == 409, res2.text


def test_cross_tenant_discrepancy_lookup_returns_404(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cross-tenant discrepancy lookup and resolve returns 404, never 403."""
    with committed_smart_context("disc-tenant-a", supplier_count=1) as ctx_a:
        tenant_a = ctx_a.workspace.tenant_id
        conn_a = _seed_connection(tenant_a, ctx_a.workspace.membership_id)
        v_a = _seed_vendor(tenant_a, conn_a, matched_supplier_id=ctx_a.supplier_ids[0])
        _seed_bill(tenant_a, conn_a, v_a, amount=Decimal("50.00"), currency="USD")
        _run_recompute(tenant_a, conn_a)

        owner_a = member_from_workspace(ctx_a.workspace, role=MemberRole.owner)
        app_a, _ = _app(monkeypatch, owner_a)
        client_a = TestClient(app_a, raise_server_exceptions=False)
        disc_id_a = client_a.get("/api/v1/accounting/discrepancies").json()["items"][0]["id"]

        with committed_smart_context("disc-tenant-b", supplier_count=1) as ctx_b:
            owner_b = member_from_workspace(ctx_b.workspace, role=MemberRole.owner)
            app_b, _ = _app(monkeypatch, owner_b)
            client_b = TestClient(app_b, raise_server_exceptions=False)

            # Tenant B list does not contain Tenant A's discrepancy
            list_b = client_b.get("/api/v1/accounting/discrepancies").json()["items"]
            assert not any(item["id"] == disc_id_a for item in list_b)

            # Tenant B trying to resolve Tenant A's discrepancy returns 404 (not 403)
            resolve_b = client_b.post(
                f"/api/v1/accounting/discrepancies/{disc_id_a}/resolve",
                json={"note": "Cross-tenant attempt"},
            )
            assert resolve_b.status_code == 404, resolve_b.text


def test_open_discrepancy_auto_resolves_when_condition_clears(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Decision #3: An open discrepancy whose underlying condition clears is auto-resolved."""
    with committed_smart_context("disc-auto-resolve", supplier_count=1) as context:
        tenant_id = context.workspace.tenant_id
        membership_id = context.workspace.membership_id
        supplier_id = context.supplier_ids[0]
        product_id = context.product_id

        conn_id = _seed_connection(tenant_id, membership_id)
        vendor_id = _seed_vendor(
            tenant_id,
            conn_id,
            display_name="Supplier Zeta",
            matched_supplier_id=supplier_id,
        )

        # Seed unmatched bill -> creates open discrepancy
        bill_id = _seed_bill(
            tenant_id,
            conn_id,
            vendor_id,
            amount=Decimal("80.00"),
            currency="USD",
            matched_supplier_id=supplier_id,
        )

        counts1 = _run_recompute(tenant_id, conn_id)
        assert counts1["unmatched_bills"] == 1
        assert counts1["inserted"] == 1

        with psycopg.connect(TEST_DATABASE_URL or "", row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute("set local role service_role")
                cur.execute(
                    "select id, status from reconciliation_discrepancy where tenant_id = %s",
                    (tenant_id,),
                )
                row = cur.fetchone()
                assert row["status"] == "open"
                disc_id = row["id"]

        # Now condition clears: bill gets matched to a purchase record
        purchase_id = _seed_purchase_record(
            tenant_id,
            membership_id,
            product_id,
            supplier_id,
            amount=Decimal("80.00"),
            currency="USD",
        )
        _seed_match(tenant_id, bill_id, purchase_id, match_method="automatic")

        # Next sync/recompute runs
        counts2 = _run_recompute(tenant_id, conn_id)
        assert counts2["unmatched_bills"] == 0
        assert counts2["auto_resolved"] == 1

        with psycopg.connect(TEST_DATABASE_URL or "", row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute("set local role service_role")
                cur.execute(
                    "select status, resolved_by, resolved_at, resolution_note "
                    "from reconciliation_discrepancy where id = %s",
                    (disc_id,),
                )
                db_row = cur.fetchone()

        # Verified per decision #3: system auto-resolved with resolved_by=null
        assert db_row["status"] == "resolved"
        assert db_row["resolved_by"] is None
        assert db_row["resolved_at"] is not None
        assert "Automatically resolved" in db_row["resolution_note"]

        # Open list is now empty; resolved list shows the auto-resolved item
        owner = member_from_workspace(context.workspace, role=MemberRole.owner)
        app, _ = _app(monkeypatch, owner)
        client = TestClient(app, raise_server_exceptions=False)

        open_res = client.get("/api/v1/accounting/discrepancies?status=open").json()
        assert len(open_res["items"]) == 0

        resolved_res = client.get("/api/v1/accounting/discrepancies?status=resolved").json()
        assert len(resolved_res["items"]) == 1
        assert resolved_res["items"][0]["id"] == str(disc_id)
        assert resolved_res["items"][0]["resolved_by"] is None


def test_unmatched_purchase_excludes_supplier_without_synced_vendor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Decision #2: unmatched_purchase scopes only to suppliers with a synced_vendor link."""
    with committed_smart_context("disc-supplier-scoping", supplier_count=2) as context:
        tenant_id = context.workspace.tenant_id
        membership_id = context.workspace.membership_id
        product_id = context.product_id

        supplier_linked = context.supplier_ids[0]
        supplier_unlinked = context.supplier_ids[1]

        conn_id = _seed_connection(tenant_id, membership_id)
        # Link supplier_linked to synced_vendor; do NOT link supplier_unlinked
        _seed_vendor(
            tenant_id,
            conn_id,
            display_name="Supplier Linked QB",
            matched_supplier_id=supplier_linked,
        )

        now = datetime.now(UTC)

        # Seed 35-day-old purchase record for supplier_linked -> SHOULD be flagged
        pr_linked = _seed_purchase_record(
            tenant_id,
            membership_id,
            product_id,
            supplier_linked,
            amount=Decimal("450.00"),
            ordered_at=now - timedelta(days=35),
        )

        # Seed 35-day-old purchase record for supplier_unlinked -> MUST NOT be flagged
        pr_unlinked = _seed_purchase_record(
            tenant_id,
            membership_id,
            product_id,
            supplier_unlinked,
            amount=Decimal("900.00"),
            ordered_at=now - timedelta(days=35),
        )

        counts = _run_recompute(tenant_id, conn_id)
        assert counts["unmatched_purchases"] == 1

        with psycopg.connect(TEST_DATABASE_URL or "", row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute("set local role service_role")
                cur.execute(
                    "select purchase_record_id from reconciliation_discrepancy "
                    "where tenant_id = %s",
                    (tenant_id,),
                )
                rows = cur.fetchall()

        flagged_pr_ids = [r["purchase_record_id"] for r in rows]
        assert pr_linked in flagged_pr_ids
        assert pr_unlinked not in flagged_pr_ids


def test_resolve_rbac_non_owner_buyer_forbidden(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-owner / non-buyer roles get 403 on POST /accounting/discrepancies/{id}/resolve."""
    with committed_smart_context("disc-rbac", supplier_count=1) as context:
        tenant_id = context.workspace.tenant_id
        membership_id = context.workspace.membership_id
        supplier_id = context.supplier_ids[0]

        conn_id = _seed_connection(tenant_id, membership_id)
        vendor_id = _seed_vendor(
            tenant_id,
            conn_id,
            matched_supplier_id=supplier_id,
        )
        _seed_bill(tenant_id, conn_id, vendor_id, amount=Decimal("10.00"))
        _run_recompute(tenant_id, conn_id)

        # Try resolving as viewer
        viewer = member_from_workspace(context.workspace, role=MemberRole.viewer)
        app, _ = _app(monkeypatch, viewer)
        client = TestClient(app, raise_server_exceptions=False)

        disc_id = uuid4()
        res = client.post(
            f"/api/v1/accounting/discrepancies/{disc_id}/resolve",
            json={"note": "Unauthorized attempt"},
        )
        assert res.status_code == 403, res.text


def test_list_discrepancies_cursor_pagination(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cursor pagination works as expected on GET /accounting/discrepancies."""
    with committed_smart_context("disc-pagination", supplier_count=1) as context:
        tenant_id = context.workspace.tenant_id
        membership_id = context.workspace.membership_id
        supplier_id = context.supplier_ids[0]

        conn_id = _seed_connection(tenant_id, membership_id)
        vendor_id = _seed_vendor(
            tenant_id,
            conn_id,
            matched_supplier_id=supplier_id,
        )

        for i in range(5):
            _seed_bill(
                tenant_id,
                conn_id,
                vendor_id,
                amount=Decimal(f"{10 + i}.00"),
                provider_bill_id=f"page-bill-{i}",
            )

        _run_recompute(tenant_id, conn_id)

        owner = member_from_workspace(context.workspace, role=MemberRole.owner)
        app, _ = _app(monkeypatch, owner)
        client = TestClient(app, raise_server_exceptions=False)

        # Page 1: limit 2
        page1 = client.get("/api/v1/accounting/discrepancies?limit=2").json()
        assert len(page1["items"]) == 2
        assert page1["next_cursor"] is not None

        # Page 2: limit 2 using cursor
        page2 = client.get(
            f"/api/v1/accounting/discrepancies?limit=2&cursor={page1['next_cursor']}"
        ).json()
        assert len(page2["items"]) == 2
        assert page2["next_cursor"] is not None

        # Items across pages should not overlap
        p1_ids = {item["id"] for item in page1["items"]}
        p2_ids = {item["id"] for item in page2["items"]}
        assert p1_ids.isdisjoint(p2_ids)

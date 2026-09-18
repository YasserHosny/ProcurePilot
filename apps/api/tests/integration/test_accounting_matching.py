"""Integration tests for accounting automatic matching (R3.1, US2, task T024).

Covers:
- Exact match between synced bill and purchase_record creates purchase_bill_match row
- Synced bill with no matching purchase record remains unmatched and visible in
  GET /accounting/bills
- Cross-tenant purchase records are never candidates for matching
- SC-002 aggregate claim: >= 90% auto-match rate on genuinely matchable batch
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
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
    settings_for_test_db,
)
from procurepilot_api.deps import bearer_token, current_member
from procurepilot_api.main import create_app
from procurepilot_api.modules.accounting.connector import (
    RawBill,
    RawVendor,
    StubConnector,
)
from procurepilot_api.modules.accounting.sync_service import SyncService
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


@pytest.fixture(autouse=True)
def _mock_audit_writer(monkeypatch: pytest.MonkeyPatch) -> RecordingAuditWriter:
    writer = RecordingAuditWriter()
    monkeypatch.setattr(
        "procurepilot_api.shared.audit.get_audit_writer",
        lambda: writer,
    )
    monkeypatch.setattr(
        "procurepilot_api.modules.accounting.service.get_audit_writer",
        lambda: writer,
    )
    monkeypatch.setattr(
        "procurepilot_api.modules.accounting.sync_service.get_audit_writer",
        lambda: writer,
    )
    return writer


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
    monkeypatch.setattr(
        "procurepilot_api.modules.accounting.sync_service.get_audit_writer",
        lambda: writer,
    )
    app = create_app(settings)
    app.dependency_overrides[current_member] = lambda: member
    app.dependency_overrides[bearer_token] = lambda: "test-token"
    return app, writer


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


def _seed_purchase_record(
    tenant_id: UUID,
    membership_id: UUID,
    product_id: UUID,
    supplier_id: UUID,
    *,
    amount: Decimal,
    currency: str = "USD",
    ordered_at: date | datetime | None = None,
    purchase_id: UUID | None = None,
) -> UUID:
    pid = purchase_id or uuid4()
    pdate = ordered_at or date.today()
    with psycopg.connect(TEST_DATABASE_URL or "") as conn:
        with conn.cursor() as cur:
            cur.execute("set local role service_role")
            cur.execute(
                """
                insert into purchase_record (
                    id, tenant_id, workspace_product_id, supplier_id,
                    recorded_by, quantity, base_unit, unit_price_amount,
                    unit_price_currency, total_paid_amount, total_paid_currency,
                    delivery_result, ordered_at, delivered_at, recorded_at
                ) values (
                    %s, %s, %s, %s,
                    %s, 1.000000, 'each', %s,
                    %s, %s, %s,
                    'delivered', %s, %s, %s
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
                    pdate,
                    pdate,
                    pdate,
                ),
            )
        conn.commit()
    return pid


def test_exact_match_creates_purchase_bill_match(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FR-007 / Acceptance Scenario 2.2: Exact match links synced bill and purchase record."""
    settings = settings_for_test_db(monkeypatch)
    with committed_smart_context("acct-match-exact", supplier_count=1) as context:
        supplier_id = context.supplier_ids[0]
        # Align supplier name with StubConnector default vendor "Global Office Supplies"
        with psycopg.connect(TEST_DATABASE_URL or "") as conn:
            with conn.cursor() as cur:
                cur.execute("set local role service_role")
                cur.execute(
                    "update supplier set name = 'Global Office Supplies' where id = %s",
                    (supplier_id,),
                )
            conn.commit()

        # Seed purchase record matching stub-bill-101 (1250.00 USD, 15 days ago)
        bill_date = date.today() - timedelta(days=15)
        purchase_id = _seed_purchase_record(
            context.workspace.tenant_id,
            context.workspace.membership_id,
            context.product_id,
            supplier_id,
            amount=Decimal("1250.00"),
            currency="USD",
            ordered_at=bill_date,
        )

        conn_id = _seed_connection(
            context.workspace.tenant_id,
            context.workspace.membership_id,
        )

        service = SyncService()
        result = service.sync(
            settings,
            tenant_id=context.workspace.tenant_id,
            connection_id=conn_id,
        )

        assert result["matches_created"] == 1

        with psycopg.connect(TEST_DATABASE_URL or "", row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute("set local role service_role")
                cur.execute(
                    """
                    select m.id, m.synced_bill_id, m.purchase_record_id, m.match_method,
                           m.matched_by
                    from purchase_bill_match m
                    join synced_bill b on b.id = m.synced_bill_id
                    where m.tenant_id = %s and b.provider_bill_id = 'stub-bill-101'
                    """,
                    (context.workspace.tenant_id,),
                )
                match_row = cur.fetchone()

        assert match_row is not None
        assert match_row["purchase_record_id"] == purchase_id
        assert match_row["match_method"] == "automatic"
        assert match_row["matched_by"] is None

        # Verify router bills endpoint returns matched status and purchase_record_id
        app, _ = _app(monkeypatch, context.member)
        client = TestClient(app, raise_server_exceptions=False)
        bills_res = client.get("/api/v1/accounting/bills?match_status=matched")
        assert bills_res.status_code == 200, bills_res.text
        matched_items = bills_res.json()["items"]
        assert len(matched_items) == 1
        assert matched_items[0]["matched"] is True
        assert matched_items[0]["purchase_record_id"] == str(purchase_id)
        assert matched_items[0]["vendor_name"] == "Global Office Supplies"


def test_unmatched_bill_stays_unmatched_and_visible(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Acceptance Scenario 2.3: Unmatched bills are not hidden, remain visible in listing."""
    settings = settings_for_test_db(monkeypatch)
    with committed_smart_context("acct-match-unmatched", supplier_count=1) as context:
        conn_id = _seed_connection(
            context.workspace.tenant_id,
            context.workspace.membership_id,
        )

        # Sync without seeding any matching purchase records
        service = SyncService()
        result = service.sync(
            settings,
            tenant_id=context.workspace.tenant_id,
            connection_id=conn_id,
        )
        assert result["matches_created"] == 0

        app, _ = _app(monkeypatch, context.member)
        client = TestClient(app, raise_server_exceptions=False)

        # GET /accounting/bills?match_status=unmatched returns all 3 bills
        unmatched_res = client.get("/api/v1/accounting/bills?match_status=unmatched")
        assert unmatched_res.status_code == 200, unmatched_res.text
        unmatched_items = unmatched_res.json()["items"]
        assert len(unmatched_items) == 3
        for item in unmatched_items:
            assert item["matched"] is False
            assert item["purchase_record_id"] is None

        # GET /accounting/bills?match_status=matched returns 0 bills
        matched_res = client.get("/api/v1/accounting/bills?match_status=matched")
        assert matched_res.status_code == 200, matched_res.text
        assert len(matched_res.json()["items"]) == 0


def test_cross_tenant_purchase_records_are_never_matched(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Principle V / SC-004: Tenant B's purchase record is never matched to Tenant A's bill."""
    settings = settings_for_test_db(monkeypatch)
    with committed_smart_context("acct-match-t-a", supplier_count=1) as ctx_a:
        with committed_smart_context("acct-match-t-b", supplier_count=1) as ctx_b:
            sup_a = ctx_a.supplier_ids[0]
            sup_b = ctx_b.supplier_ids[0]

            with psycopg.connect(TEST_DATABASE_URL or "") as conn:
                with conn.cursor() as cur:
                    cur.execute("set local role service_role")
                    cur.execute(
                        "update supplier set name = 'Global Office Supplies' where id = %s",
                        (sup_a,),
                    )
                    cur.execute(
                        "update supplier set name = 'Global Office Supplies' where id = %s",
                        (sup_b,),
                    )
                conn.commit()

            bill_date = date.today() - timedelta(days=15)

            # Seed purchase record in Tenant B that would match Tenant A's bill (1250.00 USD)
            _seed_purchase_record(
                ctx_b.workspace.tenant_id,
                ctx_b.workspace.membership_id,
                ctx_b.product_id,
                sup_b,
                amount=Decimal("1250.00"),
                currency="USD",
                ordered_at=bill_date,
            )

            # Tenant A has connection and syncs bills, but has NO purchase records in Tenant A
            conn_a = _seed_connection(
                ctx_a.workspace.tenant_id,
                ctx_a.workspace.membership_id,
            )

            service = SyncService()
            result = service.sync(
                settings,
                tenant_id=ctx_a.workspace.tenant_id,
                connection_id=conn_a,
            )

            # Must not match Tenant B's purchase record!
            assert result["matches_created"] == 0

            with psycopg.connect(TEST_DATABASE_URL or "") as conn:
                with conn.cursor() as cur:
                    cur.execute("set local role service_role")
                    cur.execute(
                        "select count(*) from purchase_bill_match where tenant_id = %s",
                        (ctx_a.workspace.tenant_id,),
                    )
                    assert cur.fetchone()[0] == 0


def test_sc_002_batch_auto_match_rate_at_least_90_percent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SC-002: At least 90% of genuinely matching bills are automatically linked."""
    settings = settings_for_test_db(monkeypatch)
    with committed_smart_context("acct-match-sc002", supplier_count=1) as context:
        supplier_id = context.supplier_ids[0]
        vendor_name = "Bulk Batch Supplier"

        with psycopg.connect(TEST_DATABASE_URL or "") as conn:
            with conn.cursor() as cur:
                cur.execute("set local role service_role")
                cur.execute(
                    "update supplier set name = %s where id = %s",
                    (vendor_name, supplier_id),
                )
            conn.commit()

        conn_id = _seed_connection(
            context.workspace.tenant_id,
            context.workspace.membership_id,
        )

        today = date.today()
        bills: list[RawBill] = []

        # Generate 20 bills and 20 purchase records:
        # - 18 genuinely matchable (same supplier, amount within $0.01, date within 14 days)
        # - 2 deliberately not matchable (one amount mismatch > $0.01, one date diff > 14 days)
        total_batch_size = 20
        matchable_count = 18

        for i in range(1, matchable_count + 1):
            bill_amt = Decimal(f"{100 + i}.00")
            # Alternate exact amount and $0.01 rounding difference
            rec_amt = bill_amt if i % 2 == 0 else bill_amt + Decimal("0.01")
            bill_date = today - timedelta(days=5)
            # Alternate exact date and small date offset (e.g. 3 days, within 14 days)
            rec_date = bill_date if i % 3 == 0 else bill_date + timedelta(days=3)

            bills.append(
                RawBill(
                    provider_bill_id=f"batch-bill-{i:03d}",
                    provider_vendor_id="batch-vendor",
                    amount=bill_amt,
                    currency="USD",
                    bill_date=bill_date,
                    status="open",
                )
            )
            _seed_purchase_record(
                context.workspace.tenant_id,
                context.workspace.membership_id,
                context.product_id,
                supplier_id,
                amount=rec_amt,
                currency="USD",
                ordered_at=rec_date,
            )

        # Bill 19: amount mismatch ($50 difference)
        bills.append(
            RawBill(
                provider_bill_id="batch-bill-019",
                provider_vendor_id="batch-vendor",
                amount=Decimal("500.00"),
                currency="USD",
                bill_date=today - timedelta(days=5),
                status="open",
            )
        )
        _seed_purchase_record(
            context.workspace.tenant_id,
            context.workspace.membership_id,
            context.product_id,
            supplier_id,
            amount=Decimal("550.00"),
            currency="USD",
            ordered_at=today - timedelta(days=5),
        )

        # Bill 20: date mismatch (30 days apart, exceeding 14-day window)
        bills.append(
            RawBill(
                provider_bill_id="batch-bill-020",
                provider_vendor_id="batch-vendor",
                amount=Decimal("600.00"),
                currency="USD",
                bill_date=today - timedelta(days=35),
                status="open",
            )
        )
        _seed_purchase_record(
            context.workspace.tenant_id,
            context.workspace.membership_id,
            context.product_id,
            supplier_id,
            amount=Decimal("600.00"),
            currency="USD",
            ordered_at=today,
        )

        vendors = [RawVendor(provider_vendor_id="batch-vendor", display_name=vendor_name)]
        connector = StubConnector(bills=bills, vendors=vendors)

        service = SyncService(connector=connector)
        result = service.sync(
            settings,
            tenant_id=context.workspace.tenant_id,
            connection_id=conn_id,
        )

        matches_created = int(result["matches_created"])
        match_rate = matches_created / total_batch_size

        assert matches_created == matchable_count
        assert match_rate >= 0.90, f"Expected match rate >= 0.90, got {match_rate}"

        # Verify DB directly contains exactly 18 matches
        with psycopg.connect(TEST_DATABASE_URL or "") as conn:
            with conn.cursor() as cur:
                cur.execute("set local role service_role")
                cur.execute(
                    "select count(*) from purchase_bill_match where tenant_id = %s",
                    (context.workspace.tenant_id,),
                )
                assert cur.fetchone()[0] == 18

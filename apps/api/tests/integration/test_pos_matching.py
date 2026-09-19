"""Integration tests for POS product matching (R3.2, US2, task T023).

Covers:
- Confident single-candidate match creates pos_product_match
  (match_method='automatic', matched_by=None)
- Ambiguous candidates are left unmatched and visible for manual review (FR-006)
- Manual match via POST /pos/signals/{id}/match succeeds and records matched_by (FR-006)
- Conflict on manual match if signal or product already matched (409 Conflict)
- Cross-tenant workspace products are never candidates (proven directly, not just assumed from RLS)
"""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import psycopg
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from psycopg.rows import dict_row

from integration.catalogue_helpers import (
    TEST_DATABASE_URL,
    make_workspace_product,
)
from integration.smart_compare_helpers import (
    committed_smart_context,
    member_from_workspace,
    settings_for_test_db,
)
from procurepilot_api.deps import bearer_token, current_member
from procurepilot_api.main import create_app
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.shared.audit import AuditEventCreate
from procurepilot_api.shared.rate_limit import mutation_limiter

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is not set; needs a migrated local Postgres",
)


@pytest.fixture(autouse=True)
def _reset_mutation_limiter() -> None:
    # See test_pos_sync.py's identical fixture for why this is needed.
    mutation_limiter.reset()


class RecordingAuditWriter:
    def __init__(self) -> None:
        self.events: list[AuditEventCreate] = []

    def record(self, event: AuditEventCreate, bearer_token: str | None = None) -> None:
        self.events.append(event)


def _app(
    monkeypatch: pytest.MonkeyPatch, member: object
) -> tuple[FastAPI, RecordingAuditWriter]:
    monkeypatch.setenv("POS_PROVIDER_MODE", "stub")
    settings = settings_for_test_db(monkeypatch)
    audit_writer = RecordingAuditWriter()
    monkeypatch.setattr(
        "procurepilot_api.modules.pos.service.get_audit_writer",
        lambda: audit_writer,
    )
    monkeypatch.setattr(
        "procurepilot_api.modules.pos.sync_service.get_audit_writer",
        lambda: audit_writer,
    )
    app = create_app(settings)
    app.dependency_overrides[current_member] = lambda: member
    app.dependency_overrides[bearer_token] = lambda: "test-token"
    return app, audit_writer


def _connect_owner(client: TestClient) -> dict[str, object]:
    start_res = client.post("/api/v1/pos/connect")
    assert start_res.status_code == 200
    state = parse_qs(urlparse(start_res.json()["authorization_url"]).query)["state"][0]
    client.get(
        f"/api/v1/pos/connect/callback?code=stub-auth-code&state={state}",
        follow_redirects=False,
    )
    return client.get("/api/v1/pos/connection").json()


def test_confident_single_match_creates_pos_product_match(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A confident single-candidate match creates pos_product_match row automatically."""
    with committed_smart_context("pos-match-confident") as context:
        owner = member_from_workspace(context.workspace, role=MemberRole.owner)
        app, _ = _app(monkeypatch, owner)
        client = TestClient(app, raise_server_exceptions=False)

        # Seed catalogue product matching stub-item-001
        with psycopg.connect(TEST_DATABASE_URL or "") as db_conn:
            with db_conn.cursor() as cur:
                product_id = make_workspace_product(
                    cur,
                    context.workspace,
                    name="Organic Whole Milk 1 Gallon",
                )
            db_conn.commit()

        _connect_owner(client)
        client.post("/api/v1/pos/sync")

        # Verify automatic match created
        with psycopg.connect(TEST_DATABASE_URL or "", row_factory=dict_row) as db_conn:
            with db_conn.cursor() as cur:
                cur.execute("set local role service_role")
                cur.execute(
                    """
                    select m.id, m.workspace_product_id, m.match_method, m.matched_by, m.confidence
                    from pos_product_match m
                    join synced_product_signal s on s.id = m.synced_product_signal_id
                    where m.tenant_id = %s and s.external_item_id = 'stub-item-001'
                    """,
                    (context.workspace.tenant_id,),
                )
                match_row = cur.fetchone()
                assert match_row is not None
                assert match_row["workspace_product_id"] == product_id
                assert match_row["match_method"] == "automatic"
                assert match_row["matched_by"] is None
                # pos_matching_auto_accept_threshold default (0.90), not quotation
                # matching's unrelated 0.92 — see matching_service.py's own docstring.
                assert match_row["confidence"] >= 0.90

        # Check API response
        sig_res = client.get(f"/api/v1/pos/signals?workspace_product_id={product_id}")
        assert sig_res.status_code == 200
        items = sig_res.json()["items"]
        assert len(items) == 1
        assert items[0]["matched"] is True
        assert items[0]["matched_workspace_product_id"] == str(product_id)


def test_ambiguous_candidates_left_unmatched(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FR-006: Multiple equally-plausible candidates (e.g. two catalogue entries sharing a
    display name — a bundle and its component both mis-entered under the same name) left
    unmatched for manual review. A merely SIMILAR name (e.g. a "Case of 500" suffix variant)
    does not reproduce this — pg_trgm trigram similarity scores a suffixed variant well below
    an exact match, so it never actually ties; a genuine tie needs identical text."""
    with committed_smart_context("pos-match-ambig") as context:
        owner = member_from_workspace(context.workspace, role=MemberRole.owner)
        app, _ = _app(monkeypatch, owner)
        client = TestClient(app, raise_server_exceptions=False)

        # Seed two catalogue products sharing the exact same display name for stub-item-004
        with psycopg.connect(TEST_DATABASE_URL or "") as db_conn:
            with db_conn.cursor() as cur:
                make_workspace_product(
                    cur,
                    context.workspace,
                    name="Eco Friendly Hot Coffee Paper Cups 12oz",
                )
                make_workspace_product(
                    cur,
                    context.workspace,
                    name="Eco Friendly Hot Coffee Paper Cups 12oz",
                )
            db_conn.commit()

        _connect_owner(client)
        client.post("/api/v1/pos/sync")

        # Verify stub-item-004 has NO automatic match
        with psycopg.connect(TEST_DATABASE_URL or "", row_factory=dict_row) as db_conn:
            with db_conn.cursor() as cur:
                cur.execute("set local role service_role")
                cur.execute(
                    """
                    select m.id
                    from pos_product_match m
                    join synced_product_signal s on s.id = m.synced_product_signal_id
                    where m.tenant_id = %s and s.external_item_id = 'stub-item-004'
                    """,
                    (context.workspace.tenant_id,),
                )
                assert cur.fetchone() is None

        # Verify it is listed in unmatched signals review list
        unmatched_res = client.get("/api/v1/pos/signals?match_status=unmatched")
        assert unmatched_res.status_code == 200
        items = unmatched_res.json()["items"]
        names = [it["external_item_name"] for it in items]
        assert "Eco Friendly Hot Coffee Paper Cups 12oz" in names


def test_manual_match_succeeds_and_records_matched_by(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FR-006: Manual match links unmatched signal, records matched_by, prevents double match."""
    with committed_smart_context("pos-match-manual") as context:
        owner = member_from_workspace(context.workspace, role=MemberRole.owner)
        app, _ = _app(monkeypatch, owner)
        client = TestClient(app, raise_server_exceptions=False)

        with psycopg.connect(TEST_DATABASE_URL or "") as db_conn:
            with db_conn.cursor() as cur:
                target_wp_id = make_workspace_product(
                    cur,
                    context.workspace,
                    name="Target Manual Product",
                )
            db_conn.commit()

        _connect_owner(client)
        client.post("/api/v1/pos/sync")

        # Get the signal ID for stub-item-004
        sig_res = client.get("/api/v1/pos/signals")
        signals = {s["external_item_name"]: s for s in sig_res.json()["items"]}
        signal = signals["Eco Friendly Hot Coffee Paper Cups 12oz"]
        signal_id = signal["id"]

        # Call POST /pos/signals/{signal_id}/match
        match_res = client.post(
            f"/api/v1/pos/signals/{signal_id}/match",
            json={"workspace_product_id": str(target_wp_id)},
        )
        assert match_res.status_code == 200, match_res.text
        match_data = match_res.json()
        assert match_data["synced_product_signal_id"] == signal_id
        assert match_data["workspace_product_id"] == str(target_wp_id)
        assert match_data["match_method"] == "manual"

        # Check in DB that matched_by is the owner's membership_id
        with psycopg.connect(TEST_DATABASE_URL or "", row_factory=dict_row) as db_conn:
            with db_conn.cursor() as cur:
                cur.execute("set local role service_role")
                cur.execute(
                    "select matched_by, match_method from pos_product_match where id = %s",
                    (match_data["id"],),
                )
                row = cur.fetchone()
                assert row is not None
                assert row["matched_by"] == context.workspace.membership_id
                assert row["match_method"] == "manual"

        # Attempting to match again must return 409 Conflict
        dup_res = client.post(
            f"/api/v1/pos/signals/{signal_id}/match",
            json={"workspace_product_id": str(target_wp_id)},
        )
        assert dup_res.status_code == 409


def test_cross_tenant_workspace_products_never_candidates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tenant isolation: workspace products belonging to tenant B are never
    candidates for tenant A."""
    with (
        committed_smart_context("pos-iso-tenant-a") as ctx_a,
        committed_smart_context("pos-iso-tenant-b") as ctx_b,
    ):
        # In Tenant B, create a matching product
        with psycopg.connect(TEST_DATABASE_URL or "") as db_conn:
            with db_conn.cursor() as cur:
                make_workspace_product(
                    cur,
                    ctx_b.workspace,
                    name="Organic Whole Milk 1 Gallon",
                )
            db_conn.commit()

        # In Tenant A, connect and sync — no local product exists for Organic Whole Milk
        owner_a = member_from_workspace(ctx_a.workspace, role=MemberRole.owner)
        app_a, _ = _app(monkeypatch, owner_a)
        client_a = TestClient(app_a, raise_server_exceptions=False)

        _connect_owner(client_a)
        client_a.post("/api/v1/pos/sync")

        # Tenant A's signal must remain UNMATCHED
        with psycopg.connect(TEST_DATABASE_URL or "", row_factory=dict_row) as db_conn:
            with db_conn.cursor() as cur:
                cur.execute("set local role service_role")
                cur.execute(
                    """
                    select m.id
                    from pos_product_match m
                    join synced_product_signal s on s.id = m.synced_product_signal_id
                    where m.tenant_id = %s and s.external_item_id = 'stub-item-001'
                    """,
                    (ctx_a.workspace.tenant_id,),
                )
                assert cur.fetchone() is None, "Cross-tenant product was erroneously matched!"

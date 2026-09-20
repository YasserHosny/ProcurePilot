"""R4.1 normalized Supplier IQ evidence boundary tests."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, timedelta
from uuid import UUID, uuid4

import psycopg
import pytest

from integration.catalogue_helpers import (
    TEST_DATABASE_URL,
    Workspace,
    act_as,
    make_workspace,
    make_workspace_product,
)
from integration.quotation_helpers import make_supplier

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is not set; needs a hosted Postgres with the migrations applied",
)

R4_TABLES = (
    "supplier_scorecard_metric",
    "supplier_scorecard_evidence",
    "negotiation_brief",
    "negotiation_brief_item",
    "negotiation_brief_item_evidence",
    "negotiation_brief_action",
)


@dataclass(frozen=True)
class SeededR4:
    tenant_id: UUID
    supplier_id: UUID
    product_id: UUID
    snapshot_id: UUID
    metric_id: UUID
    evidence_id: UUID
    brief_id: UUID
    item_id: UUID
    action_id: UUID


def _seed_r4(cur: psycopg.Cursor, workspace: Workspace, label: str) -> SeededR4:
    supplier_id = make_supplier(cur, workspace, f"{label} Supplier")
    product_id = make_workspace_product(
        cur, workspace, name=f"{label} Product", supplier_id=supplier_id
    )
    snapshot_id, metric_id, evidence_id = uuid4(), uuid4(), uuid4()
    brief_id, item_id, action_id = uuid4(), uuid4(), uuid4()
    today = date.today()

    cur.execute("reset role")
    cur.execute("set local role service_role")
    cur.execute(
        """
        insert into supplier_scorecard_snapshot
          (id, tenant_id, supplier_id, window_start, window_end, rule_version,
           metrics, risk_score, source_counts, state, confidence, release_posture,
           valid_from, valid_until, source_fingerprint, observed_history_days)
        values (%s, %s, %s, %s, %s, 'supplier-scorecard-v2', '{}'::jsonb, '{}'::jsonb,
                '{}'::jsonb, 'provisional', 'medium', 'g3_unmet', now(), now() + interval '30 days',
                %s, 90)
        """,
        (
            snapshot_id,
            workspace.tenant_id,
            supplier_id,
            today - timedelta(days=90),
            today,
            f"{label}-fp",
        ),
    )
    cur.execute(
        """
        insert into supplier_scorecard_metric
          (id, tenant_id, snapshot_id, metric_kind, bucket_key, value, confidence,
           is_sufficient, calculation_version)
        values (%s, %s, %s, 'concentration', 'GBP', .25, 'medium', true, 'supplier-risk-v2')
        """,
        (metric_id, workspace.tenant_id, snapshot_id),
    )
    cur.execute(
        """
        insert into supplier_scorecard_evidence
          (id, tenant_id, metric_id, workspace_product_id)
        values (%s, %s, %s, %s)
        """,
        (evidence_id, workspace.tenant_id, metric_id, product_id),
    )
    cur.execute(
        """
        insert into negotiation_brief
          (id, tenant_id, supplier_id, snapshot_id, brief_version, source_fingerprint,
           valid_from, valid_until, created_by_membership_id)
        values (%s, %s, %s, %s, 'brief-v1', %s, now(), now() + interval '30 days', %s)
        """,
        (
            brief_id,
            workspace.tenant_id,
            supplier_id,
            snapshot_id,
            f"{label}-brief-fp",
            workspace.membership_id,
        ),
    )
    cur.execute(
        """
        insert into negotiation_brief_item
          (id, tenant_id, brief_id, metric_id, item_kind, rank, confidence,
           valid_from, valid_until, question_i18n_key, calculation_version)
        values (%s, %s, %s, %s, 'price_trajectory', 1, 'medium', now(),
                now() + interval '30 days', 'supplierRisk.questions.price', 'supplier-risk-v2')
        """,
        (item_id, workspace.tenant_id, brief_id, metric_id),
    )
    cur.execute(
        """
        insert into negotiation_brief_item_evidence (tenant_id, item_id, evidence_id)
        values (%s, %s, %s)
        """,
        (workspace.tenant_id, item_id, evidence_id),
    )
    cur.execute(
        """
        insert into negotiation_brief_action
          (id, tenant_id, brief_id, action, idempotency_key, acted_by_membership_id)
        values (%s, %s, %s, 'acknowledged', %s, %s)
        """,
        (action_id, workspace.tenant_id, brief_id, f"{label}-action-key", workspace.membership_id),
    )
    return SeededR4(
        workspace.tenant_id,
        supplier_id,
        product_id,
        snapshot_id,
        metric_id,
        evidence_id,
        brief_id,
        item_id,
        action_id,
    )


@pytest.fixture
def seeded_r4() -> tuple[psycopg.Connection, Workspace, Workspace, SeededR4, SeededR4]:
    with psycopg.connect(TEST_DATABASE_URL or "", prepare_threshold=None) as conn:
        with conn.cursor() as cur:
            alpha = make_workspace(cur, "r41-alpha")
            beta = make_workspace(cur, "r41-beta")
            alpha_rows = _seed_r4(cur, alpha, "alpha")
            beta_rows = _seed_r4(cur, beta, "beta")
        yield conn, alpha, beta, alpha_rows, beta_rows
        conn.rollback()


def test_r4_supplier_tables_have_forced_rls_and_policies() -> None:
    with psycopg.connect(TEST_DATABASE_URL or "") as conn, conn.cursor() as cur:
        cur.execute(
            """
            select c.relname, c.relrowsecurity, c.relforcerowsecurity,
                   exists (select 1 from pg_policies p
                           where p.tablename = c.relname and p.cmd = 'SELECT'),
                   exists (select 1 from pg_policies p
                           where p.tablename = c.relname and p.cmd = 'INSERT')
            from pg_class c
            where c.relname = any(%s)
            """,
            (list(R4_TABLES),),
        )
        assert set(cur.fetchall()) == {(name, True, True, True, True) for name in R4_TABLES}


def test_r4_supplier_tables_do_not_grant_mutation_privileges() -> None:
    with psycopg.connect(TEST_DATABASE_URL or "") as conn, conn.cursor() as cur:
        cur.execute(
            """
            select grantee, table_name, privilege_type
            from information_schema.role_table_grants
            where table_schema = current_schema()
              and table_name = any(%s)
              and grantee = any(%s)
              and privilege_type = any(%s)
            """,
            (list(R4_TABLES), ["authenticated", "service_role"], ["UPDATE", "DELETE", "TRUNCATE"]),
        )
        assert cur.fetchall() == []


def test_r4_tenant_visibility_and_cross_tenant_insert_are_blocked(seeded_r4: tuple) -> None:
    conn, alpha, beta, alpha_rows, beta_rows = seeded_r4
    with conn.cursor() as cur:
        act_as(cur, alpha)
        cur.execute(
            "insert into supplier_scorecard_metric "
            "(tenant_id, snapshot_id, metric_kind, confidence, calculation_version) "
            "values (%s, %s, 'insert_policy_probe', 'low', 'test')",
            (alpha.tenant_id, alpha_rows.snapshot_id),
        )
        act_as(cur, replace(alpha, role="viewer"))
        cur.execute("savepoint r4_viewer_insert")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cur.execute(
                "insert into supplier_scorecard_metric "
                "(tenant_id, snapshot_id, metric_kind, confidence, calculation_version) "
                "values (%s, %s, 'viewer_probe', 'low', 'test')",
                (alpha.tenant_id, alpha_rows.snapshot_id),
            )
        cur.execute("rollback to savepoint r4_viewer_insert")
        act_as(cur, alpha)
        cur.execute(
            "select * from supplier_scorecard_snapshot where id = %s",
            (beta_rows.snapshot_id,),
        )
        assert cur.fetchall() == []
        for table, column, value in (
            ("supplier_scorecard_metric", "id", beta_rows.metric_id),
            ("supplier_scorecard_evidence", "id", beta_rows.evidence_id),
            ("negotiation_brief", "id", beta_rows.brief_id),
            ("negotiation_brief_item", "id", beta_rows.item_id),
            ("negotiation_brief_item_evidence", "item_id", beta_rows.item_id),
            ("negotiation_brief_action", "id", beta_rows.action_id),
        ):
            cur.execute(f"select * from {table} where {column} = %s", (value,))
            assert cur.fetchall() == []

        inserts = (
            (
                "supplier_scorecard_metric",
                "insert into supplier_scorecard_metric "
                "(tenant_id, snapshot_id, metric_kind, confidence, calculation_version) "
                "values (%s, %s, 'intrusion', 'low', 'test')",
                (alpha.tenant_id, beta_rows.snapshot_id),
            ),
            (
                "supplier_scorecard_evidence",
                "insert into supplier_scorecard_evidence "
                "(tenant_id, metric_id, workspace_product_id) values (%s, %s, %s)",
                (alpha.tenant_id, beta_rows.metric_id, beta_rows.product_id),
            ),
            (
                "negotiation_brief",
                "insert into negotiation_brief "
                "(tenant_id, supplier_id, snapshot_id, brief_version, source_fingerprint, "
                "valid_from, valid_until, created_by_membership_id) "
                "values (%s, %s, %s, 'intrusion', 'intrusion', now(), "
                "now() + interval '1 day', %s)",
                (
                    alpha.tenant_id,
                    beta_rows.supplier_id,
                    beta_rows.snapshot_id,
                    beta.membership_id,
                ),
            ),
            (
                "negotiation_brief_item",
                "insert into negotiation_brief_item "
                "(tenant_id, brief_id, item_kind, rank, confidence, valid_from, valid_until, "
                "question_i18n_key, calculation_version) "
                "values (%s, %s, 'intrusion', 99, 'low', now(), "
                "now() + interval '1 day', 'q', 'v2')",
                (alpha.tenant_id, beta_rows.brief_id),
            ),
            (
                "negotiation_brief_item_evidence",
                "insert into negotiation_brief_item_evidence "
                "(tenant_id, item_id, evidence_id) values (%s, %s, %s)",
                (alpha.tenant_id, beta_rows.item_id, beta_rows.evidence_id),
            ),
            (
                "negotiation_brief_action",
                "insert into negotiation_brief_action "
                "(tenant_id, brief_id, action, idempotency_key, acted_by_membership_id) "
                "values (%s, %s, 'acknowledged', 'intrusion', %s)",
                (alpha.tenant_id, beta_rows.brief_id, beta.membership_id),
            ),
        )
        for _table, statement, params in inserts:
            cur.execute("savepoint r4_cross_tenant_insert")
            with pytest.raises(
                (psycopg.errors.InsufficientPrivilege, psycopg.errors.ForeignKeyViolation),
            ):
                cur.execute(statement, params)
            cur.execute("rollback to savepoint r4_cross_tenant_insert")

        policy_denied_inserts = (
            (
                "supplier_scorecard_metric",
                "insert into supplier_scorecard_metric "
                "(tenant_id, snapshot_id, metric_kind, confidence, calculation_version) "
                "values (%s, %s, 'policy_denied', 'low', 'test')",
                (beta.tenant_id, beta_rows.snapshot_id),
            ),
            (
                "supplier_scorecard_evidence",
                "insert into supplier_scorecard_evidence "
                "(tenant_id, metric_id, workspace_product_id) values (%s, %s, %s)",
                (beta.tenant_id, beta_rows.metric_id, beta_rows.product_id),
            ),
            (
                "negotiation_brief",
                "insert into negotiation_brief "
                "(tenant_id, supplier_id, snapshot_id, brief_version, source_fingerprint, "
                "valid_from, valid_until, created_by_membership_id) "
                "values (%s, %s, %s, 'policy-denied', 'policy-denied', now(), "
                "now() + interval '1 day', %s)",
                (
                    beta.tenant_id,
                    beta_rows.supplier_id,
                    beta_rows.snapshot_id,
                    beta.membership_id,
                ),
            ),
            (
                "negotiation_brief_item",
                "insert into negotiation_brief_item "
                "(tenant_id, brief_id, item_kind, rank, confidence, valid_from, valid_until, "
                "question_i18n_key, calculation_version) values (%s, %s, 'policy-denied', 99, "
                "'low', now(), now() + interval '1 day', 'q', 'v2')",
                (beta.tenant_id, beta_rows.brief_id),
            ),
            (
                "negotiation_brief_item_evidence",
                "insert into negotiation_brief_item_evidence "
                "(tenant_id, item_id, evidence_id) values (%s, %s, %s)",
                (beta.tenant_id, beta_rows.item_id, beta_rows.evidence_id),
            ),
            (
                "negotiation_brief_action",
                "insert into negotiation_brief_action "
                "(tenant_id, brief_id, action, idempotency_key, acted_by_membership_id) "
                "values (%s, %s, 'acknowledged', 'policy-denied', %s)",
                (beta.tenant_id, beta_rows.brief_id, beta.membership_id),
            ),
        )
        for _table, statement, params in policy_denied_inserts:
            cur.execute("savepoint r4_insert_policy")
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                cur.execute(statement, params)
            cur.execute("rollback to savepoint r4_insert_policy")


@pytest.mark.parametrize("table", R4_TABLES)
def test_r4_tables_reject_authenticated_update_delete_and_truncate(
    table: str, seeded_r4: tuple
) -> None:
    conn, alpha, _beta, alpha_rows, _beta_rows = seeded_r4
    row_id = {
        "supplier_scorecard_metric": alpha_rows.metric_id,
        "supplier_scorecard_evidence": alpha_rows.evidence_id,
        "negotiation_brief": alpha_rows.brief_id,
        "negotiation_brief_item": alpha_rows.item_id,
        "negotiation_brief_item_evidence": alpha_rows.item_id,
        "negotiation_brief_action": alpha_rows.action_id,
    }[table]
    with conn.cursor() as cur:
        act_as(cur, alpha)
        cur.execute("savepoint r4_immutable")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cur.execute(
                f"update {table} set tenant_id = tenant_id where tenant_id = %s",
                (alpha.tenant_id,),
            )
        cur.execute("rollback to savepoint r4_immutable")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cur.execute(f"delete from {table} where tenant_id = %s", (alpha.tenant_id,))
        cur.execute("rollback to savepoint r4_immutable")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cur.execute(f"truncate {table}")
        cur.execute("rollback to savepoint r4_immutable")
        assert row_id is not None


def test_brief_item_without_evidence_cannot_commit(seeded_r4: tuple) -> None:
    conn, alpha, _beta, alpha_rows, _beta_rows = seeded_r4
    with conn.cursor() as cur:
        cur.execute("set local role service_role")
        with pytest.raises(psycopg.errors.RaiseException, match="requires evidence"):
            cur.execute(
                "insert into negotiation_brief_item "
                "(tenant_id, brief_id, item_kind, rank, confidence, valid_from, valid_until, "
                "question_i18n_key, calculation_version) values (%s, %s, 'service', 2, 'low', "
                "now(), now() + interval '1 day', 'q', 'v2')",
                (alpha.tenant_id, alpha_rows.brief_id),
            )
            conn.commit()
        conn.rollback()


def test_r4_owner_can_insert_every_new_table(seeded_r4: tuple) -> None:
    conn, alpha, _beta, alpha_rows, _beta_rows = seeded_r4
    metric_id, evidence_id = uuid4(), uuid4()
    brief_id, item_id, action_id = uuid4(), uuid4(), uuid4()
    with conn.cursor() as cur:
        cur.execute("reset role")
        cur.execute("set local role service_role")
        cur.execute("set constraints negotiation_brief_item_requires_evidence immediate")
        cur.execute("set constraints negotiation_brief_item_requires_evidence deferred")
        act_as(cur, alpha)
        cur.execute(
            "insert into supplier_scorecard_metric "
            "(id, tenant_id, snapshot_id, metric_kind, confidence, calculation_version) "
            "values (%s, %s, %s, 'owner_probe', 'low', 'test')",
            (metric_id, alpha.tenant_id, alpha_rows.snapshot_id),
        )
        cur.execute(
            "insert into supplier_scorecard_evidence "
            "(id, tenant_id, metric_id, workspace_product_id) values (%s, %s, %s, %s)",
            (evidence_id, alpha.tenant_id, metric_id, alpha_rows.product_id),
        )
        cur.execute(
            """
            insert into negotiation_brief
              (id, tenant_id, supplier_id, snapshot_id, brief_version, source_fingerprint,
               valid_from, valid_until, created_by_membership_id)
            values (%s, %s, %s, %s, 'owner-probe', 'owner-probe', now(),
                    now() + interval '1 day', %s)
            """,
            (
                brief_id,
                alpha.tenant_id,
                alpha_rows.supplier_id,
                alpha_rows.snapshot_id,
                alpha.membership_id,
            ),
        )
        cur.execute(
            """
            insert into negotiation_brief_item
              (id, tenant_id, brief_id, metric_id, item_kind, rank, confidence,
               valid_from, valid_until, question_i18n_key, calculation_version)
            values (%s, %s, %s, %s, 'owner-probe', 1, 'low', now(),
                    now() + interval '1 day', 'q', 'v2')
            """,
            (item_id, alpha.tenant_id, brief_id, metric_id),
        )
        cur.execute(
            "insert into negotiation_brief_item_evidence "
            "(tenant_id, item_id, evidence_id) values (%s, %s, %s)",
            (alpha.tenant_id, item_id, evidence_id),
        )
        cur.execute("set constraints negotiation_brief_item_requires_evidence immediate")
        cur.execute("set constraints negotiation_brief_item_requires_evidence deferred")
        cur.execute(
            "insert into negotiation_brief_action "
            "(id, tenant_id, brief_id, action, idempotency_key, acted_by_membership_id) "
            "values (%s, %s, %s, 'acknowledged', 'owner-probe', %s)",
            (action_id, alpha.tenant_id, brief_id, alpha.membership_id),
        )


def test_v2_snapshot_fingerprint_preserves_recomputation_history(seeded_r4: tuple) -> None:
    conn, alpha, _beta, alpha_rows, _beta_rows = seeded_r4
    replacement_snapshot_id = uuid4()
    with conn.cursor() as cur:
        cur.execute("reset role")
        cur.execute("set local role service_role")
        cur.execute(
            "select window_start, window_end from supplier_scorecard_snapshot where id = %s",
            (alpha_rows.snapshot_id,),
        )
        window_start, window_end = cur.fetchone()
        cur.execute(
            """
            insert into supplier_scorecard_snapshot
              (id, tenant_id, supplier_id, window_start, window_end, rule_version,
               metrics, risk_score, source_counts, state, confidence, release_posture,
               valid_from, valid_until, source_fingerprint, observed_history_days)
            values (%s, %s, %s, %s, %s, 'supplier-scorecard-v2', '{}'::jsonb, '{}'::jsonb,
                    '{}'::jsonb, 'provisional', 'medium', 'g3_unmet', now(),
                    now() + interval '30 days', %s, 90)
            """,
            (
                replacement_snapshot_id,
                alpha.tenant_id,
                alpha_rows.supplier_id,
                window_start,
                window_end,
                "alpha-recomputed-fingerprint",
            ),
        )
        cur.execute(
            "select count(*) from supplier_scorecard_snapshot "
            "where tenant_id = %s and supplier_id = %s and rule_version = 'supplier-scorecard-v2'",
            (alpha.tenant_id, alpha_rows.supplier_id),
        )
        assert cur.fetchone() == (2,)

        legacy_snapshot_id = uuid4()
        cur.execute(
            """
            insert into supplier_scorecard_snapshot
              (id, tenant_id, supplier_id, window_start, window_end, rule_version,
               metrics, risk_score, source_counts, source_fingerprint)
            values (%s, %s, %s, %s, %s, 'supplier-scorecard-v1', '{}'::jsonb,
                    '{}'::jsonb, '{}'::jsonb, 'legacy-fingerprint')
            """,
            (
                legacy_snapshot_id,
                alpha.tenant_id,
                alpha_rows.supplier_id,
                window_start,
                window_end,
            ),
        )
        cur.execute("savepoint r4_legacy_duplicate")
        with pytest.raises(psycopg.errors.UniqueViolation):
            cur.execute(
                """
                insert into supplier_scorecard_snapshot
                  (id, tenant_id, supplier_id, window_start, window_end, rule_version,
                   metrics, risk_score, source_counts, source_fingerprint)
                values (%s, %s, %s, %s, %s, 'supplier-scorecard-v1', '{}'::jsonb,
                        '{}'::jsonb, '{}'::jsonb, 'another-legacy-fingerprint')
                """,
                (
                    uuid4(),
                    alpha.tenant_id,
                    alpha_rows.supplier_id,
                    window_start,
                    window_end,
                ),
            )
        cur.execute("rollback to savepoint r4_legacy_duplicate")

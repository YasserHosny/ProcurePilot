from __future__ import annotations

import psycopg
import pytest

from integration.catalogue_helpers import TEST_DATABASE_URL
from integration.smart_compare_helpers import committed_smart_context, settings_for_test_db
from procurepilot_api.modules.ingestion.matcher import match_supplier
from procurepilot_api.modules.offers.service import _authenticated_db

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is not set; needs a migrated local Postgres",
)


def test_matches_by_domain_when_supplier_has_that_email_domain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = settings_for_test_db(monkeypatch)
    with committed_smart_context("ingestion-domain-match", supplier_count=1) as context:
        supplier_id = context.supplier_ids[0]
        with psycopg.connect(TEST_DATABASE_URL or "") as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "update supplier set email_domains = %s where id = %s",
                    (["acme.com"], supplier_id),
                )
            conn.commit()

        with _authenticated_db(settings, context.member) as conn:
            matched_id, method = match_supplier(
                conn,
                tenant_id=context.workspace.tenant_id,
                from_address="sales@acme.com",
                from_domain="acme.com",
                in_reply_to=None,
                references=[],
            )

        assert matched_id == supplier_id
        assert method == "domain"


def test_unmatched_when_no_domain_address_history_or_thread(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = settings_for_test_db(monkeypatch)
    with committed_smart_context("ingestion-no-match", supplier_count=1) as context:
        with _authenticated_db(settings, context.member) as conn:
            matched_id, method = match_supplier(
                conn,
                tenant_id=context.workspace.tenant_id,
                from_address="unknown@nowhere.test",
                from_domain="nowhere.test",
                in_reply_to=None,
                references=[],
            )

        assert matched_id is None
        assert method is None


def test_address_history_beats_domain_for_a_generic_domain_sender(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """R3's stated purpose for the address signal: a supplier sharing a generic domain
    (@gmail.com here) still matches correctly once that exact address has matched before,
    even though the domain itself resolves to nothing (or to someone else)."""
    settings = settings_for_test_db(monkeypatch)
    with committed_smart_context("ingestion-address-history", supplier_count=2) as context:
        gmail_supplier, other_supplier = context.supplier_ids
        with psycopg.connect(TEST_DATABASE_URL or "") as conn:
            with conn.cursor() as cur:
                # A second supplier also claims @gmail.com, to prove address history wins over
                # a domain match that would otherwise resolve ambiguously or to the wrong one.
                cur.execute(
                    "update supplier set email_domains = %s where id = %s",
                    (["gmail.com"], other_supplier),
                )
                cur.execute(
                    """
                    insert into ingestion_email_log
                      (tenant_id, message_id, from_address, from_domain, status, supplier_id,
                       match_method)
                    values (%s, 'prior-msg-1@gmail.com', 'jane@gmail.com', 'gmail.com',
                            'completed', %s, 'manual')
                    """,
                    (context.workspace.tenant_id, gmail_supplier),
                )
            conn.commit()

        with _authenticated_db(settings, context.member) as conn:
            matched_id, method = match_supplier(
                conn,
                tenant_id=context.workspace.tenant_id,
                from_address="jane@gmail.com",
                from_domain="gmail.com",
                in_reply_to=None,
                references=[],
            )

        assert matched_id == gmail_supplier
        assert method == "address"


def test_thread_match_inherits_supplier_from_a_prior_message_in_the_same_thread(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = settings_for_test_db(monkeypatch)
    with committed_smart_context("ingestion-thread-match", supplier_count=1) as context:
        supplier_id = context.supplier_ids[0]
        with psycopg.connect(TEST_DATABASE_URL or "") as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    insert into ingestion_email_log
                      (tenant_id, message_id, from_address, from_domain, status, supplier_id,
                       match_method)
                    values (%s, 'original@supplier.test', 'rep@supplier.test', 'supplier.test',
                            'completed', %s, 'domain')
                    """,
                    (context.workspace.tenant_id, supplier_id),
                )
            conn.commit()

        with _authenticated_db(settings, context.member) as conn:
            matched_id, method = match_supplier(
                conn,
                tenant_id=context.workspace.tenant_id,
                # A different, unregistered domain — only the thread reference should match.
                from_address="rep@differentdomain.test",
                from_domain="differentdomain.test",
                in_reply_to="original@supplier.test",
                references=[],
            )

        assert matched_id == supplier_id
        assert method == "thread"


def test_cross_tenant_address_history_and_domain_never_leak_a_match(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = settings_for_test_db(monkeypatch)
    with committed_smart_context("ingestion-tenant-a", supplier_count=1) as tenant_a:
        with committed_smart_context("ingestion-tenant-b", supplier_count=1) as tenant_b:
            supplier_a = tenant_a.supplier_ids[0]
            with psycopg.connect(TEST_DATABASE_URL or "") as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "update supplier set email_domains = %s where id = %s",
                        (["shared-domain.test"], supplier_a),
                    )
                    cur.execute(
                        """
                        insert into ingestion_email_log
                          (tenant_id, message_id, from_address, from_domain, status,
                           supplier_id, match_method)
                        values (%s, 'a-msg@shared-domain.test', 'rep@shared-domain.test',
                                'shared-domain.test', 'completed', %s, 'domain')
                        """,
                        (tenant_a.workspace.tenant_id, supplier_a),
                    )
                conn.commit()

            with _authenticated_db(settings, tenant_b.member) as conn:
                matched_id, method = match_supplier(
                    conn,
                    tenant_id=tenant_b.workspace.tenant_id,
                    from_address="rep@shared-domain.test",
                    from_domain="shared-domain.test",
                    in_reply_to=None,
                    references=[],
                )

            assert matched_id is None
            assert method is None

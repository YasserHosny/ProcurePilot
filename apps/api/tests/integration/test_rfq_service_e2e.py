from __future__ import annotations

import os
from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg import sql

from integration.quotation_helpers import PsycopgSupabaseClient, PsycopgTableQuery, _adapt_value
from procurepilot_api.config import get_settings
from procurepilot_api.deps import CurrentMember
from procurepilot_api.errors import NotFoundError, UnprocessableEntityError
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.requests import service as requests_service_module
from procurepilot_api.modules.requests.valuation import LineEstimate
from procurepilot_api.modules.rfq.service import RfqService

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is not set; needs a Postgres with the migrations applied",
)


def _seed_tenant(cur: psycopg.Cursor, *, email_suffix: str) -> tuple[UUID, UUID, UUID]:
    tenant_id, user_id, membership_id, invitation_id = uuid4(), uuid4(), uuid4(), uuid4()
    email = f"rfq-e2e-{email_suffix}@example.test"

    cur.execute(
        "insert into supported_region (code,label_en,label_ar) values ('GB','UK','ب') on conflict do nothing"  # noqa: E501
    )
    cur.execute(
        "insert into supported_currency (code,label_en,label_ar) values ('GBP','Pound','ج') on conflict do nothing"  # noqa: E501
    )
    cur.execute(
        "insert into supported_tax_model (code,label_en,label_ar,region_code) values ('uk_vat','UK VAT','ض','GB') on conflict do nothing"  # noqa: E501
    )
    cur.execute("insert into auth.users (id,email) values (%s,%s)", (user_id, email))
    cur.execute(
        "insert into platform_invitation (id,email,token_hash,expires_at) values (%s,%s,%s, now() + interval '7 days')",  # noqa: E501
        (invitation_id, email, f"hash-{invitation_id}"),
    )
    cur.execute(
        "insert into tenant (id,name,slug,region,currency,tax_model,platform_invitation_id) values (%s,%s,%s,'GB','GBP','uk_vat',%s)",  # noqa: E501
        (tenant_id, "RFQ E2E Ltd", f"rfq-e2e-{tenant_id.hex[:8]}", invitation_id),
    )
    cur.execute(
        "insert into membership (id,tenant_id,user_id,email,role,is_active_workspace) values (%s,%s,%s,%s,'owner',true)",  # noqa: E501
        (membership_id, tenant_id, user_id, email),
    )
    return tenant_id, user_id, membership_id


def _seed_rfq_and_responses(
    cur: psycopg.Cursor, tenant_id: UUID, membership_id: UUID
) -> tuple[UUID, UUID, UUID, UUID]:
    rfq_id = uuid4()
    supp1_id, supp2_id = uuid4(), uuid4()
    prod1_id, prod2_id = uuid4(), uuid4()
    branch_id = uuid4()

    # Create Branch
    cur.execute(
        "insert into branch (id, tenant_id, name) values (%s, %s, %s)",
        (branch_id, tenant_id, "Main Branch"),
    )

    # Create Products
    cur.execute(
        "insert into canonical_product (id,name,base_unit) values (%s,%s,'each'), (%s,%s,'each')",
        (uuid4(), "Prod1", uuid4(), "Prod2"),
    )
    cur.execute(
        "insert into workspace_product (id,tenant_id,canonical_product_id,tenant_name) values (%s,%s,(select id from canonical_product where name='Prod1' limit 1),%s), (%s,%s,(select id from canonical_product where name='Prod2' limit 1),%s)",  # noqa: E501
        (prod1_id, tenant_id, "Prod1", prod2_id, tenant_id, "Prod2"),
    )

    # Create Suppliers
    cur.execute(
        "insert into supplier (id,tenant_id,name,contact_email) values (%s,%s,%s,%s), (%s,%s,%s,%s)",  # noqa: E501
        (
            supp1_id,
            tenant_id,
            "Supplier 1",
            "s1@example.com",
            supp2_id,
            tenant_id,
            "Supplier 2",
            "s2@example.com",
        ),
    )

    # Create RFQ
    cur.execute(
        "insert into rfq (id,tenant_id,created_by_membership_id,status,needed_by_date,idempotency_key) values (%s,%s,%s,'responded',%s,%s)",  # noqa: E501
        (rfq_id, tenant_id, membership_id, date.today(), uuid4()),
    )
    cur.execute(
        "insert into rfq_line (id,tenant_id,rfq_id,workspace_product_id,quantity) values (%s,%s,%s,%s,10), (%s,%s,%s,%s,20)",  # noqa: E501
        (uuid4(), tenant_id, rfq_id, prod1_id, uuid4(), tenant_id, rfq_id, prod2_id),
    )

    # Create Recipients
    rec1_id, rec2_id = uuid4(), uuid4()
    cur.execute(
        "insert into rfq_recipient (id,tenant_id,rfq_id,supplier_id,status) values (%s,%s,%s,%s,'sent'), (%s,%s,%s,%s,'sent')",  # noqa: E501
        (rec1_id, tenant_id, rfq_id, supp1_id, rec2_id, tenant_id, rfq_id, supp2_id),
    )

    def _make_document(doc_id: UUID) -> None:
        storage_path = f"tenants/{tenant_id}/quotations/{doc_id}/quote.pdf"
        cur.execute(
            "insert into document "
            "(id,tenant_id,storage_bucket,storage_path,mime_type,content_hash,created_by) "
            "values (%s,%s,'quotation-documents',%s,'application/pdf',%s,%s)",
            (doc_id, tenant_id, storage_path, f"hash-{doc_id}", membership_id),
        )

    # Response 1 (Fully matched)
    doc1_id, quot1_id = uuid4(), uuid4()
    _make_document(doc1_id)
    cur.execute(
        (
            "insert into quotation (id,tenant_id,document_id,supplier_id,currency,status) "
            "values (%s,%s,%s,%s,'GBP','reviewed')"
        ),
        (quot1_id, tenant_id, doc1_id, supp1_id),
    )
    ql1_1, ql1_2 = uuid4(), uuid4()
    cur.execute(
        "insert into quotation_line "
        "(id,tenant_id,quotation_id,line_number,original_text,quantity,unit_price_amount,"
        "unit_price_currency) "
        "values (%s,%s,%s,1,'p1',10,15.5,'GBP'), (%s,%s,%s,2,'p2',20,25.0,'GBP')",
        (ql1_1, tenant_id, quot1_id, ql1_2, tenant_id, quot1_id),
    )
    cur.execute(
        "insert into match_decision "
        "(id,tenant_id,quotation_line_id,matched_workspace_product_id,outcome,is_automatic,"
        "confidence) "
        "values (%s,%s,%s,%s,'no_match_new_product',true,1), "
        "(%s,%s,%s,%s,'no_match_new_product',true,1)",
        (
            uuid4(),
            tenant_id,
            ql1_1,
            prod1_id,
            uuid4(),
            tenant_id,
            ql1_2,
            prod2_id,
        ),
    )
    resp1_id = uuid4()
    cur.execute(
        (
            "insert into rfq_response (id,tenant_id,rfq_recipient_id,quotation_id) "
            "values (%s,%s,%s,%s)"
        ),
        (resp1_id, tenant_id, rec1_id, quot1_id),
    )

    # Response 2 (Pending match for one line)
    doc2_id, quot2_id = uuid4(), uuid4()
    _make_document(doc2_id)
    cur.execute(
        (
            "insert into quotation (id,tenant_id,document_id,supplier_id,currency,status) "
            "values (%s,%s,%s,%s,'GBP','reviewed')"
        ),
        (quot2_id, tenant_id, doc2_id, supp2_id),
    )
    ql2_1, ql2_2 = uuid4(), uuid4()
    cur.execute(
        "insert into quotation_line "
        "(id,tenant_id,quotation_id,line_number,original_text,quantity,unit_price_amount,"
        "unit_price_currency) "
        "values (%s,%s,%s,1,'p1',10,14.0,'GBP'), (%s,%s,%s,2,'p2',20,26.0,'GBP')",
        (ql2_1, tenant_id, quot2_id, ql2_2, tenant_id, quot2_id),
    )
    # Only match the first product
    cur.execute(
        "insert into match_decision "
        "(id,tenant_id,quotation_line_id,matched_workspace_product_id,outcome,is_automatic,"
        "confidence) "
        "values (%s,%s,%s,%s,'no_match_new_product',true,1)",
        (uuid4(), tenant_id, ql2_1, prod1_id),
    )
    resp2_id = uuid4()
    cur.execute(
        (
            "insert into rfq_response (id,tenant_id,rfq_recipient_id,quotation_id) "
            "values (%s,%s,%s,%s)"
        ),
        (resp2_id, tenant_id, rec2_id, quot2_id),
    )

    return rfq_id, resp1_id, resp2_id, branch_id


class _ListInsertTableQuery(PsycopgTableQuery):
    """`PsycopgTableQuery.insert()` only supports a single-row dict payload; RequestsService's
    `_insert_lines()` inserts a LIST of rows in one call (bulk purchase_request_line insert).
    Mirrors `test_purchase_requests.py`'s own `_TestTableQuery` override for this exact gap.

    Also translates a raw `psycopg.Error` into `postgrest.exceptions.APIError` on the way out --
    the real PostgREST client always raises `APIError`, and `RequestsService.create_request()`'s
    idempotent-replay path specifically catches `APIError` and inspects its `.code` (the Postgres
    SQLSTATE) for '23505' (unique violation). Without this translation, a raw psycopg exception
    sails straight past that `except APIError` clause uncaught."""

    def insert(
        self, payload: dict[str, object] | list[dict[str, object]]
    ) -> _ListInsertTableQuery:
        self._operation = "insert"
        self._payload = payload  # type: ignore[assignment]
        return self

    def _execute_insert(self) -> object:
        try:
            return self._do_insert()
        except psycopg.Error as exc:
            from postgrest.exceptions import APIError

            sqlstate = getattr(exc, "sqlstate", None) or getattr(
                getattr(exc, "diag", None), "sqlstate", None
            )
            raise APIError({"code": sqlstate, "message": str(exc)}) from exc

    def _do_insert(self) -> object:
        if not isinstance(self._payload, list):
            return super()._execute_insert()
        from integration.quotation_helpers import _Response

        if not self._payload:
            return _Response([])
        keys = list(self._payload[0])
        query = sql.SQL("insert into {} ({}) values {} returning *").format(
            sql.Identifier(self._table),
            sql.SQL(",").join(sql.Identifier(key) for key in keys),
            sql.SQL(",").join(
                sql.SQL("({})").format(sql.SQL(",").join(sql.Placeholder() for _ in keys))
                for _ in self._payload
            ),
        )
        params = [_adapt_value(key, row[key]) for row in self._payload for key in keys]
        return _Response(self._fetch(query, params))


class _FakeAuthenticatedClient(PsycopgSupabaseClient):
    def table(self, table: str) -> _ListInsertTableQuery:
        return _ListInsertTableQuery(self._conn, table)


def _patch_requests_service_for_test(
    monkeypatch: pytest.MonkeyPatch, *, tenant_id: UUID, user_id: UUID, membership_id: UUID
) -> None:
    """`RfqService.prepare_request()` calls the real `RequestsService.create_request()`, which
    is PostgREST-client-based (`authenticated_client(settings, bearer_token)`), unlike the rest
    of this codebase's raw-psycopg test fixtures. Signing a real JWT for it to hit the live local
    Kong/PostgREST stack doesn't work here — conftest.py's SUPABASE_JWT_SECRET is a deliberate
    placeholder ("not used anywhere real"), not the local stack's actual GOTRUE_JWT_SECRET, so a
    hand-signed token is rejected. Mirror `test_purchase_requests.py`'s own established fix
    instead: swap `authenticated_client` for a psycopg-backed fake bound to a real, autocommitting
    connection with the right role/claims set at the SESSION level (not `local`, since autocommit
    means every statement is its own implicit transaction and `local` settings would not survive
    past the first one)."""
    conn = psycopg.connect(get_settings().database_url.get_secret_value(), autocommit=True)
    with conn.cursor() as cur:
        cur.execute("set role authenticated")
        cur.execute(
            "select set_config('request.jwt.claims', %s, false)",
            (
                (
                    f'{{"sub":"{user_id}","tenant_id":"{tenant_id}",'
                    f'"role":"authenticated","member_role":"owner"}}'
                ),
            ),
        )
    monkeypatch.setattr(
        requests_service_module,
        "authenticated_client",
        lambda _settings, _token: _FakeAuthenticatedClient(conn),
    )
    monkeypatch.setattr(
        requests_service_module.RequestsService,
        "_estimate_products",
        lambda self, product_ids: [
            LineEstimate(
                unit_price_amount=None, unit_price_currency=None, source_landed_cost_id=None
            )
            for _ in product_ids
        ],
    )
    monkeypatch.setattr(
        requests_service_module.RequestsService, "_record", lambda self, **kwargs: None
    )


def _member(
    tenant_id: UUID,
    user_id: UUID,
    membership_id: UUID,
) -> CurrentMember:
    return CurrentMember(
        membership_id=membership_id,
        tenant_id=tenant_id,
        user_id=user_id,
        email="rfq-e2e@example.test",
        role=MemberRole.owner,
    )


def test_list_responses() -> None:
    with psycopg.connect(TEST_DATABASE_URL or "", prepare_threshold=None) as conn:
        with conn.cursor() as cur:
            tenant_id, user_id, membership_id = _seed_tenant(cur, email_suffix="list")
            rfq_id, resp1_id, resp2_id, _ = _seed_rfq_and_responses(cur, tenant_id, membership_id)
        conn.commit()

    member = _member(tenant_id, user_id, membership_id)
    service = RfqService(settings=get_settings())

    comparisons = service.list_responses(member=member, rfq_id=rfq_id)
    assert len(comparisons.items) == 2

    # Check that pending_match is correctly flagged
    resp2 = next(c for c in comparisons.items if c.id == resp2_id)
    pending_lines = [line for line in resp2.lines if line.pending_match]
    assert len(pending_lines) == 1

    resp1 = next(c for c in comparisons.items if c.id == resp1_id)
    assert all(not line.pending_match for line in resp1.lines)


def test_prepare_request_and_idempotency(monkeypatch: pytest.MonkeyPatch) -> None:
    with psycopg.connect(TEST_DATABASE_URL or "", prepare_threshold=None) as conn:
        with conn.cursor() as cur:
            tenant_id, user_id, membership_id = _seed_tenant(cur, email_suffix="prep")
            rfq_id, resp1_id, resp2_id, branch_id = _seed_rfq_and_responses(
                cur, tenant_id, membership_id
            )
        conn.commit()

    _patch_requests_service_for_test(
        monkeypatch, tenant_id=tenant_id, user_id=user_id, membership_id=membership_id
    )

    member = _member(tenant_id, user_id, membership_id)
    service = RfqService(settings=get_settings())
    idem_key = uuid4()

    # prepare using resp1 (fully matched)
    res = service.prepare_request(
        bearer_token="unused-token",
        member=member,
        rfq_id=rfq_id,
        rfq_response_id=resp1_id,
        branch_id=branch_id,
        cost_centre_id=None,
        required_by_date=date.today(),
        idempotency_key=idem_key,
    )

    with psycopg.connect(TEST_DATABASE_URL or "", prepare_threshold=None) as conn:
        with conn.cursor() as cur:
            cur.execute(
                (
                    "select source_rfq_response_id, estimated_total_amount, "
                    "estimated_total_currency, has_incomplete_estimate "
                    "from purchase_request where id = %s"
                ),
                (res.purchase_request_id,),
            )
            source_id, total_amt, total_currency, incomplete = cur.fetchone()
            assert source_id == resp1_id
            assert total_amt == Decimal("655.00")  # 10*15.5 + 20*25.0 = 155 + 500 = 655
            # The override must tag the total with the RESPONSE's quoted currency, not whatever
            # _estimate_products()'s landed-cost estimate happened to use (monkeypatched to None
            # here, but in production these can genuinely differ) -- an amount tagged with the
            # wrong currency violates this codebase's own non-negotiable (CLAUDE.md #6).
            assert total_currency == "GBP"
            assert incomplete is False

            cur.execute("select status from rfq where id = %s", (rfq_id,))
            assert cur.fetchone()[0] == "converted"

            cur.execute(
                "select estimated_unit_price_amount from purchase_request_line "
                "where purchase_request_id = %s order by estimated_unit_price_amount",
                (res.purchase_request_id,),
            )
            lines = cur.fetchall()
            assert len(lines) == 2
            prices = [line[0] for line in lines]
            assert Decimal("15.50") in prices
            assert Decimal("25.00") in prices

    # Test idempotency
    res2 = service.prepare_request(
        bearer_token="unused-token",
        member=member,
        rfq_id=rfq_id,
        rfq_response_id=resp1_id,
        branch_id=branch_id,
        cost_centre_id=None,
        required_by_date=date.today(),
        idempotency_key=idem_key,
    )
    assert res2.purchase_request_id == res.purchase_request_id

    # Validate that only one request was created
    with psycopg.connect(TEST_DATABASE_URL or "", prepare_threshold=None) as conn:
        with conn.cursor() as cur:
            cur.execute("select count(*) from purchase_request where tenant_id = %s", (tenant_id,))
            count = cur.fetchone()[0]
            assert count == 1


def test_prepare_request_not_found() -> None:
    with psycopg.connect(TEST_DATABASE_URL or "", prepare_threshold=None) as conn:
        with conn.cursor() as cur:
            tenant_id, user_id, membership_id = _seed_tenant(cur, email_suffix="nf")
            rfq_id, resp1_id, resp2_id, branch_id = _seed_rfq_and_responses(
                cur, tenant_id, membership_id
            )
        conn.commit()

    member = _member(tenant_id, user_id, membership_id)
    service = RfqService(settings=get_settings())
    idem_key = uuid4()

    with pytest.raises(NotFoundError):
        service.prepare_request(
            bearer_token="unused-token",
            member=member,
            rfq_id=rfq_id,
            rfq_response_id=uuid4(),  # fake response id
            branch_id=branch_id,
            cost_centre_id=None,
            required_by_date=date.today(),
            idempotency_key=idem_key,
        )


def test_prepare_request_pending_match() -> None:
    with psycopg.connect(TEST_DATABASE_URL or "", prepare_threshold=None) as conn:
        with conn.cursor() as cur:
            tenant_id, user_id, membership_id = _seed_tenant(cur, email_suffix="pm")
            rfq_id, resp1_id, resp2_id, branch_id = _seed_rfq_and_responses(
                cur, tenant_id, membership_id
            )
        conn.commit()

    member = _member(tenant_id, user_id, membership_id)
    service = RfqService(settings=get_settings())
    idem_key = uuid4()

    # prepare using resp2 (has pending match)
    with pytest.raises(UnprocessableEntityError) as exc:
        service.prepare_request(
            bearer_token="unused-token",
            member=member,
            rfq_id=rfq_id,
            rfq_response_id=resp2_id,
            branch_id=branch_id,
            cost_centre_id=None,
            required_by_date=date.today(),
            idempotency_key=idem_key,
        )
    assert exc.value.details == {"reason": "pending_matches"}

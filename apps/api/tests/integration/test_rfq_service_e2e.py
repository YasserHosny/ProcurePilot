from __future__ import annotations

import os
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg import sql

from integration.quotation_helpers import PsycopgSupabaseClient, PsycopgTableQuery, _adapt_value
from procurepilot_api.config import get_settings
from procurepilot_api.deps import CurrentMember
from procurepilot_api.errors import ConflictError, NotFoundError, UnprocessableEntityError
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.requests import service as requests_service_module
from procurepilot_api.modules.requests.valuation import LineEstimate
from procurepilot_api.modules.rfq import service as rfq_service_module
from procurepilot_api.modules.rfq.service import RfqService

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is not set; needs a Postgres with the migrations applied",
)


def _seed_tenant(cur: psycopg.Cursor, *, email_suffix: str) -> tuple[UUID, UUID, UUID]:
    tenant_id, user_id, membership_id, invitation_id = uuid4(), uuid4(), uuid4(), uuid4()
    email = f"rfq-e2e-{email_suffix}-{user_id}@example.test"

    # See `catalogue_helpers.make_workspace`: a pooled backend may still carry a leaked role.
    cur.execute("reset role")
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

    def insert(self, payload: dict[str, object] | list[dict[str, object]]) -> _ListInsertTableQuery:
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
        return _ListInsertTableQuery(self._conn, table, claims=self._claims)


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
    connection. Role and claims are applied per operation with `set local` inside a transaction
    (`authenticated_scope`), never at session level: through the transaction-mode pooler a
    session-level `set role` leaks onto the server connection and breaks later tests."""
    conn = psycopg.connect(get_settings().database_url.get_secret_value(), autocommit=True)
    claims = (
        f'{{"sub":"{user_id}","tenant_id":"{tenant_id}",'
        f'"role":"authenticated","member_role":"owner"}}'
    )
    monkeypatch.setattr(
        requests_service_module,
        "authenticated_client",
        lambda _settings, _token: _FakeAuthenticatedClient(conn, claims=claims),
    )
    monkeypatch.setattr(
        requests_service_module.RequestsService,
        "_estimate_products",
        lambda self, product_ids, **_kw: [
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
    # The buyer edits «Required by» on the compare page: the draft must carry that date, not the
    # RFQ's own needed-by date (today in this fixture).  (P-155, PPS-199)
    required_by = date.today() + timedelta(days=9)

    # prepare using resp1 (fully matched)
    res = service.prepare_request(
        bearer_token="unused-token",
        member=member,
        rfq_id=rfq_id,
        rfq_response_id=resp1_id,
        branch_id=branch_id,
        cost_centre_id=None,
        required_by_date=required_by,
        idempotency_key=idem_key,
    )

    with psycopg.connect(TEST_DATABASE_URL or "", prepare_threshold=None) as conn:
        with conn.cursor() as cur:
            cur.execute(
                (
                    "select source_rfq_response_id, estimated_total_amount, "
                    "estimated_total_currency, has_incomplete_estimate, required_by_date "
                    "from purchase_request where id = %s"
                ),
                (res.purchase_request_id,),
            )
            source_id, total_amt, total_currency, incomplete, stored_required_by = cur.fetchone()
            assert source_id == resp1_id
            assert stored_required_by == required_by
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
        required_by_date=required_by,
        idempotency_key=idem_key,
    )
    assert res2.purchase_request_id == res.purchase_request_id

    # Validate that only one request was created
    with psycopg.connect(TEST_DATABASE_URL or "", prepare_threshold=None) as conn:
        with conn.cursor() as cur:
            cur.execute("select count(*) from purchase_request where tenant_id = %s", (tenant_id,))
            count = cur.fetchone()[0]
            assert count == 1

    # One request per RFQ: a new preparation (different key, even from another response) is
    # refused once the RFQ is converted, and creates nothing.
    with pytest.raises(ConflictError) as refused:
        service.prepare_request(
            bearer_token="unused-token",
            member=member,
            rfq_id=rfq_id,
            rfq_response_id=resp1_id,
            branch_id=branch_id,
            cost_centre_id=None,
            required_by_date=required_by,
            idempotency_key=uuid4(),
        )
    assert refused.value.details == {"resource": "rfq", "reason": "rfq_already_converted"}

    # A key that belongs to an unrelated request (not prepared from this RFQ) is not a replay.
    unrelated_key = uuid4()
    with psycopg.connect(TEST_DATABASE_URL or "", prepare_threshold=None) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "insert into purchase_request (tenant_id,branch_id,requested_by_membership_id,"
                "required_by_date,status,idempotency_key) "
                "values (%s,%s,%s,current_date + 7,'draft',%s)",
                (tenant_id, branch_id, membership_id, unrelated_key),
            )
        conn.commit()
    with pytest.raises(ConflictError):
        service.prepare_request(
            bearer_token="unused-token",
            member=member,
            rfq_id=rfq_id,
            rfq_response_id=resp1_id,
            branch_id=branch_id,
            cost_centre_id=None,
            required_by_date=required_by,
            idempotency_key=unrelated_key,
        )
    with psycopg.connect(TEST_DATABASE_URL or "", prepare_threshold=None) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "select count(*) from purchase_request where tenant_id = %s "
                "and source_rfq_response_id is not null",
                (tenant_id,),
            )
            assert cur.fetchone()[0] == 1


@pytest.fixture
def prepare_case(monkeypatch: pytest.MonkeyPatch) -> tuple[RfqService, dict]:
    with psycopg.connect(TEST_DATABASE_URL or "", prepare_threshold=None) as conn:
        with conn.cursor() as cur:
            tenant_id, user_id, membership_id = _seed_tenant(cur, email_suffix="integrity")
            rfq_id, response_id, _, branch_id = _seed_rfq_and_responses(
                cur, tenant_id, membership_id
            )
    _patch_requests_service_for_test(
        monkeypatch, tenant_id=tenant_id, user_id=user_id, membership_id=membership_id
    )
    return RfqService(get_settings()), {
        "bearer_token": "unused-token",
        "member": _member(tenant_id, user_id, membership_id),
        "rfq_id": rfq_id,
        "rfq_response_id": response_id,
        "branch_id": branch_id,
        "required_by_date": date.today(),
        "idempotency_key": uuid4(),
    }


def test_prepare_request_recovers_interrupted_finalisation(
    monkeypatch: pytest.MonkeyPatch, prepare_case: tuple[RfqService, dict]
) -> None:
    service, kwargs = prepare_case
    original = rfq_service_module.estimate_from_source_response
    failed = False

    def fail_once_after_create(conn: psycopg.Connection, **params: object) -> dict:
        nonlocal failed
        with conn.cursor() as cur:
            cur.execute(
                "select id from purchase_request where idempotency_key = %s",
                (kwargs["idempotency_key"],),
            )
            draft_exists = cur.fetchone() is not None
        if draft_exists and not failed:
            failed = True
            raise RuntimeError("interrupted finalisation")
        return original(conn, **params)

    monkeypatch.setattr(rfq_service_module, "estimate_from_source_response", fail_once_after_create)
    with pytest.raises(RuntimeError, match="interrupted finalisation"):
        service.prepare_request(**kwargs)

    with psycopg.connect(TEST_DATABASE_URL or "", prepare_threshold=None) as conn:
        assert conn.execute(
            "select source_rfq_response_id, estimated_total_amount from purchase_request "
            "where idempotency_key = %s",
            (kwargs["idempotency_key"],),
        ).fetchone() == (None, None)
        assert (
            conn.execute("select status from rfq where id = %s", (kwargs["rfq_id"],)).fetchone()[0]
            == "responded"
        )

    result = service.prepare_request(**kwargs)
    assert service.prepare_request(**kwargs) == result
    with psycopg.connect(TEST_DATABASE_URL or "", prepare_threshold=None) as conn:
        assert conn.execute(
            "select source_rfq_response_id, estimated_total_amount, estimated_total_currency "
            "from purchase_request where id = %s",
            (result.purchase_request_id,),
        ).fetchone() == (kwargs["rfq_response_id"], Decimal("655.00"), "GBP")
        assert conn.execute(
            "select estimated_unit_price_amount, estimated_unit_price_currency "
            "from purchase_request_line where purchase_request_id = %s "
            "order by estimated_unit_price_amount",
            (result.purchase_request_id,),
        ).fetchall() == [(Decimal("15.50"), "GBP"), (Decimal("25.00"), "GBP")]
        assert (
            conn.execute("select status from rfq where id = %s", (kwargs["rfq_id"],)).fetchone()[0]
            == "converted"
        )
        assert (
            conn.execute(
                "select count(*) from purchase_request where tenant_id = %s",
                (kwargs["member"].tenant_id,),
            ).fetchone()[0]
            == 1
        )


def test_prepare_request_rejects_submitted_interrupted_finalisation(
    monkeypatch: pytest.MonkeyPatch, prepare_case: tuple[RfqService, dict]
) -> None:
    service, kwargs = prepare_case
    original = rfq_service_module.estimate_from_source_response
    failed = False

    def fail_once_after_create(conn: psycopg.Connection, **params: object) -> dict:
        nonlocal failed
        draft_exists = conn.execute(
            "select id from purchase_request where idempotency_key = %s",
            (kwargs["idempotency_key"],),
        ).fetchone()
        if draft_exists and not failed:
            failed = True
            raise RuntimeError("interrupted finalisation")
        return original(conn, **params)

    monkeypatch.setattr(rfq_service_module, "estimate_from_source_response", fail_once_after_create)
    with pytest.raises(RuntimeError, match="interrupted finalisation"):
        service.prepare_request(**kwargs)

    with psycopg.connect(TEST_DATABASE_URL or "", prepare_threshold=None) as conn:
        request_id = conn.execute(
            "select id from purchase_request where tenant_id = %s and idempotency_key = %s",
            (kwargs["member"].tenant_id, kwargs["idempotency_key"]),
        ).fetchone()[0]

    submitted = requests_service_module.RequestsService(get_settings()).submit_request(
        bearer_token=kwargs["bearer_token"], member=kwargs["member"], request_id=request_id
    )
    assert submitted.status == "submitted"

    def frozen_values() -> tuple:
        with psycopg.connect(TEST_DATABASE_URL or "", prepare_threshold=None) as conn:
            request = conn.execute(
                "select status, source_rfq_response_id, estimated_total_amount, "
                "estimated_total_currency, has_incomplete_estimate from purchase_request "
                "where id = %s and tenant_id = %s",
                (request_id, kwargs["member"].tenant_id),
            ).fetchone()
            lines = conn.execute(
                "select id, estimated_unit_price_amount, estimated_unit_price_currency, "
                "estimated_unit_price_source_landed_cost_id, estimated_at "
                "from purchase_request_line where purchase_request_id = %s and tenant_id = %s "
                "order by id",
                (request_id, kwargs["member"].tenant_id),
            ).fetchall()
            rfq_status = conn.execute(
                "select status from rfq where id = %s", (kwargs["rfq_id"],)
            ).fetchone()
        return request, lines, rfq_status

    before = frozen_values()
    assert before[0][1] is None
    with pytest.raises(ConflictError) as exc:
        service.prepare_request(**kwargs)
    assert exc.value.status_code == 409
    assert exc.value.details == {
        "resource": "purchase_request",
        "reason": "request_not_recoverable",
    }
    assert frozen_values() == before


@pytest.mark.parametrize("currency_source", ["quotation", "estimate", "fallback"])
def test_prepare_request_rejects_mixed_currencies_before_create(
    monkeypatch: pytest.MonkeyPatch,
    prepare_case: tuple[RfqService, dict],
    currency_source: str,
) -> None:
    service, kwargs = prepare_case
    if currency_source == "quotation":
        with psycopg.connect(TEST_DATABASE_URL or "", prepare_threshold=None) as conn:
            conn.execute(
                "update quotation_line set unit_price_currency = 'USD' where line_number = 2 "
                "and quotation_id = (select quotation_id from rfq_response where id = %s)",
                (kwargs["rfq_response_id"],),
            )
    else:
        original = rfq_service_module.estimate_from_source_response

        def mixed_estimates(conn: psycopg.Connection, **params: object) -> dict:
            estimates = original(conn, **params)
            first, second = estimates
            estimates[first] = LineEstimate(Decimal("19.00"), "USD", None)
            if currency_source == "fallback":
                del estimates[second]
            return estimates

        monkeypatch.setattr(rfq_service_module, "estimate_from_source_response", mixed_estimates)

    with pytest.raises(UnprocessableEntityError) as exc:
        service.prepare_request(**kwargs)
    assert exc.value.status_code == 422
    assert exc.value.details == {"reason": "mixed_currencies", "currencies": ["GBP", "USD"]}
    with psycopg.connect(TEST_DATABASE_URL or "", prepare_threshold=None) as conn:
        assert (
            conn.execute(
                "select count(*) from purchase_request where tenant_id = %s",
                (kwargs["member"].tenant_id,),
            ).fetchone()[0]
            == 0
        )
        assert (
            conn.execute("select status from rfq where id = %s", (kwargs["rfq_id"],)).fetchone()[0]
            == "responded"
        )


@pytest.mark.parametrize("currency_source", ["quotation", "estimate"])
def test_prepare_request_same_currency_total_is_line_sum(
    monkeypatch: pytest.MonkeyPatch,
    prepare_case: tuple[RfqService, dict],
    currency_source: str,
) -> None:
    service, kwargs = prepare_case
    currency = "GBP"
    if currency_source == "estimate":
        original = rfq_service_module.estimate_from_source_response
        currency = "USD"

        def usd_estimates(conn: psycopg.Connection, **params: object) -> dict:
            return {
                pid: LineEstimate(Decimal("19.00"), "USD", None) for pid in original(conn, **params)
            }

        monkeypatch.setattr(rfq_service_module, "estimate_from_source_response", usd_estimates)

    result = service.prepare_request(**kwargs)
    with psycopg.connect(TEST_DATABASE_URL or "", prepare_threshold=None) as conn:
        before = conn.execute(
            "select estimated_total_amount, estimated_total_currency from purchase_request "
            "where id = %s",
            (result.purchase_request_id,),
        ).fetchone()
        line_total, currencies = conn.execute(
            "select sum(quantity * estimated_unit_price_amount), "
            "array_agg(distinct estimated_unit_price_currency) from purchase_request_line "
            "where purchase_request_id = %s",
            (result.purchase_request_id,),
        ).fetchone()
        assert before == (line_total, currency)
        assert line_total == (Decimal("570.00") if currency == "USD" else Decimal("655.00"))
        assert currencies == [currency]
    assert service.prepare_request(**kwargs) == result
    with psycopg.connect(TEST_DATABASE_URL or "", prepare_threshold=None) as conn:
        assert (
            conn.execute(
                "select estimated_total_amount, estimated_total_currency from purchase_request "
                "where id = %s",
                (result.purchase_request_id,),
            ).fetchone()
            == before
        )


def test_prepare_request_rechecks_currencies_during_finalisation(
    monkeypatch: pytest.MonkeyPatch, prepare_case: tuple[RfqService, dict]
) -> None:
    service, kwargs = prepare_case
    original = rfq_service_module.estimate_from_source_response
    calls = 0

    def changed_estimates(conn: psycopg.Connection, **params: object) -> dict:
        nonlocal calls
        calls += 1
        estimates = original(conn, **params)
        if calls == 2:
            estimates[next(iter(estimates))] = LineEstimate(Decimal("19.00"), "USD", None)
        return estimates

    monkeypatch.setattr(rfq_service_module, "estimate_from_source_response", changed_estimates)
    with pytest.raises(UnprocessableEntityError) as exc:
        service.prepare_request(**kwargs)
    assert exc.value.details == {"reason": "mixed_currencies", "currencies": ["GBP", "USD"]}
    with psycopg.connect(TEST_DATABASE_URL or "", prepare_threshold=None) as conn:
        assert conn.execute(
            "select source_rfq_response_id, estimated_total_amount, estimated_total_currency "
            "from purchase_request where idempotency_key = %s",
            (kwargs["idempotency_key"],),
        ).fetchone() == (None, None, None)
        assert (
            conn.execute(
                "select count(*) from purchase_request_line where purchase_request_id = "
                "(select id from purchase_request where idempotency_key = %s) "
                "and estimated_unit_price_currency is not null",
                (kwargs["idempotency_key"],),
            ).fetchone()[0]
            == 0
        )
        assert (
            conn.execute("select status from rfq where id = %s", (kwargs["rfq_id"],)).fetchone()[0]
            == "responded"
        )
    # The committed draft is still recoverable once the effective prices are consistent.
    service.prepare_request(**kwargs)


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


def test_list_rfqs() -> None:
    with psycopg.connect(TEST_DATABASE_URL or "", prepare_threshold=None) as conn:
        with conn.cursor() as cur:
            tenant_id, user_id, membership_id = _seed_tenant(cur, email_suffix="list-rfqs")
            rfq_id, resp1_id, resp2_id, branch_id = _seed_rfq_and_responses(
                cur, tenant_id, membership_id
            )
        conn.commit()

    member = _member(tenant_id, user_id, membership_id)
    service = RfqService(settings=get_settings())

    result = service.list_rfqs(member=member)
    assert len(result.items) == 1
    summary = result.items[0]
    assert summary.id == rfq_id
    assert summary.status == "responded"
    assert summary.recipient_count == 2
    assert summary.response_count == 2
    assert summary.converted_purchase_request_id is None

    # status filter
    matching = service.list_rfqs(member=member, status="responded")
    assert len(matching.items) == 1
    none_matching = service.list_rfqs(member=member, status="expired")
    assert len(none_matching.items) == 0

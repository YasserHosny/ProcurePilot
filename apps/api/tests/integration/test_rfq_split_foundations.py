"""Spec 024 foundations on the RFQ side (T006): one preparation lock per RFQ, and an RFQ's
history names every request it converted into."""

from __future__ import annotations

from uuid import uuid4

import psycopg
import pytest
from psycopg.rows import dict_row

from integration.catalogue_helpers import TEST_DATABASE_URL
from integration.test_rfq_service_e2e import _member, _seed_rfq_and_responses, _seed_tenant
from procurepilot_api.config import get_settings
from procurepilot_api.modules.rfq.service import RfqService, lock_rfq_for_preparation

pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="TEST_DATABASE_URL is not set")


def test_an_rfq_converted_by_a_split_lists_every_request_and_its_group() -> None:
    with psycopg.connect(TEST_DATABASE_URL or "", prepare_threshold=None) as conn:
        with conn.cursor() as cur:
            tenant_id, user_id, membership_id = _seed_tenant(cur, email_suffix="split-history")
            rfq_id, resp1_id, resp2_id, branch_id = _seed_rfq_and_responses(
                cur, tenant_id, membership_id
            )
            job_id, group_id = uuid4(), uuid4()
            cur.execute(
                "insert into basket_split_job (id,tenant_id,requested_by,supplier_ids,items,"
                "status,rfq_id) values (%s,%s,%s,array[gen_random_uuid(),gen_random_uuid()],"
                "'[]'::jsonb,'queued',%s)",
                (job_id, tenant_id, membership_id, rfq_id),
            )
            cur.execute(
                "insert into purchase_request_group (id,tenant_id,rfq_id,basket_split_job_id,"
                "branch_id,combined_total_amount,combined_total_currency,idempotency_key,"
                "created_by_membership_id) values (%s,%s,%s,%s,%s,4063,'GBP',%s,%s)",
                (group_id, tenant_id, rfq_id, job_id, branch_id, uuid4(), membership_id),
            )
            request_ids = []
            for response_id in (resp1_id, resp2_id):
                request_id = uuid4()
                request_ids.append(request_id)
                cur.execute(
                    "insert into purchase_request (id,tenant_id,branch_id,"
                    "requested_by_membership_id,required_by_date,status,"
                    "source_rfq_response_id,request_group_id) "
                    "values (%s,%s,%s,%s,current_date+7,'draft',%s,%s)",
                    (request_id, tenant_id, branch_id, membership_id, response_id, group_id),
                )
            cur.execute("update rfq set status = 'converted' where id = %s", (rfq_id,))
        conn.commit()

    summary = (
        RfqService(settings=get_settings())
        .list_rfqs(member=_member(tenant_id, user_id, membership_id))
        .items[0]
    )
    assert summary.id == rfq_id
    assert sorted(summary.converted_purchase_request_ids) == sorted(request_ids)
    assert summary.request_group_id == group_id
    # The single-request field stays for older clients: one of the converted requests.
    assert summary.converted_purchase_request_id in request_ids


def test_a_single_request_conversion_reports_one_id_and_no_group() -> None:
    with psycopg.connect(TEST_DATABASE_URL or "", prepare_threshold=None) as conn:
        with conn.cursor() as cur:
            tenant_id, user_id, membership_id = _seed_tenant(cur, email_suffix="single-history")
            rfq_id, resp1_id, _resp2_id, branch_id = _seed_rfq_and_responses(
                cur, tenant_id, membership_id
            )
            request_id = uuid4()
            cur.execute(
                "insert into purchase_request (id,tenant_id,branch_id,requested_by_membership_id,"
                "required_by_date,status,source_rfq_response_id) "
                "values (%s,%s,%s,%s,current_date+7,'draft',%s)",
                (request_id, tenant_id, branch_id, membership_id, resp1_id),
            )
        conn.commit()

    summary = (
        RfqService(settings=get_settings())
        .list_rfqs(member=_member(tenant_id, user_id, membership_id))
        .items[0]
    )
    assert summary.converted_purchase_request_ids == [request_id]
    assert summary.converted_purchase_request_id == request_id
    assert summary.request_group_id is None


def test_preparations_of_one_rfq_are_serialised() -> None:
    """Single-supplier preparation and split preparation share one lock (research R4), so they
    can never both convert the same RFQ."""
    with psycopg.connect(TEST_DATABASE_URL or "", prepare_threshold=None) as conn:
        with conn.cursor() as cur:
            tenant_id, _user_id, membership_id = _seed_tenant(cur, email_suffix="split-lock")
            rfq_id, *_ = _seed_rfq_and_responses(cur, tenant_id, membership_id)
        conn.commit()

    with (
        psycopg.connect(TEST_DATABASE_URL or "", prepare_threshold=None) as first,
        psycopg.connect(TEST_DATABASE_URL or "", prepare_threshold=None) as second,
    ):
        with first.cursor(row_factory=dict_row) as cur:
            assert lock_rfq_for_preparation(cur, tenant_id=tenant_id, rfq_id=rfq_id) == "responded"
        with second.cursor(row_factory=dict_row) as cur:
            cur.execute("set lock_timeout = '200ms'")
            with pytest.raises(psycopg.errors.LockNotAvailable):
                lock_rfq_for_preparation(cur, tenant_id=tenant_id, rfq_id=rfq_id)
        second.rollback()
        first.rollback()
        with second.cursor(row_factory=dict_row) as cur:
            assert lock_rfq_for_preparation(cur, tenant_id=tenant_id, rfq_id=rfq_id) == "responded"
        second.rollback()


def test_round1_fixture_reproduces_authoritative_pack_totals() -> None:
    from decimal import Decimal

    from integration.fixtures.round1_rfq import round1_rfq

    with round1_rfq() as fixture:
        with psycopg.connect(TEST_DATABASE_URL or "", prepare_threshold=None) as conn:
            rows = conn.execute(
                "select q.supplier_id, sum(ql.quantity * ql.unit_price_amount) "
                "from quotation q join quotation_line ql on ql.quotation_id = q.id "
                "where q.id = any(%s) group by q.supplier_id",
                (fixture.quotation_ids,),
            ).fetchall()
        assert dict(rows) == dict(
            zip(fixture.supplier_ids, [Decimal("4147"), Decimal("4137")], strict=True)
        )
        assert fixture.split_total == Decimal("4063")

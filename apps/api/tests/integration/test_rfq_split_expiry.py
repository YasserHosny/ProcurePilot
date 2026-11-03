"""RFQ split expiry guards and completed preparation replay (PPS-176)."""

from __future__ import annotations

from uuid import uuid4

import psycopg
import pytest

from integration.catalogue_helpers import TEST_DATABASE_URL
from integration.fixtures.round1_rfq import Round1Rfq, round1_rfq
from integration.test_rfq_split import _authenticate, _post
from integration.test_rfq_split import queue as split_queue
from integration.test_rfq_split_prepare import _complete, _prepare
from integration.test_rfq_split_prepare import isolated_rate_limits as split_rate_limits

queue = split_queue
isolated_rate_limits = split_rate_limits

pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="TEST_DATABASE_URL is not set")


def _set_sent_date(fixture: Round1Rfq, days: int) -> None:
    with psycopg.connect(TEST_DATABASE_URL or "", prepare_threshold=None) as conn:
        conn.execute(
            "update rfq set status='sent', needed_by_date=current_date+%s where id=%s",
            (days, fixture.rfq_id),
        )


def test_start_split_rejects_expired_rfq_without_job(
    monkeypatch: pytest.MonkeyPatch, queue: list
) -> None:
    with round1_rfq() as fixture:
        _authenticate(monkeypatch, fixture)
        _set_sent_date(fixture, -1)
        response = _post(fixture)
        assert response.status_code == 422, response.text
        assert response.json()["details"] == {"reason": "rfq_expired"}
        assert queue == []
        with psycopg.connect(TEST_DATABASE_URL or "", prepare_threshold=None) as conn:
            assert conn.execute(
                "select count(*) from basket_split_job where rfq_id=%s", (fixture.rfq_id,)
            ).fetchone() == (0,)


def test_prepare_split_rejects_newly_expired_rfq_without_requests(
    monkeypatch: pytest.MonkeyPatch, queue: list
) -> None:
    with round1_rfq() as fixture:
        _authenticate(monkeypatch, fixture)
        job_id = _complete(fixture)
        _set_sent_date(fixture, -1)
        response = _prepare(fixture, job_id)
        assert response.status_code == 422, response.text
        assert response.json()["details"] == {"reason": "rfq_expired"}
        with psycopg.connect(TEST_DATABASE_URL or "", prepare_threshold=None) as conn:
            for table in ("purchase_request_group", "purchase_request"):
                assert conn.execute(
                    f"select count(*) from {table} where tenant_id=%s",
                    (fixture.workspace.tenant_id,),
                ).fetchone() == (0,)
            assert conn.execute(
                "select status from rfq where id=%s", (fixture.rfq_id,)
            ).fetchone() == ("sent",)
            assert conn.execute(
                "select count(*) from audit_event where tenant_id=%s "
                "and action='requests.group_prepared'",
                (fixture.workspace.tenant_id,),
            ).fetchone() == (0,)


def test_prepared_split_replays_after_rfq_expires(
    monkeypatch: pytest.MonkeyPatch, queue: list
) -> None:
    with round1_rfq() as fixture:
        _authenticate(monkeypatch, fixture)
        job_id = _complete(fixture)
        key = uuid4()
        prepared = _prepare(fixture, job_id, key)
        assert prepared.status_code == 201, prepared.text
        # Force effective expiry as well as a past date to exercise replay precedence.
        _set_sent_date(fixture, -1)
        replay = _prepare(fixture, job_id, key)
        assert replay.status_code == 200, replay.text
        assert replay.json() == prepared.json()
        with psycopg.connect(TEST_DATABASE_URL or "", prepare_threshold=None) as conn:
            assert conn.execute(
                "select count(*) from purchase_request_group where rfq_id=%s",
                (fixture.rfq_id,),
            ).fetchone() == (1,)
            assert conn.execute(
                "select count(*) from purchase_request where source_rfq_id=%s",
                (fixture.rfq_id,),
            ).fetchone() == (len(prepared.json()["purchase_request_ids"]),)


def test_split_needed_tomorrow_starts_and_prepares(
    monkeypatch: pytest.MonkeyPatch, queue: list
) -> None:
    with round1_rfq() as fixture:
        _authenticate(monkeypatch, fixture)
        _set_sent_date(fixture, 1)
        job_id = _complete(fixture)
        response = _prepare(fixture, job_id)
        assert response.status_code == 201, response.text
        assert len(response.json()["purchase_request_ids"]) == 2
        assert len(queue) == 1

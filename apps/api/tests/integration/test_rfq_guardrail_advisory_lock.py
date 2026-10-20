"""Regression tests for RFQ guardrail evaluation advisory lock behaviour.

Verifies that:
1. No advisory lock remains held after _evaluate_guardrails_for_rfq:
   - on early-return when responses are pending
   - on successful firing (draft preparation)
   - after raising an exception
   Locks are checked by filtering pg_locks for this RFQ's specific advisory lock key
   across all backends to ensure the RFQ lock is released and free.
2. Concurrent evaluations for the same RFQ create exactly one draft without deadlocking
   or leaking locks under transaction pooling.
3. Behind a transaction-mode pooler, no pooled backend retains the RFQ advisory lock.
"""

from __future__ import annotations

import os
import sys
import threading
import uuid
from typing import Any

import psycopg
import pytest

sys.path.append(os.path.dirname(__file__))

from test_rfq_guardrail_deferred import (  # noqa: E402
    _FakeAuthenticatedClient,
    _make_fixture,
)

from procurepilot_api import db
from procurepilot_api.config import Settings, get_settings
from procurepilot_api.modules.ingestion import orchestrator
from procurepilot_api.modules.ingestion.orchestrator import _evaluate_guardrails_for_rfq

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is not set; needs Postgres with migrations applied",
)


def _count_rfq_advisory_locks(
    inspector: psycopg.Connection[Any], tenant_id: uuid.UUID, rfq_id: uuid.UUID
) -> int:
    """Count active advisory locks matching this RFQ's key across ANY backend in pg_locks.

    A 64-bit bigint lock key from hashtextextended(key, 0) is split by PostgreSQL into:
      classid  = high 32 bits
      objid    = low 32 bits
      objsubid = 1
    Filtering by these exact values avoids false positives from unrelated advisory locks held
    by other clients or workers reusing pooled backends.
    """
    advisory_key = f"{tenant_id}:{rfq_id}"
    with inspector.cursor() as cur:
        cur.execute(
            """
            with target as (
                select hashtextextended(%s, 0) as raw_lock_id
            )
            select count(*)
            from pg_locks, target
            where locktype = 'advisory'
              and classid = ((target.raw_lock_id >> 32) & 4294967295)
              and objid = (target.raw_lock_id & 4294967295)
              and objsubid = 1
            """,
            (advisory_key,),
        )
        row = cur.fetchone()
        assert row is not None
        return int(row[0])


def _setup_requests_client(
    monkeypatch: pytest.MonkeyPatch, tenant_id: uuid.UUID, user_id: uuid.UUID
) -> list[psycopg.Connection[Any]]:
    from procurepilot_api.modules.requests import service as requests_service_module
    from procurepilot_api.modules.requests.valuation import LineEstimate

    claims = (
        f'{{"sub":"{user_id}","tenant_id":"{tenant_id}",'
        f'"role":"authenticated","member_role":"owner"}}'
    )
    local = threading.local()
    connections: list[psycopg.Connection[Any]] = []
    lock = threading.Lock()

    def client(_settings: object, _token: str) -> _FakeAuthenticatedClient:
        conn = getattr(local, "conn", None)
        if conn is None:
            conn = db.connect(get_settings().database_url.get_secret_value(), autocommit=True)
            local.conn = conn
            with lock:
                connections.append(conn)
        return _FakeAuthenticatedClient(conn, claims=claims)

    monkeypatch.setattr(requests_service_module, "authenticated_client", client)
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
    return connections


def _configure_fixture_ready_to_fire(
    settings: Settings, rfq_id: uuid.UUID, winning_response: uuid.UUID
) -> None:
    with db.connect(settings.database_url.get_secret_value()) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "update quotation set status = 'refused' where id = "
                "(select response.quotation_id from rfq_response response "
                "join rfq_recipient recipient on recipient.id = response.rfq_recipient_id "
                "where recipient.rfq_id = %s and response.id <> %s)",
                (rfq_id, winning_response),
            )
            cur.execute(
                "update quotation_line ql set unit_price_amount = 15.5 "
                "where ql.quotation_id = (select quotation_id from rfq_response where id = %s) "
                "and line_number = 1",
                (winning_response,),
            )
            cur.execute(
                "update quotation_line ql set unit_price_amount = 25 "
                "where ql.quotation_id = (select quotation_id from rfq_response where id = %s) "
                "and line_number = 2",
                (winning_response,),
            )
        conn.commit()


def test_no_advisory_lock_held_after_early_return_pending_responses() -> None:
    """Early return when responses are pending must not leave an advisory lock held."""
    settings = get_settings()
    tenant_id, _, _, rfq_id, _, _ = _make_fixture()

    with db.connect(settings.database_url.get_secret_value()) as inspector:
        with db.connect(settings.database_url.get_secret_value()) as conn:
            # Response B has pending matches, so responses_pending is True -> early return
            _evaluate_guardrails_for_rfq(settings, conn, tenant_id=tenant_id, rfq_id=rfq_id)

        locks_held = _count_rfq_advisory_locks(inspector, tenant_id, rfq_id)
        assert locks_held == 0, f"Expected 0 locks held for RFQ key, found {locks_held}"

        with inspector.cursor() as cur:
            cur.execute(
                "select count(*) from auto_preparation_event where tenant_id = %s and rfq_id = %s",
                (tenant_id, rfq_id),
            )
            assert cur.fetchone()[0] == 0


def test_no_advisory_lock_held_after_firing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Successful firing path must commit and release the advisory lock completely."""
    settings = get_settings()
    tenant_id, user_id, _, rfq_id, response_a, _ = _make_fixture()
    req_conns = _setup_requests_client(monkeypatch, tenant_id, user_id)
    try:
        _configure_fixture_ready_to_fire(settings, rfq_id, response_a)

        with db.connect(settings.database_url.get_secret_value()) as inspector:
            with db.connect(settings.database_url.get_secret_value()) as conn:
                _evaluate_guardrails_for_rfq(settings, conn, tenant_id=tenant_id, rfq_id=rfq_id)

            locks_held = _count_rfq_advisory_locks(inspector, tenant_id, rfq_id)
            assert locks_held == 0, f"Expected 0 locks held for RFQ key, found {locks_held}"

            with inspector.cursor() as cur:
                cur.execute(
                    "select count(*) from auto_preparation_event "
                    "where tenant_id = %s and rfq_id = %s",
                    (tenant_id, rfq_id),
                )
                assert cur.fetchone()[0] == 1
                cur.execute("select status from rfq where id = %s", (rfq_id,))
                assert cur.fetchone()[0] == "converted"
    finally:
        for c in req_conns:
            try:
                c.close()
            except Exception:
                pass


def test_no_advisory_lock_held_after_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    """When an evaluation raises, rollback must release the advisory lock completely."""
    settings = get_settings()
    tenant_id, _, _, rfq_id, _, _ = _make_fixture()

    def _failing_snapshot(cur: object, *, tenant_id: uuid.UUID, rfq_id: uuid.UUID) -> object:
        raise RuntimeError("Simulated failure during guardrail evaluation")

    monkeypatch.setattr(orchestrator, "compute_guardrail_evaluation", _failing_snapshot)

    with db.connect(settings.database_url.get_secret_value()) as inspector:
        with db.connect(settings.database_url.get_secret_value()) as conn:
            with pytest.raises(RuntimeError, match="Simulated failure"):
                _evaluate_guardrails_for_rfq(settings, conn, tenant_id=tenant_id, rfq_id=rfq_id)

        locks_held = _count_rfq_advisory_locks(inspector, tenant_id, rfq_id)
        assert locks_held == 0, f"Expected 0 locks held for RFQ key, found {locks_held}"


def test_concurrent_evaluations_create_exactly_one_draft(monkeypatch: pytest.MonkeyPatch) -> None:
    """Two concurrent evaluations for the same RFQ must serialize and prepare exactly one draft."""
    settings = get_settings()
    tenant_id, user_id, _, rfq_id, response_a, _ = _make_fixture()
    req_conns = _setup_requests_client(monkeypatch, tenant_id, user_id)
    try:
        _configure_fixture_ready_to_fire(settings, rfq_id, response_a)

        barrier = threading.Barrier(2)
        errors: list[BaseException] = []

        def evaluate() -> None:
            try:
                with db.connect(settings.database_url.get_secret_value()) as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            "select set_config('lock_timeout', '30s', true), "
                            "set_config('statement_timeout', '30s', true)"
                        )
                    barrier.wait(timeout=5)
                    _evaluate_guardrails_for_rfq(settings, conn, tenant_id=tenant_id, rfq_id=rfq_id)
            except BaseException as exc:
                errors.append(exc)

        threads = [threading.Thread(target=evaluate) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=60)

        assert all(not thread.is_alive() for thread in threads), "concurrent evaluation stalled"
        assert not errors, f"Concurrent evaluation raised errors: {errors}"

        with db.connect(settings.database_url.get_secret_value()) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "select count(*) from auto_preparation_event "
                    "where tenant_id = %s and rfq_id = %s",
                    (tenant_id, rfq_id),
                )
                assert cur.fetchone()[0] == 1

                cur.execute(
                    "select count(*) from purchase_request "
                    "where tenant_id = %s and source_rfq_response_id = %s",
                    (tenant_id, response_a),
                )
                assert cur.fetchone()[0] == 1

                cur.execute("select status from rfq where id = %s", (rfq_id,))
                assert cur.fetchone()[0] == "converted"
    finally:
        for c in req_conns:
            try:
                c.close()
            except Exception:
                pass


class SimulatedPoolerConnection:
    """Simulates a transaction-mode pooler (like Supavisor) by switching the underlying
    backend connection upon transaction boundaries (commit or rollback).

    Under transaction pooling, each transaction checks out a backend connection and returns it
    to the pool on commit/rollback. Any subsequent statement (such as a session-level unlock in a
    `finally` block executed after rollback) runs on a different pooled backend connection.
    """

    def __init__(self, connections: list[psycopg.Connection[Any]]) -> None:
        if len(connections) < 2:
            raise ValueError("Need at least 2 connections to simulate pooler switching")
        self._connections = list(connections)
        self._idx = 0

    @property
    def current_conn(self) -> psycopg.Connection[Any]:
        return self._connections[self._idx]

    def _switch(self) -> None:
        if self._idx + 1 < len(self._connections):
            self._idx += 1

    def cursor(self, *args: object, **kwargs: object) -> object:
        return self.current_conn.cursor(*args, **kwargs)

    def commit(self) -> None:
        self.current_conn.commit()
        self._switch()

    def rollback(self) -> None:
        self.current_conn.rollback()
        self._switch()

    def close(self) -> None:
        for c in self._connections:
            try:
                c.close()
            except Exception:
                pass

    def __enter__(self) -> SimulatedPoolerConnection:
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        pass

    def __getattr__(self, name: str) -> object:
        return getattr(self.current_conn, name)


def test_simulated_pooler_early_return_advisory_lock_not_leaked() -> None:
    """Simulated transaction pooler: early-return path must not leak advisory lock.

    Under transaction pooling, conn.rollback() returns backend 0 to the pool. If session-level
    advisory locking is used, the subsequent pg_advisory_unlock() runs on backend 1, leaving
    backend 0 holding the session lock.
    With pg_advisory_xact_lock, conn.rollback() atomically releases the lock on backend 0.
    """
    settings = get_settings()
    tenant_id, _, _, rfq_id, _, _ = _make_fixture()

    pool_conns = [
        db.connect(settings.database_url.get_secret_value()),
        db.connect(settings.database_url.get_secret_value()),
        db.connect(settings.database_url.get_secret_value()),
    ]
    inspector = db.connect(settings.database_url.get_secret_value())
    try:
        pooler_conn = SimulatedPoolerConnection(pool_conns)
        _evaluate_guardrails_for_rfq(
            settings,
            pooler_conn,
            tenant_id=tenant_id,
            rfq_id=rfq_id,  # type: ignore[arg-type]
        )
        # Check lock BEFORE closing pooled connections
        locks_held = _count_rfq_advisory_locks(inspector, tenant_id, rfq_id)
        assert locks_held == 0, (
            f"Advisory lock leaked under simulated pooler for RFQ key; count = {locks_held}"
        )
    finally:
        inspector.close()
        for c in pool_conns:
            try:
                c.close()
            except Exception:
                pass


def test_simulated_pooler_firing_advisory_lock_not_leaked(monkeypatch: pytest.MonkeyPatch) -> None:
    """Simulated transaction pooler: firing path must not leak advisory lock."""
    settings = get_settings()
    tenant_id, user_id, _, rfq_id, response_a, _ = _make_fixture()
    req_conns = _setup_requests_client(monkeypatch, tenant_id, user_id)
    pool_conns = [
        db.connect(settings.database_url.get_secret_value()),
        db.connect(settings.database_url.get_secret_value()),
        db.connect(settings.database_url.get_secret_value()),
    ]
    inspector = db.connect(settings.database_url.get_secret_value())
    try:
        _configure_fixture_ready_to_fire(settings, rfq_id, response_a)
        pooler_conn = SimulatedPoolerConnection(pool_conns)
        _evaluate_guardrails_for_rfq(
            settings,
            pooler_conn,
            tenant_id=tenant_id,
            rfq_id=rfq_id,  # type: ignore[arg-type]
        )
        locks_held = _count_rfq_advisory_locks(inspector, tenant_id, rfq_id)
        assert locks_held == 0, (
            f"Advisory lock leaked under simulated pooler firing for RFQ key; count = {locks_held}"
        )
    finally:
        inspector.close()
        for c in pool_conns:
            try:
                c.close()
            except Exception:
                pass
        for c in req_conns:
            try:
                c.close()
            except Exception:
                pass


def test_simulated_pooler_exception_advisory_lock_not_leaked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Simulated transaction pooler: exception path must not leak advisory lock."""
    settings = get_settings()
    tenant_id, _, _, rfq_id, _, _ = _make_fixture()

    def _failing_snapshot(cur: object, *, tenant_id: uuid.UUID, rfq_id: uuid.UUID) -> object:
        raise RuntimeError("Simulated failure during guardrail evaluation")

    monkeypatch.setattr(orchestrator, "compute_guardrail_evaluation", _failing_snapshot)

    pool_conns = [
        db.connect(settings.database_url.get_secret_value()),
        db.connect(settings.database_url.get_secret_value()),
        db.connect(settings.database_url.get_secret_value()),
    ]
    inspector = db.connect(settings.database_url.get_secret_value())
    try:
        pooler_conn = SimulatedPoolerConnection(pool_conns)
        with pytest.raises(RuntimeError, match="Simulated failure"):
            _evaluate_guardrails_for_rfq(
                settings,
                pooler_conn,
                tenant_id=tenant_id,
                rfq_id=rfq_id,  # type: ignore[arg-type]
            )
        locks_held = _count_rfq_advisory_locks(inspector, tenant_id, rfq_id)
        assert locks_held == 0, (
            f"Advisory lock leaked under simulated pooler exception; count = {locks_held}"
        )
    finally:
        inspector.close()
        for c in pool_conns:
            try:
                c.close()
            except Exception:
                pass

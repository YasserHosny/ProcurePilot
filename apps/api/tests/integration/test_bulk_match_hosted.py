"""Opt-in real PostgREST benchmark; only creates/changes its own test workspace.

PP_HOSTED_ENV_FILE supplies hosted REST credentials without committing them. TEST_DATABASE_URL
supplies fixture DML. No migrations or DDL are run. Audit events remain append-only.
"""

from __future__ import annotations

import os
from collections import Counter
from dataclasses import replace
from threading import Lock
from time import perf_counter
from unittest.mock import Mock
from uuid import UUID, uuid4, uuid5

import httpx
import pytest
from dotenv import dotenv_values
from supabase import create_client

from integration.catalogue_helpers import (
    TEST_DATABASE_URL,
    act_as,
    delete_tenant_scoped_rows,
    make_workspace,
    make_workspace_product,
)
from integration.quotation_helpers import make_line, make_quotation, make_supplier
from integration.test_match_alias_learning import _candidate, _member, _open_task
from procurepilot_api import db
from procurepilot_api.config import Settings
from procurepilot_api.modules.matching import resolution_service as module
from procurepilot_api.modules.matching.resolution_service import MatchResolutionService
from procurepilot_api.modules.matching.schemas import MatchResolutionRequest

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL or not os.environ.get("PP_HOSTED_ENV_FILE"),
    reason="requires TEST_DATABASE_URL and PP_HOSTED_ENV_FILE for hosted REST benchmark",
)


def test_hosted_bulk_semantics_and_timing(monkeypatch: pytest.MonkeyPatch) -> None:
    values = dotenv_values(os.environ["PP_HOSTED_ENV_FILE"])
    settings = Settings(**{k.lower(): v for k, v in values.items() if v}, _env_file=None)
    assert "localhost" not in settings.supabase_url
    assert "localhost" not in TEST_DATABASE_URL
    # The audit writer uses get_settings(); use the same hosted settings as the service.
    from procurepilot_api.shared import audit

    monkeypatch.setattr(audit, "get_settings", lambda: settings)
    enqueue = Mock()
    monkeypatch.setattr(module, "enqueue_guardrail_evaluation", enqueue)
    counts: Counter[str] = Counter()
    lock = Lock()
    request_times: list[float] = []
    client_times: list[float] = []
    original_client = module.authenticated_client

    def timed_client(settings: Settings, token: str) -> object:
        start = perf_counter()
        client = original_client(settings, token)
        with lock:
            client_times.append(perf_counter() - start)
        return client

    monkeypatch.setattr(module, "authenticated_client", timed_client)
    original_send = httpx.Client.send

    def count_send(self: httpx.Client, request: httpx.Request, **kwargs: object) -> httpx.Response:
        if "/rest/v1/" in str(request.url):
            with lock:
                counts[request.url.path] += 1
        start = perf_counter()
        try:
            return original_send(self, request, **kwargs)
        finally:
            if "/rest/v1/" in str(request.url):
                with lock:
                    request_times.append(perf_counter() - start)

    monkeypatch.setattr(httpx.Client, "send", count_send)
    password = uuid4().hex + "aA1!"
    email = f"bulk-speed-{uuid4().hex}@example.test"
    admin = create_client(
        settings.supabase_url, settings.supabase_service_role_key.get_secret_value()
    )
    user = admin.auth.admin.create_user(
        {"email": email, "password": password, "email_confirm": True}
    ).user
    assert user is not None
    with db.connect(TEST_DATABASE_URL) as conn:
        with conn.cursor() as cur:
            workspace = make_workspace(cur, "bulk-speed-test")
            cur.execute(
                "update membership set user_id=%s where id=%s", (user.id, workspace.membership_id)
            )
            cur.execute("delete from auth.users where id=%s", (workspace.user_id,))
            workspace = replace(workspace, user_id=UUID(user.id))
            supplier = make_supplier(cur, workspace)
            quotations = [
                make_quotation(cur, workspace, supplier_id=supplier, status="reviewed")
                for _ in range(2)
            ]
            pairs = []
            # A single resolve baseline plus eleven bulk lines across two quotations.
            for n in range(12):
                text = f"Speed test product {n}"
                product = make_workspace_product(cur, workspace, name=text)
                line = make_line(cur, workspace, quotations[n % 2])
                cur.execute(
                    "update quotation_line set original_text=%s, line_number=%s where id=%s",
                    (text, n + 100, line),
                )
                candidate = _candidate(cur, workspace, line, product)
                if n:
                    _open_task(cur, workspace, line)
                pairs.append((line, candidate))
        conn.commit()
        try:
            auth = create_client(
                settings.supabase_url, settings.supabase_anon_key.get_secret_value()
            )
            session = auth.auth.sign_in_with_password(
                {"email": email, "password": password}
            ).session
            assert session is not None
            token = session.access_token
            counts.clear()
            service = MatchResolutionService(settings)
            member = _member(workspace)
            start = perf_counter()
            service.resolve(
                bearer_token=token,
                member=member,
                line_id=pairs[0][0],
                payload=MatchResolutionRequest(
                    outcome="same_product", selected_match_candidate_id=pairs[0][1]
                ),
                idempotency_key=uuid4(),
            )
            print(
                f"\nSINGLE seconds={perf_counter() - start:.3f} round_trips={sum(counts.values())}"
            )
            counts.clear()
            request_times.clear()
            client_times.clear()
            enqueue.reset_mock()
            key = uuid4()
            start = perf_counter()
            result = service.confirm_exact_matches(
                bearer_token=token, member=member, idempotency_key=key
            )
            elapsed = perf_counter() - start
            bulk_round_trips = sum(counts.values())
            print(
                f"BULK seconds={elapsed:.3f} round_trips={sum(counts.values())} "
                f"guardrails={enqueue.call_count}"
            )
            print(
                f"HTTP max={max(request_times):.3f}s "
                f"mean={sum(request_times) / len(request_times):.3f}s "
                f"slow_over_1s={sum(t > 1 for t in request_times)} "
                f"client_create_max={max(client_times):.3f}s"
            )
            assert (result.confirmed, result.skipped) == (11, 0)
            with conn.cursor() as cur:
                act_as(cur, workspace)
                cur.execute(
                    "select count(*), bool_and(not is_automatic and decided_by=%s "
                    "and alias_id is not null) from match_decision",
                    (member.membership_id,),
                )
                assert cur.fetchone() == (12, True)
                cur.execute("select count(*) from match_task where status='resolved'")
                assert cur.fetchone()[0] == 11
                cur.execute(
                    "select quotation_line_id, idempotency_key from match_resolution_idempotency "
                    "where quotation_line_id = any(%s)",
                    ([line_id for line_id, _ in pairs[1:]],),
                )
                assert dict(cur.fetchall()) == {
                    line_id: uuid5(key, str(line_id)) for line_id, _ in pairs[1:]
                }
                cur.execute("select count(*) from product_alias")
                assert cur.fetchone()[0] == 12
                cur.execute("select count(*) from landed_cost")
                assert cur.fetchone()[0] == 12
                cur.execute("select count(*) from audit_event where action='matching.resolved'")
                assert cur.fetchone()[0] == 12
            conn.rollback()
            retry = service.confirm_exact_matches(
                bearer_token=token, member=member, idempotency_key=key
            )
            assert (retry.confirmed, retry.skipped) == (11, 0)
            if os.environ.get("PP_BULK_BASELINE"):
                return
            assert enqueue.call_count == 2
            assert {call.kwargs["quotation_id"] for call in enqueue.call_args_list} == set(
                quotations
            )
            assert bulk_round_trips <= 175, f"bulk made {bulk_round_trips} REST round trips"
            assert elapsed < 5, f"hosted bulk took {elapsed:.3f}s"
        finally:
            conn.rollback()
            with conn.cursor() as cur:
                cur.execute("reset role")
                delete_tenant_scoped_rows(cur, workspace.tenant_id)
            conn.commit()
            admin.auth.admin.delete_user(user.id)

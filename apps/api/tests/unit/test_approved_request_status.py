"""Approval preserves the approved request state until an order exists (ADR-025)."""

from contextlib import nullcontext
from types import SimpleNamespace
from uuid import uuid4

import pytest
from unit.test_approval_decisions import member, request_row, step_row

from procurepilot_api.modules.requests import service as module
from procurepilot_api.modules.requests.service import RequestsService


@pytest.mark.parametrize("keyed", [False, True])
def test_transactional_approval_returns_approved(
    monkeypatch: pytest.MonkeyPatch, keyed: bool
) -> None:
    actor = member()
    rid = uuid4()
    request = request_row(rid, uuid4())
    step = step_row(rid, actor.membership_id)

    class Cursor:
        query = ""

        def execute(self, query: str, params: tuple = ()) -> None:
            self.query = query
            if "update purchase_request" in query:
                request["status"] = params[0]
            if "update approval_step" in query:
                step["status"] = params[0]

        def fetchone(self) -> dict | None:
            if "audit_event" in self.query:
                return None
            if "push_notification" in self.query:
                return {"id": uuid4()}
            return step.copy() if "approval_step" in self.query else request.copy()

    cursor = Cursor()
    conn = SimpleNamespace(cursor=lambda **_: nullcontext(cursor))
    monkeypatch.setattr(module.db, "connect", lambda *_: nullcontext(conn))
    result, decision, notification = RequestsService()._decide_and_notify(
        member=actor,
        request_id=str(rid),
        step_id=str(step["id"]),
        decision="approved",
        comment=None,
        now="2026-11-05T00:00:00Z",
        idempotency_key=uuid4() if keyed else None,
    )
    assert result["status"] == "approved"
    assert decision["status"] == "approved"
    assert notification is not None

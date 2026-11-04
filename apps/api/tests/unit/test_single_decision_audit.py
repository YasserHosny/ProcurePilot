"""Single-request decision validation and audit orchestration."""

from __future__ import annotations

import inspect
from uuid import uuid4

import psycopg
import pytest
from unit.test_approval_decisions import (
    member,
    prepare_decision_service,
    request_row,
    step_row,
)

from procurepilot_api.errors import (
    ConflictError,
    ServiceUnavailableError,
    UnprocessableEntityError,
)
from procurepilot_api.modules.requests import service as module
from procurepilot_api.modules.requests.schemas import ApprovalDecisionInput
from procurepilot_api.modules.requests.service import RequestsService


@pytest.mark.parametrize("decision", ["approved", "rejected"])
@pytest.mark.parametrize(
    "comment",
    [None, "", " \t\n ", "x" * 2000, "x" * 2001, " " * 2001, " padded "],
    ids=["absent", "empty", "whitespace", "limit", "over-limit", "long-blank", "padded"],
)
def test_single_decision_comment_validation(
    monkeypatch: pytest.MonkeyPatch, decision: str, comment: str | None
) -> None:
    actor = member()
    rid = uuid4()
    req = request_row(rid, uuid4())
    step = step_row(rid, actor.membership_id)
    writes: list[object] = []

    def decide(**kwargs: object) -> tuple[dict, dict, None]:
        writes.append(kwargs)
        return {**req, "status": "rejected"}, {**step, "status": decision}, None

    service, _, _ = prepare_decision_service(
        monkeypatch, current_member=actor, req=req, step=step, decide_and_notify=decide
    )
    reason = (
        "comment_too_long"
        if comment is not None and len(comment) > 2000
        else "comment_required"
        if decision == "rejected" and (comment is None or not comment.strip())
        else None
    )
    kwargs = dict(
        bearer_token="token",
        member=actor,
        request_id=rid,
        payload=ApprovalDecisionInput(comment=comment),
        decision=decision,
    )
    if reason:
        with pytest.raises(UnprocessableEntityError) as exc:
            service._decide_request(**kwargs)
        assert exc.value.status_code == 422
        assert exc.value.details == {"reason": reason}
        assert writes == []
    else:
        service._decide_request(**kwargs)
        assert writes[0]["comment"] == comment


def test_group_and_single_use_same_comment_validator() -> None:
    helper = module._validate_decision_comment
    for method in (RequestsService._decide_request, RequestsService._transition_group):
        assert helper.__name__ in inspect.getsource(method)


def test_single_decision_does_not_record_a_second_audit_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    actor = member()
    rid = uuid4()
    req = request_row(rid, uuid4())
    step = step_row(rid, actor.membership_id)
    service, _, recorded = prepare_decision_service(
        monkeypatch,
        current_member=actor,
        req=req,
        step=step,
        decide_and_notify=lambda **_: ({**req, "status": "ordered"}, step, None),
    )
    service.approve_request(
        bearer_token="token",
        member=actor,
        request_id=rid,
        payload=ApprovalDecisionInput(comment="Approved"),
    )
    assert recorded == []


@pytest.mark.parametrize("decision", ["approved", "rejected"])
@pytest.mark.parametrize("fail_audit", [False, True])
@pytest.mark.parametrize("self_decision", [False, True])
def test_audit_is_part_of_decision_transaction(
    monkeypatch: pytest.MonkeyPatch,
    decision: str,
    fail_audit: bool,
    self_decision: bool,
) -> None:
    from collections.abc import Iterator
    from contextlib import contextmanager
    from types import SimpleNamespace

    actor = member()
    rid, sid, nid = uuid4(), uuid4(), uuid4()
    persisted: list[str] = []
    pending: list[str] = []
    audits: list[object] = []
    active = False

    class Cursor:
        def __enter__(self) -> Cursor:
            return self

        def __exit__(self, *_: object) -> None:
            pass

        def execute(self, query: str, params: object = None) -> None:
            if "record_audit_event" in query:
                assert active, "audit must run before transaction commit"
                audits.append(params)
                if fail_audit:
                    raise RuntimeError("audit write failed")
                pending.append("audit")
            if "insert into push_notification" in query:
                pending.append("notification")

        def fetchone(self) -> dict[str, object]:
            return {"id": nid}

    @contextmanager
    def connect(*_: object, **__: object) -> Iterator[object]:
        nonlocal active
        active = True
        pending.clear()
        try:
            yield SimpleNamespace(cursor=lambda **_: Cursor())
        except Exception:
            pending.clear()
            raise
        else:
            persisted.extend(pending)
        finally:
            active = False

    service = RequestsService()

    def apply(*_: object, **__: object) -> tuple[dict, dict]:
        pending.extend(["request", "step"])
        return {"requested_by_membership_id": actor.membership_id if self_decision else uuid4()}, {
            "id": sid
        }

    monkeypatch.setattr(module.db, "connect", connect)
    monkeypatch.setattr(service, "_apply_request_decision", apply)
    kwargs = dict(
        member=actor,
        request_id=str(rid),
        step_id=str(sid),
        decision=decision,
        comment="Reason",
        now="2026-11-03T00:00:00Z",
    )
    if fail_audit:
        with pytest.raises(RuntimeError, match="audit write failed"):
            service._decide_and_notify(**kwargs)
        assert persisted == []
    else:
        service._decide_and_notify(**kwargs)
        assert sorted(persisted) == ["audit", "notification", "request", "step"]
        assert len(audits) == 1
        assert audits[0][0] == f"requests.approval_step_{decision}"
        expected_target = {
            "purchase_request_id": str(rid),
            "approval_step_id": str(sid),
            "decided_by_membership_id": str(actor.membership_id),
            "comment": "Reason",
        }
        if self_decision:
            expected_target["self_approved"] = True
        assert audits[0][4].obj == expected_target


def test_decide_and_notify_translates_database_error_and_preserves_conflict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from collections.abc import Iterator
    from contextlib import contextmanager
    from types import SimpleNamespace

    actor = member()
    rid, sid = uuid4(), uuid4()
    service = RequestsService()
    kwargs = dict(
        member=actor,
        request_id=str(rid),
        step_id=str(sid),
        decision="approved",
        comment="Reason",
        now="2026-11-03T00:00:00Z",
    )

    class ErrorCursor:
        def __enter__(self) -> ErrorCursor:
            return self

        def __exit__(self, *_: object) -> None:
            pass

        def execute(self, *_: object, **__: object) -> None:
            raise psycopg.OperationalError("database error")

        def fetchone(self) -> dict[str, object] | None:
            return None

    @contextmanager
    def connect_with_error(*_: object, **__: object) -> Iterator[object]:
        yield SimpleNamespace(cursor=lambda **_: ErrorCursor())

    monkeypatch.setattr(module.db, "connect", connect_with_error)
    with pytest.raises(ServiceUnavailableError) as exc:
        service._decide_and_notify(**kwargs)
    assert exc.value.status_code == 503
    assert exc.value.details == {"dependency": "database"}
    assert isinstance(exc.value.__cause__, psycopg.Error)

    class PassthroughCursor:
        def __enter__(self) -> PassthroughCursor:
            return self

        def __exit__(self, *_: object) -> None:
            pass

        def execute(self, *_: object, **__: object) -> None:
            pass

        def fetchone(self) -> dict[str, object] | None:
            return None

    @contextmanager
    def connect_ok(*_: object, **__: object) -> Iterator[object]:
        yield SimpleNamespace(cursor=lambda **_: PassthroughCursor())

    def raise_conflict(*_: object, **__: object) -> tuple[dict, dict]:
        raise ConflictError(details={"reason": "no_pending_approval"})

    monkeypatch.setattr(module.db, "connect", connect_ok)
    monkeypatch.setattr(service, "_apply_request_decision", raise_conflict)
    with pytest.raises(ConflictError) as exc:
        service._decide_and_notify(**kwargs)
    assert exc.value.status_code == 409
    assert exc.value.details == {"reason": "no_pending_approval"}

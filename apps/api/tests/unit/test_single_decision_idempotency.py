"""Optional decision keys preserve authorization and suppress repeated writes."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from unit.test_approval_decisions import member, prepare_decision_service, request_row, step_row

from procurepilot_api.deps import CurrentMember
from procurepilot_api.errors import ConflictError, NotFoundError, PermissionDeniedError
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.requests import router
from procurepilot_api.modules.requests import service as module
from procurepilot_api.modules.requests.schemas import ApprovalDecisionInput, PurchaseRequest

DecisionDB = tuple[SimpleNamespace, CurrentMember, Callable[..., PurchaseRequest]]


@pytest.fixture
def decision_db(monkeypatch: pytest.MonkeyPatch) -> DecisionDB:
    actor = member()
    rid = uuid4()
    req = request_row(rid, uuid4())
    step = step_row(rid, actor.membership_id)
    state = SimpleNamespace(req=req, step=step, audits=[], pushes=[], enqueues=[], queries=[])

    class Cursor:
        def __enter__(self) -> Cursor:
            return self

        def __exit__(self, *_: object) -> None:
            pass

        def execute(self, query: str, params: tuple | None = None) -> None:
            state.queries.append((query, params))
            self.row = None
            if "from purchase_request where" in query:
                self.row = state.req
            elif "from approval_step" in query:
                self.row = state.step
            elif "from audit_event" in query:
                self.row = next((a for a in state.audits if a[:5] == tuple(params)), None)
            elif "record_audit_event" in query:
                target = params[4].obj
                state.audits.append(
                    (
                        params[1],
                        params[2],
                        params[0],
                        target["purchase_request_id"],
                        target.get("idempotency_key"),
                        target,
                    )
                )
            elif "insert into push_notification" in query:
                nid = uuid4()
                state.pushes.append(nid)
                self.row = {"id": nid}

        def fetchone(self) -> object:
            return self.row

    @contextmanager
    def connect(*_: object, **__: object) -> Iterator[SimpleNamespace]:
        yield SimpleNamespace(cursor=lambda **_: Cursor())

    service, _, _ = prepare_decision_service(monkeypatch, current_member=actor, req=req, step=step)
    monkeypatch.setattr(module.db, "connect", connect)
    monkeypatch.setattr(module, "enqueue_push_job", lambda _, nid: state.enqueues.append(nid))

    def apply(_: object, **kwargs: object) -> tuple[dict, dict]:
        if req["status"] != "submitted":
            raise ConflictError(details={"reason": "not_submitted"})
        req["status"] = kwargs["request_status"]
        step.update(status=kwargs["decision"], comment=kwargs["comment"])
        return req, step

    monkeypatch.setattr(service, "_apply_request_decision", apply)

    def call(
        action: str = "approve",
        key: UUID | None = None,
        who: CurrentMember | None = None,
        comment: str | None = "Reason",
    ) -> PurchaseRequest:
        return getattr(service, f"{action}_request")(
            bearer_token="token",
            member=who or actor,
            request_id=rid,
            payload=ApprovalDecisionInput(comment=comment),
            idempotency_key=key,
        )

    return state, actor, call


@pytest.mark.parametrize("action", ["approve", "reject"])
def test_replay_returns_current_decision_without_writes(
    decision_db: DecisionDB, action: str
) -> None:
    state, actor, call = decision_db
    key = uuid4()
    first = call(action, key)
    state.req["status"] = "delivered" if action == "approve" else "rejected"
    replay = call(action, key, comment=" " * 2001)
    assert replay.status == state.req["status"]
    assert replay.approval_step == first.approval_step
    assert len(state.audits) == len(state.pushes) == len(state.enqueues) == 1
    assert state.audits[0][4] == str(key)
    lock = (actor.tenant_id.int ^ first.id.int) & 0x7FFFFFFFFFFFFFFF
    assert ("select pg_advisory_xact_lock(%s)", (lock,)) in state.queries


@pytest.mark.parametrize("retry", ["different_key", "opposite", "owner", "tenant", "no_key"])
def test_non_replays_conflict(decision_db: DecisionDB, retry: str) -> None:
    _, actor, call = decision_db
    key = uuid4()
    call(key=key)
    who = actor
    if retry == "owner":
        who = actor.model_copy(update={"membership_id": uuid4(), "role": MemberRole.owner})
    if retry == "tenant":
        who = actor.model_copy(update={"tenant_id": uuid4()})
    with pytest.raises(ConflictError):
        call(
            "reject" if retry == "opposite" else "approve",
            None if retry == "no_key" else uuid4() if retry == "different_key" else key,
            who,
        )


def test_authorization_precedes_replay(decision_db: DecisionDB) -> None:
    state, _, call = decision_db
    key = uuid4()
    call(key=key)
    state.step["assigned_membership_id"] = uuid4()
    with pytest.raises(PermissionDeniedError):
        call(key=key)
    state.req = None
    with pytest.raises(NotFoundError):
        call(key=key)
    assert len(state.audits) == len(state.pushes) == 1


@pytest.mark.parametrize("action", ["approve", "reject"])
def test_router_forwards_optional_key(action: str) -> None:
    captured = {}
    service = SimpleNamespace(**{f"{action}_request": lambda **kw: captured.update(kw)})
    key = uuid4()
    getattr(router, f"{action}_request")(
        request_id=uuid4(),
        payload=ApprovalDecisionInput(),
        token="token",
        member=member(),
        service=service,
        idempotency_key=key,
    )
    assert captured["idempotency_key"] == key


@pytest.mark.parametrize(
    "action,comment,reason",
    [
        ("approve", "x" * 2001, "comment_too_long"),
        ("reject", " ", "comment_required"),
    ],
)
def test_keyed_first_attempt_validates_comment(
    decision_db: DecisionDB, action: str, comment: str, reason: str
) -> None:
    from procurepilot_api.errors import UnprocessableEntityError

    state, _, call = decision_db
    with pytest.raises(UnprocessableEntityError) as exc:
        call(action, uuid4(), comment=comment)
    assert exc.value.details == {"reason": reason}
    assert state.audits == state.pushes == state.enqueues == []

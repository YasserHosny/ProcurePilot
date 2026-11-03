"""«Confirm & next» stays inside the quotation the buyer is working through (P-153, PPS-197)."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID, uuid4

from procurepilot_api.modules.matching.router import NextMatchTask, next_match_task


class _RecordingService:
    def __init__(self, items: list[object]) -> None:
        self._items = items
        self.calls: list[dict[str, object]] = []

    def list_match_tasks(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        return SimpleNamespace(items=self._items)


def _task(task_id: UUID, line_id: UUID) -> object:
    return SimpleNamespace(id=task_id, quotation_line=SimpleNamespace(id=line_id))


def _next(
    service: _RecordingService,
    *,
    exclude_task_id: UUID | None,
    quotation_id: UUID | None,
) -> NextMatchTask:
    return next_match_task(
        token="t",
        member=SimpleNamespace(),  # type: ignore[arg-type]
        service=service,  # type: ignore[arg-type]
        exclude_task_id=exclude_task_id,
        quotation_id=quotation_id,
    )


def test_next_task_is_looked_up_inside_the_given_quotation() -> None:
    quotation_id = uuid4()
    task_id, line_id = uuid4(), uuid4()
    service = _RecordingService([_task(task_id, line_id)])

    result = _next(service, exclude_task_id=None, quotation_id=quotation_id)

    assert service.calls[0]["quotation_id"] == quotation_id
    assert service.calls[0]["status"] == "open"
    assert result.next_quotation_line_id == line_id


def test_next_task_skips_the_excluded_task_and_reports_none_when_the_quotation_is_done() -> None:
    quotation_id = uuid4()
    only = uuid4()
    service = _RecordingService([_task(only, uuid4())])

    result = _next(service, exclude_task_id=only, quotation_id=quotation_id)

    assert result.next_task_id is None
    assert result.next_quotation_line_id is None


def test_next_task_without_a_quotation_keeps_the_workspace_wide_behaviour() -> None:
    service = _RecordingService([_task(uuid4(), uuid4())])

    _next(service, exclude_task_id=None, quotation_id=None)

    assert service.calls[0].get("quotation_id") is None

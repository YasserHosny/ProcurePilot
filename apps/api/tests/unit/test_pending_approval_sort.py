"""Pending decision ordering and cursor contract."""

from uuid import UUID, uuid4

import pytest
from pydantic import TypeAdapter, ValidationError

from procurepilot_api.errors import UnprocessableEntityError
from procurepilot_api.modules.requests import schemas, service

SORTS = ["submitted_desc", "submitted_asc", "required_by_asc", "total_desc", "total_asc"]


@pytest.mark.parametrize("sort", SORTS)
def test_sort_and_cursor_round_trip(sort: str) -> None:
    assert TypeAdapter(schemas.PendingApprovalSort).validate_python(sort) == sort
    value = (
        "2026-10-01T00:00:00.123456Z"
        if sort.startswith("submitted")
        else "2026-10-01"
        if sort == "required_by_asc"
        else "123.4500"
    )
    branch, step = uuid4(), uuid4()
    cursor = service._encode_approval_cursor(value, step, sort=sort, branch_id=branch)
    assert service._decode_approval_cursor(cursor, sort=sort, branch_id=branch) == (value, step)
    for other_sort, other_branch in [
        (sort, uuid4()),
        (sort, None),
        (SORTS[(SORTS.index(sort) + 1) % 5], branch),
    ]:
        with pytest.raises(UnprocessableEntityError) as error:
            service._decode_approval_cursor(cursor, sort=other_sort, branch_id=other_branch)
        assert error.value.status_code == 422
        assert error.value.details == {"cursor": "invalid"}


def test_invalid_sort() -> None:
    with pytest.raises(ValidationError):
        TypeAdapter(schemas.PendingApprovalSort).validate_python("invalid")


@pytest.mark.parametrize("sort", SORTS[2:])
def test_null_cursor(sort: str) -> None:
    step = UUID(int=1)
    cursor = service._encode_approval_cursor(None, step, sort=sort)
    assert service._decode_approval_cursor(cursor, sort=sort) == (None, step)


@pytest.mark.parametrize("sort", SORTS)
@pytest.mark.parametrize("mutation", ["none", "decision", "submission"])
def test_keyset_dataset(sort: str, mutation: str) -> None:
    import sqlite3

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        create table purchase_request (id text, status text, branch_id text,
            requested_by_membership_id text, required_by_date text, estimated_total_amount numeric,
            tenant_id text, request_group_id text);
        create table purchase_request_group (id text, tenant_id text,
            combined_total_amount numeric);
        create table approval_step (id text, purchase_request_id text, status text,
            assigned_membership_id text, created_at text);
    """)
    branch, actor = uuid4(), uuid4()
    values = [2, None, 1, 2, None, 3, 1]
    for i, value in enumerate(values, 1):
        conn.execute(
            "insert into purchase_request (id, status, branch_id, requested_by_membership_id, "
            "required_by_date, estimated_total_amount) values (?, ?, ?, ?, ?, ?)",
            (
                str(UUID(int=i)),
                "submitted",
                str(branch),
                str(uuid4()),
                f"2026-10-{value:02d}" if value else None,
                value,
            ),
        )
        conn.execute(
            "insert into approval_step values (?, ?, ?, ?, ?)",
            (
                str(UUID(int=i)),
                str(UUID(int=i)),
                "pending",
                str(actor),
                f"2026-10-01T00:00:00.00000{i // 2}Z",
            ),
        )
    expected_indices = {
        "submitted_desc": [6, 7, 4, 5, 2, 3, 1],
        "submitted_asc": [1, 2, 3, 4, 5, 6, 7],
        "required_by_asc": [3, 7, 1, 4, 6, 2, 5],
        "total_desc": [6, 1, 4, 3, 7, 2, 5],
        "total_asc": [3, 7, 1, 4, 6, 2, 5],
    }[sort]
    boundary = None
    seen = []
    while True:
        query, params = service._pending_approval_query(
            sort=sort,
            branch_id=branch,
            membership_id=actor,
            is_owner=True,
            is_sole_owner=True,
            boundary=boundary,
            limit=2,
        )
        # SQLite expressions lack column affinity; emulate Postgres numeric parameter typing.
        if boundary is not None and sort.startswith("total") and boundary[0] is not None:
            params[-4:-2] = [float(boundary[0]), float(boundary[0])]
        rows = conn.execute(
            query.replace("%s", "?"), [str(p) if isinstance(p, UUID) else p for p in params]
        ).fetchall()
        if not rows:
            break
        page = rows[:2]
        seen.extend(int(UUID(row["id"])) for row in page)
        last = page[-1]
        value = last["sort_value"]
        cursor = service._encode_approval_cursor(
            None if value is None else str(value), UUID(last["id"]), sort=sort, branch_id=branch
        )
        boundary = service._decode_approval_cursor(cursor, sort=sort, branch_id=branch)
        if len(seen) == 2 and mutation == "decision":
            conn.execute("update approval_step set status='approved' where id=?", (page[0]["id"],))
        elif len(seen) == 2 and mutation == "submission":
            # A new row before the boundary must not shift the remaining rows.
            conn.execute(
                "insert into purchase_request (id, status, branch_id, requested_by_membership_id, "
                "required_by_date, estimated_total_amount) values (?, ?, ?, ?, ?, ?)",
                (
                    str(UUID(int=99)),
                    "submitted",
                    str(branch),
                    str(uuid4()),
                    "2020-01-01",
                    999 if sort == "total_desc" else -1,
                ),
            )
            conn.execute(
                "insert into approval_step values (?, ?, ?, ?, ?)",
                (
                    str(UUID(int=99)),
                    str(UUID(int=99)),
                    "pending",
                    str(actor),
                    "2030-01-01T00:00:00Z" if sort == "submitted_desc" else "2020-01-01T00:00:00Z",
                ),
            )
        if len(rows) <= 2:
            break
    assert seen == expected_indices


def test_sql_reads_use_authenticated_claims_and_identical_filters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import json
    from contextlib import nullcontext
    from unittest.mock import Mock

    from unit.test_approval_decisions import member

    actor = member()
    branch = uuid4()
    cur = Mock()
    cur.fetchall.side_effect = [[], []]
    cur.fetchone.return_value = {"total": 7}
    connection = Mock()
    connection.cursor.return_value = nullcontext(cur)
    connect = Mock(return_value=nullcontext(connection))
    monkeypatch.setattr(service.db, "connect", connect)
    result = service.RequestsService()._pending_approval_page(
        member=actor, sort="total_desc", branch_id=branch, boundary=("20", uuid4()), limit=2
    )
    assert result == ([], 7)
    calls = cur.execute.call_args_list
    assert calls[0].args == ("set local role authenticated",)
    claims = json.loads(calls[1].args[1][0])
    assert claims == {
        "sub": str(actor.user_id),
        "tenant_id": str(actor.tenant_id),
        "role": "authenticated",
        "member_role": actor.role.value,
    }
    count_query, count_params = calls[3].args
    page_query, page_params = calls[4].args
    assert "count(*) as total" in count_query
    assert "ast.*" in page_query  # Includes created_at for default cursor generation.
    for predicate in (
        "ast.assigned_membership_id = %s",
        "pr.requested_by_membership_id <> %s",
        "pr.branch_id = %s",
    ):
        assert predicate in count_query and predicate in page_query
    assert page_params[: len(count_params)] == count_params
    assert "limit" not in count_query
    assert "prg.tenant_id = pr.tenant_id" in count_query
    assert "prg.id = pr.request_group_id" in count_query


@pytest.mark.parametrize(
    "sort,value",
    [
        ("total_asc", "NaN"),
        ("total_desc", "Infinity"),
        ("total_asc", "bad"),
        *[
            (sort, value)
            for sort in ("total_asc", "total_desc")
            for value in (
                "1E+200000",
                "١٢٣",
                "100000000000000",
                "-100000000000000",
                "1.00001",
                "1e1",
                "1_000",
                " 12",
                "12.",
                ".12",
            )
        ],
        ("submitted_asc", None),
        ("required_by_asc", "bad"),
    ],
)
def test_invalid_cursor_values(sort: str, value: str | None) -> None:
    cursor = service._encode_approval_cursor(value, uuid4(), sort=sort)
    with pytest.raises(UnprocessableEntityError) as error:
        service._decode_approval_cursor(cursor, sort=sort)
    assert error.value.status_code == 422
    assert error.value.details == {"cursor": "invalid"}


@pytest.mark.parametrize("sort", ["total_asc", "total_desc"])
@pytest.mark.parametrize("value", ["99999999999999.9999", "-99999999999999.9999", "+12.3400", "0"])
def test_valid_amount_cursor_boundary(sort: str, value: str) -> None:
    step_id = uuid4()
    cursor = service._encode_approval_cursor(value, step_id, sort=sort)
    assert service._decode_approval_cursor(cursor, sort=sort) == (value, step_id)


def test_legacy_default_cursor_remains_valid() -> None:
    import base64
    import json

    step_id = uuid4()
    cursor = base64.urlsafe_b64encode(
        json.dumps({"created_at": "2026-10-01T00:00:00Z", "id": str(step_id)}).encode()
    ).decode()
    assert service._decode_approval_cursor(cursor) == ("2026-10-01T00:00:00.000000Z", step_id)


@pytest.mark.parametrize("sort", ["total_desc", "total_asc"])
@pytest.mark.parametrize("limit", [1, 2])
def test_group_total_keyset(sort: str, limit: int) -> None:
    import sqlite3

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        create table purchase_request (id text, tenant_id text, request_group_id text,
            status text, estimated_total_amount numeric);
        create table purchase_request_group (id text, tenant_id text,
            combined_total_amount numeric);
        create table approval_step (id text, purchase_request_id text, status text);
        insert into purchase_request_group values ('group', 'tenant', 100.2500);
        insert into purchase_request values ('1', 'tenant', 'group', 'submitted', 1);
        insert into purchase_request values ('2', 'tenant', 'group', 'submitted', 2);
        insert into purchase_request values ('3', 'tenant', null, 'submitted', 50);
    """)
    for i in range(1, 4):
        conn.execute(
            "insert into approval_step values (?, ?, 'pending')", (str(UUID(int=i)), str(i))
        )
    options = dict(
        sort=sort,
        branch_id=None,
        membership_id=uuid4(),
        is_owner=True,
        is_sole_owner=True,
        limit=limit,
    )
    boundary = None
    seen = []
    while True:
        query, params = service._pending_approval_query(**options, boundary=boundary, count=True)
        assert conn.execute(query.replace("%s", "?"), params).fetchone()["total"] == 3
        query, params = service._pending_approval_query(**options, boundary=boundary)
        # SQLite expressions lack column affinity; emulate Postgres numeric parameter typing.
        if boundary is not None and sort.startswith("total") and boundary[0] is not None:
            params[-4:-2] = [float(boundary[0]), float(boundary[0])]
        rows = conn.execute(
            query.replace("%s", "?"), [str(p) if isinstance(p, UUID) else p for p in params]
        ).fetchall()
        page = rows[:limit]
        assert len(seen) < 3
        seen.extend(row["purchase_request_id"] for row in page)
        if len(rows) <= limit:
            break
        last = page[-1]
        cursor = service._encode_approval_cursor(
            str(last["sort_value"]), UUID(last["id"]), sort=sort
        )
        boundary = service._decode_approval_cursor(cursor, sort=sort)
    assert seen == (["1", "2", "3"] if sort == "total_desc" else ["3", "1", "2"])

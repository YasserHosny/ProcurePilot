"""Match decisions are correctable without being updated (spec 023 FR-005, research R5).

A correction inserts a new decision that names the one it supersedes. The database keeps each
line's decisions a single chain with one head, and `current_match_decision` serves the heads.
"""

from __future__ import annotations

from collections.abc import Iterator
from uuid import UUID, uuid4

import pytest

from integration.catalogue_helpers import (
    TEST_DATABASE_URL,
    Workspace,
    act_as,
    make_workspace,
    make_workspace_product,
    reset_role,
)
from integration.quotation_helpers import (
    ensure_quotation_reference_data,
    make_line,
    make_quotation,
)

psycopg = pytest.importorskip("psycopg")
from psycopg import errors  # noqa: E402

pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="TEST_DATABASE_URL not set")


@pytest.fixture
def conn() -> Iterator[psycopg.Connection]:
    with psycopg.connect(TEST_DATABASE_URL or "", prepare_threshold=None) as connection:
        yield connection
        connection.rollback()


def _candidate(cur: psycopg.Cursor, ws: Workspace, line_id: UUID, product_id: UUID) -> UUID:
    act_as(cur, ws)
    cur.execute(
        "select id from match_candidate "
        "where quotation_line_id = %s and candidate_workspace_product_id = %s",
        (line_id, product_id),
    )
    existing = cur.fetchone()
    if existing is not None:
        return existing[0]
    candidate_id = uuid4()
    cur.execute(
        """
        insert into match_candidate
          (id, tenant_id, quotation_line_id, candidate_workspace_product_id,
           confidence, reasons, rank, scoring_version, embedding_model)
        values (%s, %s, %s, %s, 0.9, '{}'::jsonb,
                (select coalesce(max(rank), 0) + 1 from match_candidate
                  where quotation_line_id = %s),
                'matching-score-v2', 'stub-hash-v1')
        """,
        (candidate_id, ws.tenant_id, line_id, product_id, line_id),
    )
    return candidate_id


def _decide(
    cur: psycopg.Cursor,
    ws: Workspace,
    line_id: UUID,
    product_id: UUID,
    *,
    supersedes: UUID | None = None,
    automatic: bool = False,
) -> UUID:
    candidate_id = _candidate(cur, ws, line_id, product_id)
    decision_id = uuid4()
    act_as(cur, ws)
    cur.execute(
        """
        insert into match_decision
          (id, tenant_id, quotation_line_id, matched_workspace_product_id,
           selected_match_candidate_id, outcome, is_automatic, decided_by, confidence,
           supersedes_decision_id)
        values (%s, %s, %s, %s, %s, 'same_product', %s, %s, 0.9, %s)
        """,
        (
            decision_id,
            ws.tenant_id,
            line_id,
            product_id,
            candidate_id,
            automatic,
            None if automatic else ws.membership_id,
            supersedes,
        ),
    )
    return decision_id


def _current(cur: psycopg.Cursor, ws: Workspace, line_id: UUID) -> list[UUID]:
    act_as(cur, ws)
    cur.execute("select id from current_match_decision where quotation_line_id = %s", (line_id,))
    return [row[0] for row in cur.fetchall()]


LineFixture = tuple[Workspace, UUID, UUID, UUID]


@pytest.fixture
def line(conn: psycopg.Connection) -> LineFixture:
    with conn.cursor() as cur:
        ensure_quotation_reference_data(cur)
        ws = make_workspace(cur, "supersession")
        product_a = make_workspace_product(cur, ws, name="Rice 10 kg")
        product_b = make_workspace_product(cur, ws, name="Flour 10 kg")
        quotation_id = make_quotation(cur, ws, status="reviewed")
        line_id = make_line(cur, ws, quotation_id)
        reset_role(cur)
    return ws, line_id, product_a, product_b


def test_a_second_root_decision_for_a_line_is_refused(
    conn: psycopg.Connection, line: LineFixture
) -> None:
    ws, line_id, product_a, product_b = line
    with conn.cursor() as cur:
        _decide(cur, ws, line_id, product_a, automatic=True)
        with pytest.raises(errors.UniqueViolation):
            with conn.transaction():
                _decide(cur, ws, line_id, product_b)


def test_a_correction_of_the_head_becomes_the_current_decision(
    conn: psycopg.Connection, line: LineFixture
) -> None:
    ws, line_id, product_a, product_b = line
    with conn.cursor() as cur:
        first = _decide(cur, ws, line_id, product_a, automatic=True)
        assert _current(cur, ws, line_id) == [first]
        second = _decide(cur, ws, line_id, product_b, supersedes=first)
        assert _current(cur, ws, line_id) == [second]
        third = _decide(cur, ws, line_id, product_a, supersedes=second)
        assert _current(cur, ws, line_id) == [third]
        # History stays: all three rows remain in the table.
        act_as(cur, ws)
        cur.execute("select count(*) from match_decision where quotation_line_id = %s", (line_id,))
        assert cur.fetchone()[0] == 3


def test_a_decision_can_be_superseded_only_once(
    conn: psycopg.Connection, line: LineFixture
) -> None:
    ws, line_id, product_a, product_b = line
    with conn.cursor() as cur:
        first = _decide(cur, ws, line_id, product_a, automatic=True)
        _decide(cur, ws, line_id, product_b, supersedes=first)
        with pytest.raises((errors.UniqueViolation, errors.CheckViolation)):
            with conn.transaction():
                _decide(cur, ws, line_id, product_a, supersedes=first)


def test_a_correction_must_target_the_same_line(
    conn: psycopg.Connection, line: LineFixture
) -> None:
    ws, line_id, product_a, product_b = line
    with conn.cursor() as cur:
        first = _decide(cur, ws, line_id, product_a, automatic=True)
        reset_role(cur)
        other_quotation = make_quotation(cur, ws, status="reviewed")
        other_line = make_line(cur, ws, other_quotation)
        with pytest.raises(errors.CheckViolation):
            with conn.transaction():
                _decide(cur, ws, other_line, product_b, supersedes=first)


def test_a_correction_cannot_point_at_another_tenants_decision(
    conn: psycopg.Connection, line: LineFixture
) -> None:
    ws, line_id, product_a, _ = line
    with conn.cursor() as cur:
        first = _decide(cur, ws, line_id, product_a, automatic=True)
        reset_role(cur)
        other = make_workspace(cur, "supersession-other")
        other_product = make_workspace_product(cur, other, name="Oil 18 L")
        other_quotation = make_quotation(cur, other, status="reviewed")
        other_line = make_line(cur, other, other_quotation)
        with pytest.raises((errors.ForeignKeyViolation, errors.CheckViolation)):
            with conn.transaction():
                _decide(cur, other, other_line, other_product, supersedes=first)


def test_clients_still_cannot_update_or_delete_decisions(
    conn: psycopg.Connection, line: LineFixture
) -> None:
    ws, line_id, product_a, _ = line
    with conn.cursor() as cur:
        first = _decide(cur, ws, line_id, product_a, automatic=True)
        for statement in (
            "update match_decision set confidence = 0.1 where id = %s",
            "delete from match_decision where id = %s",
        ):
            with pytest.raises(errors.InsufficientPrivilege):
                with conn.transaction():
                    act_as(cur, ws)
                    cur.execute(statement, (first,))


def test_current_match_decision_never_shows_another_tenants_rows(
    conn: psycopg.Connection, line: LineFixture
) -> None:
    ws, line_id, product_a, _ = line
    with conn.cursor() as cur:
        _decide(cur, ws, line_id, product_a, automatic=True)
        reset_role(cur)
        other = make_workspace(cur, "supersession-reader")
        act_as(cur, other)
        cur.execute(
            "select count(*) from current_match_decision where quotation_line_id = %s",
            (line_id,),
        )
        assert cur.fetchone()[0] == 0
        act_as(cur, ws)
        cur.execute(
            "select count(*) from current_match_decision where quotation_line_id = %s",
            (line_id,),
        )
        assert cur.fetchone()[0] == 1


def test_learned_from_decision_must_be_in_the_same_tenant(
    conn: psycopg.Connection, line: LineFixture
) -> None:
    ws, line_id, product_a, _ = line
    with conn.cursor() as cur:
        first = _decide(cur, ws, line_id, product_a, automatic=True)
        reset_role(cur)
        other = make_workspace(cur, "supersession-learned")
        other_product = make_workspace_product(cur, other, name="Sugar 50 kg")
        other_quotation = make_quotation(cur, other, status="reviewed")
        other_line = make_line(cur, other, other_quotation)
        candidate_id = _candidate(cur, other, other_line, other_product)
        with pytest.raises(errors.ForeignKeyViolation):
            with conn.transaction():
                act_as(cur, other)
                cur.execute(
                    """
                    insert into match_decision
                      (tenant_id, quotation_line_id, matched_workspace_product_id,
                       selected_match_candidate_id, outcome, is_automatic, confidence,
                       learned_from_decision_id)
                    values (%s, %s, %s, %s, 'same_product', true, 0.9, %s)
                    """,
                    (other.tenant_id, other_line, other_product, candidate_id, first),
                )

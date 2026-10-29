"""A split's requests belong to one purchase_request_group (spec 024 data-model.md).

The group is immutable evidence of a split preparation: tenant-private (ENABLE + FORCE RLS,
USING and WITH CHECK), one per RFQ, idempotent per key, with every amount carrying its
currency. Requests point at their group with a composite, tenant-pinned foreign key.
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
    reset_role,
)
from integration.test_branch_scoped_visibility import _make_member

psycopg = pytest.importorskip("psycopg")
from psycopg import errors  # noqa: E402

pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="TEST_DATABASE_URL not set")


@pytest.fixture
def conn() -> Iterator[psycopg.Connection]:
    with psycopg.connect(TEST_DATABASE_URL or "", prepare_threshold=None) as connection:
        yield connection
        connection.rollback()


Setup = tuple[Workspace, UUID, UUID, UUID]


def _setup(cur: psycopg.Cursor, label: str) -> Setup:
    """A workspace with a branch, an RFQ and a completed basket job for it."""
    ws = make_workspace(cur, label)
    branch, rfq, job = uuid4(), uuid4(), uuid4()
    reset_role(cur)
    cur.execute(
        "insert into branch (id,tenant_id,name) values (%s,%s,'Al Olaya')", (branch, ws.tenant_id)
    )
    cur.execute(
        "insert into rfq (id,tenant_id,created_by_membership_id,status,needed_by_date,"
        "idempotency_key) values (%s,%s,%s,'responded',current_date+7,%s)",
        (rfq, ws.tenant_id, ws.membership_id, uuid4()),
    )
    cur.execute(
        "insert into basket_split_job (id,tenant_id,requested_by,supplier_ids,items,status) "
        "values (%s,%s,%s,array[gen_random_uuid(),gen_random_uuid()],'[]'::jsonb,'queued')",
        (job, ws.tenant_id, ws.membership_id),
    )
    return ws, branch, rfq, job


def _insert_group(
    cur: psycopg.Cursor,
    ws: Workspace,
    branch: UUID,
    rfq: UUID,
    job: UUID,
    *,
    key: UUID | None = None,
    saving_currency: str | None = "SAR",
) -> UUID:
    group = uuid4()
    cur.execute(
        "insert into purchase_request_group (id,tenant_id,rfq_id,basket_split_job_id,branch_id,"
        "combined_total_amount,combined_total_currency,best_single_total_amount,"
        "best_single_total_currency,saving_amount,saving_currency,idempotency_key,"
        "created_by_membership_id) "
        "values (%s,%s,%s,%s,%s,4063,'SAR',4137,'SAR',74,%s,%s,%s)",
        (
            group,
            ws.tenant_id,
            rfq,
            job,
            branch,
            saving_currency,
            key or uuid4(),
            ws.membership_id,
        ),
    )
    return group


def test_a_member_creates_a_group_for_their_rfq_and_reads_it(
    conn: psycopg.Connection,
) -> None:
    with conn.cursor() as cur:
        ensure = _setup(cur, "group-schema-own")
        ws, branch, rfq, job = ensure
        act_as(cur, ws)
        group = _insert_group(cur, ws, branch, rfq, job)
        cur.execute("select count(*) from purchase_request_group where id = %s", (group,))
        assert cur.fetchone()[0] == 1


def test_a_group_for_another_tenants_rfq_is_refused(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        owner, branch, rfq, job = _setup(cur, "group-schema-owner")
        stranger, s_branch, s_rfq, s_job = _setup(cur, "group-schema-stranger")
        act_as(cur, stranger)
        # Pinning the row to the stranger's tenant but naming the owner's RFQ: the composite FK
        # (tenant_id, rfq_id) cannot resolve. Naming the owner's tenant: RLS WITH CHECK refuses.
        with pytest.raises((errors.ForeignKeyViolation, errors.InsufficientPrivilege)):
            with conn.transaction():
                _insert_group(cur, stranger, s_branch, rfq, s_job)
        with pytest.raises(errors.InsufficientPrivilege):
            with conn.transaction():
                _insert_group(cur, owner, branch, rfq, job)


def test_one_group_per_rfq_and_per_idempotency_key(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        ws, branch, rfq, job = _setup(cur, "group-schema-unique")
        act_as(cur, ws)
        key = uuid4()
        _insert_group(cur, ws, branch, rfq, job, key=key)
        with pytest.raises(errors.UniqueViolation):
            with conn.transaction():
                _insert_group(cur, ws, branch, rfq, job)
        reset_role(cur)
        other_rfq = uuid4()
        cur.execute(
            "insert into rfq (id,tenant_id,created_by_membership_id,status,needed_by_date,"
            "idempotency_key) values (%s,%s,%s,'responded',current_date+7,%s)",
            (other_rfq, ws.tenant_id, ws.membership_id, uuid4()),
        )
        act_as(cur, ws)
        with pytest.raises(errors.UniqueViolation):
            with conn.transaction():
                _insert_group(cur, ws, branch, other_rfq, job, key=key)


def test_clients_cannot_update_or_delete_a_group(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        ws, branch, rfq, job = _setup(cur, "group-schema-immutable")
        act_as(cur, ws)
        group = _insert_group(cur, ws, branch, rfq, job)
        for statement in (
            "update purchase_request_group set saving_amount = 1 where id = %s",
            "delete from purchase_request_group where id = %s",
        ):
            with pytest.raises(errors.InsufficientPrivilege):
                with conn.transaction():
                    act_as(cur, ws)
                    cur.execute(statement, (group,))


def test_another_tenant_cannot_see_a_group(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        ws, branch, rfq, job = _setup(cur, "group-schema-hidden")
        act_as(cur, ws)
        group = _insert_group(cur, ws, branch, rfq, job)
        reset_role(cur)
        stranger = make_workspace(cur, "group-schema-peeker")
        act_as(cur, stranger)
        cur.execute("select count(*) from purchase_request_group where id = %s", (group,))
        assert cur.fetchone()[0] == 0


def test_every_amount_carries_its_currency(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        ws, branch, rfq, job = _setup(cur, "group-schema-money")
        act_as(cur, ws)
        with pytest.raises(errors.CheckViolation):
            with conn.transaction():
                _insert_group(cur, ws, branch, rfq, job, saving_currency=None)


def test_a_request_joins_only_a_group_of_its_own_tenant(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        ws, branch, rfq, job = _setup(cur, "group-schema-request")
        act_as(cur, ws)
        group = _insert_group(cur, ws, branch, rfq, job)
        request = uuid4()
        cur.execute(
            "insert into purchase_request (id,tenant_id,branch_id,requested_by_membership_id,"
            "required_by_date,status,request_group_id) "
            "values (%s,%s,%s,%s,current_date+7,'draft',%s)",
            (request, ws.tenant_id, branch, ws.membership_id, group),
        )
        reset_role(cur)
        other, o_branch, o_rfq, o_job = _setup(cur, "group-schema-request-other")
        act_as(cur, other)
        with pytest.raises(errors.ForeignKeyViolation):
            with conn.transaction():
                cur.execute(
                    "insert into purchase_request (tenant_id,branch_id,"
                    "requested_by_membership_id,required_by_date,status,request_group_id) "
                    "values (%s,%s,%s,current_date+7,'draft',%s)",
                    (other.tenant_id, o_branch, other.membership_id, group),
                )


def test_a_basket_job_names_only_an_rfq_of_its_own_tenant(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        ws, branch, rfq, job = _setup(cur, "group-schema-job")
        other, o_branch, o_rfq, o_job = _setup(cur, "group-schema-job-other")
        reset_role(cur)
        cur.execute("update basket_split_job set rfq_id = %s where id = %s", (rfq, job))
        with pytest.raises(errors.ForeignKeyViolation):
            with conn.transaction():
                cur.execute("update basket_split_job set rfq_id = %s where id = %s", (rfq, o_job))


def test_group_threshold_match_is_an_approval_step_source(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        cur.execute("select 'group_threshold_match'::approval_step_source")
        assert cur.fetchone()[0] == "group_threshold_match"


def _group_in_new_branch(cur: psycopg.Cursor, ws: Workspace, name: str) -> tuple[UUID, UUID]:
    """Another branch with its own RFQ, job and group, created by the workspace owner."""
    reset_role(cur)
    branch, rfq, job = uuid4(), uuid4(), uuid4()
    cur.execute(
        "insert into branch (id,tenant_id,name) values (%s,%s,%s)", (branch, ws.tenant_id, name)
    )
    cur.execute(
        "insert into rfq (id,tenant_id,created_by_membership_id,status,needed_by_date,"
        "idempotency_key) values (%s,%s,%s,'responded',current_date+7,%s)",
        (rfq, ws.tenant_id, ws.membership_id, uuid4()),
    )
    cur.execute(
        "insert into basket_split_job (id,tenant_id,requested_by,supplier_ids,items,status) "
        "values (%s,%s,%s,array[gen_random_uuid(),gen_random_uuid()],'[]'::jsonb,'queued')",
        (job, ws.tenant_id, ws.membership_id),
    )
    act_as(cur, ws)
    return branch, _insert_group(cur, ws, branch, rfq, job)


def test_a_branch_scoped_member_sees_only_their_branches_groups(
    conn: psycopg.Connection,
) -> None:
    """Same visibility as purchase_request (data-model.md): owners, unassigned members, members
    of the group's branch, and the group's creator."""
    with conn.cursor() as cur:
        owner, branch_a, rfq_a, job_a = _setup(cur, "group-schema-branches")
        act_as(cur, owner)
        group_a = _insert_group(cur, owner, branch_a, rfq_a, job_a)
        _branch_b, group_b = _group_in_new_branch(cur, owner, "Al Malaz")
        reset_role(cur)
        scoped = _make_member(cur, owner.tenant_id, "group-schema-scoped", "buyer")
        unscoped = _make_member(cur, owner.tenant_id, "group-schema-unscoped", "buyer")
        cur.execute(
            "insert into branch_role_assignment (id,tenant_id,membership_id,branch_id) "
            "values (%s,%s,%s,%s)",
            (uuid4(), owner.tenant_id, scoped.membership_id, branch_a),
        )
        visible: dict[str, set[UUID]] = {}
        for label, member in (("owner", owner), ("scoped", scoped), ("unscoped", unscoped)):
            act_as(cur, member)
            cur.execute(
                "select id from purchase_request_group where id = any(%s)", ([group_a, group_b],)
            )
            visible[label] = {row[0] for row in cur.fetchall()}
            reset_role(cur)
        assert visible == {
            "owner": {group_a, group_b},
            "scoped": {group_a},
            "unscoped": {group_a, group_b},
        }


def test_a_scoped_member_always_sees_a_group_they_created(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        owner, branch_a, rfq_a, job_a = _setup(cur, "group-schema-creator")
        branch_b, _ = _group_in_new_branch(cur, owner, "Al Malaz")
        reset_role(cur)
        scoped = _make_member(cur, owner.tenant_id, "group-schema-creator-buyer", "buyer")
        cur.execute(
            "insert into branch_role_assignment (id,tenant_id,membership_id,branch_id) "
            "values (%s,%s,%s,%s)",
            (uuid4(), owner.tenant_id, scoped.membership_id, branch_b),
        )
        act_as(cur, scoped)
        group = _insert_group(cur, scoped, branch_a, rfq_a, job_a)
        cur.execute("select count(*) from purchase_request_group where id = %s", (group,))
        assert cur.fetchone()[0] == 1


def test_a_group_is_filed_only_under_its_creators_own_membership(
    conn: psycopg.Connection,
) -> None:
    with conn.cursor() as cur:
        owner, branch, rfq, job = _setup(cur, "group-schema-attribution")
        reset_role(cur)
        buyer = _make_member(cur, owner.tenant_id, "group-schema-attribution-buyer", "buyer")
        act_as(cur, buyer)
        # The buyer names the owner as the creator: refused, the row would misattribute evidence
        # that can never be corrected.
        with pytest.raises(errors.InsufficientPrivilege):
            with conn.transaction():
                _insert_group(cur, owner, branch, rfq, job)
        _insert_group(cur, buyer, branch, rfq, job)

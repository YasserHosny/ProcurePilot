-- 20260822000038_branch_role_assignment.sql — task T005, chunk R2.0
--
-- Sequenced right after branch (not after cost_centre/budget) because the branch-scoped
-- visibility policies on branch, cost_centre, and budget all depend on this table existing —
-- see the note at the end of 20260822000037_branch.sql.
--
-- Extends the existing membership/role relationship rather than replacing it: membership.role
-- remains the tenant-wide role value (owner, buyer, branch_manager, approver, viewer, unchanged
-- since chunk 4.1). This table adds branch scope on top of a branch_manager or approver role; a
-- member whose role is not branch-scoped simply has no rows here.

create table if not exists branch_role_assignment (
  id             uuid primary key default gen_random_uuid(),
  tenant_id      uuid not null references tenant(id) on delete cascade,
  membership_id  uuid not null,
  branch_id      uuid not null,
  created_at     timestamptz not null default now(),

  -- Composite (tenant_id, id) FKs: a tenant-A assignment can never reference a tenant-B
  -- membership or branch row, closing the GitHub issue #7 class of gap from day one.
  constraint branch_role_assignment_membership_fkey
    foreign key (tenant_id, membership_id) references membership (tenant_id, id) on delete cascade,
  constraint branch_role_assignment_branch_fkey
    foreign key (tenant_id, branch_id) references branch (tenant_id, id) on delete cascade,

  -- A member cannot be assigned to the same branch twice; one member scoped to multiple
  -- branches is supported as separate rows (research.md R2, spec.md edge case).
  constraint branch_role_assignment_unique unique (tenant_id, membership_id, branch_id)
);

create index if not exists branch_role_assignment_tenant_idx on branch_role_assignment (tenant_id);
create index if not exists branch_role_assignment_membership_idx on branch_role_assignment (membership_id);
create index if not exists branch_role_assignment_branch_idx on branch_role_assignment (branch_id);

comment on table branch_role_assignment is
  'A branch-scoped role (branch_manager, approver) member''s assigned branch(es). No
   is_active/soft-delete column: removing an assignment is a real row delete here, since this
   join table carries no history worth preserving on its own — the audit log (FR-012) is where
   the historical record of an assignment change lives.';

alter table branch_role_assignment enable row level security;
alter table branch_role_assignment force  row level security;

create policy branch_role_assignment_tenant_isolation on branch_role_assignment
  for all to authenticated
  using      (tenant_id = current_tenant_id())
  with check  (tenant_id = current_tenant_id());

-- Read: an owner sees every assignment in the tenant; a non-owner sees only their own
-- assignment row(s), matching "readable by the assigned member for their own row(s) and by
-- owner for all" from data-model.md's RLS Summary. Write: owner-only, enforced at the
-- application layer (matching the branch table's own owner-only-write pattern).
--
-- RESTRICTIVE, not permissive: branch_role_assignment_tenant_isolation above is a permissive
-- FOR ALL policy, and Postgres combines multiple permissive policies with OR — a second
-- permissive SELECT policy here would be bypassed entirely by the tenant-isolation policy
-- alone (any tenant-matching row would already satisfy it). Marking this one RESTRICTIVE
-- makes Postgres AND it against the permissive result instead, which is the actual narrowing
-- this policy exists to enforce. Re-checks tenant_id explicitly too, defensively, rather than
-- relying solely on the permissive policy for that half of the check.
create policy branch_role_assignment_visibility on branch_role_assignment
  as restrictive
  for select to authenticated
  using (
    tenant_id = current_tenant_id()
    and (
      current_member_role() = 'owner'
      or membership_id = current_membership_id()
    )
  );

grant select, insert, update, delete on branch_role_assignment to authenticated;
grant select, insert, update, delete on branch_role_assignment to service_role;

-- ---------------------------------------------------------------------------
-- Now that branch_role_assignment exists, add branch's own branch-scoped visibility policy
-- (deferred from 20260822000037_branch.sql to avoid a forward reference).
--
-- RESTRICTIVE for the same reason as branch_role_assignment_visibility above:
-- branch_tenant_isolation on `branch` is a permissive FOR ALL policy, and a second permissive
-- SELECT policy would be OR-combined with it — meaning any tenant-matching row would already
-- satisfy visibility via the tenant-isolation policy alone, bypassing branch scoping entirely.
-- ---------------------------------------------------------------------------

create policy branch_scoped_visibility on branch
  as restrictive
  for select to authenticated
  using (
    tenant_id = current_tenant_id()
    and (
      current_member_role() = 'owner'
      or not exists (
        select 1 from branch_role_assignment
        where branch_role_assignment.tenant_id = branch.tenant_id
          and branch_role_assignment.membership_id = current_membership_id()
      )
      or exists (
        select 1 from branch_role_assignment
        where branch_role_assignment.tenant_id = branch.tenant_id
          and branch_role_assignment.membership_id = current_membership_id()
          and branch_role_assignment.branch_id = branch.id
      )
    )
  );

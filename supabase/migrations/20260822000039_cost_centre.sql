-- 20260822000039_cost_centre.sql — task T003, chunk R2.0
--
-- cost_centre — a budget-tracking grouping within a tenant, independent of physical location.
-- Sequenced after branch_role_assignment so its branch-scoped visibility policy can reference
-- that table directly, with no forward reference.

create table if not exists cost_centre (
  id                          uuid primary key default gen_random_uuid(),
  tenant_id                   uuid not null references tenant(id) on delete cascade,
  name                        text not null,
  code                        text not null,
  budget_owner_membership_id  uuid,
  branch_id                   uuid,
  is_orphaned                 boolean not null default false,
  is_archived                 boolean not null default false,
  created_at                  timestamptz not null default now(),
  updated_at                  timestamptz not null default now(),

  constraint cost_centre_tenant_id_key unique (tenant_id, id),
  constraint cost_centre_tenant_code_key unique (tenant_id, code),

  constraint cost_centre_budget_owner_fkey
    foreign key (tenant_id, budget_owner_membership_id) references membership (tenant_id, id)
    on delete set null,
  constraint cost_centre_branch_fkey
    foreign key (tenant_id, branch_id) references branch (tenant_id, id)
    on delete set null
);

create index if not exists cost_centre_tenant_idx on cost_centre (tenant_id);
create index if not exists cost_centre_branch_idx on cost_centre (branch_id);

comment on table cost_centre is
  'A budget-tracking grouping within a tenant, optionally linked to one branch (null =
   organisation-wide). is_orphaned is a flag set by application logic when the linked branch is
   deactivated or the budget owner is removed (FR-010) — not a derived/computed column, so the
   orphan state stays visible even after the branch or member row itself changes further. No
   hard-delete path: archival (is_archived = true) is the only retirement path.';

comment on column cost_centre.branch_id is
  'ON DELETE SET NULL, not CASCADE: a cost centre outliving its branch link becomes an
   organisation-wide cost centre from the database''s point of view, flagged is_orphaned by the
   application so the owner is prompted to reassign or archive it (FR-010) — it is never
   silently deleted along with the branch.';

alter table cost_centre enable row level security;
alter table cost_centre force  row level security;

create policy cost_centre_tenant_isolation on cost_centre
  for all to authenticated
  using      (tenant_id = current_tenant_id())
  with check  (tenant_id = current_tenant_id());

-- RESTRICTIVE for the same reason as branch's own scoped-visibility policy: a second permissive
-- SELECT policy would be OR-combined with cost_centre_tenant_isolation above and bypassed
-- entirely. branch_id null (organisation-wide) is always visible once tenant matches.
create policy cost_centre_scoped_visibility on cost_centre
  as restrictive
  for select to authenticated
  using (
    tenant_id = current_tenant_id()
    and (
      cost_centre.branch_id is null
      or current_member_role() = 'owner'
      or not exists (
        select 1 from branch_role_assignment
        where branch_role_assignment.tenant_id = cost_centre.tenant_id
          and branch_role_assignment.membership_id = current_membership_id()
      )
      or exists (
        select 1 from branch_role_assignment
        where branch_role_assignment.tenant_id = cost_centre.tenant_id
          and branch_role_assignment.membership_id = current_membership_id()
          and branch_role_assignment.branch_id = cost_centre.branch_id
      )
    )
  );

grant select, insert, update, delete on cost_centre to authenticated;
grant select, insert, update, delete on cost_centre to service_role;

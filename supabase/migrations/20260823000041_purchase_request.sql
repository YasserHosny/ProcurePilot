-- 20260823000041_purchase_request.sql — task T001, chunk R2.1
--
-- purchase_request — a requester's ask to buy something, scoped to a branch and optionally a
-- cost centre. Reuses R2.0's branch-scoped visibility mechanism (current_membership_id(),
-- current_member_role(), branch_role_assignment) verbatim — no new isolation axis, per
-- research.md R1 — extended with one additional clause: the requester always sees their own
-- request regardless of branch scoping, since a request is inherently "theirs" even if their
-- own role happens to be scoped to a different branch by the time they look at it later.
--
-- Write authorization (who may create/edit/withdraw/decide) is enforced at the application
-- layer, not by a write-narrowing RLS policy — matching the exact pattern already established
-- for branch/cost_centre/budget in R2.0, where "owner-only writes" is an app-layer RBAC check,
-- not a second RLS policy. This table's writers are actually three different actors (requester,
-- assigned approver, owner), which is even more reason to keep that authorization logic in one
-- place (the service layer) rather than spread across several restrictive SQL policies.

create type purchase_request_status as enum ('draft', 'submitted', 'approved', 'rejected', 'withdrawn');

create table if not exists purchase_request (
  id                            uuid primary key default gen_random_uuid(),
  tenant_id                     uuid not null references tenant(id) on delete cascade,
  branch_id                     uuid not null,
  cost_centre_id                uuid,
  requested_by_membership_id    uuid not null,
  required_by_date              date not null,
  status                        purchase_request_status not null default 'draft',
  estimated_total_amount        numeric(18, 4),
  estimated_total_currency      text references supported_currency(code),
  has_incomplete_estimate       boolean not null default false,
  submitted_at                  timestamptz,
  withdrawn_at                  timestamptz,
  created_at                    timestamptz not null default now(),
  updated_at                    timestamptz not null default now(),

  constraint purchase_request_tenant_id_key unique (tenant_id, id),

  constraint purchase_request_branch_fkey
    foreign key (tenant_id, branch_id) references branch (tenant_id, id),
  constraint purchase_request_cost_centre_fkey
    foreign key (tenant_id, cost_centre_id) references cost_centre (tenant_id, id),
  constraint purchase_request_requested_by_fkey
    foreign key (tenant_id, requested_by_membership_id) references membership (tenant_id, id),

  -- estimated_total_amount / estimated_total_currency are null together or populated together
  -- (research.md R2 — null when lines span more than one currency, or no line has any estimate).
  constraint purchase_request_estimated_total_paired check (
    (estimated_total_amount is null) = (estimated_total_currency is null)
  )
);

create index if not exists purchase_request_tenant_idx on purchase_request (tenant_id);
create index if not exists purchase_request_branch_idx on purchase_request (branch_id);
create index if not exists purchase_request_requester_idx on purchase_request (requested_by_membership_id);
create index if not exists purchase_request_status_idx on purchase_request (tenant_id, status);

comment on table purchase_request is
  'A requester''s ask to buy something (chunk R2.1). Moves draft -> submitted ->
   (approved | rejected | withdrawn). No hard-delete path once submitted: withdraw is the only
   requester-initiated retirement (FR-004); a draft may be hard-deleted by its own requester.';

alter table purchase_request enable row level security;
alter table purchase_request force  row level security;

create policy purchase_request_tenant_isolation on purchase_request
  for all to authenticated
  using      (tenant_id = current_tenant_id())
  with check  (tenant_id = current_tenant_id());

-- RESTRICTIVE, SELECT-only, same shape as branch/cost_centre's own scoped-visibility policies —
-- see the note on those migrations for why RESTRICTIVE (not a second permissive policy) is
-- required to actually narrow visibility. The requester-always-sees-own clause is this chunk's
-- one addition to the R2.0 shape.
create policy purchase_request_scoped_visibility on purchase_request
  as restrictive
  for select to authenticated
  using (
    tenant_id = current_tenant_id()
    and (
      current_member_role() = 'owner'
      or requested_by_membership_id = current_membership_id()
      or not exists (
        select 1 from branch_role_assignment
        where branch_role_assignment.tenant_id = purchase_request.tenant_id
          and branch_role_assignment.membership_id = current_membership_id()
      )
      or exists (
        select 1 from branch_role_assignment
        where branch_role_assignment.tenant_id = purchase_request.tenant_id
          and branch_role_assignment.membership_id = current_membership_id()
          and branch_role_assignment.branch_id = purchase_request.branch_id
      )
    )
  );

grant select, insert, update, delete on purchase_request to authenticated;
grant select, insert, update, delete on purchase_request to service_role;

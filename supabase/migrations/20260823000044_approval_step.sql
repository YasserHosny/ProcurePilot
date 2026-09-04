-- 20260823000044_approval_step.sql — task T003, chunk R2.1
--
-- approval_step — the record of a single decision (or pending decision) on a request, produced
-- by routing at submission time (research.md R3). One row per request in this release (a single
-- resolved approval step, not a multi-stage chain — unique (tenant_id, purchase_request_id)).
--
-- The status='pending' iff decided_by/decided_at are null check constraint directly encodes
-- FR-006 ("no request may become approved without a recorded human decision") at the database
-- level, not only the application layer — the strongest form of Principle III's guarantee this
-- schema can express.

create type approval_step_status as enum ('pending', 'approved', 'rejected');
create type approval_step_source as enum ('threshold_match', 'delegate', 'owner_fallback');

create table if not exists approval_step (
  id                          uuid primary key default gen_random_uuid(),
  tenant_id                   uuid not null references tenant(id) on delete cascade,
  purchase_request_id         uuid not null,
  assigned_membership_id      uuid not null,
  source                      approval_step_source not null,
  status                      approval_step_status not null default 'pending',
  comment                     text,
  decided_by_membership_id    uuid,
  decided_at                  timestamptz,
  created_at                  timestamptz not null default now(),

  constraint approval_step_request_fkey
    foreign key (tenant_id, purchase_request_id) references purchase_request (tenant_id, id) on delete cascade,
  constraint approval_step_assigned_fkey
    foreign key (tenant_id, assigned_membership_id) references membership (tenant_id, id),
  constraint approval_step_decided_by_fkey
    foreign key (tenant_id, decided_by_membership_id) references membership (tenant_id, id),

  constraint approval_step_one_per_request unique (tenant_id, purchase_request_id),

  -- FR-006, enforced in the database, not only the application layer: a decision fields pair is
  -- present if and only if the step is no longer pending. Deliberately does NOT also require
  -- decided_by_membership_id = assigned_membership_id — FR-007's owner-override legitimately
  -- lets someone other than the resolved assignee decide; the RBAC guard (service-layer,
  -- covered by contract/integration tests), not a check constraint, enforces "only the assignee
  -- or an owner" per research.md R3.
  constraint approval_step_decision_fields_paired check (
    (status = 'pending') = (decided_by_membership_id is null and decided_at is null)
  )
);

create index if not exists approval_step_tenant_idx on approval_step (tenant_id);
create index if not exists approval_step_assigned_idx on approval_step (assigned_membership_id);
create index if not exists approval_step_status_idx on approval_step (tenant_id, status);

comment on table approval_step is
  'The single resolved decision (or pending decision) on a purchase request (chunk R2.1),
   produced by routing at submission time (research.md R3) and never silently re-resolved
   afterward. source records HOW assigned_membership_id was resolved (informational only).';

alter table approval_step enable row level security;
alter table approval_step force  row level security;

create policy approval_step_tenant_isolation on approval_step
  for all to authenticated
  using      (tenant_id = current_tenant_id())
  with check  (tenant_id = current_tenant_id());

-- RESTRICTIVE, SELECT-only: owner sees all; the assigned approver sees their own step; the
-- requester sees the step on their own request (read-only, for status visibility) — matching
-- data-model.md's RLS Summary exactly. Write authorization (only the assignee or owner may
-- transition status) is an application-layer RBAC check, same as every other table in this
-- chunk and in R2.0.
create policy approval_step_scoped_visibility on approval_step
  as restrictive
  for select to authenticated
  using (
    tenant_id = current_tenant_id()
    and (
      current_member_role() = 'owner'
      or assigned_membership_id = current_membership_id()
      or exists (
        select 1 from purchase_request
        where purchase_request.tenant_id = approval_step.tenant_id
          and purchase_request.id = approval_step.purchase_request_id
          and purchase_request.requested_by_membership_id = current_membership_id()
      )
    )
  );

grant select, insert, update, delete on approval_step to authenticated;
grant select, insert, update, delete on approval_step to service_role;

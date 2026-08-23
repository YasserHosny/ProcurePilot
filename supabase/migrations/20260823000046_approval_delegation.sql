-- 20260823000046_approval_delegation.sql — task T005, chunk R2.1
--
-- approval_delegation — a time-bounded handoff of one approver's pending and incoming decisions
-- to another eligible approver (research.md R3). Tenant-wide read (no branch-scoped
-- restriction — a delegation is not per-branch secret data); write restricted to the delegator
-- themselves or an owner, enforced at the application layer.

create table if not exists approval_delegation (
  id                          uuid primary key default gen_random_uuid(),
  tenant_id                   uuid not null references tenant(id) on delete cascade,
  delegator_membership_id     uuid not null,
  delegate_membership_id      uuid not null,
  starts_on                   date not null,
  ends_on                     date not null,
  created_at                  timestamptz not null default now(),

  constraint approval_delegation_delegator_fkey
    foreign key (tenant_id, delegator_membership_id) references membership (tenant_id, id),
  constraint approval_delegation_delegate_fkey
    foreign key (tenant_id, delegate_membership_id) references membership (tenant_id, id),

  constraint approval_delegation_distinct_parties check (delegator_membership_id <> delegate_membership_id),
  constraint approval_delegation_date_range check (ends_on >= starts_on)
);

create index if not exists approval_delegation_tenant_idx on approval_delegation (tenant_id);
create index if not exists approval_delegation_delegator_idx on approval_delegation (delegator_membership_id);
create index if not exists approval_delegation_window_idx on approval_delegation (tenant_id, starts_on, ends_on);

comment on table approval_delegation is
  'A time-bounded handoff of one approver''s pending/incoming decisions to another eligible
   approver (chunk R2.1). Checked AFTER threshold resolution at submission time, not instead of
   it — research.md R3. No uniqueness constraint preventing overlapping windows for the same
   delegator; routing resolves a genuine overlap by preferring the most-recently-created
   delegation covering the request date, since two truly overlapping active delegations for the
   same person is expected misconfiguration, not a designed state.';

alter table approval_delegation enable row level security;
alter table approval_delegation force  row level security;

create policy approval_delegation_tenant_isolation on approval_delegation
  for all to authenticated
  using      (tenant_id = current_tenant_id())
  with check  (tenant_id = current_tenant_id());

grant select, insert, update, delete on approval_delegation to authenticated;
grant select, insert, update, delete on approval_delegation to service_role;

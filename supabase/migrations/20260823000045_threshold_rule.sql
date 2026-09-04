-- 20260823000045_threshold_rule.sql — task T004, chunk R2.1
--
-- threshold_rule — an owner-defined rule mapping a request-value range and an optional branch
-- scope to the approver a matching request should route to (research.md R3). Tenant-wide
-- configuration: unlike branch/cost_centre/budget, this table gets NO branch-scoped RESTRICTIVE
-- visibility policy — every member can read the rules that determine routing, per research.md
-- R1 (routing outcomes are not a per-branch secret); only an owner may write them, enforced at
-- the application layer, matching this codebase's established owner-only-write pattern.

create table if not exists threshold_rule (
  id                        uuid primary key default gen_random_uuid(),
  tenant_id                 uuid not null references tenant(id) on delete cascade,
  branch_id                 uuid,
  min_amount                numeric(18, 4) not null,
  max_amount                numeric(18, 4),
  currency                  text not null references supported_currency(code),
  approver_membership_id    uuid not null,
  created_by                uuid not null,
  created_at                timestamptz not null default now(),
  updated_at                timestamptz not null default now(),

  constraint threshold_rule_branch_fkey
    foreign key (tenant_id, branch_id) references branch (tenant_id, id),
  constraint threshold_rule_approver_fkey
    foreign key (tenant_id, approver_membership_id) references membership (tenant_id, id),
  constraint threshold_rule_created_by_fkey
    foreign key (tenant_id, created_by) references membership (tenant_id, id),

  constraint threshold_rule_range_check check (max_amount is null or max_amount > min_amount)
);

create index if not exists threshold_rule_tenant_idx on threshold_rule (tenant_id);
create index if not exists threshold_rule_branch_idx on threshold_rule (tenant_id, branch_id);

comment on table threshold_rule is
  'Owner-defined request-value-range -> approver routing rule (chunk R2.1). branch_id null =
   tenant-wide default. Deliberately no uniqueness constraint preventing overlapping ranges —
   research.md R3''s narrowest-range tie-break resolves a genuine overlap deterministically at
   routing time rather than the database refusing the owner''s configuration outright.';

alter table threshold_rule enable row level security;
alter table threshold_rule force  row level security;

create policy threshold_rule_tenant_isolation on threshold_rule
  for all to authenticated
  using      (tenant_id = current_tenant_id())
  with check  (tenant_id = current_tenant_id());

grant select, insert, update, delete on threshold_rule to authenticated;
grant select, insert, update, delete on threshold_rule to service_role;

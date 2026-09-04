-- 20260822000040_budget.sql — task T004, chunk R2.0
--
-- budget — a defined spending allowance for a period, scoped to exactly one of: the
-- organisation, one branch, or one cost centre. This chunk defines and stores budgets only;
-- checking real spend against them is explicitly out of scope until R2.1 (spec.md User Story 3).

create type budget_period as enum ('monthly', 'quarterly', 'annual');
create type budget_scope  as enum ('organisation', 'branch', 'cost_centre');

create table if not exists budget (
  id             uuid primary key default gen_random_uuid(),
  tenant_id      uuid not null references tenant(id) on delete cascade,
  amount         numeric(18, 4) not null check (amount >= 0),
  currency       text not null references supported_currency(code),
  period         budget_period not null,
  period_start   date not null,
  scope          budget_scope not null,
  branch_id      uuid,
  cost_centre_id uuid,
  created_by     uuid not null,
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now(),

  constraint budget_branch_fkey
    foreign key (tenant_id, branch_id) references branch (tenant_id, id) on delete cascade,
  constraint budget_cost_centre_fkey
    foreign key (tenant_id, cost_centre_id) references cost_centre (tenant_id, id) on delete cascade,
  constraint budget_created_by_fkey
    foreign key (tenant_id, created_by) references membership (tenant_id, id),

  -- The scope enum and the actual populated reference column can never disagree — mirrors the
  -- existing quotation_stated_total_has_currency-style paired-nullability pattern from chunk 4.3.
  constraint budget_scope_target check (
    (scope = 'organisation' and branch_id is null and cost_centre_id is null)
    or (scope = 'branch' and branch_id is not null and cost_centre_id is null)
    or (scope = 'cost_centre' and cost_centre_id is not null and branch_id is null)
  )
);

create index if not exists budget_tenant_idx on budget (tenant_id);
create index if not exists budget_scope_branch_idx on budget (scope, branch_id);
create index if not exists budget_scope_cost_centre_idx on budget (scope, cost_centre_id);

comment on table budget is
  'A spending allowance for a period, at exactly one scope. Deliberately no uniqueness
   constraint preventing overlapping periods for the same scope (spec.md User Story 3,
   Acceptance Scenario 3: e.g. a running annual budget plus a supplementary quarterly top-up
   may legitimately coexist) — the application layer surfaces an overlap warning, the database
   does not block it. currency is never inferred from tenant.currency (research.md R3).';

alter table budget enable row level security;
alter table budget force  row level security;

create policy budget_tenant_isolation on budget
  for all to authenticated
  using      (tenant_id = current_tenant_id())
  with check  (tenant_id = current_tenant_id());

-- RESTRICTIVE for the same reason as branch/cost_centre's own scoped-visibility policies.
-- scope = 'organisation' is always visible once tenant matches; branch/cost_centre-scoped
-- budgets are visible per the same branch_role_assignment check, evaluated via a direct
-- branch_id match for scope=branch, or via the linked cost centre's own branch_id for
-- scope=cost_centre.
create policy budget_scoped_visibility on budget
  as restrictive
  for select to authenticated
  using (
    tenant_id = current_tenant_id()
    and (
      budget.scope = 'organisation'
      or current_member_role() = 'owner'
      or not exists (
        select 1 from branch_role_assignment
        where branch_role_assignment.tenant_id = budget.tenant_id
          and branch_role_assignment.membership_id = current_membership_id()
      )
      or (
        budget.scope = 'branch'
        and exists (
          select 1 from branch_role_assignment
          where branch_role_assignment.tenant_id = budget.tenant_id
            and branch_role_assignment.membership_id = current_membership_id()
            and branch_role_assignment.branch_id = budget.branch_id
        )
      )
      or (
        budget.scope = 'cost_centre'
        and exists (
          select 1 from cost_centre
          where cost_centre.tenant_id = budget.tenant_id
            and cost_centre.id = budget.cost_centre_id
            and (
              -- An organisation-wide cost centre (no branch link) is always visible, matching
              -- cost_centre_scoped_visibility's own rule — without this, a branch_role_assignment
              -- join on branch_id would never match a NULL branch_id (NULL never equals NULL).
              cost_centre.branch_id is null
              or exists (
                select 1 from branch_role_assignment
                where branch_role_assignment.tenant_id = cost_centre.tenant_id
                  and branch_role_assignment.membership_id = current_membership_id()
                  and branch_role_assignment.branch_id = cost_centre.branch_id
              )
            )
        )
      )
    )
  );

grant select, insert, update, delete on budget to authenticated;
grant select, insert, update, delete on budget to service_role;

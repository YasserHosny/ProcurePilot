-- 20260823000043_purchase_request_line.sql — task T002, chunk R2.1
--
-- purchase_request_line — one item and quantity within a purchase request, plus its estimated
-- value (research.md R2). Visibility is inherited via purchase_request_id: rather than
-- duplicating branch_id onto this table purely for RLS, the scoped-visibility policy joins to
-- the parent purchase_request row directly, mirroring how branch_role_assignment lookups already
-- work in R2.0's own policies (an EXISTS join against a related table is already this codebase's
-- established RLS idiom, not a new one).

create table if not exists purchase_request_line (
  id                                            uuid primary key default gen_random_uuid(),
  tenant_id                                     uuid not null references tenant(id) on delete cascade,
  purchase_request_id                           uuid not null,
  workspace_product_id                          uuid not null,
  quantity                                      numeric(18, 6) not null check (quantity > 0),
  note                                           text,
  estimated_unit_price_amount                   numeric(18, 4),
  estimated_unit_price_currency                 text references supported_currency(code),
  estimated_unit_price_source_landed_cost_id    uuid,
  estimated_at                                  timestamptz,
  created_at                                    timestamptz not null default now(),

  constraint purchase_request_line_request_fkey
    foreign key (tenant_id, purchase_request_id) references purchase_request (tenant_id, id) on delete cascade,
  constraint purchase_request_line_product_fkey
    foreign key (tenant_id, workspace_product_id) references workspace_product (tenant_id, id),
  constraint purchase_request_line_landed_cost_fkey
    foreign key (tenant_id, estimated_unit_price_source_landed_cost_id) references landed_cost (tenant_id, id),

  -- The three estimate columns are null together or populated together (research.md R2 — null
  -- exactly when the product has no reachable price-history row).
  constraint purchase_request_line_estimate_paired check (
    (estimated_unit_price_amount is null) = (estimated_unit_price_currency is null)
    and (estimated_unit_price_amount is null) = (estimated_unit_price_source_landed_cost_id is null)
  )
);

create index if not exists purchase_request_line_tenant_idx on purchase_request_line (tenant_id);
create index if not exists purchase_request_line_request_idx on purchase_request_line (purchase_request_id);

comment on table purchase_request_line is
  'One item/quantity within a purchase request (chunk R2.1). estimated_unit_price_* is recomputed
   live while the parent request is draft, and frozen (estimated_at stamped, never updated again)
   once the parent request is submitted — research.md R2. A line with no reachable landed_cost
   row has all three estimate columns null, and the parent request is flagged
   has_incomplete_estimate.';

alter table purchase_request_line enable row level security;
alter table purchase_request_line force  row level security;

create policy purchase_request_line_tenant_isolation on purchase_request_line
  for all to authenticated
  using      (tenant_id = current_tenant_id())
  with check  (tenant_id = current_tenant_id());

-- RESTRICTIVE, SELECT-only: a line is visible exactly when its parent purchase_request is
-- visible under that table's own scoped-visibility policy. Re-derived here (not simply
-- delegated) because RLS policies on one table cannot reference another table's policy directly
-- — only its rows, via a join, which is what this EXISTS clause does.
create policy purchase_request_line_scoped_visibility on purchase_request_line
  as restrictive
  for select to authenticated
  using (
    tenant_id = current_tenant_id()
    and exists (
      select 1 from purchase_request
      where purchase_request.tenant_id = purchase_request_line.tenant_id
        and purchase_request.id = purchase_request_line.purchase_request_id
        and (
          current_member_role() = 'owner'
          or purchase_request.requested_by_membership_id = current_membership_id()
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
    )
  );

grant select, insert, update, delete on purchase_request_line to authenticated;
grant select, insert, update, delete on purchase_request_line to service_role;

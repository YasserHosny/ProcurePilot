-- R3.4 data-freshness engine: durable, tenant-scoped refresh intent.
-- This table schedules source refresh work; it never mutates append-only offer history.

create table if not exists offer_refresh_schedule (
  id                    uuid primary key default gen_random_uuid(),
  tenant_id             uuid not null references tenant(id) on delete cascade,
  workspace_product_id  uuid not null,
  supplier_id           uuid not null,
  cadence_days          integer not null default 14 check (cadence_days between 1 and 365),
  status                text not null default 'active'
                        check (status in ('active', 'paused', 'due')),
  next_refresh_at       timestamptz not null default now(),
  last_observed_at      timestamptz,
  last_requested_at     timestamptz,
  last_error             text,
  created_at            timestamptz not null default now(),
  updated_at            timestamptz not null default now(),

  constraint offer_refresh_schedule_tenant_id_key unique (tenant_id, id),
  constraint offer_refresh_schedule_product_fkey
    foreign key (tenant_id, workspace_product_id)
    references workspace_product (tenant_id, id) on delete cascade,
  constraint offer_refresh_schedule_supplier_fkey
    foreign key (tenant_id, supplier_id)
    references supplier (tenant_id, id) on delete cascade,
  constraint offer_refresh_schedule_source_key
    unique (tenant_id, workspace_product_id, supplier_id)
);

create index if not exists offer_refresh_schedule_due_idx
  on offer_refresh_schedule (status, next_refresh_at)
  where status = 'active';
create index if not exists offer_refresh_schedule_tenant_product_idx
  on offer_refresh_schedule (tenant_id, workspace_product_id);

comment on table offer_refresh_schedule is
  'Connector-neutral refresh intent for active offers. It schedules source work without changing
   append-only landed_cost history or authorising a purchase.';

alter table offer_refresh_schedule enable row level security;
alter table offer_refresh_schedule force row level security;

create policy offer_refresh_schedule_tenant_select on offer_refresh_schedule
  for select to authenticated
  using (tenant_id = current_tenant_id());

create policy offer_refresh_schedule_owner_buyer_insert on offer_refresh_schedule
  for insert to authenticated
  with check (
    tenant_id = current_tenant_id()
    and current_member_role() in ('owner', 'buyer')
  );

create policy offer_refresh_schedule_owner_buyer_update on offer_refresh_schedule
  for update to authenticated
  using (
    tenant_id = current_tenant_id()
    and current_member_role() in ('owner', 'buyer')
  )
  with check (
    tenant_id = current_tenant_id()
    and current_member_role() in ('owner', 'buyer')
  );

grant select on offer_refresh_schedule to authenticated;
grant insert, update on offer_refresh_schedule to authenticated;
grant select, insert, update on offer_refresh_schedule to service_role;

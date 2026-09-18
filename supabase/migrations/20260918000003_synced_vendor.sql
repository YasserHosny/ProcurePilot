-- 20260918000003_synced_vendor.sql — task T005, chunk R3.1 (014-accounting-integration)
--
-- synced_vendor — QuickBooks's Vendor entity as of the most recent sync. Not itself a
-- spec-named entity; exists to persist the vendor<->supplier name match (research.md R3) so
-- later syncs reuse the stored link instead of re-matching by name every run. Sync-derived, but
-- written the same way ingestion's own worker writes document/quotation (see
-- ingestion/orchestrator.py's _act_as_tenant): a system-triggered write fakes an `authenticated`
-- session scoped to the tenant via set_config('request.jwt.claims', ...), not a literal
-- service_role connection — no such helper exists elsewhere in this codebase, so introducing one
-- just for this table would be new inconsistency, not less of it. RLS (tenant_id =
-- current_tenant_id()) is the real boundary here, exactly as it is for every worker-written
-- table already; there is no secret column on this table to warrant extra restriction (contrast
-- accounting_connection's access_token/refresh_token column split, which exists for that reason
-- specifically).

create table if not exists synced_vendor (
  id                    uuid primary key default gen_random_uuid(),
  tenant_id             uuid not null references tenant(id) on delete cascade,
  connection_id         uuid not null,

  provider_vendor_id    text not null,
  display_name          text not null,
  matched_supplier_id   uuid,

  created_at            timestamptz not null default now(),
  updated_at            timestamptz not null default now(),

  constraint synced_vendor_connection_fkey
    foreign key (tenant_id, connection_id) references accounting_connection (tenant_id, id),

  constraint synced_vendor_supplier_fkey
    foreign key (tenant_id, matched_supplier_id) references supplier (tenant_id, id)
    on delete set null (matched_supplier_id),

  constraint synced_vendor_tenant_id_key unique (tenant_id, id),

  constraint synced_vendor_provider_id_key
    unique (tenant_id, connection_id, provider_vendor_id)
);

create index if not exists synced_vendor_tenant_idx
  on synced_vendor (tenant_id, connection_id);

create index if not exists synced_vendor_matched_supplier_idx
  on synced_vendor (tenant_id, matched_supplier_id)
  where matched_supplier_id is not null;

comment on table synced_vendor is
  'QuickBooks Vendor as of the most recent sync (R3.1). Written by the sync worker/service
   (system-triggered, acting as authenticated for the tenant — see file header), read by any
   member. See specs/014-accounting-integration/data-model.md.';

alter table synced_vendor enable row level security;
alter table synced_vendor force  row level security;

create policy synced_vendor_tenant_select on synced_vendor
  for select to authenticated
  using (tenant_id = current_tenant_id());

create policy synced_vendor_tenant_insert on synced_vendor
  for insert to authenticated
  with check (tenant_id = current_tenant_id());

create policy synced_vendor_tenant_update on synced_vendor
  for update to authenticated
  using (tenant_id = current_tenant_id())
  with check (tenant_id = current_tenant_id());

grant select, insert, update on synced_vendor to authenticated;
grant select, insert, update on synced_vendor to service_role;

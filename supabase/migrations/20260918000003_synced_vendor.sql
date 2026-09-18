-- 20260918000003_synced_vendor.sql — task T005, chunk R3.1 (014-accounting-integration)
--
-- synced_vendor — QuickBooks's Vendor entity as of the most recent sync. Not itself a
-- spec-named entity; exists to persist the vendor<->supplier name match (research.md R3) so
-- later syncs reuse the stored link instead of re-matching by name every run. Sync-derived: no
-- direct member mutation, matching document/quotation's own "system writes, member reads"
-- split for ingestion-produced rows.

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
  'QuickBooks Vendor as of the most recent sync (R3.1). Sync-derived: written only by the sync
   worker''s service-role path. See specs/014-accounting-integration/data-model.md.';

alter table synced_vendor enable row level security;
alter table synced_vendor force  row level security;

create policy synced_vendor_tenant_select on synced_vendor
  for select to authenticated
  using (tenant_id = current_tenant_id());

grant select on synced_vendor to authenticated;
grant select, insert, update on synced_vendor to service_role;

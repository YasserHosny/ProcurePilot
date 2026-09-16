-- 20260917000004_catalogue_imports.sql — task T004, chunk R3.0 (013-automated-ingestion)
--
-- catalogue_imports — tracks supplier catalogue bulk price refresh operations (CSV/XLSX).
-- Stores source file references in storage, parse/import statistics, validation error details,
-- and resolved column mappings.
--
-- Non-negotiable 1: ENABLE + FORCE RLS with USING and WITH CHECK using current_tenant_id().
-- Non-negotiable 2: Tenancy resolved from current_tenant_id(), write restricted to owners and buyers.

create type catalogue_import_status as enum (
  'pending', 'processing', 'completed', 'failed'
);

create table if not exists catalogue_imports (
  id               uuid primary key default gen_random_uuid(),
  tenant_id        uuid not null references tenant(id) on delete cascade,
  supplier_id      uuid not null references supplier(id) on delete cascade,

  file_name        text not null check (char_length(file_name) between 1 and 255),
  file_path        text not null,
  file_size_bytes  bigint not null check (file_size_bytes > 0),
  file_format      text not null check (file_format in ('csv', 'xlsx')),

  status           catalogue_import_status not null default 'pending',
  total_rows       integer check (total_rows is null or total_rows >= 0),
  imported_rows    integer check (imported_rows is null or imported_rows >= 0),
  skipped_rows     integer check (skipped_rows is null or skipped_rows >= 0),
  error_rows       integer check (error_rows is null or error_rows >= 0),
  error_details    jsonb not null default '[]'::jsonb,
  column_mapping   jsonb not null default '{}'::jsonb,

  created_at       timestamptz not null default now(),
  completed_at     timestamptz,
  created_by       uuid not null references membership(id),

  constraint catalogue_imports_tenant_id_key unique (tenant_id, id),
  constraint catalogue_imports_completed_after_created
    check (completed_at is null or completed_at >= created_at)
);

create index if not exists catalogue_imports_tenant_supplier_idx
  on catalogue_imports (tenant_id, supplier_id, created_at desc);

create index if not exists catalogue_imports_tenant_status_idx
  on catalogue_imports (tenant_id, status, created_at desc);

comment on table catalogue_imports is
  'Supplier catalogue refresh and bulk price import history and telemetry (R3.0). See
   specs/013-automated-ingestion/data-model.md.';

alter table catalogue_imports enable row level security;
alter table catalogue_imports force  row level security;

create policy catalogue_imports_tenant_select on catalogue_imports
  for select to authenticated
  using (tenant_id = current_tenant_id());

create policy catalogue_imports_owner_buyer_insert on catalogue_imports
  for insert to authenticated
  with check (
    tenant_id = current_tenant_id()
    and current_member_role() in ('owner', 'buyer')
  );

create policy catalogue_imports_owner_buyer_update on catalogue_imports
  for update to authenticated
  using (
    tenant_id = current_tenant_id()
    and current_member_role() in ('owner', 'buyer')
  )
  with check (
    tenant_id = current_tenant_id()
    and current_member_role() in ('owner', 'buyer')
  );

grant select, insert, update, delete on catalogue_imports to authenticated;
grant select, insert, update, delete on catalogue_imports to service_role;
